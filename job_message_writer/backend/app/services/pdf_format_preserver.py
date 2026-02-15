"""
PDF Format Preserver — uses PyMuPDF to do in-place text replacement.
Keeps exact same layout, fonts, sizes, colors. Only bullet-point content changes.

Approach:
1. Parse original PDF → extract every text span with formatting metadata
2. Classify lines: BULLET_TEXT, SKILL_CONTENT, or STRUCTURE (untouched)
3. Group bullet text into logical bullet points
4. Send ONLY modifiable content to Claude with strict keyword-only constraints
5. Redact target spans → re-insert new text at identical positions
6. Apply all redactions ONCE per page → output new PDF
"""

import fitz  # PyMuPDF
import json
import logging
import os
import re
import sys
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ─── Data classes ───────────────────────────────────────────────────────────

class LineType(Enum):
    STRUCTURE = "structure"       # Don't touch: headers, company, dates, locations
    BULLET_MARKER = "bullet_marker"  # The ● character itself
    BULLET_TEXT = "bullet_text"   # Modifiable bullet point text
    SKILL_CONTENT = "skill_content"  # Modifiable skill values after bold label
    ZWS_PADDING = "zws_padding"  # Zero-width space padding from Google Docs


@dataclass
class TextSpan:
    """A single text span with formatting metadata."""
    page_num: int
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    text: str
    font_name: str
    font_size: float
    color: int
    flags: int
    origin: Tuple[float, float]

    @property
    def is_bold(self) -> bool:
        return bool(self.flags & (1 << 4))

    @property
    def is_bullet_char(self) -> bool:
        clean = self.text.replace("\u200b", "").strip()
        return clean in ("●", "•", "◦", "○", "■", "▪", "·", "▸", "▹", "–", "—", "-")

    @property
    def is_zwsp_only(self) -> bool:
        return not self.text.replace("\u200b", "").replace(" ", "").strip()


@dataclass
class ClassifiedLine:
    """A visual line (spans grouped by y-position) with its classification."""
    spans: List[TextSpan]
    line_type: LineType
    page_num: int
    y_pos: float  # y-origin of the line

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.spans if not s.is_zwsp_only)

    @property
    def clean_text(self) -> str:
        return self.text.replace("\u200b", "").strip()


@dataclass
class BulletPoint:
    """A complete bullet point (may span multiple visual lines)."""
    marker_line: Optional[ClassifiedLine]  # The ● line
    text_lines: List[ClassifiedLine]       # The text lines
    section_name: str

    @property
    def full_text(self) -> str:
        return " ".join(line.clean_text for line in self.text_lines)

    # Inline bullet characters that may prefix text in a single span
    _INLINE_BULLET_CHARS = ("•", "●", "◦", "○", "■", "▪", "·", "▸", "▹", "–", "—")

    @property
    def line_texts(self) -> List[str]:
        """Get text for each line, stripping bullet characters (both separate spans and inline)."""
        result = []
        for line in self.text_lines:
            # Join only non-bullet, non-ZWS spans
            parts = [s.text for s in line.spans
                     if not s.is_bullet_char and not s.is_zwsp_only]
            text = " ".join(parts).replace("\u200b", "").strip()
            # Strip leading inline bullet characters (e.g., "• Designed..." → "Designed...")
            # These occur when the bullet char is in the same span as the text
            for bc in self._INLINE_BULLET_CHARS:
                if text.startswith(bc + " ") or text.startswith(bc + "\t"):
                    text = text[len(bc):].strip()
                    break
                elif text == bc:
                    text = ""
                    break
            result.append(text)
        return result

    @property
    def line_char_counts(self) -> List[int]:
        return [len(t) for t in self.line_texts]


@dataclass
class SkillLine:
    """A skills line: bold label + modifiable content."""
    label_spans: List[TextSpan]   # Bold label ("Languages: ")
    content_spans: List[TextSpan]  # Regular content ("Python, R, SQL...")
    section_name: str

    @property
    def label_text(self) -> str:
        return "".join(s.text for s in self.label_spans).replace("\u200b", "")

    @property
    def content_text(self) -> str:
        return "".join(s.text for s in self.content_spans).replace("\u200b", "").strip()


@dataclass
class TitleSkillLine:
    """A job title line with parenthesized tech stack, e.g. 'Software Engineer (React, Node, AWS)'."""
    full_spans: List[TextSpan]     # All spans that make up the title
    title_part: str                # "Software Engineer"
    skills_part: str               # "React, Node, AWS"
    full_text: str                 # "Software Engineer (React, Node, AWS)"


def sanitize_bullet_replacements(
    bullets: List[BulletPoint],
    bullet_replacements: Dict[int, List[str]],
    length_tolerance: float = 0.15,
) -> Dict[int, List[str]]:
    """
    Keep only bullet replacements that preserve shape closely enough for safe PDF reflow.

    Rules enforced:
    - replacement index must exist
    - same number of lines as original bullet
    - no empty replacement lines
    - each replacement line length within tolerance of original line length
    """
    sanitized: Dict[int, List[str]] = {}

    for idx, lines in bullet_replacements.items():
        if idx < 0 or idx >= len(bullets):
            logger.warning(f"[SANITIZE] Bullet idx {idx} out of range, dropping")
            continue

        original_lines = bullets[idx].line_texts
        normalized = [line.strip() for line in lines]

        if len(normalized) != len(original_lines):
            logger.warning(
                f"[SANITIZE] Bullet {idx}: line count mismatch "
                f"(orig={len(original_lines)}, new={len(normalized)}), dropping"
            )
            continue

        if any(not line for line in normalized):
            logger.warning(f"[SANITIZE] Bullet {idx}: empty replacement line, dropping")
            continue

        out_of_bounds = False
        for line_idx, (orig, new) in enumerate(zip(original_lines, normalized)):
            orig_len = len(orig.strip())
            if orig_len == 0:
                continue
            delta = abs(len(new) - orig_len) / orig_len
            if delta > length_tolerance:
                logger.warning(
                    f"[SANITIZE] Bullet {idx} line {line_idx}: length delta {delta:.2f} "
                    f"exceeds tolerance {length_tolerance:.2f}, dropping"
                )
                out_of_bounds = True
                break

        if out_of_bounds:
            continue

        sanitized[idx] = normalized

    return sanitized


# ─── Overflow Detection & Prevention ──────────────────────────────────────

class _OverflowDetector:
    """Detects and prevents text overflow by measuring rendered widths.

    Works with the existing _WidthCalculator and _CMapManager to compute
    exact rendered widths and determine if replacement text will overflow
    the available line width in the PDF.
    """

    # Maximum Tc adjustment we allow (matches existing clamp in _inject_width_adjustment)
    MAX_TC = 0.15

    def __init__(self, doc, cmap_mgr: '_CMapManager', width_calc: '_WidthCalculator'):
        self._doc = doc
        self._cmap = cmap_mgr
        self._wc = width_calc
        # Cache page dimensions: page_num -> (width, height)
        self._page_dims: Dict[int, Tuple[float, float]] = {}
        # Cache inferred content bounds: page_num -> (left_x, right_x, top_y, bottom_y)
        self._page_bounds: Dict[int, Tuple[float, float, float, float]] = {}

    def _get_page_dims(self, page_num: int) -> Tuple[float, float]:
        """Get page width and height in points."""
        if page_num not in self._page_dims:
            page = self._doc[page_num]
            rect = page.rect
            self._page_dims[page_num] = (rect.width, rect.height)
        return self._page_dims[page_num]

    def measure_text_width(self, text: str, font_tag: str, font_size: float) -> float:
        """Measure the rendered width of text in points using font glyph widths."""
        hex_encoded, _ = self._cmap.encode_text(font_tag, text)
        if not hex_encoded:
            # Fallback: estimate based on average char width
            return len(text) * font_size * 0.5
        byte_width = self._cmap.get_byte_width(font_tag)
        return self._wc.text_width_from_hex(font_tag, hex_encoded, font_size, byte_width)

    def measure_hex_width(self, hex_string: str, font_tag: str, font_size: float) -> float:
        """Measure rendered width from hex-encoded text."""
        if not hex_string:
            return 0.0
        byte_width = self._cmap.get_byte_width(font_tag)
        return self._wc.text_width_from_hex(font_tag, hex_string, font_size, byte_width)

    def get_available_width(
        self, x_start: float, page_num: int,
        all_blocks: Optional[List['ContentBlock']] = None,
    ) -> float:
        """Calculate available text width from x_start to the right margin.

        Uses content analysis to infer the right boundary from existing text
        positions on the page, falling back to page width minus standard margin.
        """
        page_w, _ = self._get_page_dims(page_num)

        if page_num in self._page_bounds:
            _, right_x, _, _ = self._page_bounds[page_num]
            return right_x - x_start

        # Infer right boundary from all content blocks on this page
        if all_blocks:
            page_blocks = [b for b in all_blocks if b.page_num == page_num and b.text_ops]
            if page_blocks:
                max_right = 0.0
                for block in page_blocks:
                    # Estimate right edge: x + rendered width of all text ops
                    block_text = block.full_text
                    if block_text and block.font_tag:
                        block_w = self.measure_text_width(
                            block_text, block.font_tag, block.font_size
                        )
                        max_right = max(max_right, block.x + block_w)

                if max_right > x_start:
                    # Add a small buffer (2pt) to avoid false overflow detection
                    right_bound = max_right + 2.0
                    left_x = min(b.x for b in page_blocks)
                    self._page_bounds[page_num] = (left_x, right_bound, 0, 0)
                    return right_bound - x_start

        # Fallback: page width minus 0.5 inch right margin
        return page_w - 36.0 - x_start

    def would_overflow(
        self, new_text: str, font_tag: str, font_size: float,
        x_start: float, page_num: int,
        all_blocks: Optional[List['ContentBlock']] = None,
    ) -> Tuple[bool, float, float]:
        """Check if rendering new_text would overflow the available line width.

        Returns:
            (overflows: bool, text_width: float, available_width: float)
        """
        text_w = self.measure_text_width(new_text, font_tag, font_size)
        avail_w = self.get_available_width(x_start, page_num, all_blocks)

        # Account for Tc compression: at max Tc clamp, we can shrink text by
        # MAX_TC * num_chars * (Th=1.0) additional points
        num_chars = len(new_text)
        max_tc_savings = self.MAX_TC * num_chars
        effective_width = text_w - max_tc_savings

        return effective_width > avail_w, text_w, avail_w

    def wrap_text(
        self, text: str, max_width: float,
        font_tag: str, font_size: float,
    ) -> List[str]:
        """Greedy word-wrap: split text into lines that fit within max_width.

        Uses exact glyph widths from the PDF font's /Widths or /W array.
        Returns a list of line strings.
        """
        words = text.split()
        if not words:
            return [text]

        lines: List[str] = []
        current_line: List[str] = []
        current_width = 0.0
        space_w = self.measure_text_width(" ", font_tag, font_size)
        # Minimum space width fallback (some fonts report 0 for space)
        if space_w < 0.1:
            space_w = font_size * 0.25

        for word in words:
            word_w = self.measure_text_width(word, font_tag, font_size)
            if current_line:
                test_width = current_width + space_w + word_w
                if test_width > max_width:
                    # This word would overflow — start new line
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    current_width = word_w
                else:
                    current_line.append(word)
                    current_width = test_width
            else:
                current_line = [word]
                current_width = word_w

        if current_line:
            lines.append(" ".join(current_line))

        return lines if lines else [text]

    def get_line_leading(
        self, blocks: List['ContentBlock'], page_num: int,
    ) -> float:
        """Measure actual line leading (baseline-to-baseline distance) from
        consecutive content blocks on the same page.

        Falls back to font_size * 1.2 if no consecutive blocks are found.
        """
        page_blocks = sorted(
            [b for b in blocks if b.page_num == page_num and b.text_ops],
            key=lambda b: -b.y  # Sort top-to-bottom (y decreases downward)
        )
        if len(page_blocks) < 2:
            return page_blocks[0].font_size * 1.2 if page_blocks else 12.0

        # Collect y-distances between consecutive blocks at similar x positions
        deltas: List[float] = []
        for i in range(len(page_blocks) - 1):
            b1, b2 = page_blocks[i], page_blocks[i + 1]
            # Only measure between blocks that are roughly left-aligned (same column)
            if abs(b1.x - b2.x) < 20:
                dy = b1.y - b2.y
                if 4 < dy < 30:  # Reasonable line spacing range
                    deltas.append(dy)

        if deltas:
            return sum(deltas) / len(deltas)
        # Fallback
        return page_blocks[0].font_size * 1.2


def validate_replacements_by_width(
    pdf_path: str,
    bullets: List[BulletPoint],
    skills: List[SkillLine],
    bullet_replacements: Dict[int, List[str]],
    skill_replacements: Dict[int, str],
    title_skills: Optional[List[TitleSkillLine]] = None,
    title_replacements: Optional[Dict[int, str]] = None,
) -> Tuple[Dict[int, List[str]], Dict[int, str], Dict[int, str]]:
    """Validate all replacements against rendered width constraints.

    For each replacement, measures the actual rendered width using the PDF's
    font metrics and compares against the available line width. Replacements
    that would overflow are dropped (rejected) to prevent visual corruption.

    This is called AFTER sanitize_bullet_replacements (character-count check)
    as an additional rendered-width safety net.

    Returns filtered (bullet_replacements, skill_replacements, title_replacements).
    """
    doc = fitz.open(pdf_path)
    cmap_mgr = _CMapManager(doc)
    width_calc = _WidthCalculator(doc)
    detector = _OverflowDetector(doc, cmap_mgr, width_calc)

    # Parse content blocks for margin inference
    all_blocks: List[ContentBlock] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        for xref in page.get_contents():
            try:
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap_mgr, page_num, xref)
                all_blocks.extend(blocks)
            except Exception:
                pass

    # ── Validate bullet replacements ──
    validated_bullets: Dict[int, List[str]] = {}
    for idx, new_lines in bullet_replacements.items():
        if idx < 0 or idx >= len(bullets):
            continue
        bp = bullets[idx]
        original_lines = bp.line_texts

        # Get font info from the bullet's first text span
        text_spans = [
            s for tl in bp.text_lines for s in tl.spans
            if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()
        ]
        if not text_spans:
            validated_bullets[idx] = new_lines
            continue

        font_name = text_spans[0].font_name
        font_size = text_spans[0].font_size
        page_num = text_spans[0].page_num
        x_start = text_spans[0].bbox[0]  # Left edge of text

        # Resolve font name to font tag
        font_tag = None
        for tag, name in cmap_mgr.font_names.items():
            if name == font_name or font_name in name:
                font_tag = tag
                break
        if not font_tag:
            # Can't measure without font info — pass through
            validated_bullets[idx] = new_lines
            continue

        # Check each line's rendered width against original line width
        overflow = False
        for li, new_line in enumerate(new_lines):
            orig_line = original_lines[li] if li < len(original_lines) else ""
            orig_w = detector.measure_text_width(orig_line, font_tag, font_size) if orig_line else 0
            text_w = detector.measure_text_width(new_line, font_tag, font_size)
            max_tc_savings = _OverflowDetector.MAX_TC * len(new_line)
            if orig_w > 0 and text_w - max_tc_savings > orig_w:
                logger.warning(
                    f"[WIDTH-CHECK] Bullet {idx} line {li}: rendered width {text_w:.1f}pt "
                    f"exceeds original {orig_w:.1f}pt (even with Tc), dropping bullet"
                )
                overflow = True
                break

        if not overflow:
            validated_bullets[idx] = new_lines

    # ── Validate skill replacements ──
    validated_skills: Dict[int, str] = {}
    for idx, new_content in skill_replacements.items():
        if idx < 0 or idx >= len(skills):
            continue
        sk = skills[idx]
        if not sk.content_spans:
            validated_skills[idx] = new_content
            continue

        font_name = sk.content_spans[0].font_name
        font_size = sk.content_spans[0].font_size
        page_num = sk.content_spans[0].page_num
        x_start = sk.content_spans[0].bbox[0]

        font_tag = None
        for tag, name in cmap_mgr.font_names.items():
            if name == font_name or font_name in name:
                font_tag = tag
                break
        if not font_tag:
            validated_skills[idx] = new_content
            continue

        orig_content = sk.content_text if hasattr(sk, 'content_text') else " ".join(s.text for s in sk.content_spans)
        orig_w = detector.measure_text_width(orig_content, font_tag, font_size)
        text_w = detector.measure_text_width(new_content, font_tag, font_size)
        max_tc_savings = _OverflowDetector.MAX_TC * len(new_content)
        if orig_w > 0 and text_w - max_tc_savings > orig_w:
            logger.warning(
                f"[WIDTH-CHECK] Skill {idx}: rendered width {text_w:.1f}pt "
                f"exceeds original {orig_w:.1f}pt, dropping"
            )
        else:
            validated_skills[idx] = new_content

    # ── Validate title replacements ──
    validated_titles: Dict[int, str] = {}
    if title_skills and title_replacements:
        for idx, new_skills_part in title_replacements.items():
            if idx < 0 or idx >= len(title_skills):
                continue
            ts = title_skills[idx]
            if not ts.full_spans:
                validated_titles[idx] = new_skills_part
                continue

            font_name = ts.full_spans[0].font_name
            font_size = ts.full_spans[0].font_size
            page_num = ts.full_spans[0].page_num
            x_start = ts.full_spans[0].bbox[0]

            font_tag = None
            for tag, name in cmap_mgr.font_names.items():
                if name == font_name or font_name in name:
                    font_tag = tag
                    break
            if not font_tag:
                validated_titles[idx] = new_skills_part
                continue

            full_new = f"{ts.title_part} ({new_skills_part})"
            full_orig = f"{ts.title_part} ({ts.skills_part})"
            orig_w = detector.measure_text_width(full_orig, font_tag, font_size)
            text_w = detector.measure_text_width(full_new, font_tag, font_size)
            max_tc_savings = _OverflowDetector.MAX_TC * len(full_new)
            if orig_w > 0 and text_w - max_tc_savings > orig_w:
                logger.warning(
                    f"[WIDTH-CHECK] Title {idx}: rendered width {text_w:.1f}pt "
                    f"exceeds original {orig_w:.1f}pt, dropping"
                )
            else:
                validated_titles[idx] = new_skills_part
    elif title_replacements:
        validated_titles = dict(title_replacements)

    dropped_b = len(bullet_replacements) - len(validated_bullets)
    dropped_s = len(skill_replacements) - len(validated_skills)
    dropped_t = len(title_replacements or {}) - len(validated_titles)
    if dropped_b or dropped_s or dropped_t:
        logger.info(
            f"[WIDTH-CHECK] Dropped {dropped_b} bullets, {dropped_s} skills, "
            f"{dropped_t} titles due to rendered-width overflow"
        )
    else:
        logger.info("[WIDTH-CHECK] All replacements passed rendered-width validation")

    doc.close()
    return validated_bullets, validated_skills, validated_titles


# ─── Boundary Detection (Date/Contact Protection) ──────────────────────────

class _BoundaryDetector:
    """Detect semantic boundaries within content blocks to protect dates,
    contact info, and other immutable content from being overwritten.

    The #1 production bug was dates being wiped because the extension logic
    in _do_replacement() grabbed date blocks at the same Y-position as the
    title being replaced. This class provides pattern matching to identify
    and protect such blocks.
    """

    # Full date patterns (for complete date strings)
    DATE_PATTERNS = [
        # "March 2025", "Jan 2020", "December 2019"
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\.?\s*\d{4}\b',
        # "2020 - 2024", "2020 – Present", "2020—Current"
        r'\b\d{4}\s*[-–—]\s*(?:\d{4}|Present|Current|Now)\b',
        # "Jan 2020 -" or "March 2025 –" (start of a date range)
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\.?\s*\d{4}\s*[-–—]',
        # Full date range: "Jan 2020 – Dec 2024"
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b',
        # Standalone "Present" or "Current" (common end of date ranges)
        r'^(?:Present|Current|Now)$',
        # MM/YYYY format: "01/2020 - 12/2024"
        r'\b\d{1,2}/\d{4}\b',
    ]

    # Fragment patterns — for split-across-blocks dates in content streams.
    # PDFs often split "March 2025 – Oct 2025" into blocks like:
    #   "March" | "2025-Oct" | "2025"
    # These fragments must also be detected and protected.
    DATE_FRAGMENT_PATTERNS = [
        # Standalone month names: "Jan", "March", "Nov", "September"
        r'^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?$',
        # Standalone 4-digit year in resume range (2015-2030)
        r'^20[12]\d$',
        # Year-dash-month fragments: "2025-Oct", "2021–Jun", "2019—Dec"
        r'^20[12]\d\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*$',
        # Month-dash fragments: "Oct-", "Jun–"
        r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s*[-–—]$',
    ]

    _date_re = [re.compile(p, re.IGNORECASE) for p in DATE_PATTERNS]
    _date_fragment_re = [re.compile(p, re.IGNORECASE) for p in DATE_FRAGMENT_PATTERNS]

    LOCATION_PATTERNS = [
        # "City, State" or "City, ST" or "City, Country"
        r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2}$',
        # "Remote" standalone
        r'^Remote$',
    ]

    _location_re = [re.compile(p, re.IGNORECASE) for p in LOCATION_PATTERNS]

    @classmethod
    def is_date_text(cls, text: str) -> bool:
        """Check if text contains date patterns (employment dates, etc.)."""
        clean = text.strip()
        if not clean:
            return False
        for pattern in cls._date_re:
            if pattern.search(clean):
                return True
        return False

    @classmethod
    def is_date_fragment(cls, text: str) -> bool:
        """Check if text is a date fragment (month name, year, or partial date range).

        Content stream blocks often split dates across multiple blocks.
        This catches fragments like "Nov", "2025", "2025-Oct" that are parts
        of larger date strings.
        """
        clean = text.strip()
        if not clean:
            return False
        for pattern in cls._date_fragment_re:
            if pattern.search(clean):
                return True
        return False

    @classmethod
    def is_location_text(cls, text: str) -> bool:
        """Check if text looks like a location (City, State)."""
        clean = text.strip()
        if not clean:
            return False
        for pattern in cls._location_re:
            if pattern.search(clean):
                return True
        return False

    @classmethod
    def is_protected(cls, text: str) -> bool:
        """Check if a content block's text should be protected from replacement.

        Protected content includes:
        - Employment/education dates (full or fragments)
        - Locations (City, State)
        """
        return cls.is_date_text(text) or cls.is_date_fragment(text) or cls.is_location_text(text)

    @classmethod
    def filter_extension_blocks(
        cls,
        all_blocks: List['ContentBlock'],
        extension_candidates: List[int],
        matched_block_indices: Optional[List[int]] = None,
    ) -> List[int]:
        """Filter extension candidates, removing blocks with protected content.

        Called during the tail-end extension in _do_replacement() to prevent
        date/location blocks from being zeroed out.

        Uses two strategies:
        1. Text pattern matching (dates, locations)
        2. X-position gap detection: if the extension block is >200pt to the
           right of the matched content, it's likely a right-aligned date
        """
        # Calculate the max X of the matched blocks (for gap detection)
        matched_max_x = 0.0
        if matched_block_indices:
            for mi in matched_block_indices:
                b = all_blocks[mi]
                matched_max_x = max(matched_max_x, b.x)

        filtered = []
        for bi in extension_candidates:
            block = all_blocks[bi]
            text = block.full_text.strip()

            # Strategy 1: Text pattern matching
            if text and cls.is_protected(text):
                logger.info(
                    f"[BOUNDARY] Protected block (text pattern) at "
                    f"x={block.x:.1f} y={block.y:.1f}: '{text[:60]}'"
                )
                continue

            # Strategy 2: X-position gap detection
            # If this extension block is far to the right of the matched content,
            # it's likely a right-aligned date/location even if text patterns
            # don't match (e.g., company name at right side)
            if matched_max_x > 0 and block.x - matched_max_x > 200:
                logger.info(
                    f"[BOUNDARY] Protected block (x-gap {block.x - matched_max_x:.0f}pt) at "
                    f"x={block.x:.1f} y={block.y:.1f}: '{text[:60]}'"
                )
                continue

            filtered.append(bi)
        return filtered

    @classmethod
    def filter_matched_blocks(
        cls,
        all_blocks: List['ContentBlock'],
        block_indices: List[int],
        original_text: str,
    ) -> List[int]:
        """Filter matched blocks, removing any that contain ONLY date/protected text.

        This handles cases where _find_blocks_for_text matched too aggressively
        and included date blocks in the match. We keep blocks whose text is part
        of the original replacement target, but remove blocks that are purely
        date content that was swept in by the matching algorithm.
        """
        if not block_indices:
            return block_indices

        orig_clean = original_text.replace("\u200b", "").strip().lower()
        filtered = []

        for bi in block_indices:
            block = all_blocks[bi]
            block_text = block.full_text.strip()
            if not block_text:
                filtered.append(bi)
                continue

            # If block text appears in the original text, it's part of the target
            block_text_lower = block_text.lower().strip()
            if block_text_lower in orig_clean:
                filtered.append(bi)
                continue

            # If block text is protected AND not in the original, skip it
            if cls.is_protected(block_text):
                logger.info(
                    f"[BOUNDARY] Removed matched block with protected text: "
                    f"'{block_text[:60]}'"
                )
                continue

            # Keep non-protected blocks that may be fragments
            filtered.append(bi)

        return filtered


# ─── Font Analysis (Character Availability) ────────────────────────────────

class FontAnalyzer:
    """Analyze PDF fonts and build character availability maps.

    Used to:
    1. Determine which characters are available in each font BEFORE LLM generation
    2. Include character constraints in the LLM prompt
    3. Validate replacement text against font capabilities
    4. Avoid triggering FontAugmentor (which causes garbled text bugs)
    """

    def __init__(self, cmap_mgr: '_CMapManager'):
        self._cmap = cmap_mgr

    def get_available_chars(self, font_tag: str) -> set:
        """Get the set of Unicode characters available in a font."""
        font_data = self._cmap.font_cmaps.get(font_tag, {})
        fwd = font_data.get("fwd", {})
        chars = set()
        for cid, char_str in fwd.items():
            for ch in char_str:
                chars.add(ch)
        return chars

    def get_all_available_chars(self) -> set:
        """Get union of available characters across ALL fonts."""
        all_chars = set()
        for font_tag in self._cmap.font_cmaps:
            all_chars.update(self.get_available_chars(font_tag))
        return all_chars

    def get_unavailable_standard_chars(self, font_tag: str) -> List[str]:
        """Get standard ASCII chars that are NOT available in a font.

        Returns list of missing chars from the printable ASCII set (a-z, A-Z, 0-9, common punctuation).
        Used to tell the LLM which characters to avoid for this font.
        """
        available = self.get_available_chars(font_tag)
        if not available:
            return []
        standard = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:!?-/()&%+')
        missing = sorted(ch for ch in standard if ch not in available)
        return missing

    def check_text(self, text: str, font_tag: str) -> List[str]:
        """Check which characters in text are NOT available in the font.

        Returns list of unavailable characters (empty = all available).
        """
        available = self.get_available_chars(font_tag)
        if not available:
            return []  # Can't check, assume all available
        missing = []
        seen = set()
        for ch in text:
            if ch not in available and ch not in seen and ch != ' ':
                # Space is almost always available but sometimes missing from CMap
                missing.append(ch)
                seen.add(ch)
        return missing

    def build_char_constraint_string(self) -> str:
        """Build a human-readable summary of available characters for LLM prompt.

        Uses the intersection of text font character sets (fonts with 10+ chars).
        Excludes symbol/bullet fonts that only have a few glyphs.
        """
        if not self._cmap.font_cmaps:
            return ""

        # Use the LARGEST text font (body font) as the basis for constraints.
        # Intersection of multiple fonts is too restrictive — e.g., bold font
        # may lack commas/periods that the body font has.
        # Per-font checking in _do_replacement handles specific font limitations.
        largest_set = set()
        for ft in self._cmap.font_cmaps:
            chars = self.get_available_chars(ft)
            if len(chars) > len(largest_set):
                largest_set = chars

        if not largest_set or len(largest_set) < 30:
            return ""

        common = largest_set

        # Check if standard ASCII is mostly covered
        ascii_letters = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
        ascii_digits = set('0123456789')
        common_punct = set('.,;:!?()-/&@#$%+\'"')

        missing_letters = ascii_letters - common
        missing_digits = ascii_digits - common
        missing_punct = common_punct - common

        if not missing_letters and not missing_digits:
            # Full ASCII coverage — just note any missing punctuation
            if missing_punct:
                return f"AVOID these characters (not in font): {' '.join(sorted(missing_punct))}"
            return ""  # No constraint needed

        # Some letters/digits are missing — tell LLM to avoid them
        all_missing = sorted(missing_letters | missing_digits | missing_punct)
        if len(all_missing) <= 30:
            # Reasonable number of missing chars — use AVOID list
            avoid_desc = []
            if missing_letters:
                avoid_desc.append(f"letters: {' '.join(sorted(missing_letters))}")
            if missing_digits:
                avoid_desc.append(f"digits: {' '.join(sorted(missing_digits))}")
            if missing_punct:
                avoid_desc.append(f"punctuation: {' '.join(sorted(missing_punct))}")
            return f"AVOID these characters (not in font): {'; '.join(avoid_desc)}"

        # Too many missing chars — build explicit ONLY-use list
        avail_printable = sorted(c for c in common if c.isprintable() and c != ' ')
        if len(avail_printable) > 80:
            return ""  # Too many to list, probably fine

        return f"ONLY use these characters: {''.join(avail_printable)} and space"

    def get_font_summary(self) -> str:
        """Get a summary of all fonts and their character coverage."""
        lines = []
        for font_tag in sorted(self._cmap.font_cmaps.keys()):
            font_name = self._cmap.font_names.get(font_tag, "unknown")
            chars = self.get_available_chars(font_tag)
            ascii_count = sum(1 for c in chars if c.isascii() and c.isprintable())
            lines.append(
                f"  {font_tag} ({font_name}): {len(chars)} chars "
                f"({ascii_count} ASCII)"
            )
        return "\n".join(lines)


# ─── Width Budget Calculator ──────────────────────────────────────────────

def calculate_width_budgets(
    pdf_path: str,
    bullets: List['BulletPoint'],
    skills: List['SkillLine'],
    title_skills: Optional[List['TitleSkillLine']] = None,
) -> Dict[str, Any]:
    """Calculate per-item max character counts based on rendered font widths.

    For each bullet line, skill, and title, computes the maximum number of
    characters that fit within the available width. This is used as a hard
    constraint in the LLM prompt, replacing the generic "±15%" rule.

    Returns:
        {
            "bullet_budgets": {idx: [max_chars_line1, max_chars_line2, ...]},
            "skill_budgets": {idx: max_chars},
            "title_budgets": {idx: max_chars_for_skills_part},
        }
    """
    doc = fitz.open(pdf_path)
    cmap_mgr = _CMapManager(doc)
    width_calc = _WidthCalculator(doc)
    detector = _OverflowDetector(doc, cmap_mgr, width_calc)

    # Parse content blocks for margin inference
    all_blocks: List['ContentBlock'] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        for xref in page.get_contents():
            try:
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap_mgr, page_num, xref)
                all_blocks.extend(blocks)
            except Exception:
                pass

    def _avg_char_width(text: str, font_tag: str, font_size: float) -> float:
        """Get average character width in points for the given text and font."""
        if not text.strip():
            return font_size * 0.5
        w = detector.measure_text_width(text, font_tag, font_size)
        if w > 0 and len(text.strip()) > 0:
            return w / len(text.strip())
        return font_size * 0.5

    def _resolve_font_tag(font_name: str) -> Optional[str]:
        for tag, name in cmap_mgr.font_names.items():
            if name == font_name or font_name in name:
                return tag
        return None

    bullet_budgets: Dict[int, List[int]] = {}
    skill_budgets: Dict[int, int] = {}
    title_budgets: Dict[int, int] = {}

    # ── Bullet budgets ──
    for idx, bp in enumerate(bullets):
        text_spans = [
            s for tl in bp.text_lines for s in tl.spans
            if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()
        ]
        if not text_spans:
            continue

        font_tag = _resolve_font_tag(text_spans[0].font_name)
        if not font_tag:
            continue

        font_size = text_spans[0].font_size

        line_budgets = []
        for lt in bp.line_texts:
            # Use original line width as budget basis (avoids CTM coordinate issues)
            orig_line_w = detector.measure_text_width(lt, font_tag, font_size)
            tc_headroom = detector.MAX_TC * max(len(lt), 1)
            effective_w = orig_line_w + tc_headroom

            avg_cw = _avg_char_width(lt, font_tag, font_size)
            max_chars = int(effective_w / avg_cw) if avg_cw > 0 else len(lt)
            # Floor at original length (never budget LESS than current text)
            max_chars = max(max_chars, len(lt))
            line_budgets.append(max_chars)

        bullet_budgets[idx] = line_budgets

    # ── Skill budgets ──
    for idx, sk in enumerate(skills):
        if not sk.content_spans:
            continue
        font_tag = _resolve_font_tag(sk.content_spans[0].font_name)
        if not font_tag:
            continue

        font_size = sk.content_spans[0].font_size

        content = sk.content_text if hasattr(sk, 'content_text') else " ".join(s.text for s in sk.content_spans)
        orig_w = detector.measure_text_width(content, font_tag, font_size)
        tc_headroom = detector.MAX_TC * max(len(content), 1)
        effective_w = orig_w + tc_headroom

        avg_cw = _avg_char_width(content, font_tag, font_size)
        max_chars = int(effective_w / avg_cw) if avg_cw > 0 else len(content)
        max_chars = max(max_chars, len(content))
        skill_budgets[idx] = max_chars

    # ── Title budgets ──
    if title_skills:
        for idx, ts in enumerate(title_skills):
            if not ts.full_spans:
                continue
            font_tag = _resolve_font_tag(ts.full_spans[0].font_name)
            if not font_tag:
                continue

            font_size = ts.full_spans[0].font_size

            # Use original skills_part width as budget basis
            orig_skills_w = detector.measure_text_width(ts.skills_part, font_tag, font_size)
            tc_headroom = detector.MAX_TC * max(len(ts.skills_part), 1)
            effective_skills_w = orig_skills_w + tc_headroom

            avg_cw = _avg_char_width(ts.skills_part, font_tag, font_size)
            max_chars = int(effective_skills_w / avg_cw) if avg_cw > 0 else len(ts.skills_part)
            max_chars = max(max_chars, len(ts.skills_part))
            title_budgets[idx] = max_chars

    doc.close()

    budget_info = {
        "bullet_budgets": bullet_budgets,
        "skill_budgets": skill_budgets,
        "title_budgets": title_budgets,
    }

    total_items = len(bullet_budgets) + len(skill_budgets) + len(title_budgets)
    logger.info(f"[BUDGET] Calculated width budgets for {total_items} items")

    return budget_info


# ─── Step 1: Extract spans ─────────────────────────────────────────────────

def extract_spans_from_pdf(pdf_path: str) -> List[TextSpan]:
    """Extract all text spans from a PDF with their formatting metadata."""
    doc = fitz.open(pdf_path)
    all_spans = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    ts = TextSpan(
                        page_num=page_num,
                        bbox=tuple(span["bbox"]),
                        text=span["text"],
                        font_name=span["font"],
                        font_size=span["size"],
                        color=span["color"],
                        flags=span["flags"],
                        origin=tuple(span["origin"]),
                    )
                    all_spans.append(ts)

    doc.close()
    return all_spans


# ─── Step 2: Group into visual lines ───────────────────────────────────────

def group_into_visual_lines(spans: List[TextSpan]) -> List[List[TextSpan]]:
    """Group spans by y-position into visual lines, splitting multi-column layouts."""
    if not spans:
        return []

    sorted_spans = sorted(spans, key=lambda s: (s.page_num, s.origin[1], s.origin[0]))
    raw_lines: List[List[TextSpan]] = []
    current: List[TextSpan] = [sorted_spans[0]]

    for span in sorted_spans[1:]:
        prev = current[-1]
        if span.page_num == prev.page_num and abs(span.origin[1] - prev.origin[1]) < 3:
            current.append(span)
        else:
            raw_lines.append(current)
            current = [span]

    if current:
        raw_lines.append(current)

    # Detect multi-column pages by counting standalone right-column lines.
    # True 2-column layouts have many lines where ALL spans start at x > page_midpoint.
    # Single-column with right-aligned dates has 0% standalone right-column lines.
    from collections import defaultdict
    column_pages: set = set()
    page_lines_map: dict = defaultdict(list)
    for raw_line in raw_lines:
        page_lines_map[raw_line[0].page_num].append(raw_line)

    for page_num, p_lines in page_lines_map.items():
        total_lines = len(p_lines)
        right_only = sum(
            1 for rl in p_lines
            if min(s.origin[0] for s in rl) > 250
        )
        # If >20% of lines on this page start in the right half, it's a column layout
        if total_lines > 0 and right_only / total_lines > 0.20:
            column_pages.add(page_num)

    # Split multi-column lines only on detected column pages
    lines: List[List[TextSpan]] = []
    for raw_line in raw_lines:
        page_num = raw_line[0].page_num
        if len(raw_line) <= 1 or page_num not in column_pages:
            lines.append(raw_line)
            continue
        x_sorted = sorted(raw_line, key=lambda s: s.origin[0])
        segments: List[List[TextSpan]] = [[x_sorted[0]]]
        for i in range(1, len(x_sorted)):
            prev_span = x_sorted[i - 1]
            cur_span = x_sorted[i]
            gap = cur_span.origin[0] - prev_span.bbox[2]
            if gap > 80:
                segments.append([cur_span])
            else:
                segments[-1].append(cur_span)
        lines.extend(segments)

    return lines


# ─── Step 3: Classify lines ───────────────────────────────────────────────

SECTION_HEADERS = {
    "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "TECHNOLOGIES",
    "TECHNICAL STRENGTHS", "KEY SKILLS", "COMPETENCIES",
    "EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE", "EMPLOYMENT",
    "PROJECTS", "PROJECT EXPERIENCE", "TECHNICAL PROJECTS",
    "EDUCATION", "CERTIFICATIONS", "CERTIFICATES",
    "SUMMARY", "PROFESSIONAL SUMMARY", "OBJECTIVE", "ABOUT",
    "ACHIEVEMENTS", "AWARDS", "PUBLICATIONS", "VOLUNTEER",
    "HONORS", "HONORS & AWARDS", "EXTRACURRICULAR",
    "LANGUAGES", "INTERESTS", "REFERENCES",
    "CONTACT", "CONTACT INFORMATION",
    "AWARDS & ACHIEVEMENTS", "AWARDS & ACHIEVEMENTS:",
    "MOST PROUD OF", "STRENGTHS", "MY LIFE PHILOSOPHY",
}


def classify_lines(
    visual_lines: List[List[TextSpan]],
) -> Tuple[List[ClassifiedLine], Dict[str, str]]:
    """
    Classify each visual line and track which section it belongs to.
    Returns classified lines and a mapping of y_pos -> section_name.
    """
    classified: List[ClassifiedLine] = []
    current_section = "HEADER"  # Before first section header

    # First pass: find all bullet marker y-positions
    bullet_y_positions = set()
    for line in visual_lines:
        for span in line:
            if span.is_bullet_char:
                bullet_y_positions.add(round(span.origin[1], 1))

    # Median font size for header detection
    all_sizes = [s.font_size for line in visual_lines for s in line if not s.is_zwsp_only]
    median_size = sorted(all_sizes)[len(all_sizes) // 2] if all_sizes else 10

    for line in visual_lines:
        page_num = line[0].page_num
        y_pos = line[0].origin[1]
        y_rounded = round(y_pos, 1)

        # Get the combined clean text
        clean = "".join(s.text for s in line).replace("\u200b", "").strip()
        clean_upper = clean.upper()

        # Skip completely empty / ZWS-only lines
        if not clean:
            classified.append(ClassifiedLine(
                spans=line, line_type=LineType.ZWS_PADDING,
                page_num=page_num, y_pos=y_pos,
            ))
            continue

        # Check if this is a section header
        # Normalize: collapse XeTeX kerning spaces like "Sum mary" → "SUMMARY"
        import re
        # Lines with bullet markers are never section headers
        has_bullet_in_line = any(s.is_bullet_char for s in line) or any(
            s.text.replace("\u200b", "").lstrip()[:1] in ("●", "•", "◦", "○", "■", "▪", "·", "▸", "▹")
            for s in line if not s.is_zwsp_only
        )
        clean_collapsed = re.sub(r'[^A-Z0-9&:]', '', clean_upper)  # strip all non-alpha
        is_header = False
        if not has_bullet_in_line:
            for header in SECTION_HEADERS:
                header_collapsed = re.sub(r'[^A-Z0-9&:]', '', header)
                if (clean_upper == header or clean_upper.startswith(header + " ")
                        or clean_collapsed == header_collapsed
                        or (len(header_collapsed) > 3 and clean_collapsed.startswith(header_collapsed))):
                    is_header = True
                    current_section = clean
                    break

        # Also detect by formatting: bold + short + significantly larger font + all-caps
        # Must be all-caps to distinguish from bold company names / titles
        if not is_header and not has_bullet_in_line:
            non_zwsp = [s for s in line if not s.is_zwsp_only]
            if non_zwsp and len(clean) < 40:
                first = non_zwsp[0]
                alpha_chars = [c for c in clean if c.isalpha()]
                is_all_caps = alpha_chars and all(c.isupper() for c in alpha_chars)
                if first.is_bold and first.font_size > median_size + 1.0 and is_all_caps:
                    is_header = True
                    current_section = clean

        if is_header:
            classified.append(ClassifiedLine(
                spans=line, line_type=LineType.STRUCTURE,
                page_num=page_num, y_pos=y_pos,
            ))
            continue

        # Precompute span properties
        non_zwsp = [s for s in line if not s.is_zwsp_only]
        has_bullet_span = any(s.is_bullet_char for s in line)
        text_spans = [s for s in line if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()]

        # Detect inline bullets: text starts with "• " or "· " but bullet is not a separate span
        # Common in XeTeX (Awesome-CV) where "• Led service mesh..." is one span
        INLINE_BULLET_CHARS = ("•", "●", "◦", "○", "■", "▪", "·", "▸", "▹")
        if not has_bullet_span and non_zwsp:
            first_text = non_zwsp[0].text.replace("\u200b", "").lstrip()
            if any(first_text.startswith(bc + " ") or first_text.startswith(bc + "\t") for bc in INLINE_BULLET_CHARS):
                has_bullet_span = True  # treat as having a bullet marker

        # Check if this line IS a standalone bullet marker (● only, no text)
        if non_zwsp and all(s.is_bullet_char for s in non_zwsp):
            classified.append(ClassifiedLine(
                spans=line, line_type=LineType.BULLET_MARKER,
                page_num=page_num, y_pos=y_pos,
            ))
            continue

        # ── SKILLS CHECK (must come before bullet_text check) ──
        # Skills lines: ● Languages: Python, R, SQL... → has bullet + bold label + regular content
        section_collapsed = re.sub(r'[^A-Z0-9&:]', '', current_section.upper())
        is_skill_section = section_collapsed in (
            "SKILLS", "TECHNICALSKILLS", "CORECOMPETENCIES", "TECHNOLOGIES",
            "TECHNICALSTRENGTHS", "KEYSKILLS", "COMPETENCIES",
        )
        if is_skill_section and non_zwsp:
            non_bullet = [s for s in non_zwsp if not s.is_bullet_char]
            has_bold = any(s.is_bold for s in non_bullet)
            has_regular = any(not s.is_bold for s in non_bullet)
            if has_bold and has_regular:
                classified.append(ClassifiedLine(
                    spans=line, line_type=LineType.SKILL_CONTENT,
                    page_num=page_num, y_pos=y_pos,
                ))
                continue
            # Continuation line in skills (regular only, no bold label)
            if not has_bold and has_regular:
                prev_skills = [c for c in classified if c.line_type == LineType.SKILL_CONTENT]
                if prev_skills and abs(y_pos - prev_skills[-1].y_pos) < 15:
                    classified.append(ClassifiedLine(
                        spans=line, line_type=LineType.SKILL_CONTENT,
                        page_num=page_num, y_pos=y_pos,
                    ))
                    continue

        # ── BULLET TEXT CHECK ──
        # Only in sections that can have bullets (not HEADER, EDUCATION, SKILLS, etc.)
        is_bullet_section = section_collapsed in (
            "WORKEXPERIENCE", "EXPERIENCE", "PROFESSIONALEXPERIENCE", "EMPLOYMENT",
            "PROJECTS", "PROJECTEXPERIENCE", "TECHNICALPROJECTS",
            "AWARDS", "ACHIEVEMENTS", "AWARDS&ACHIEVEMENTS", "AWARDS&ACHIEVEMENTS:",
            "CERTIFICATIONS", "PUBLICATIONS", "VOLUNTEER",
            "HONORS", "HONORS&AWARDS", "EXTRACURRICULAR",
            "SUMMARY", "PROFESSIONALSUMMARY",
            "MOSTPROUDOF",
        )

        # Line contains both ● and text on same visual line
        if has_bullet_span and text_spans and is_bullet_section:
            classified.append(ClassifiedLine(
                spans=line, line_type=LineType.BULLET_TEXT,
                page_num=page_num, y_pos=y_pos,
            ))
            continue

        # Line is text-only but shares y with a bullet marker
        if y_rounded in bullet_y_positions and text_spans and not has_bullet_span and is_bullet_section:
            classified.append(ClassifiedLine(
                spans=line, line_type=LineType.BULLET_TEXT,
                page_num=page_num, y_pos=y_pos,
            ))
            continue

        # Continuation of bullet text (same x as previous bullet's text, in bullet sections)
        # Bold check removed: wrapped bold phrases (e.g. "availability" continuing bold from prev line)
        # are valid continuations. The x-match + y-proximity is sufficient to distinguish from structure.
        if non_zwsp and is_bullet_section:
            first_non_zwsp = non_zwsp[0]
            prev_bullets = [c for c in classified if c.line_type == LineType.BULLET_TEXT]
            if prev_bullets:
                last_bullet = prev_bullets[-1]
                last_bullet_y = last_bullet.y_pos
                # Close in y: same page within ~15 units, OR first line of new page
                # (page break = last bullet on prev page, continuation on next page top)
                same_page = (page_num == last_bullet.page_num)
                y_close = same_page and abs(y_pos - last_bullet_y) < 15
                page_break_continuation = (
                    not same_page
                    and page_num == last_bullet.page_num + 1
                    and y_pos < 120  # near top of new page
                )
                if y_close or page_break_continuation:
                    # Get text x of previous bullet (first non-bullet, non-zwsp span)
                    last_text_x = None
                    for s in last_bullet.spans:
                        if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip():
                            last_text_x = s.origin[0]
                            break
                    cur_x = first_non_zwsp.origin[0]
                    # Match if x is close to previous bullet's text x (±15 units)
                    if last_text_x is not None and abs(cur_x - last_text_x) < 15:
                        classified.append(ClassifiedLine(
                            spans=line, line_type=LineType.BULLET_TEXT,
                            page_num=page_num, y_pos=y_pos,
                        ))
                        continue

        # Project description lines (at left margin, in PROJECTS section)
        if (current_section.upper() in ("PROJECTS", "PROJECT EXPERIENCE", "TECHNICAL PROJECTS")
                and non_zwsp
                and non_zwsp[0].origin[0] < 20):
            first_span = non_zwsp[0]
            if not first_span.is_bold:
                # Starts with regular text — definitely a description line
                classified.append(ClassifiedLine(
                    spans=line, line_type=LineType.BULLET_TEXT,
                    page_num=page_num, y_pos=y_pos,
                ))
                continue
            elif first_span.is_bold:
                # Starts bold — could be a project title or a description continuation
                # Project titles have patterns like "Name: description | tech"
                first_bold_text = first_span.text.replace("\u200b", "").strip()
                is_likely_title = (":" in first_bold_text or "|" in first_bold_text
                                   or "–" in first_bold_text)
                # It's a continuation ONLY if not a title and close to previous bullet line
                if not is_likely_title:
                    prev_bt = [c for c in classified if c.line_type == LineType.BULLET_TEXT]
                    if prev_bt and abs(y_pos - prev_bt[-1].y_pos) < 15:
                        classified.append(ClassifiedLine(
                            spans=line, line_type=LineType.BULLET_TEXT,
                            page_num=page_num, y_pos=y_pos,
                        ))
                        continue

        # Everything else is structure (company names, dates, locations, titles)
        classified.append(ClassifiedLine(
            spans=line, line_type=LineType.STRUCTURE,
            page_num=page_num, y_pos=y_pos,
        ))

    return classified, {}


# ─── Step 4: Group bullet text into bullet points ──────────────────────────

def group_bullet_points(
    classified: List[ClassifiedLine],
) -> Tuple[List[BulletPoint], List[SkillLine], List[TitleSkillLine]]:
    """Group bullet text lines into logical bullet points, skill lines, and title skill lines."""
    bullets: List[BulletPoint] = []
    skills: List[SkillLine] = []
    title_skills: List[TitleSkillLine] = []
    current_section = "HEADER"

    current_bullet: Optional[BulletPoint] = None

    for cl in classified:
        # Track current section
        if cl.line_type == LineType.STRUCTURE:
            clean_upper = cl.clean_text.upper()
            clean_collapsed = re.sub(r'[^A-Z0-9&:]', '', clean_upper)
            for header in SECTION_HEADERS:
                header_collapsed = re.sub(r'[^A-Z0-9&:]', '', header)
                if (clean_upper == header or clean_upper.startswith(header + " ")
                        or clean_collapsed == header_collapsed
                        or (len(header_collapsed) > 3 and clean_collapsed.startswith(header_collapsed))):
                    current_section = cl.clean_text
                    break

            # Detect title skill lines: "(Tech1, Tech2, ...)" pattern in STRUCTURE
            clean = cl.clean_text
            paren_match = re.search(r'\(([^)]*,\s*[^)]+)\)', clean)
            grp_section_collapsed = re.sub(r'[^A-Z0-9&:]', '', current_section.upper())
            if paren_match and grp_section_collapsed in (
                "WORKEXPERIENCE", "EXPERIENCE", "PROFESSIONALEXPERIENCE",
            ):
                title_part = clean[:paren_match.start()].strip()
                skills_part = paren_match.group(1).strip()
                # Only if it looks like a tech list (multiple comma-separated items)
                if len(skills_part.split(",")) >= 2:
                    # Use full line spans (not just bold) so parentheses content is fully redacted/replaced.
                    full_spans = [s for s in cl.spans if not s.is_zwsp_only and s.text.strip()]
                    if full_spans:
                        title_skills.append(TitleSkillLine(
                            full_spans=full_spans,
                            title_part=title_part,
                            skills_part=skills_part,
                            full_text=clean.strip(),
                        ))

        if cl.line_type == LineType.BULLET_MARKER:
            # Standalone bullet marker — start a new bullet point
            if current_bullet and current_bullet.text_lines:
                bullets.append(current_bullet)
            current_bullet = BulletPoint(
                marker_line=cl, text_lines=[], section_name=current_section,
            )

        elif cl.line_type == LineType.BULLET_TEXT:
            # Check if this line contains a bullet char (● + text on same line)
            # Also detect inline bullets where "• text" is one span
            INLINE_BULLET_CHARS = ("•", "●", "◦", "○", "■", "▪", "·", "▸", "▹")
            has_bullet_char = any(s.is_bullet_char for s in cl.spans)
            if not has_bullet_char:
                non_zwsp_spans = [s for s in cl.spans if not s.is_zwsp_only]
                if non_zwsp_spans:
                    ft = non_zwsp_spans[0].text.replace("\u200b", "").lstrip()
                    if any(ft.startswith(bc + " ") or ft.startswith(bc + "\t") for bc in INLINE_BULLET_CHARS):
                        has_bullet_char = True
            if has_bullet_char:
                # This is a NEW bullet point (● is inline with text)
                if current_bullet and current_bullet.text_lines:
                    bullets.append(current_bullet)
                current_bullet = BulletPoint(
                    marker_line=None, text_lines=[], section_name=current_section,
                )
            elif current_bullet is None:
                # Continuation text without a marker — treat as its own bullet
                current_bullet = BulletPoint(
                    marker_line=None, text_lines=[], section_name=current_section,
                )
            current_bullet.text_lines.append(cl)

        elif cl.line_type == LineType.SKILL_CONTENT:
            # Split into label spans (bold) and content spans (regular)
            # Skip bullet chars and ZWS-only spans
            label_spans = []
            content_spans = []
            for span in cl.spans:
                if span.is_zwsp_only or span.is_bullet_char:
                    continue
                if span.is_bold:
                    label_spans.append(span)
                else:
                    content_spans.append(span)

            if content_spans:
                if not label_spans and skills:
                    # Continuation of previous skill line (wrapped text, no bold label).
                    # Merge into parent skill to keep indices aligned with Claude's
                    # per-category replacements.
                    skills[-1].content_spans.extend(content_spans)
                else:
                    skills.append(SkillLine(
                        label_spans=label_spans,
                        content_spans=content_spans,
                        section_name=current_section,
                    ))

        else:
            # Non-bullet/skill line — finalize any pending bullet
            if current_bullet and current_bullet.text_lines:
                bullets.append(current_bullet)
                current_bullet = None

    # Don't forget last bullet
    if current_bullet and current_bullet.text_lines:
        bullets.append(current_bullet)

    return bullets, skills, title_skills


# ─── Step 5: Claude optimization ──────────────────────────────────────────

async def generate_optimized_content(
    bullets: List[BulletPoint],
    skills: List[SkillLine],
    job_description: str,
    title_skills: Optional[List[TitleSkillLine]] = None,
    char_constraint: str = "",
    width_budgets: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[int, List[str]], Dict[int, str], Dict[int, str]]:
    """
    Send bullet points, skills, and title tech stacks to Claude for optimization.

    Args:
        char_constraint: Optional character constraint string from FontAnalyzer.
            If provided, appended to each LLM prompt to prevent generating
            characters that the PDF font cannot render.
        width_budgets: Optional per-item max character counts from calculate_width_budgets().
            If provided, per-item constraints are included in the LLM prompt.

    Returns:
        bullet_replacements: {bullet_index: [line1_text, line2_text, ...]}
        skill_replacements: {skill_index: "new content text"}
        title_replacements: {title_index: "new skills part text"}
    """
    from app.llm.claude_client import ClaudeClient
    import asyncio

    claude = ClaudeClient()

    # Filter out awards/achievements bullets (factual, not optimizable)
    SKIP_SECTIONS = {"AWARDS", "ACHIEVEMENTS", "AWARDS & ACHIEVEMENTS", "AWARDS & ACHIEVEMENTS:"}

    # ── Define all optimization tasks as async functions ──

    BULLET_BATCH_SIZE = 7  # Split large bullet sets into parallel batches

    async def _optimize_bullets() -> Dict[int, List[str]]:
        replacements: Dict[int, List[str]] = {}
        if not bullets:
            return replacements

        # Build bullet texts with ORIGINAL indices preserved
        bullet_budgets = (width_budgets or {}).get("bullet_budgets", {})
        bullet_texts = []
        for i, bp in enumerate(bullets):
            if bp.section_name.upper().strip() in SKIP_SECTIONS:
                continue
            lines_info = []
            budgets = bullet_budgets.get(i, [])
            for j, lt in enumerate(bp.line_texts):
                max_chars = budgets[j] if j < len(budgets) else None
                if max_chars:
                    lines_info.append(f"    Line {j+1} ({len(lt)} chars, max {max_chars}): {lt}")
                else:
                    lines_info.append(f"    Line {j+1} ({len(lt)} chars): {lt}")
            bullet_texts.append(f"  BULLET {i+1} ({bp.section_name}):\n" + "\n".join(lines_info))

        if not bullet_texts:
            return replacements

        sys_prompt = (
            "You are an expert resume optimizer. You tailor resume bullet points to match "
            "specific job descriptions by incorporating relevant keywords, rephrasing to "
            "emphasize relevant experience, and using terminology from the job posting. "
            "You must make REAL, MEANINGFUL changes that make the resume clearly targeted "
            "to the specific job."
        )

        async def _process_bullet_batch(batch_texts: List[str], batch_max_tokens: int) -> Dict[int, List[str]]:
            """Process a batch of bullets — same prompt, same parsing, same rules."""
            batch_result: Dict[int, List[str]] = {}
            char_rule = f"\n9. {char_constraint}" if char_constraint else ""
            usr_prompt = f"""Rewrite these resume bullet points to be strongly tailored for the job description below.

RULES:
1. Incorporate keywords, phrases, and terminology directly from the job description
2. Rephrase to emphasize skills and experience most relevant to this specific role
3. Use action verbs and terminology that mirror the job posting's language
4. PRESERVE: company names, metrics, percentages, dates, and factual claims — do NOT fabricate
5. Each bullet must have EXACTLY the same number of lines as the original
6. Each line MUST NOT exceed its max character count (shown as "max N"). Stay close to the original length but NEVER go over the max
7. Every bullet MUST be modified — do not return any bullet unchanged
8. Focus on what the job description specifically asks for and weave those themes into each bullet{char_rule}

JOB DESCRIPTION:
{job_description[:3000]}

BULLET POINTS TO OPTIMIZE:
{chr(10).join(batch_texts)}

OUTPUT FORMAT — Return ONLY this JSON, no explanation:
{{
  "bullets": [
    {{
      "index": 1,
      "lines": ["line 1 text", "line 2 text"]
    }},
    ...
  ]
}}

IMPORTANT: Make each bullet clearly targeted to THIS specific job. A reader should be able to tell which job this resume was tailored for.
"""
            try:
                response = await claude._send_request(sys_prompt, usr_prompt, max_tokens=batch_max_tokens)
                parsed = _parse_json_response(response)
                if parsed and "bullets" in parsed:
                    for item in parsed["bullets"]:
                        idx = item.get("index", 0) - 1  # Original 0-based index
                        lines = item.get("lines", [])
                        if 0 <= idx < len(bullets) and lines:
                            batch_result[idx] = lines
            except Exception as e:
                logger.error(f"Failed to optimize bullet batch: {e}", exc_info=True)
            return batch_result

        if len(bullet_texts) <= BULLET_BATCH_SIZE:
            # Small enough for a single call
            logger.info(f"[BULLET OPT] Sending {len(bullet_texts)} bullets in single call")
            replacements = await _process_bullet_batch(bullet_texts, 8192)
            logger.info(f"[BULLET OPT] Parsed {len(replacements)} bullet replacements")
        else:
            # Split into batches and run in parallel
            batches = [
                bullet_texts[i:i + BULLET_BATCH_SIZE]
                for i in range(0, len(bullet_texts), BULLET_BATCH_SIZE)
            ]
            # Scale max_tokens per batch proportionally
            tokens_per_batch = max(4096, 8192 // len(batches) * 2)
            logger.info(f"[BULLET OPT] Splitting {len(bullet_texts)} bullets into {len(batches)} parallel batches")

            batch_results = await asyncio.gather(
                *[_process_bullet_batch(batch, tokens_per_batch) for batch in batches]
            )
            for batch_result in batch_results:
                replacements.update(batch_result)
            logger.info(f"[BULLET OPT] Parsed {len(replacements)} bullet replacements from {len(batches)} batches")

        return replacements

    async def _optimize_skills() -> Dict[int, str]:
        replacements: Dict[int, str] = {}
        if not skills:
            return replacements

        s_budgets = (width_budgets or {}).get("skill_budgets", {})
        skill_texts = []
        for i, sk in enumerate(skills):
            max_c = s_budgets.get(i)
            if max_c:
                skill_texts.append(f"  {i+1}. [{len(sk.content_text)} chars, max {max_c}] {sk.label_text} {sk.content_text}")
            else:
                skill_texts.append(f"  {i+1}. {sk.label_text} {sk.content_text}")

        sys_prompt = (
            "You are an expert resume skills optimizer. You reorder, substitute, and emphasize "
            "skills to strongly match a specific job description."
        )

        char_rule = f"\n9. {char_constraint}" if char_constraint else ""
        usr_prompt = f"""Optimize these skill lines to best match the job description below.

RULES:
1. REORDER skills to put the most job-relevant ones FIRST
2. Substitute equivalent terms to match JD language (e.g., "PostgreSQL" → "Postgres", "JS" → "JavaScript", "REST" → "RESTful APIs")
3. You may add 1-2 closely related skills if they appear in the JD and the candidate likely has them based on their other skills
4. You may remove less relevant skills to make room for more relevant ones
5. Keep the SAME comma-separated format
6. Each line MUST NOT exceed its max character count (shown as "max N" in brackets). Stay close to original but NEVER go over the max
7. Return ONLY the values after the label (e.g., for "Languages: Python, R, SQL" return "Python, R, SQL" — NOT "Languages: Python, R, SQL")
8. The ordering should CLEARLY reflect what this specific job prioritizes{char_rule}

JOB DESCRIPTION:
{job_description[:3000]}

SKILL LINES:
{chr(10).join(skill_texts)}

OUTPUT FORMAT — Return ONLY this JSON:
{{
  "skills": [
    {{"index": 1, "content": "reordered, skill, values, here"}},
    ...
  ]
}}
"""
        try:
            response = await claude._send_request(sys_prompt, usr_prompt)
            parsed = _parse_json_response(response)
            if parsed and "skills" in parsed:
                for item in parsed["skills"]:
                    idx = item.get("index", 0) - 1
                    content = item.get("content", "")
                    if 0 <= idx < len(skills) and content:
                        label = skills[idx].label_text.strip()
                        if label and content.startswith(label):
                            content = content[len(label):].strip()
                        label_base = label.rstrip(": ").strip()
                        if label_base and content.startswith(label_base):
                            content = content[len(label_base):].lstrip(": ").strip()
                        replacements[idx] = content
        except Exception as e:
            logger.error(f"Failed to optimize skills: {e}")
        return replacements

    async def _optimize_titles() -> Dict[int, str]:
        replacements: Dict[int, str] = {}
        if not title_skills:
            return replacements

        t_budgets = (width_budgets or {}).get("title_budgets", {})
        title_texts = []
        for i, ts in enumerate(title_skills):
            max_c = t_budgets.get(i)
            if max_c:
                title_texts.append(f"  {i+1}. [{len(ts.skills_part)} chars, max {max_c}] {ts.title_part} ({ts.skills_part})")
            else:
                title_texts.append(f"  {i+1}. {ts.title_part} ({ts.skills_part})")

        sys_prompt = (
            "You are a resume title optimizer. You replace the tech stack in job title "
            "parentheses to match a target job description's technology requirements."
        )

        char_rule = f"\n5. {char_constraint}" if char_constraint else ""
        usr_prompt = f"""Replace the tech stacks in these job title parentheses to match the job description.

RULES:
1. ONLY change the technologies inside the parentheses — do NOT change the job title itself
2. Use technologies from the JD that the candidate actually knows (based on their current tech stacks)
3. Keep the SAME number of technologies (same comma-separated count)
4. The skills text MUST NOT exceed the max character count shown in brackets. Stay close to original length but NEVER go over the max{char_rule}

JOB DESCRIPTION:
{job_description[:3000]}

TITLE LINES:
{chr(10).join(title_texts)}

OUTPUT FORMAT — Return ONLY this JSON:
{{
  "titles": [
    {{"index": 1, "skills": "Tech1, Tech2, Tech3"}},
    ...
  ]
}}
"""
        try:
            response = await claude._send_request(sys_prompt, usr_prompt)
            parsed = _parse_json_response(response)
            if parsed and "titles" in parsed:
                for item in parsed["titles"]:
                    idx = item.get("index", 0) - 1
                    new_skills = item.get("skills", "")
                    if 0 <= idx < len(title_skills) and new_skills:
                        replacements[idx] = new_skills
        except Exception as e:
            logger.error(f"Failed to optimize title skills: {e}")
        return replacements

    # Run ALL Claude calls in parallel — bullets, skills, and titles are independent
    logger.info("[PARALLEL] Running bullet, skill, and title optimization concurrently")
    bullet_replacements, skill_replacements, title_replacements = await asyncio.gather(
        _optimize_bullets(),
        _optimize_skills(),
        _optimize_titles(),
    )

    return bullet_replacements, skill_replacements, title_replacements


def _parse_json_response(response: str) -> Optional[Dict]:
    """Parse JSON from Claude's response, handling markdown code blocks."""
    response = response.strip()
    # Strip markdown code block (handle triple backticks anywhere)
    if "```" in response:
        # Extract content between first ``` and last ```
        match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', response)
        if match:
            response = match.group(1).strip()
        else:
            # Just strip leading/trailing ```
            response = re.sub(r'^```(?:json)?\s*\n?', '', response)
            response = re.sub(r'\n?\s*```\s*$', '', response)
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        logger.warning(f"[JSON PARSE] First attempt failed: {e}")
        logger.warning(f"[JSON PARSE] Response start: {response[:200]}")
        logger.warning(f"[JSON PARSE] Response end: {response[-200:]}")
        # Try to find JSON object in response
        match = re.search(r'(\{[\s\S]*\})', response)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e2:
                logger.warning(f"[JSON PARSE] Second attempt failed: {e2}")
        # Try finding JSON array wrapper
        match = re.search(r'(\[[\s\S]*\])', response)
        if match:
            try:
                obj = json.loads(match.group(1))
                return {"bullets": obj} if isinstance(obj, list) else None
            except json.JSONDecodeError:
                pass
    return None


# ─── Step 6: Content Stream Engine ────────────────────────────────────────
#
# Architecture: Instead of redact+insert (which destroys formatting), we parse
# the raw PDF content stream, find text operators (Tj/TJ), and surgically patch
# the hex-encoded CID sequences in-place. This preserves 100% of the original
# font references, positioning, kerning, and rendering.

@dataclass
class TextOp:
    """A single text-showing operation within a BT/ET block."""
    hex_string: str          # Raw hex like "002F00480044" (always hex, even for Type1 literal strings)
    decoded_text: str        # Unicode text decoded via CMap
    byte_offset: int         # Position of '<' or '(' in stream bytes for patching
    byte_length: int         # Length of <hex> or (literal) including delimiters in stream
    operator: str            # "Tj" or "TJ"
    is_literal: bool = False # True if original was a literal string (...), False for hex <...>
    tj_array_start: int = -1 # Byte offset of '[' for TJ array ops (-1 if Tj)


@dataclass
class ContentBlock:
    """A complete BT/ET text block with all state."""
    font_tag: str            # "F5" (without slash)
    font_size: float         # 10.0
    x: float                 # Absolute x position (from Tm/Td)
    y: float                 # Absolute y position (from Tm/Td)
    text_ops: List[TextOp]   # All text operations in this block
    stream_xref: int         # Which content stream xref this belongs to
    page_num: int

    @property
    def full_text(self) -> str:
        return "".join(op.decoded_text for op in self.text_ops)


class _CMapManager:
    """Manages ToUnicode CMaps for encoding/decoding CID ↔ Unicode."""

    def __init__(self, doc):
        # font_tag → {"fwd": {cid: char}, "rev": {char: cid}, "font_name": str}
        self.font_cmaps: Dict[str, Dict] = {}
        # font_tag → font_name (e.g., "F5" → "TimesNewRomanPSMT")
        self.font_names: Dict[str, str] = {}
        self._build_all_cmaps(doc)

    def _build_all_cmaps(self, doc):
        """Extract ToUnicode CMaps for every font on every page."""
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            # Get font resources from page
            fonts = self._get_page_fonts(doc, page)
            for font_tag, font_xref, font_name in fonts:
                if font_tag in self.font_cmaps:
                    continue
                self.font_names[font_tag] = font_name
                tounicode_stream = self._get_tounicode_stream(doc, font_xref)
                if tounicode_stream:
                    fwd, rev, byte_width = self._parse_tounicode(tounicode_stream)
                    self.font_cmaps[font_tag] = {
                        "fwd": fwd, "rev": rev, "byte_width": byte_width,
                    }
                    logger.info(
                        f"[CMAP] Font {font_tag} ({font_name}): "
                        f"{len(fwd)} forward mappings, {len(rev)} reverse mappings, "
                        f"{byte_width}-byte CIDs"
                    )
                else:
                    # No ToUnicode CMap — try to build from Encoding/Differences
                    subtype_val = doc.xref_get_key(font_xref, "Subtype")
                    subtype = subtype_val[1].strip().strip("/") if subtype_val[0] != "null" else ""

                    # Try building CMap from /Encoding + /Differences (works for TrueType + Type1)
                    encoding_cmap = self._build_cmap_from_encoding(doc, font_xref)
                    if encoding_cmap:
                        fwd, rev = encoding_cmap
                        self.font_cmaps[font_tag] = {
                            "fwd": fwd, "rev": rev, "byte_width": 1,
                        }
                        logger.info(
                            f"[CMAP] Font {font_tag} ({font_name}): "
                            f"{len(fwd)} mappings from Encoding/Differences ({subtype}), 1-byte CIDs"
                        )
                    elif subtype in ("Type1", "TrueType"):
                        # Fallback: identity CMap for simple fonts
                        fwd, rev = self._build_identity_cmap()
                        self.font_cmaps[font_tag] = {
                            "fwd": fwd, "rev": rev, "byte_width": 1,
                        }
                        logger.info(
                            f"[CMAP] Font {font_tag} ({font_name}): "
                            f"identity CMap ({subtype}, no ToUnicode), 1-byte CIDs"
                        )

    @staticmethod
    def _build_identity_cmap() -> Tuple[Dict[int, str], Dict[str, int]]:
        """Build identity CMap for simple fonts: byte value → same Unicode codepoint.

        Covers printable ASCII (0x20-0x7E) and Latin-1 supplement (0xA0-0xFF)
        for accented characters like é, ñ, ü etc.
        """
        fwd: Dict[int, str] = {}
        rev: Dict[str, int] = {}
        # Map printable ASCII range (0x20-0x7E) directly
        for code in range(0x20, 0x7F):
            char = chr(code)
            fwd[code] = char
            rev[char] = code
        # Map Latin-1 supplement (0xA0-0xFF) for accented characters
        for code in range(0xA0, 0x100):
            char = chr(code)
            fwd[code] = char
            rev[char] = code
        return fwd, rev

    # Standard PDF encoding glyph name → Unicode mappings
    _GLYPH_TO_UNICODE = {
        "space": 0x0020, "exclam": 0x0021, "quotedbl": 0x0022, "numbersign": 0x0023,
        "dollar": 0x0024, "percent": 0x0025, "ampersand": 0x0026, "quotesingle": 0x0027,
        "parenleft": 0x0028, "parenright": 0x0029, "asterisk": 0x002A, "plus": 0x002B,
        "comma": 0x002C, "hyphen": 0x002D, "period": 0x002E, "slash": 0x002F,
        "zero": 0x0030, "one": 0x0031, "two": 0x0032, "three": 0x0033,
        "four": 0x0034, "five": 0x0035, "six": 0x0036, "seven": 0x0037,
        "eight": 0x0038, "nine": 0x0039, "colon": 0x003A, "semicolon": 0x003B,
        "less": 0x003C, "equal": 0x003D, "greater": 0x003E, "question": 0x003F,
        "at": 0x0040, "bracketleft": 0x005B, "backslash": 0x005C,
        "bracketright": 0x005D, "asciicircum": 0x005E, "underscore": 0x005F,
        "grave": 0x0060, "braceleft": 0x007B, "bar": 0x007C,
        "braceright": 0x007D, "asciitilde": 0x007E,
        # Latin-1 supplement
        "exclamdown": 0x00A1, "cent": 0x00A2, "sterling": 0x00A3, "currency": 0x00A4,
        "yen": 0x00A5, "brokenbar": 0x00A6, "section": 0x00A7, "dieresis": 0x00A8,
        "copyright": 0x00A9, "ordfeminine": 0x00AA, "guillemotleft": 0x00AB,
        "logicalnot": 0x00AC, "registered": 0x00AE, "macron": 0x00AF,
        "degree": 0x00B0, "plusminus": 0x00B1, "twosuperior": 0x00B2,
        "threesuperior": 0x00B3, "acute": 0x00B4, "mu": 0x00B5,
        "paragraph": 0x00B6, "periodcentered": 0x00B7, "cedilla": 0x00B8,
        "onesuperior": 0x00B9, "ordmasculine": 0x00BA, "guillemotright": 0x00BB,
        "onequarter": 0x00BC, "onehalf": 0x00BD, "threequarters": 0x00BE,
        "questiondown": 0x00BF,
        "Agrave": 0x00C0, "Aacute": 0x00C1, "Acircumflex": 0x00C2, "Atilde": 0x00C3,
        "Adieresis": 0x00C4, "Aring": 0x00C5, "AE": 0x00C6, "Ccedilla": 0x00C7,
        "Egrave": 0x00C8, "Eacute": 0x00C9, "Ecircumflex": 0x00CA, "Edieresis": 0x00CB,
        "Igrave": 0x00CC, "Iacute": 0x00CD, "Icircumflex": 0x00CE, "Idieresis": 0x00CF,
        "Eth": 0x00D0, "Ntilde": 0x00D1, "Ograve": 0x00D2, "Oacute": 0x00D3,
        "Ocircumflex": 0x00D4, "Otilde": 0x00D5, "Odieresis": 0x00D6, "multiply": 0x00D7,
        "Oslash": 0x00D8, "Ugrave": 0x00D9, "Uacute": 0x00DA, "Ucircumflex": 0x00DB,
        "Udieresis": 0x00DC, "Yacute": 0x00DD, "Thorn": 0x00DE, "germandbls": 0x00DF,
        "agrave": 0x00E0, "aacute": 0x00E1, "acircumflex": 0x00E2, "atilde": 0x00E3,
        "adieresis": 0x00E4, "aring": 0x00E5, "ae": 0x00E6, "ccedilla": 0x00E7,
        "egrave": 0x00E8, "eacute": 0x00E9, "ecircumflex": 0x00EA, "edieresis": 0x00EB,
        "igrave": 0x00EC, "iacute": 0x00ED, "icircumflex": 0x00EE, "idieresis": 0x00EF,
        "eth": 0x00F0, "ntilde": 0x00F1, "ograve": 0x00F2, "oacute": 0x00F3,
        "ocircumflex": 0x00F4, "otilde": 0x00F5, "odieresis": 0x00F6, "divide": 0x00F7,
        "oslash": 0x00F8, "ugrave": 0x00F9, "uacute": 0x00FA, "ucircumflex": 0x00FB,
        "udieresis": 0x00FC, "yacute": 0x00FD, "thorn": 0x00FE, "ydieresis": 0x00FF,
        # Common Windows-1252 extras (not in Latin-1 but common in PDFs)
        "bullet": 0x2022, "endash": 0x2013, "emdash": 0x2014,
        "quotedblleft": 0x201C, "quotedblright": 0x201D,
        "quoteleft": 0x2018, "quoteright": 0x2019,
        "ellipsis": 0x2026, "trademark": 0x2122, "fi": 0xFB01, "fl": 0xFB02,
    }

    def _build_cmap_from_encoding(self, doc, font_xref: int) -> Optional[Tuple[Dict[int, str], Dict[str, int]]]:
        """Build CMap from /Encoding and /Differences arrays.

        PDF fonts can specify character mappings via:
        - /Encoding /WinAnsiEncoding (or /MacRomanEncoding)
        - /Encoding << /BaseEncoding /WinAnsiEncoding /Differences [code /glyphname ...] >>
        """
        try:
            enc_val = doc.xref_get_key(font_xref, "Encoding")
            if enc_val[0] == "null" or not enc_val[1]:
                return None

            enc_text = enc_val[1].strip()

            # Start with identity mapping as base
            fwd, rev = self._build_identity_cmap()

            # Check for base encoding name (e.g., /WinAnsiEncoding)
            if enc_text.startswith("/"):
                # Simple named encoding — identity CMap covers most standard encodings
                return fwd, rev

            # Check for indirect reference to encoding dict
            if "0 R" in enc_text:
                ref_match = re.match(r'(\d+)\s+0\s+R', enc_text)
                if ref_match:
                    enc_xref = int(ref_match.group(1))
                    enc_obj = doc.xref_object(enc_xref)
                    if enc_obj:
                        enc_text = enc_obj.strip()

            # Parse Differences array if present
            # Format: /Differences [code1 /name1 /name2 code2 /name3 ...]
            diff_match = re.search(r'/Differences\s*\[(.*?)\]', enc_text, re.DOTALL)
            if diff_match:
                diff_content = diff_match.group(1).strip()
                tokens = diff_content.split()
                current_code = 0
                for token in tokens:
                    token = token.strip()
                    if not token:
                        continue
                    if token.startswith("/"):
                        # Glyph name
                        glyph_name = token[1:]
                        # Single letter names map to themselves
                        if len(glyph_name) == 1 and glyph_name.isalpha():
                            unicode_val = ord(glyph_name)
                        else:
                            unicode_val = self._GLYPH_TO_UNICODE.get(glyph_name)
                            if unicode_val is None and len(glyph_name) == 1:
                                unicode_val = ord(glyph_name)
                        if unicode_val is not None:
                            char = chr(unicode_val)
                            fwd[current_code] = char
                            rev[char] = current_code
                        current_code += 1
                    else:
                        # Integer code
                        try:
                            current_code = int(token)
                        except ValueError:
                            pass

            return fwd, rev

        except Exception as e:
            logger.debug(f"[CMAP] Failed to build CMap from encoding for xref {font_xref}: {e}")
            return None

    def _get_page_fonts(self, doc, page) -> List[Tuple[str, int, str]]:
        """Get (font_tag, font_xref, font_name) for all fonts on a page."""
        results = []
        try:
            # page.get_fonts() returns list of (xref, ext, type, basefont, name, encoding)
            for f in page.get_fonts():
                xref = f[0]
                basefont = f[3]  # e.g., "ABCDEF+TimesNewRomanPSMT"
                name = f[4]     # e.g., "F5"
                if not name or xref == 0:
                    continue
                # Clean basefont (remove subset prefix)
                clean_name = basefont.split("+", 1)[-1] if "+" in basefont else basefont
                results.append((name, xref, clean_name))
        except Exception as e:
            logger.warning(f"[CMAP] Failed to get page fonts: {e}")
        return results

    def _get_tounicode_stream(self, doc, font_xref: int) -> Optional[bytes]:
        """Extract the ToUnicode CMap stream for a font."""
        try:
            # Check if the font has a ToUnicode entry
            tounicode_val = doc.xref_get_key(font_xref, "ToUnicode")
            if tounicode_val[0] == "null" or not tounicode_val[1]:
                # Try via DescendantFonts for Type0 fonts
                desc_val = doc.xref_get_key(font_xref, "DescendantFonts")
                if desc_val[0] != "null" and desc_val[1]:
                    # Parse indirect reference array
                    desc_text = desc_val[1].strip().strip("[]").strip()
                    ref_match = re.match(r'(\d+)\s+0\s+R', desc_text)
                    if ref_match:
                        child_xref = int(ref_match.group(1))
                        tounicode_val = doc.xref_get_key(child_xref, "ToUnicode")
                if tounicode_val[0] == "null" or not tounicode_val[1]:
                    return None

            # Extract the xref of the ToUnicode stream
            tu_text = tounicode_val[1].strip()
            if "0 R" in tu_text:
                tu_xref = int(tu_text.split()[0])
                return doc.xref_stream(tu_xref)
            return None
        except Exception as e:
            logger.debug(f"[CMAP] Failed to get ToUnicode for xref {font_xref}: {e}")
            return None

    @staticmethod
    def _hex_to_unicode_str(hex_str: str) -> str:
        """Convert a hex Unicode value string to a Python string.

        Handles:
        - Single char: "0041" → "A"
        - Multi-char (ligatures): "00660066" → "ff", "006600660069" → "ffi"
        - Surrogate pairs (emoji): "D83DDD82" → emoji character
        - Long icon names: "0048004F005500530045..." → "HOUSE..."
        """
        # Decode as UTF-16BE bytes — this handles everything:
        # single chars, multi-char sequences, and surrogate pairs
        try:
            raw_bytes = bytes.fromhex(hex_str)
            # Ensure even number of bytes for UTF-16BE
            if len(raw_bytes) % 2 != 0:
                raw_bytes = b'\x00' + raw_bytes
            return raw_bytes.decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            # Fallback: try as single codepoint
            try:
                val = int(hex_str, 16)
                if val <= 0x10FFFF:
                    return chr(val)
            except (ValueError, OverflowError):
                pass
            return "\ufffd"  # replacement character

    def _parse_tounicode(self, stream: bytes) -> Tuple[Dict[int, str], Dict[str, int], int]:
        """Parse CMap stream into forward (cid→char), reverse (char→cid), and byte_width.

        byte_width: 1 for TrueType single-byte encoding, 2 for CID fonts.
        Detected from the codespace range.

        Handles:
        - Standard single-char mappings: <CID> <Unicode>
        - Multi-char ligature mappings: <0B> <00660066> → "ff"
        - Surrogate pair emoji: <0243> <D83DDD82>
        - Long icon name mappings: <0091> <0048004F0055...>
        """
        text = stream.decode("latin-1", errors="replace")
        fwd: Dict[int, str] = {}

        # Detect byte width from codespace range
        # <00> <FF> = 1-byte, <0000> <FFFF> = 2-byte
        byte_width = 2  # default
        cs_match = re.search(r'begincodespacerange\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', text)
        if cs_match:
            start_hex = cs_match.group(1)
            byte_width = len(start_hex) // 2  # "00" → 1, "0000" → 2

        # Parse beginbfchar sections: individual character mappings
        in_bfchar = False
        for line in text.split("\n"):
            line = line.strip()
            if "beginbfchar" in line:
                in_bfchar = True
                continue
            if "endbfchar" in line:
                in_bfchar = False
                continue
            if in_bfchar:
                match = re.match(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', line)
                if match:
                    cid = int(match.group(1), 16)
                    unicode_str = self._hex_to_unicode_str(match.group(2))
                    fwd[cid] = unicode_str

        # Parse beginbfrange sections: range mappings
        in_bfrange = False
        for line in text.split("\n"):
            line = line.strip()
            if "beginbfrange" in line:
                in_bfrange = True
                continue
            if "endbfrange" in line:
                in_bfrange = False
                continue
            if in_bfrange:
                match = re.match(
                    r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', line
                )
                if match:
                    start_cid = int(match.group(1), 16)
                    end_cid = int(match.group(2), 16)
                    start_unicode_hex = match.group(3)
                    # For ranges, the start value is always a single char
                    # and we increment the last code point
                    try:
                        start_val = int(start_unicode_hex, 16)
                        for i in range(end_cid - start_cid + 1):
                            code = start_val + i
                            if code <= 0x10FFFF:
                                fwd[start_cid + i] = chr(code)
                    except (ValueError, OverflowError):
                        pass

        # Build reverse mapping (char/string → cid)
        # For multi-char mappings (ligatures), include them in reverse too
        rev: Dict[str, int] = {v: k for k, v in fwd.items()}
        return fwd, rev, byte_width

    def decode_hex(self, font_tag: str, hex_string: str) -> str:
        """Decode hex CID string to Unicode text."""
        font_data = self.font_cmaps.get(font_tag, {})
        cmap = font_data.get("fwd", {})
        if not cmap:
            return ""
        byte_width = font_data.get("byte_width", 2)
        hex_chars = byte_width * 2  # 1 byte = 2 hex chars, 2 bytes = 4 hex chars
        chars = []
        for i in range(0, len(hex_string), hex_chars):
            if i + hex_chars > len(hex_string):
                break
            cid = int(hex_string[i:i + hex_chars], 16)
            ch = cmap.get(cid)
            if ch:
                chars.append(ch)
            else:
                chars.append("\ufffd")  # replacement character
        return "".join(chars)

    def encode_text(self, font_tag: str, text: str) -> Tuple[str, List[str]]:
        """Encode Unicode text to hex CID string. Returns (hex_string, missing_chars)."""
        font_data = self.font_cmaps.get(font_tag, {})
        rev = font_data.get("rev", {})
        if not rev:
            return "", list(text)
        byte_width = font_data.get("byte_width", 2)
        hex_chars = byte_width * 2  # 1 byte = 2 hex chars, 2 bytes = 4 hex chars
        hex_parts = []
        missing = []
        for ch in text:
            cid = rev.get(ch)
            if cid is not None:
                hex_parts.append(f"{cid:0{hex_chars}X}")
            else:
                missing.append(ch)
        return "".join(hex_parts), missing

    def has_char(self, font_tag: str, ch: str) -> bool:
        """Check if a character is in the font's CMap."""
        rev = self.font_cmaps.get(font_tag, {}).get("rev", {})
        return ch in rev

    def add_mapping(self, font_tag: str, char: str, cid: int):
        """Add a new character mapping (used after font augmentation)."""
        if font_tag not in self.font_cmaps:
            self.font_cmaps[font_tag] = {"fwd": {}, "rev": {}, "byte_width": 2}
        self.font_cmaps[font_tag]["fwd"][cid] = char
        self.font_cmaps[font_tag]["rev"][char] = cid

    def get_byte_width(self, font_tag: str) -> int:
        """Get the byte width for a font (1 for TrueType, 2 for CID)."""
        return self.font_cmaps.get(font_tag, {}).get("byte_width", 2)


def _literal_to_hex(raw_bytes: bytes) -> str:
    """Convert raw literal string bytes to hex string for uniform handling.

    Handles PDF literal string escapes:
    - \\n, \\r, \\t, \\b, \\f, \\(, \\), \\\\
    - \\NNN (octal escape, 1-3 digits)
    - Line continuation (backslash + newline)

    Returns hex string where each byte is 2 hex chars (1-byte CID encoding).
    """
    result = []
    i = 0
    while i < len(raw_bytes):
        b = raw_bytes[i]
        if b == 0x5C:  # backslash
            i += 1
            if i >= len(raw_bytes):
                break
            esc = raw_bytes[i]
            if esc == 0x6E:  # \n
                result.append(0x0A)
            elif esc == 0x72:  # \r
                result.append(0x0D)
            elif esc == 0x74:  # \t
                result.append(0x09)
            elif esc == 0x62:  # \b
                result.append(0x08)
            elif esc == 0x66:  # \f
                result.append(0x0C)
            elif esc == 0x28:  # \(
                result.append(0x28)
            elif esc == 0x29:  # \)
                result.append(0x29)
            elif esc == 0x5C:  # \\
                result.append(0x5C)
            elif 0x30 <= esc <= 0x37:  # octal digit
                # Read up to 3 octal digits
                octal = chr(esc)
                for _ in range(2):
                    if i + 1 < len(raw_bytes) and 0x30 <= raw_bytes[i + 1] <= 0x37:
                        i += 1
                        octal += chr(raw_bytes[i])
                    else:
                        break
                result.append(int(octal, 8) & 0xFF)
            elif esc in (0x0A, 0x0D):  # line continuation
                # Skip \r\n or \n or \r
                if esc == 0x0D and i + 1 < len(raw_bytes) and raw_bytes[i + 1] == 0x0A:
                    i += 1
                # Don't add any byte — this is a line continuation
            else:
                result.append(esc)  # Unknown escape, use as-is
            i += 1
        else:
            result.append(b)
            i += 1
    return "".join(f"{b:02X}" for b in result)


def _hex_to_literal(hex_string: str) -> bytes:
    """Convert hex string back to PDF literal string bytes.

    Returns the bytes that go between ( and ) in a PDF literal string.
    Escapes special characters: (, ), \\, and non-printable bytes.
    """
    raw = bytes.fromhex(hex_string)
    result = bytearray()
    for b in raw:
        if b == 0x28:  # (
            result.extend(b"\\(")
        elif b == 0x29:  # )
            result.extend(b"\\)")
        elif b == 0x5C:  # \
            result.extend(b"\\\\")
        elif b < 0x20 or b > 0x7E:
            # Non-printable: use octal escape
            result.extend(f"\\{b:03o}".encode("ascii"))
        else:
            result.append(b)
    return bytes(result)


def _parse_content_stream(
    stream_bytes: bytes,
    cmap_mgr: _CMapManager,
    page_num: int,
    stream_xref: int,
) -> List[ContentBlock]:
    """Parse raw content stream bytes into structured ContentBlock objects.

    Scans for BT/ET blocks, tracks font state (Tf), position (Tm/Td),
    and extracts text operations (Tj/TJ) with hex strings and byte offsets.
    """
    if not stream_bytes:
        return []

    try:
        return _parse_content_stream_inner(stream_bytes, cmap_mgr, page_num, stream_xref)
    except Exception as e:
        logger.warning(f"[PARSE] Content stream parse failed for xref {stream_xref} page {page_num}: {e}")
        return []


def _parse_content_stream_inner(
    stream_bytes: bytes,
    cmap_mgr: _CMapManager,
    page_num: int,
    stream_xref: int,
) -> List[ContentBlock]:
    """Inner implementation of content stream parser."""
    text = stream_bytes.decode("latin-1", errors="replace")
    blocks: List[ContentBlock] = []

    # State tracking
    in_bt = False
    current_font = ""
    current_size = 0.0
    # Text matrix components (Tm sets absolute, Td adds relative)
    tx, ty = 0.0, 0.0
    text_ops: List[TextOp] = []
    bt_offset = 0

    # CTM (Current Transformation Matrix) tracking — full 6-element [a, b, c, d, e, f]
    # Maps text-space coordinates to absolute page coordinates via:
    #   abs_x = ctm_a * tx + ctm_c * ty + ctm_e
    #   abs_y = ctm_b * tx + ctm_d * ty + ctm_f
    # This prevents blocks at different visual locations from sharing the same (x, y)
    # when the PDF uses cm operators with scaling + translation (common in resume PDFs).
    ctm_a, ctm_b, ctm_c, ctm_d, ctm_e, ctm_f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
    # Graphics state stack for q/Q save/restore
    gstate_stack: List[Tuple[float, float, float, float, float, float]] = []

    # We need to track positions in the original byte stream for patching
    pos = 0
    length = len(text)

    while pos < length:
        # Skip whitespace
        while pos < length and text[pos] in " \t\r\n":
            pos += 1
        if pos >= length:
            break

        # Check for q (save graphics state)
        if not in_bt and text[pos] == "q" and (pos + 1 >= length or text[pos + 1] in " \t\r\n"):
            gstate_stack.append((ctm_a, ctm_b, ctm_c, ctm_d, ctm_e, ctm_f))
            pos += 1
            continue

        # Check for Q (restore graphics state)
        if not in_bt and text[pos] == "Q" and (pos + 1 >= length or text[pos + 1] in " \t\r\n"):
            if gstate_stack:
                ctm_a, ctm_b, ctm_c, ctm_d, ctm_e, ctm_f = gstate_stack.pop()
            pos += 1
            continue

        # Check for BT (begin text)
        if text[pos:pos + 2] == "BT" and (pos + 2 >= length or text[pos + 2] in " \t\r\n"):
            in_bt = True
            bt_offset = pos
            text_ops = []
            current_font = ""
            current_size = 0.0
            tx, ty = 0.0, 0.0
            pos += 2
            continue

        # Check for ET (end text)
        if text[pos:pos + 2] == "ET" and (pos + 2 >= length or text[pos + 2] in " \t\r\n"):
            if in_bt and text_ops and current_font:
                # Transform text-space (tx, ty) to absolute page coordinates via CTM
                abs_x = ctm_a * tx + ctm_c * ty + ctm_e
                abs_y = ctm_b * tx + ctm_d * ty + ctm_f
                blocks.append(ContentBlock(
                    font_tag=current_font,
                    font_size=current_size,
                    x=abs_x,
                    y=abs_y,
                    text_ops=list(text_ops),
                    stream_xref=stream_xref,
                    page_num=page_num,
                ))
            in_bt = False
            pos += 2
            continue

        if not in_bt:
            # Outside BT/ET — we need to parse cm operators for CTM tracking.
            # cm is preceded by 6 numbers: "1 0 0 -1 0 792 cm"
            if text[pos] in "-0123456789.":
                # Collect numbers (potential cm operands)
                _nums: List[float] = []
                _scan = pos
                while _scan < length:
                    while _scan < length and text[_scan] in " \t\r\n":
                        _scan += 1
                    if _scan >= length or text[_scan] not in "-0123456789.":
                        break
                    num_start = _scan
                    if text[_scan] == "-":
                        _scan += 1
                    while _scan < length and text[_scan] in "0123456789.":
                        _scan += 1
                    try:
                        _nums.append(float(text[num_start:_scan]))
                    except ValueError:
                        break
                    if _scan >= length:
                        break
                    if text[_scan] not in " \t\r\n" and text[_scan] not in "-0123456789.":
                        break
                # Check if cm follows
                while _scan < length and text[_scan] in " \t\r\n":
                    _scan += 1
                if len(_nums) >= 6 and _scan + 1 < length and text[_scan:_scan + 2] == "cm":
                    ma, mb, mc, md, me, mf = _nums[-6], _nums[-5], _nums[-4], _nums[-3], _nums[-2], _nums[-1]
                    new_a = ctm_a * ma + ctm_b * mc
                    new_b = ctm_a * mb + ctm_b * md
                    new_c = ctm_c * ma + ctm_d * mc
                    new_d = ctm_c * mb + ctm_d * md
                    new_e = ctm_e * ma + ctm_f * mc + me
                    new_f = ctm_e * mb + ctm_f * md + mf
                    ctm_a, ctm_b, ctm_c, ctm_d, ctm_e, ctm_f = new_a, new_b, new_c, new_d, new_e, new_f
                    pos = _scan + 2
                    continue
                # Not a cm operator — skip past the numbers
                pos = _scan if _scan > pos else pos + 1
                continue
            # Skip non-numeric tokens outside BT
            pos += 1
            continue

        # Inside BT/ET block — parse operators

        # Check for hex string <...> (CID/Type0/TrueType fonts)
        if text[pos] == "<" and pos + 1 < length and text[pos + 1] != "<":
            hex_start = pos
            end = text.find(">", pos + 1)
            if end == -1:
                pos += 1
                continue
            hex_content = text[pos + 1:end].replace(" ", "").replace("\n", "").replace("\r", "")
            hex_byte_offset = hex_start  # offset of '<' in stream
            hex_byte_length = end - hex_start + 1  # length including < and >
            pos = end + 1

            # Skip whitespace after hex string
            while pos < length and text[pos] in " \t\r\n":
                pos += 1

            # Check for Tj operator
            if pos < length and text[pos:pos + 2] == "Tj":
                decoded = cmap_mgr.decode_hex(current_font, hex_content)
                text_ops.append(TextOp(
                    hex_string=hex_content,
                    decoded_text=decoded,
                    byte_offset=hex_byte_offset,
                    byte_length=hex_byte_length,
                    operator="Tj",
                ))
                pos += 2
            # If not followed by Tj, it might be part of a TJ array — handled below
            continue

        # Check for literal string (...) (Type1 fonts)
        if text[pos] == "(":
            str_start = pos
            pos += 1
            depth = 1
            # Parse literal string with balanced parentheses and backslash escapes
            while pos < length and depth > 0:
                ch = text[pos]
                if ch == "\\":
                    pos += 2  # skip escape sequence
                    continue
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                pos += 1
            # pos is now after the closing ')'
            str_end = pos
            # Convert the literal string bytes to hex for uniform handling
            # The raw bytes between '(' and ')' are the character codes
            raw_literal = stream_bytes[str_start + 1:str_end - 1]
            hex_content = _literal_to_hex(raw_literal)
            hex_byte_offset = str_start  # offset of '(' in stream
            hex_byte_length = str_end - str_start  # length including ( and )

            # Skip whitespace
            while pos < length and text[pos] in " \t\r\n":
                pos += 1

            # Check for Tj operator
            if pos < length and text[pos:pos + 2] == "Tj":
                decoded = cmap_mgr.decode_hex(current_font, hex_content)
                text_ops.append(TextOp(
                    hex_string=hex_content,
                    decoded_text=decoded,
                    byte_offset=hex_byte_offset,
                    byte_length=hex_byte_length,
                    operator="Tj",
                    is_literal=True,
                ))
                pos += 2
            continue

        # Check for '[' (TJ array start)
        if text[pos] == "[":
            array_start = pos
            pos += 1
            # Parse TJ array contents until ']'
            tj_ops = []
            pending_space = False  # Track if a large kerning gap means a word break
            while pos < length and text[pos] != "]":
                # Skip whitespace
                while pos < length and text[pos] in " \t\r\n":
                    pos += 1
                if pos >= length or text[pos] == "]":
                    break

                # Hex string in TJ array
                if text[pos] == "<":
                    hex_start = pos
                    end = text.find(">", pos + 1)
                    if end == -1:
                        pos += 1
                        continue
                    hex_content = text[pos + 1:end].replace(" ", "").replace("\n", "").replace("\r", "")
                    hex_byte_offset = hex_start
                    hex_byte_length = end - hex_start + 1
                    decoded = cmap_mgr.decode_hex(current_font, hex_content)
                    if pending_space and decoded:
                        decoded = " " + decoded
                        pending_space = False
                    tj_ops.append(TextOp(
                        hex_string=hex_content,
                        decoded_text=decoded,
                        byte_offset=hex_byte_offset,
                        byte_length=hex_byte_length,
                        operator="TJ",
                        tj_array_start=array_start,
                    ))
                    pos = end + 1
                # Literal string in TJ array (Type1 fonts)
                elif text[pos] == "(":
                    str_start = pos
                    pos += 1
                    depth = 1
                    while pos < length and depth > 0:
                        ch = text[pos]
                        if ch == "\\":
                            pos += 2
                            continue
                        elif ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                        pos += 1
                    str_end = pos
                    raw_literal = stream_bytes[str_start + 1:str_end - 1]
                    hex_content = _literal_to_hex(raw_literal)
                    hex_byte_offset = str_start
                    hex_byte_length = str_end - str_start
                    decoded = cmap_mgr.decode_hex(current_font, hex_content)
                    if pending_space and decoded:
                        decoded = " " + decoded
                        pending_space = False
                    tj_ops.append(TextOp(
                        hex_string=hex_content,
                        decoded_text=decoded,
                        byte_offset=hex_byte_offset,
                        byte_length=hex_byte_length,
                        operator="TJ",
                        is_literal=True,
                        tj_array_start=array_start,
                    ))
                elif text[pos] in "-0123456789.":
                    # Read the kerning value
                    kern_start = pos
                    while pos < length and text[pos] not in " \t\r\n<(]":
                        pos += 1
                    try:
                        kern_val = float(text[kern_start:pos])
                        # Large negative kerning (< -100) typically indicates a word space
                        # In TJ arrays, kerning is in 1/1000 of text space units
                        if kern_val < -100:
                            pending_space = True
                    except ValueError:
                        pass
                else:
                    pos += 1

            if pos < length and text[pos] == "]":
                pos += 1
            # Skip whitespace after ']'
            while pos < length and text[pos] in " \t\r\n":
                pos += 1
            # Check for TJ operator
            if pos + 1 < length and text[pos:pos + 2] == "TJ":
                text_ops.extend(tj_ops)
                pos += 2
            continue

        # Check for Tf (set font)
        # Pattern: /FontTag Size Tf
        if text[pos] == "/":
            # Read font tag
            tag_start = pos + 1
            tag_end = tag_start
            while tag_end < length and text[tag_end] not in " \t\r\n":
                tag_end += 1
            font_tag = text[tag_start:tag_end]
            pos = tag_end

            # Skip whitespace
            while pos < length and text[pos] in " \t\r\n":
                pos += 1

            # Try to read font size number
            num_start = pos
            while pos < length and text[pos] in "-0123456789.":
                pos += 1
            if pos > num_start:
                try:
                    size_val = float(text[num_start:pos])
                except ValueError:
                    size_val = 0.0

                # Skip whitespace
                while pos < length and text[pos] in " \t\r\n":
                    pos += 1

                # Check for Tf
                if pos + 1 < length and text[pos:pos + 2] == "Tf":
                    # If font changes mid-BT/ET and we have accumulated text ops,
                    # save the current block and start a new one.
                    # This is critical for LaTeX/Type1 PDFs where a single BT/ET
                    # block contains text in multiple fonts.
                    if font_tag != current_font and text_ops and current_font:
                        blocks.append(ContentBlock(
                            font_tag=current_font,
                            font_size=current_size,
                            x=tx,
                            y=ty,
                            text_ops=list(text_ops),
                            stream_xref=stream_xref,
                            page_num=page_num,
                        ))
                        text_ops = []
                    current_font = font_tag
                    current_size = abs(size_val)
                    pos += 2
            continue

        # Check for Tm (set text matrix) — 6 numbers followed by "Tm"
        # Check for Td (relative move) — 2 numbers followed by "Td"
        # We need to look ahead for number sequences
        if text[pos] in "-0123456789.":
            # Collect numbers
            nums = []
            scan_pos = pos
            while True:
                # Read a number
                num_start = scan_pos
                while scan_pos < length and text[scan_pos] in "-0123456789.":
                    scan_pos += 1
                if scan_pos > num_start:
                    try:
                        nums.append(float(text[num_start:scan_pos]))
                    except ValueError:
                        break
                else:
                    break
                # Skip whitespace
                while scan_pos < length and text[scan_pos] in " \t\r\n":
                    scan_pos += 1
                # Check if next is an operator or another number
                if scan_pos >= length:
                    break
                if text[scan_pos] not in "-0123456789.":
                    break

            # Now check what operator follows
            if scan_pos < length:
                # Check for Tm (6 numbers)
                if len(nums) >= 6 and scan_pos + 1 < length and text[scan_pos:scan_pos + 2] == "Tm":
                    # Flush current block before position change
                    if text_ops and current_font:
                        abs_x = ctm_a * tx + ctm_c * ty + ctm_e
                        abs_y = ctm_b * tx + ctm_d * ty + ctm_f
                        blocks.append(ContentBlock(
                            font_tag=current_font,
                            font_size=current_size,
                            x=abs_x,
                            y=abs_y,
                            text_ops=list(text_ops),
                            stream_xref=stream_xref,
                            page_num=page_num,
                        ))
                        text_ops = []
                    # Tm sets text matrix: a b c d tx ty
                    tx = nums[4]
                    ty = nums[5]
                    pos = scan_pos + 2
                    continue
                # Check for Td (2 numbers)
                elif len(nums) >= 2 and scan_pos + 1 < length and text[scan_pos:scan_pos + 2] == "Td":
                    # Flush current block before position change
                    if text_ops and current_font:
                        abs_x = ctm_a * tx + ctm_c * ty + ctm_e
                        abs_y = ctm_b * tx + ctm_d * ty + ctm_f
                        blocks.append(ContentBlock(
                            font_tag=current_font,
                            font_size=current_size,
                            x=abs_x,
                            y=abs_y,
                            text_ops=list(text_ops),
                            stream_xref=stream_xref,
                            page_num=page_num,
                        ))
                        text_ops = []
                    tx += nums[0]
                    ty += nums[1]
                    pos = scan_pos + 2
                    continue
                # Check for TD (2 numbers, like Td but also sets leading)
                elif len(nums) >= 2 and scan_pos + 1 < length and text[scan_pos:scan_pos + 2] == "TD":
                    if text_ops and current_font:
                        abs_x = ctm_a * tx + ctm_c * ty + ctm_e
                        abs_y = ctm_b * tx + ctm_d * ty + ctm_f
                        blocks.append(ContentBlock(
                            font_tag=current_font,
                            font_size=current_size,
                            x=abs_x,
                            y=abs_y,
                            text_ops=list(text_ops),
                            stream_xref=stream_xref,
                            page_num=page_num,
                        ))
                        text_ops = []
                    tx += nums[0]
                    ty += nums[1]
                    pos = scan_pos + 2
                    continue
                # (cm is now handled outside BT/ET in the not-in_bt section above)

            # Not a recognized pattern, skip ahead
            pos = scan_pos if scan_pos > pos else pos + 1
            continue

        # Skip other tokens
        pos += 1

    return blocks


class _WidthCalculator:
    """Calculates exact text widths from CIDFont W arrays."""

    def __init__(self, doc):
        # font_tag → {cid: width_in_font_units}
        self.font_widths: Dict[str, Dict[int, float]] = {}
        self._default_widths: Dict[str, float] = {}  # font_tag → DW value
        self._extract_all_widths(doc)

    def _extract_all_widths(self, doc):
        """Extract W arrays from all CIDFont dictionaries in the document."""
        seen_xrefs = set()
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            for f in page.get_fonts():
                xref = f[0]
                name = f[4]  # font tag like "F5"
                if not name or xref in seen_xrefs or xref == 0:
                    continue
                seen_xrefs.add(xref)

                try:
                    self._extract_font_widths(doc, xref, name)
                except Exception as e:
                    logger.debug(f"[WIDTH] Failed to extract widths for {name} (xref {xref}): {e}")

    def _extract_font_widths(self, doc, font_xref: int, font_tag: str):
        """Extract width info from either Type0/CID fonts or TrueType fonts."""
        # Check font subtype to determine width extraction method
        subtype_val = doc.xref_get_key(font_xref, "Subtype")
        subtype = subtype_val[1].strip().strip("/") if subtype_val[0] != "null" else ""

        if subtype in ("TrueType", "Type1"):
            # Both TrueType and Type1 use /Widths array + /FirstChar
            self._extract_truetype_widths(doc, font_xref, font_tag)
        else:
            self._extract_type0_widths(doc, font_xref, font_tag)

    def _extract_truetype_widths(self, doc, font_xref: int, font_tag: str):
        """Extract widths from a TrueType or Type1 font (/Widths array + /FirstChar)."""
        # Get FirstChar
        first_char_val = doc.xref_get_key(font_xref, "FirstChar")
        if first_char_val[0] == "null":
            return
        first_char = int(first_char_val[1])

        # Get Widths array
        widths_val = doc.xref_get_key(font_xref, "Widths")
        if widths_val[0] == "null" or not widths_val[1]:
            return

        # Resolve indirect reference: "31 0 R" → fetch actual array
        w_text = widths_val[1].strip()
        if widths_val[0] == "xref":
            ref_m = re.match(r'(\d+)\s+0\s+R', w_text)
            if ref_m:
                w_xref = int(ref_m.group(1))
                try:
                    w_text = doc.xref_object(w_xref).strip()
                except Exception:
                    return

        # Parse the widths array: [w0 w1 w2 ...]
        if w_text.startswith("["):
            w_text = w_text[1:]
        if w_text.endswith("]"):
            w_text = w_text[:-1]

        widths: Dict[int, float] = {}
        for i, part in enumerate(w_text.split()):
            try:
                widths[first_char + i] = float(part)
            except ValueError:
                continue

        self.font_widths[font_tag] = widths
        self._default_widths[font_tag] = 500.0
        logger.info(f"[WIDTH] Font {font_tag} (TrueType/Type1): {len(widths)} width entries")

    def _extract_type0_widths(self, doc, font_xref: int, font_tag: str):
        """Extract W array and DW from a Type0/CID font."""
        # For Type0 fonts, widths are in DescendantFonts[0]
        desc_val = doc.xref_get_key(font_xref, "DescendantFonts")
        if desc_val[0] == "null" or not desc_val[1]:
            return

        # Parse the DescendantFonts reference to get CIDFont xref
        desc_text = desc_val[1].strip().strip("[]").strip()
        ref_match = re.match(r'(\d+)\s+0\s+R', desc_text)
        if not ref_match:
            return
        cidfont_xref = int(ref_match.group(1))

        # Get DW (default width)
        dw_val = doc.xref_get_key(cidfont_xref, "DW")
        default_width = 1000.0  # PDF spec default
        if dw_val[0] != "null" and dw_val[1]:
            try:
                default_width = float(dw_val[1])
            except ValueError:
                pass
        self._default_widths[font_tag] = default_width

        # Get W array (may be inline or an indirect reference)
        w_val = doc.xref_get_key(cidfont_xref, "W")
        if w_val[0] == "null" or not w_val[1]:
            return

        widths: Dict[int, float] = {}
        w_text = w_val[1].strip()

        # Handle indirect reference: "60 0 R" → resolve via xref_object
        if w_val[0] == "xref":
            ref_m = re.match(r'(\d+)\s+0\s+R', w_text)
            if ref_m:
                w_xref = int(ref_m.group(1))
                try:
                    w_text = doc.xref_object(w_xref).strip()
                except Exception:
                    return

        # Parse W array: [CID [w1 w2 ...] CID [w1 w2 ...] ...]
        # or: [CID1 CID2 width] for ranges with same width
        tokens = self._tokenize_w_array(w_text)
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if isinstance(token, (int, float)):
                start_cid = int(token)
                i += 1
                if i >= len(tokens):
                    break
                next_token = tokens[i]
                if isinstance(next_token, list):
                    # Format: CID [w1 w2 w3 ...]
                    for j, w in enumerate(next_token):
                        widths[start_cid + j] = float(w)
                    i += 1
                elif isinstance(next_token, (int, float)):
                    # Format: CID1 CID2 width
                    end_cid = int(next_token)
                    i += 1
                    if i < len(tokens) and isinstance(tokens[i], (int, float)):
                        w = float(tokens[i])
                        for cid in range(start_cid, end_cid + 1):
                            widths[cid] = w
                        i += 1
            else:
                i += 1

        self.font_widths[font_tag] = widths
        logger.info(f"[WIDTH] Font {font_tag}: {len(widths)} width entries, DW={default_width}")

    def _tokenize_w_array(self, text: str) -> list:
        """Tokenize a W array string into numbers and sub-arrays."""
        tokens = []
        pos = 0
        text = text.strip()
        if text.startswith("["):
            text = text[1:]
        if text.endswith("]"):
            text = text[:-1]
        length = len(text)

        while pos < length:
            while pos < length and text[pos] in " \t\r\n":
                pos += 1
            if pos >= length:
                break

            if text[pos] == "[":
                # Sub-array
                end = text.find("]", pos)
                if end == -1:
                    break
                sub_text = text[pos + 1:end]
                sub_nums = []
                for part in sub_text.split():
                    try:
                        sub_nums.append(float(part))
                    except ValueError:
                        continue
                tokens.append(sub_nums)
                pos = end + 1
            elif text[pos] in "-0123456789.":
                num_start = pos
                while pos < length and text[pos] not in " \t\r\n[]":
                    pos += 1
                try:
                    tokens.append(float(text[num_start:pos]))
                except ValueError:
                    pass
            else:
                pos += 1

        return tokens

    def text_width_from_hex(
        self, font_tag: str, hex_string: str, font_size: float,
        byte_width: int = 2,
    ) -> float:
        """Calculate rendered width of hex-encoded CID text at given font size.

        Args:
            byte_width: 1 for TrueType/Type1 (2 hex chars per CID),
                        2 for Type0/CID (4 hex chars per CID).
        """
        widths = self.font_widths.get(font_tag, {})
        default_w = self._default_widths.get(font_tag, 1000.0)
        hex_per_char = byte_width * 2  # 2 or 4 hex chars
        total = 0.0
        for i in range(0, len(hex_string), hex_per_char):
            if i + hex_per_char > len(hex_string):
                break
            cid = int(hex_string[i:i + hex_per_char], 16)
            w = widths.get(cid, default_w)
            total += w
        return total * font_size / 1000.0


class _FontAugmentor:
    """Handles missing characters by loading system fonts and creating new CMap entries."""

    # Cross-platform font paths: {font_name: [(platform, path), ...]}
    _FONT_SEARCH_PATHS = {
        "TimesNewRomanPSMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/times.ttf"),
            ("darwin", "/Library/Fonts/Times New Roman.ttf"),
            ("win32", "C:\\Windows\\Fonts\\times.ttf"),
        ],
        "TimesNewRomanPS-BoldMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/timesbd.ttf"),
            ("darwin", "/Library/Fonts/Times New Roman Bold.ttf"),
            ("win32", "C:\\Windows\\Fonts\\timesbd.ttf"),
        ],
        "TimesNewRomanPS-ItalicMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/timesi.ttf"),
            ("darwin", "/Library/Fonts/Times New Roman Italic.ttf"),
            ("win32", "C:\\Windows\\Fonts\\timesi.ttf"),
        ],
        "TimesNewRomanPS-BoldItalicMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/timesbi.ttf"),
            ("darwin", "/Library/Fonts/Times New Roman Bold Italic.ttf"),
            ("win32", "C:\\Windows\\Fonts\\timesbi.ttf"),
        ],
        "ArialMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/arial.ttf"),
            ("darwin", "/Library/Fonts/Arial.ttf"),
            ("win32", "C:\\Windows\\Fonts\\arial.ttf"),
        ],
        "Arial-BoldMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf"),
            ("darwin", "/Library/Fonts/Arial Bold.ttf"),
            ("win32", "C:\\Windows\\Fonts\\arialbd.ttf"),
        ],
        "Arial-ItalicMT": [
            ("linux", "/usr/share/fonts/truetype/msttcorefonts/ariali.ttf"),
            ("darwin", "/Library/Fonts/Arial Italic.ttf"),
            ("win32", "C:\\Windows\\Fonts\\ariali.ttf"),
        ],
        "Lato-Regular": [
            ("linux", "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"),
            ("darwin", "/Library/Fonts/Lato-Regular.ttf"),
        ],
        "Lato-Bold": [
            ("linux", "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"),
            ("darwin", "/Library/Fonts/Lato-Bold.ttf"),
        ],
    }

    # Mapping from common PDF font names to system font keys
    FONT_ALIASES = {
        "calibri": "Lato-Regular",
        "calibri-bold": "Lato-Bold",
        "cambria": "TimesNewRomanPSMT",
        "cambria-bold": "TimesNewRomanPS-BoldMT",
        "garamond": "TimesNewRomanPSMT",
    }

    def __init__(self):
        self._system_font_cache: Dict[str, Any] = {}  # path → TTFont
        self._platform = sys.platform
        # Build resolved SYSTEM_FONTS dict for this platform
        self.SYSTEM_FONTS = self._resolve_platform_fonts()

    def _resolve_platform_fonts(self) -> Dict[str, str]:
        """Resolve font paths for the current platform."""
        import sys
        platform = sys.platform
        resolved: Dict[str, str] = {}
        for font_name, paths in self._FONT_SEARCH_PATHS.items():
            for plat, path in paths:
                if platform.startswith(plat) and os.path.exists(path):
                    resolved[font_name] = path
                    break
            # If platform-specific path not found, try all paths
            if font_name not in resolved:
                for _, path in paths:
                    if os.path.exists(path):
                        resolved[font_name] = path
                        break
        return resolved

    def resolve_missing_chars(
        self,
        doc,
        page,
        font_tag: str,
        font_name: str,
        missing_chars: List[str],
        cmap_mgr: _CMapManager,
        width_calc: _WidthCalculator,
    ) -> bool:
        """
        Resolve missing characters by finding them in the system font and
        adding CMap entries. Updates cmap_mgr and width_calc in place.

        Returns True if all missing chars were resolved.
        """
        if not missing_chars:
            return True

        # Deduplicate and skip chars already in CMap
        unique_chars = []
        seen = set()
        rev = cmap_mgr.font_cmaps.get(font_tag, {}).get("rev", {})
        for ch in missing_chars:
            if ch not in seen and ch not in rev:
                unique_chars.append(ch)
                seen.add(ch)
        if not unique_chars:
            return True

        system_font = self._load_system_font(font_name)
        if not system_font:
            logger.warning(f"[FONT_AUG] No system font found for '{font_name}'")
            return False

        try:
            from fontTools.ttLib import TTFont
            cmap_table = system_font.getBestCmap()
            if not cmap_table:
                logger.warning(f"[FONT_AUG] System font has no cmap table")
                return False

            # Get existing CMap to find unused CID range
            existing_fwd = cmap_mgr.font_cmaps.get(font_tag, {}).get("fwd", {})
            max_existing_cid = max(existing_fwd.keys()) if existing_fwd else 100

            # Get the hmtx table for widths
            hmtx = system_font.get("hmtx")
            glyf_order = system_font.getGlyphOrder()

            # Build glyph_name → gid (int) mapping
            name_to_gid = {name: idx for idx, name in enumerate(glyf_order)}

            all_resolved = True
            for ch in unique_chars:
                code_point = ord(ch)
                glyph_name = cmap_table.get(code_point)
                if glyph_name is None:
                    logger.warning(f"[FONT_AUG] Char '{ch}' (U+{code_point:04X}) not in system font")
                    all_resolved = False
                    continue

                # Convert glyph name to numeric GID
                gid = name_to_gid.get(glyph_name, -1)
                if gid < 0:
                    logger.warning(f"[FONT_AUG] Glyph '{glyph_name}' for '{ch}' has no GID")
                    all_resolved = False
                    continue

                # Assign a new CID (use the GID from system font if possible,
                # otherwise use max_existing + 1)
                new_cid = gid if gid not in existing_fwd else max_existing_cid + 1
                max_existing_cid = max(max_existing_cid, new_cid)

                # Add to CMap manager
                cmap_mgr.add_mapping(font_tag, ch, new_cid)

                # Get width from system font
                if hmtx:
                    try:
                        advance_width = hmtx[glyph_name][0]  # (width, lsb)
                    except (KeyError, IndexError):
                        advance_width = 500
                    # Add to width calculator
                    if font_tag not in width_calc.font_widths:
                        width_calc.font_widths[font_tag] = {}
                    width_calc.font_widths[font_tag][new_cid] = float(advance_width)

                logger.info(
                    f"[FONT_AUG] Mapped '{ch}' (U+{code_point:04X}) → CID {new_cid} "
                    f"in font {font_tag}"
                )

            return all_resolved

        except ImportError:
            logger.warning("[FONT_AUG] fontTools not available, cannot augment fonts")
            return False
        except Exception as e:
            logger.warning(f"[FONT_AUG] Font augmentation failed: {e}")
            return False

    def _load_system_font(self, font_name: str) -> Optional[Any]:
        """Load a system font matching the given PDF font name."""
        # Direct match
        path = self.SYSTEM_FONTS.get(font_name)

        # Try alias match
        if not path:
            name_lower = font_name.lower()
            for alias, key in self.FONT_ALIASES.items():
                if alias in name_lower:
                    path = self.SYSTEM_FONTS.get(key)
                    break

        # Try fuzzy match
        if not path:
            name_lower = font_name.lower()
            for sys_name, sys_path in self.SYSTEM_FONTS.items():
                if sys_name.lower() in name_lower or name_lower in sys_name.lower():
                    path = sys_path
                    break

        # Fallback: try any sans-serif or serif font as generic fallback
        if not path:
            name_lower = font_name.lower()
            is_serif = any(k in name_lower for k in ("serif", "roman", "garamond", "cambria", "georgia", "book"))
            # Pick the best available fallback from resolved fonts
            if is_serif:
                path = self.SYSTEM_FONTS.get("TimesNewRomanPSMT")
            if not path:
                path = self.SYSTEM_FONTS.get("Lato-Regular") or self.SYSTEM_FONTS.get("ArialMT")
            if not path:
                # Last resort: try to find any resolved font
                for v in self.SYSTEM_FONTS.values():
                    if os.path.exists(v):
                        path = v
                        break

        if not path or not os.path.exists(path):
            return None

        if path in self._system_font_cache:
            return self._system_font_cache[path]

        try:
            from fontTools.ttLib import TTFont
            font = TTFont(path)
            self._system_font_cache[path] = font
            return font
        except Exception as e:
            logger.warning(f"[FONT_AUG] Failed to load system font {path}: {e}")
            return None


def _update_truetype_widths(doc, font_xref: int, new_widths: Dict[int, float]) -> None:
    """
    Update /Widths, /FirstChar, /LastChar for a simple TrueType font.

    Simple TrueType fonts store widths as:
        /FirstChar N  /LastChar M  /Widths [w0 w1 ... w(M-N)]
    where /Widths[i] is the width for CID (FirstChar + i).

    To add new CIDs beyond LastChar, we extend the array with zeros for gaps
    and set the new widths at the correct positions.
    """
    if not new_widths:
        return

    try:
        fc_val = doc.xref_get_key(font_xref, "FirstChar")
        lc_val = doc.xref_get_key(font_xref, "LastChar")
        w_val = doc.xref_get_key(font_xref, "Widths")

        if fc_val[0] == "null" or lc_val[0] == "null" or w_val[0] == "null":
            logger.debug("[FONT_AUG] TrueType font missing FirstChar/LastChar/Widths")
            return

        first_char = int(fc_val[1].strip())
        last_char = int(lc_val[1].strip())

        # Parse existing widths array
        w_text = w_val[1].strip()
        # Resolve indirect reference
        if w_val[0] == "xref":
            ref_m = re.match(r'(\d+)\s+0\s+R', w_text)
            if ref_m:
                w_indirect_xref = int(ref_m.group(1))
                w_text = doc.xref_object(w_indirect_xref).strip()

        # Parse the array: "[w0 w1 w2 ...]"
        inner = w_text.strip("[]").strip()
        existing_widths = [float(x) for x in inner.split()] if inner else []

        # Find new max CID
        max_new_cid = max(new_widths.keys())
        new_last_char = max(last_char, max_new_cid)

        # Extend widths array to cover all CIDs up to new_last_char
        needed_len = new_last_char - first_char + 1
        while len(existing_widths) < needed_len:
            existing_widths.append(0)

        # Set new widths
        for cid, width in new_widths.items():
            idx = cid - first_char
            if 0 <= idx < len(existing_widths):
                existing_widths[idx] = width

        # Write back
        new_w_text = "[" + " ".join(f"{w:.5f}" if w != int(w) else str(int(w)) for w in existing_widths) + "]"
        doc.xref_set_key(font_xref, "Widths", new_w_text)
        doc.xref_set_key(font_xref, "LastChar", str(new_last_char))
        logger.info(
            f"[FONT_AUG] Updated TrueType /Widths: LastChar {last_char} → {new_last_char}, "
            f"{len(new_widths)} new entries"
        )
    except Exception as e:
        logger.warning(f"[FONT_AUG] Failed to update TrueType widths: {e}")


def _update_pdf_font_structures(
    doc,
    page,
    font_tag: str,
    new_mappings: Dict[str, int],
    new_widths: Dict[int, float],
) -> None:
    """
    Update the PDF's ToUnicode CMap and W array to include new character mappings.
    This makes the new CIDs renderable by the PDF viewer.
    """
    # Find the font xref
    font_xref = None
    for f in page.get_fonts():
        if f[4] == font_tag:
            font_xref = f[0]
            break
    if not font_xref:
        return

    # 1. Update ToUnicode CMap
    try:
        tounicode_val = doc.xref_get_key(font_xref, "ToUnicode")
        if tounicode_val[0] != "null" and tounicode_val[1] and "0 R" in tounicode_val[1]:
            tu_xref = int(tounicode_val[1].strip().split()[0])
            old_stream = doc.xref_stream(tu_xref)
            old_text = old_stream.decode("latin-1", errors="replace")

            # Build new bfchar entries
            new_entries = []
            for char, cid in new_mappings.items():
                unicode_hex = f"{ord(char):04X}"
                new_entries.append(f"<{cid:04X}> <{unicode_hex}>")

            if new_entries:
                insert_block = (
                    f"\n{len(new_entries)} beginbfchar\n"
                    + "\n".join(new_entries)
                    + "\nendbfchar\n"
                )
                endcmap_pos = old_text.rfind("endcmap")
                if endcmap_pos > 0:
                    new_text = old_text[:endcmap_pos] + insert_block + old_text[endcmap_pos:]
                    doc.update_stream(tu_xref, new_text.encode("latin-1"))
                    logger.info(f"[FONT_AUG] Updated ToUnicode CMap with {len(new_entries)} new entries")
    except Exception as e:
        logger.warning(f"[FONT_AUG] Failed to update ToUnicode CMap: {e}")

    # 2. Update width arrays (CIDFont /W or simple TrueType /Widths)
    try:
        desc_val = doc.xref_get_key(font_xref, "DescendantFonts")
        if desc_val[0] != "null" and desc_val[1]:
            # ── Type0/CID font path: update /W array on DescendantFont ──
            desc_text = desc_val[1].strip().strip("[]").strip()
            ref_match = re.match(r'(\d+)\s+0\s+R', desc_text)
            if ref_match:
                cidfont_xref = int(ref_match.group(1))
                w_val = doc.xref_get_key(cidfont_xref, "W")
                if w_val[0] != "null" and w_val[1]:
                    w_text = w_val[1].strip()

                    # Resolve indirect reference: W stored as "60 0 R"
                    if w_val[0] == "xref":
                        ref_m = re.match(r'(\d+)\s+0\s+R', w_text)
                        if ref_m:
                            w_indirect_xref = int(ref_m.group(1))
                            w_text = doc.xref_object(w_indirect_xref).strip()

                    # Append new width entries before the closing ']'
                    new_w_entries = []
                    for cid, width in new_widths.items():
                        new_w_entries.append(f"{cid}[{width:.5f}]")
                    if new_w_entries:
                        if w_text.endswith("]"):
                            w_text = w_text[:-1]
                        w_text += " " + " ".join(new_w_entries) + "]"
                        doc.xref_set_key(cidfont_xref, "W", w_text)
                        logger.info(f"[FONT_AUG] Updated W array with {len(new_w_entries)} new entries")
        else:
            # ── Simple TrueType font path: update /Widths, /FirstChar, /LastChar ──
            _update_truetype_widths(doc, font_xref, new_widths)
    except Exception as e:
        logger.debug(f"[FONT_AUG] Width array update skipped (non-critical): {e}")

    # 3. Update the font's FontFile2 with augmented subset
    try:
        _augment_font_file(doc, font_xref, font_tag, new_mappings)
    except Exception as e:
        logger.warning(f"[FONT_AUG] Failed to augment FontFile2: {e}")


def _augment_font_file(doc, font_xref: int, font_tag: str, new_mappings: Dict[str, int]):
    """
    Augment the embedded font's FontFile2 with glyphs from the system font.
    This ensures new CIDs actually render correctly.

    Handles two font structure paths:
    - Type0/CID: font_xref → DescendantFonts → CIDFont → FontDescriptor → FontFile2
    - Simple TrueType: font_xref → FontDescriptor → FontFile2
    """
    try:
        from fontTools.ttLib import TTFont
        from io import BytesIO

        # ── Locate FontDescriptor and BaseFont name ──
        fd_xref = None
        basefont_name = ""

        # Path 1: Type0/CID font (has DescendantFonts)
        desc_val = doc.xref_get_key(font_xref, "DescendantFonts")
        if desc_val[0] != "null" and desc_val[1]:
            desc_text = desc_val[1].strip().strip("[]").strip()
            ref_match = re.match(r'(\d+)\s+0\s+R', desc_text)
            if ref_match:
                cidfont_xref = int(ref_match.group(1))
                fd_val = doc.xref_get_key(cidfont_xref, "FontDescriptor")
                if fd_val[0] != "null" and fd_val[1]:
                    fd_match = re.match(r'(\d+)\s+0\s+R', fd_val[1].strip())
                    if fd_match:
                        fd_xref = int(fd_match.group(1))
                # Get BaseFont from CIDFont
                bf_val = doc.xref_get_key(cidfont_xref, "BaseFont")
                if bf_val[0] != "null" and bf_val[1]:
                    basefont_name = bf_val[1].strip().lstrip("/")

        # Path 2: Simple TrueType font (FontDescriptor directly on font dict)
        if fd_xref is None:
            fd_val = doc.xref_get_key(font_xref, "FontDescriptor")
            if fd_val[0] != "null" and fd_val[1]:
                fd_match = re.match(r'(\d+)\s+0\s+R', fd_val[1].strip())
                if fd_match:
                    fd_xref = int(fd_match.group(1))
            # Get BaseFont from font dict
            bf_val = doc.xref_get_key(font_xref, "BaseFont")
            if bf_val[0] != "null" and bf_val[1]:
                basefont_name = bf_val[1].strip().lstrip("/")

        if fd_xref is None:
            logger.debug(f"[FONT_AUG] No FontDescriptor found for {font_tag}")
            return

        # Strip subset prefix (e.g. "BAAAAA+TimesNewRomanPSMT" → "TimesNewRomanPSMT")
        if "+" in basefont_name:
            basefont_name = basefont_name.split("+", 1)[1]

        # ── Get FontFile2 ──
        ff2_val = doc.xref_get_key(fd_xref, "FontFile2")
        if ff2_val[0] == "null":
            logger.debug(f"[FONT_AUG] No FontFile2 for {font_tag}")
            return
        ff2_match = re.match(r'(\d+)\s+0\s+R', ff2_val[1].strip())
        if not ff2_match:
            return
        ff2_xref = int(ff2_match.group(1))

        # Read the embedded font
        font_bytes = doc.xref_stream(ff2_xref)
        embedded_font = TTFont(BytesIO(font_bytes))

        # Load matching system font
        augmentor = _FontAugmentor()
        system_font = augmentor._load_system_font(basefont_name)
        if not system_font:
            logger.info(f"[FONT_AUG] No system font for '{basefont_name}', skipping FontFile2 augmentation")
            return

        # Copy glyph data from system font to embedded font
        sys_cmap = system_font.getBestCmap()
        sys_glyf = system_font.get("glyf")
        emb_glyf = embedded_font.get("glyf")
        emb_hmtx = embedded_font.get("hmtx")
        sys_hmtx = system_font.get("hmtx")

        if not all([sys_cmap, sys_glyf, emb_glyf, emb_hmtx, sys_hmtx]):
            return

        sys_glyph_order = system_font.getGlyphOrder()
        emb_glyph_order = list(embedded_font.getGlyphOrder())

        for char, cid in new_mappings.items():
            code_point = ord(char)
            sys_glyph_name = sys_cmap.get(code_point)
            if sys_glyph_name is None:
                continue

            # Target glyph name in embedded font (by CID/GID)
            if cid < len(emb_glyph_order):
                target_name = emb_glyph_order[cid]
            else:
                target_name = f"gid{cid:05d}"

            # Ensure target slot exists
            if target_name not in emb_glyph_order:
                while len(emb_glyph_order) <= cid:
                    placeholder = f"gid{len(emb_glyph_order):05d}"
                    emb_glyph_order.append(placeholder)

            try:
                # Copy glyph outline
                if sys_glyph_name in sys_glyf:
                    emb_glyf[target_name] = sys_glyf[sys_glyph_name]

                # Copy metrics
                if sys_glyph_name in sys_hmtx.metrics:
                    emb_hmtx[target_name] = sys_hmtx[sys_glyph_name]
            except Exception as e:
                logger.debug(f"[FONT_AUG] Failed to copy glyph '{char}': {e}")

        # Save augmented font back to PDF
        try:
            buf = BytesIO()
            embedded_font.save(buf)
            new_font_bytes = buf.getvalue()
            doc.update_stream(ff2_xref, new_font_bytes)
            # Update Length1 if present
            doc.xref_set_key(ff2_xref, "Length1", str(len(new_font_bytes)))
            logger.info(f"[FONT_AUG] Updated FontFile2 ({len(font_bytes)} → {len(new_font_bytes)} bytes)")
        except Exception as e:
            logger.warning(f"[FONT_AUG] Failed to save augmented font: {e}")

    except ImportError:
        logger.debug("[FONT_AUG] fontTools not available for FontFile2 augmentation")
    except Exception as e:
        logger.warning(f"[FONT_AUG] FontFile2 augmentation failed: {e}")


def _find_blocks_for_text(
    content_blocks: List[ContentBlock],
    target_text: str,
    font_tag: str,
    used_block_indices: set,
) -> Optional[List[int]]:
    """
    Find a sequence of content blocks whose concatenated decoded text
    matches the target text. Uses text-content matching (not coordinates).

    Returns list of block indices, or None if not found.
    """
    target_clean = " ".join(target_text.replace("\u200b", "").split()).strip()
    if not target_clean:
        return None
    target_len = len(target_clean)

    # Try to find the target text as a subsequence of content blocks
    for start in range(len(content_blocks)):
        if start in used_block_indices:
            continue
        block = content_blocks[start]
        if not block.text_ops:
            continue

        first_text = block.full_text.replace("\u200b", "").strip()
        if not first_text:
            continue

        # Quick check: the first block's text should be the START of the target
        prefix_len = min(len(first_text), 5)
        if prefix_len < 3:
            # Short block — peek ahead to verify this isn't a stray char.
            # Combine with next non-empty block and check the combined prefix.
            combined = first_text
            for peek in range(start + 1, min(start + 10, len(content_blocks))):
                if peek in used_block_indices:
                    continue
                peek_text = content_blocks[peek].full_text.replace("\u200b", "").strip()
                if peek_text:
                    combined += peek_text
                    break
            combined_prefix = combined.lower()[:5]
            if not target_clean.lower().startswith(combined_prefix):
                continue
        else:
            if not target_clean.lower().startswith(first_text.lower()[:prefix_len]):
                continue

        # Build concatenated text both with and without inter-block spaces
        # (some PDFs split words across blocks: "Softwar"+"e" = "Software")
        concat_spaced = ""
        concat_raw = ""
        block_indices = []

        for j in range(start, min(start + 300, len(content_blocks))):
            if j in used_block_indices:
                continue
            b = content_blocks[j]
            if not b.text_ops:
                continue

            text = b.full_text
            if not text:
                continue

            # Spaced version: add space between blocks
            if concat_spaced and not concat_spaced.endswith(" ") and not text.startswith(" "):
                concat_spaced += " "
            concat_spaced += text
            # Raw version: no added spaces
            concat_raw += text
            block_indices.append(j)

            # Normalize both versions for comparison
            spaced_clean = " ".join(concat_spaced.replace("\u200b", "").split()).strip()
            raw_clean = " ".join(concat_raw.replace("\u200b", "").split()).strip()
            concat_len = max(len(spaced_clean), len(raw_clean))

            # Check for match when we have enough text (try both versions)
            if concat_len >= target_len * 0.90:
                if _texts_match(spaced_clean, target_clean) or _texts_match(raw_clean, target_clean):
                    raw_len = len(raw_clean)
                    # Detect single-char-per-block: if average chars/block < 3,
                    # use strict 100% threshold to avoid leaving garbage chars.
                    # Otherwise use 95% to avoid overreaching into next bullet.
                    avg_chars = raw_len / max(len(block_indices), 1)
                    threshold = 1.0 if avg_chars < 3 else 0.95
                    # Use concat_len (max of spaced/raw) for threshold check.
                    # Raw text lacks inter-block spaces, so comparing raw_len
                    # to a target that HAS spaces causes false extension into
                    # date/location blocks to make up the character deficit.
                    if concat_len >= target_len * threshold:
                        return block_indices
                    # Extend: keep collecting blocks until concat covers target.
                    # Skip blocks with protected content (dates, locations).
                    for k in range(j + 1, min(start + 300, len(content_blocks))):
                        if concat_len >= target_len * threshold:
                            break
                        if k in used_block_indices:
                            continue
                        bk = content_blocks[k]
                        if not bk.text_ops:
                            continue
                        tk = bk.full_text
                        if not tk:
                            continue
                        # Don't extend into protected blocks (dates, locations)
                        if _BoundaryDetector.is_protected(tk.strip()):
                            break
                        concat_raw += tk
                        block_indices.append(k)
                        raw_clean = " ".join(concat_raw.replace("\u200b", "").split()).strip()
                        concat_len = max(len(raw_clean), concat_len)
                    return block_indices

            # If we've gone well past the target length, stop
            if concat_len > target_len * 1.5:
                break

    return None


def _texts_match(text_a: str, text_b: str) -> bool:
    """Check if two texts match using token-based comparison with character fallback.

    Token-based matching is robust against punctuation spacing differences
    like 'relevance , multi' vs 'relevance, multi' which cause character-level
    alignment to fail completely for the rest of the string.

    Character-level fallback handles cases where words are split across PDF blocks
    (e.g., "Softwar e" vs "Software").
    """
    import re
    a = " ".join(text_a.split()).lower()
    b = " ".join(text_b.split()).lower()
    if a == b:
        return True

    # Tokenize: split on whitespace, strip punctuation from tokens for comparison
    tokens_a = [t for t in re.findall(r'[a-z0-9]+', a) if len(t) > 1]
    tokens_b = [t for t in re.findall(r'[a-z0-9]+', b) if len(t) > 1]

    if not tokens_a or not tokens_b:
        # Fall through to character-level check
        pass
    else:
        # Token count must be within 15%
        count_ratio = min(len(tokens_a), len(tokens_b)) / max(len(tokens_a), len(tokens_b))
        if count_ratio >= 0.85:
            # Check what fraction of tokens in A appear in B (order-preserving)
            set_b = set(tokens_b)
            matching = sum(1 for t in tokens_a if t in set_b)
            match_ratio = matching / len(tokens_a)
            if match_ratio >= 0.85:
                return True

    # Character-level fallback: strip all spaces/punctuation and compare
    # This handles split-word cases like "Softwar e" vs "Software"
    chars_a = re.sub(r'[^a-z0-9]', '', a)
    chars_b = re.sub(r'[^a-z0-9]', '', b)
    if not chars_a or not chars_b:
        return False

    # Check length similarity
    len_ratio = min(len(chars_a), len(chars_b)) / max(len(chars_a), len(chars_b))
    if len_ratio < 0.85:
        return False

    # Use the shorter string and check if it's contained in the longer
    shorter, longer = (chars_a, chars_b) if len(chars_a) <= len(chars_b) else (chars_b, chars_a)
    if shorter in longer:
        return True

    # Prefix match: check if both start with the same content (handles trailing date differences)
    prefix_len = min(len(chars_a), len(chars_b))
    common = 0
    for i in range(prefix_len):
        if chars_a[i] == chars_b[i]:
            common += 1
        else:
            break
    if common >= prefix_len * 0.85:
        return True

    return False


def _patch_content_stream(
    doc,
    page_num: int,
    all_content_blocks: List[ContentBlock],
    classified_lines: List[ClassifiedLine],
    bullets: List[BulletPoint],
    skills: List[SkillLine],
    bullet_replacements: Dict[int, List[str]],
    skill_replacements: Dict[int, str],
    cmap_mgr: _CMapManager,
    width_calc: _WidthCalculator,
    font_aug: _FontAugmentor,
    title_skills: Optional[List[TitleSkillLine]] = None,
    title_replacements: Optional[Dict[int, str]] = None,
) -> None:
    """
    Core patching function. Modifies content stream in-place.

    Strategy: TEXT-BASED MATCHING.
    1. For each replacement, get the original text from the classified line
    2. Find content blocks whose concatenated decoded text matches the original
    3. Put the full replacement hex in the first block, empty all subsequent blocks
    4. Collect patches sorted descending by offset, apply, and write back
    """
    page = doc[page_num]

    # Collect all patches grouped by stream xref
    stream_patches: Dict[int, List[Tuple[int, int, bytes]]] = {}
    used_block_indices: set = set()

    def queue_patch(stream_xref: int, offset: int, old_len: int, new_bytes: bytes):
        if stream_xref not in stream_patches:
            stream_patches[stream_xref] = []
        stream_patches[stream_xref].append((offset, old_len, new_bytes))

    def _do_replacement(
        original_text: str,
        new_text: str,
        font_tag: str,
        label: str,
    ) -> bool:
        """Find and patch content blocks for one text replacement."""
        # Resolve font name (e.g., "TimesNewRomanPSMT") to font tag (e.g., "F5")
        resolved_font_tag = font_tag
        if font_tag and not font_tag.startswith("F"):
            for tag, name in cmap_mgr.font_names.items():
                if name == font_tag or font_tag in name:
                    resolved_font_tag = tag
                    break
        block_indices = _find_blocks_for_text(
            all_content_blocks, original_text, resolved_font_tag, used_block_indices
        )
        if not block_indices:
            logger.warning(
                f"[PATCH] Could not find content blocks for {label}: "
                f"'{original_text[:50]}'"
            )
            return False

        # ── Extend to capture tail-end fragments on same visual lines ──
        # The matcher stops at 95% threshold, leaving tail-end blocks with
        # original text ("product", "compliance", etc.) as visible leftovers.
        # Fix: scan forward from the last matched block on each y-line and
        # grab adjacent blocks at the same y-position and font.
        match_font = all_content_blocks[block_indices[0]].font_tag
        matched_set = set(block_indices)
        last_bi_per_y: Dict[float, int] = {}
        for bi in block_indices:
            y_key = round(all_content_blocks[bi].y, 1)
            if y_key not in last_bi_per_y or bi > last_bi_per_y[y_key]:
                last_bi_per_y[y_key] = bi

        extension = []
        for y_key, last_bi in last_bi_per_y.items():
            for k in range(last_bi + 1, min(last_bi + 20, len(all_content_blocks))):
                if k in used_block_indices or k in matched_set:
                    break  # Hit another replacement's territory
                bk = all_content_blocks[k]
                if not bk.text_ops:
                    continue  # Skip empty blocks (positioning-only)
                if abs(round(bk.y, 1) - y_key) > 3:
                    break  # Different visual line — stop
                if bk.font_tag != match_font:
                    break  # Different font (section header, etc.) — stop
                extension.append(k)

        # ── Boundary protection: filter out date/location blocks ──
        # The extension logic above grabs ALL blocks at the same Y-position,
        # which includes right-aligned dates like "March 2025 – Oct 2025".
        # Filter these out to prevent date wiping (Bug #1).
        if extension:
            extension = _BoundaryDetector.filter_extension_blocks(
                all_content_blocks, extension,
                matched_block_indices=block_indices,
            )

        if extension:
            logger.info(
                f"[PATCH] {label}: extended by {len(extension)} tail-end blocks"
            )
            block_indices.extend(extension)

        # ── Also check matched blocks for accidental date inclusion ──
        # If the text matching algorithm was too aggressive and included
        # date blocks in the initial match, remove them.
        block_indices = _BoundaryDetector.filter_matched_blocks(
            all_content_blocks, block_indices, original_text
        )
        if not block_indices:
            logger.warning(
                f"[PATCH] All blocks filtered as protected for {label}: "
                f"'{original_text[:50]}'"
            )
            return False

        # Mark blocks as used
        used_block_indices.update(block_indices)

        # Determine the font from the first matching block
        first_block = all_content_blocks[block_indices[0]]
        actual_font = first_block.font_tag

        # Encode new text to hex CIDs
        hex_encoded, missing_chars = cmap_mgr.encode_text(actual_font, new_text)

        # Handle missing characters — skip replacement to avoid garbled text.
        # Font augmentation for TrueType subset fonts is unreliable (internal cmap
        # table not updated → PDF viewers render .notdef boxes). The validation
        # system should have caught this; if it didn't, skip rather than garble.
        if missing_chars:
            logger.warning(
                f"[PATCH] Font {actual_font} missing chars {missing_chars[:5]} "
                f"for {label} — skipping to preserve original text"
            )
            return False

        if not hex_encoded:
            return False

        # Determine if we're patching literal strings or hex strings
        first_block = all_content_blocks[block_indices[0]]
        uses_literal = first_block.text_ops[0].is_literal if first_block.text_ops else False

        def _build_literal_content(text: str, font_tag: str) -> bytes:
            """Build literal string content with TJ kerning for word spacing.

            For Type1/literal fonts, spaces between words must be created by
            TJ kerning values (negative numbers between literal strings), NOT
            by space glyphs — Type1 fonts often have space outside /Widths range.

            Returns bytes like: (word1) -333 (word2) -333 (word3)
            This goes inside the existing [...] TJ array, replacing a single
            (literal) element.
            """
            words = text.split()
            if not words:
                return b"()"
            if len(words) == 1:
                w_hex, _ = cmap_mgr.encode_text(font_tag, words[0])
                if not w_hex:
                    return b"()"
                return b"(" + _hex_to_literal(w_hex) + b")"

            # Build TJ-style kerned output: (word1) -333 (word2) -333 (word3)
            parts = []
            for wi, word in enumerate(words):
                w_hex, _ = cmap_mgr.encode_text(font_tag, word)
                if not w_hex:
                    continue
                parts.append(b"(" + _hex_to_literal(w_hex) + b")")
                if wi < len(words) - 1:
                    parts.append(b" -333 ")
            return b"".join(parts) if parts else b"()"

        # ── Width-aware adjustment ──
        # Use Tc (character spacing) instead of Tz (horizontal scaling).
        # Tc distributes width difference as micro-adjustments between character
        # gaps, preserving character shapes. Tz distorts character shapes, which
        # is visually obvious even at 95%. Tc is invisible at typical levels.
        font_data = cmap_mgr.font_cmaps.get(actual_font, {})
        byte_width = font_data.get("byte_width", 2)
        hex_per_char = byte_width * 2
        widths_map = width_calc.font_widths.get(actual_font, {})
        default_w = width_calc._default_widths.get(actual_font, 1000.0)

        def _calc_hex_width(hex_str: str) -> float:
            """Calculate width units for a hex-encoded string."""
            total = 0.0
            for ci in range(0, len(hex_str), hex_per_char):
                if ci + hex_per_char > len(hex_str):
                    break
                cid = int(hex_str[ci:ci + hex_per_char], 16)
                total += widths_map.get(cid, default_w)
            return total

        def _inject_width_adjustment(
            op: TextOp, xref: int, orig_hex: str, new_hex: str,
            content_bytes: bytes, font_size: float = 1.0,
        ) -> bytes:
            """Inject Tc (character spacing) to match replacement width to original.

            Tc adjusts gaps between characters uniformly. This is far less visible
            than Tz (horizontal scaling) because character shapes are preserved —
            only the inter-character spacing changes.

            _calc_hex_width returns raw font units (1/1000 text space).
            PDF displacement: tx = (w0 * Tfs + Tc) * Th
            To match widths: Tc = (orig_w - new_w) * Tfs / (1000 * num_chars)
            where Tfs = font_size from the Tf operator.
            """
            if not orig_hex or not new_hex:
                adj_bytes = b" 0 Tc "
            else:
                orig_w = _calc_hex_width(orig_hex)
                new_w = _calc_hex_width(new_hex)
                num_new_chars = max(1, len(new_hex) // hex_per_char)

                if orig_w <= 0 or abs(new_w - orig_w) < orig_w * 0.01:
                    adj_bytes = b" 0 Tc "  # <1% difference, no adjustment
                else:
                    # Tc = (orig_w - new_w) * font_size / (1000 * num_chars)
                    # font_size converts raw font units to user-space points
                    tc_val = (orig_w - new_w) * font_size / (1000.0 * num_new_chars)
                    # Clamp to ±0.15pt per character — beyond this is visible
                    tc_val = max(-0.15, min(0.15, tc_val))
                    adj_bytes = f" {tc_val:.4f} Tc ".encode("latin-1")
            if op.operator == "TJ" and op.tj_array_start >= 0:
                queue_patch(xref, op.tj_array_start, 0, adj_bytes)
                return content_bytes
            else:
                return adj_bytes + content_bytes

        # ── Unified distribution: all-in-first-block per y-group ──
        # Group blocks by y-position, sort each group by x (left-to-right).
        # For multi-line matches: split replacement by WORDS (not chars) per line.
        # For single-line matches: put all text in leftmost block.
        # In all cases: zero remaining blocks, apply Tz scaling if wider.
        y_groups: Dict[float, List[int]] = {}  # rounded_y → [block_index, ...]
        for bi in block_indices:
            block = all_content_blocks[bi]
            y_key = round(block.y, 1)
            if y_key not in y_groups:
                y_groups[y_key] = []
            y_groups[y_key].append(bi)

        # Order y-groups by first appearance in block_indices (reading order).
        # We can't sort by raw y-value because some PDFs use negative y-coords
        # (flipped text matrix). block_indices follows the text reading order
        # since _find_blocks_for_text matches sequentially from the text start.
        seen_y_set: set = set()
        sorted_y_keys: List[float] = []
        for bi in block_indices:
            y_key = round(all_content_blocks[bi].y, 1)
            if y_key not in seen_y_set:
                sorted_y_keys.append(y_key)
                seen_y_set.add(y_key)
        # Sort blocks within each group by x ascending (left-to-right).
        for y_key in sorted_y_keys:
            y_groups[y_key].sort(key=lambda bi: all_content_blocks[bi].x)

        empty_bytes = b"()" if uses_literal else b"<>"

        if len(sorted_y_keys) > 1:
            # Multi-line: distribute WORDS proportionally across y-groups.
            # This avoids mid-word splits that character-level distribution causes.
            y_group_chars: Dict[int, int] = {}
            for y_key in sorted_y_keys:
                total_chars = 0
                for bi in y_groups[y_key]:
                    block = all_content_blocks[bi]
                    total_chars += sum(len(op.decoded_text) for op in block.text_ops)
                y_group_chars[y_key] = max(total_chars, 1)
            total_orig_chars = sum(y_group_chars.values())

            # Split new text into words and distribute by proportion
            words = new_text.split()
            word_idx = 0
            for yi, y_key in enumerate(sorted_y_keys):
                group_blocks = y_groups[y_key]
                orig_count = y_group_chars[y_key]

                # Last y-group gets all remaining words
                if yi == len(sorted_y_keys) - 1:
                    line_words = words[word_idx:]
                else:
                    proportion = orig_count / total_orig_chars
                    alloc_words = max(1, round(len(words) * proportion))
                    line_words = words[word_idx:word_idx + alloc_words]
                    word_idx += alloc_words

                line_text = " ".join(line_words) if line_words else ""

                if not line_text:
                    for bi in group_blocks:
                        block = all_content_blocks[bi]
                        for op in block.text_ops:
                            queue_patch(block.stream_xref, op.byte_offset,
                                        op.byte_length, empty_bytes)
                    continue

                # Determine font for this y-group's first block.
                # Different y-groups may use different fonts (e.g. regular vs bold).
                # Encoding text with the wrong font's CMap produces garbled output.
                first_bi = group_blocks[0]
                first_blk = all_content_blocks[first_bi]
                group_font = first_blk.font_tag

                # Encode this line's text using the correct font for this group
                line_hex, line_missing = cmap_mgr.encode_text(group_font, line_text)

                # Skip if this group's font is missing characters
                if line_missing:
                    logger.warning(
                        f"[PATCH] Font {group_font} missing chars {line_missing[:5]} "
                        f"for {label} (y-group {yi}) — zeroing this line"
                    )
                    line_hex = ""  # Will be caught by 'if not line_hex' below

                if not line_hex:
                    continue

                # Collect original hex for this y-group (for Tc calculation)
                line_orig_hex = ""
                for bi in group_blocks:
                    block = all_content_blocks[bi]
                    for op in block.text_ops:
                        line_orig_hex += op.hex_string

                # Use group font's width data for width calculations
                group_font_data = cmap_mgr.font_cmaps.get(group_font, {})
                group_byte_width = group_font_data.get("byte_width", 2)
                group_hex_per_char = group_byte_width * 2
                group_widths_map = width_calc.font_widths.get(group_font, {})
                group_default_w = width_calc._default_widths.get(group_font, 1000.0)

                def _calc_group_hex_width(hex_str: str) -> float:
                    total = 0.0
                    for ci in range(0, len(hex_str), group_hex_per_char):
                        if ci + group_hex_per_char > len(hex_str):
                            break
                        cid = int(hex_str[ci:ci + group_hex_per_char], 16)
                        total += group_widths_map.get(cid, group_default_w)
                    return total

                # Build content bytes for this line
                if uses_literal:
                    # Use TJ kerning for word spacing (Type1 fonts)
                    line_content = _build_literal_content(line_text, group_font)
                else:
                    line_content = f"<{line_hex}>".encode("latin-1")

                # Put in first (leftmost) block, Tc adjust, zero the rest
                if first_blk.text_ops:
                    first_op = first_blk.text_ops[0]
                    line_content = _inject_width_adjustment(
                        first_op, first_blk.stream_xref,
                        line_orig_hex, line_hex, line_content,
                        font_size=first_blk.font_size,
                    )
                    queue_patch(first_blk.stream_xref, first_op.byte_offset,
                                first_op.byte_length, line_content)
                    for op in first_blk.text_ops[1:]:
                        queue_patch(first_blk.stream_xref, op.byte_offset,
                                    op.byte_length, empty_bytes)

                for bi in group_blocks[1:]:
                    block = all_content_blocks[bi]
                    for op in block.text_ops:
                        queue_patch(block.stream_xref, op.byte_offset,
                                    op.byte_length, empty_bytes)

        else:
            # Single y-line (any number of blocks): all text in leftmost block.
            # Sort already done above, so block_indices[0] may not be leftmost.
            # Use the first entry in the sorted y-group instead.
            sole_y = sorted_y_keys[0]
            sorted_blocks = y_groups[sole_y]

            first_bi = sorted_blocks[0]
            first_blk = all_content_blocks[first_bi]

            # Re-encode if leftmost block uses a different font than actual_font
            group_font = first_blk.font_tag
            if group_font != actual_font:
                hex_encoded, line_missing = cmap_mgr.encode_text(group_font, new_text)
                if line_missing:
                    logger.warning(
                        f"[PATCH] Font {group_font} missing chars {line_missing[:5]} "
                        f"for {label} — skipping to preserve original text"
                    )
                    return False
                if not hex_encoded:
                    return False

            if uses_literal:
                # Use TJ kerning for word spacing (Type1 fonts)
                new_content_bytes = _build_literal_content(new_text, group_font)
            else:
                new_content_bytes = f"<{hex_encoded}>".encode("latin-1")

            # Calculate original total hex from all blocks for Tz
            all_orig_hex = ""
            for bi in sorted_blocks:
                block = all_content_blocks[bi]
                for op in block.text_ops:
                    all_orig_hex += op.hex_string

            if first_blk.text_ops:
                first_op = first_blk.text_ops[0]
                new_content_bytes = _inject_width_adjustment(
                    first_op, first_blk.stream_xref,
                    all_orig_hex, hex_encoded, new_content_bytes,
                    font_size=first_blk.font_size,
                )
                queue_patch(first_blk.stream_xref, first_op.byte_offset,
                            first_op.byte_length, new_content_bytes)
                for op in first_blk.text_ops[1:]:
                    queue_patch(first_blk.stream_xref, op.byte_offset,
                                op.byte_length, empty_bytes)

            for bi in sorted_blocks[1:]:
                block = all_content_blocks[bi]
                for op in block.text_ops:
                    queue_patch(block.stream_xref, op.byte_offset,
                                op.byte_length, empty_bytes)

        # ── Inject Tc/Tz reset after last patched op within BT/ET block ──
        # Tc and Tz persist across text ops within the same BT/ET block.
        # Without reset, subsequent unpatched ops (section headers etc.)
        # inherit non-default Tc/Tz from our replacement.
        try:
            last_op = None
            last_xref = None
            highest_offset = -1
            for bi in block_indices:
                block = all_content_blocks[bi]
                for op in block.text_ops:
                    if op.byte_offset > highest_offset:
                        highest_offset = op.byte_offset
                        last_op = op
                        last_xref = block.stream_xref
            if last_op and last_xref is not None:
                stream = doc.xref_stream(last_xref)
                if stream:
                    hex_end = last_op.byte_offset + last_op.byte_length
                    after_pos = -1
                    if last_op.operator == "TJ":
                        # For TJ arrays, find "]" then "TJ" after it
                        for i in range(hex_end, min(hex_end + 500, len(stream))):
                            if stream[i:i+1] == b']':
                                for j in range(i + 1, min(i + 20, len(stream))):
                                    if stream[j:j+2] == b'TJ':
                                        after_pos = j + 2
                                        break
                                break
                    else:  # Tj
                        for i in range(hex_end, min(hex_end + 30, len(stream))):
                            if stream[i:i+2] == b'Tj':
                                after_pos = i + 2
                                break
                    if after_pos > 0:
                        queue_patch(last_xref, after_pos, 0, b" 0 Tc 100 Tz ")
        except Exception:
            pass  # Non-critical, skip on error

        logger.info(
            f"[PATCH] {label}: '{original_text[:40]}' → '{new_text[:40]}' "
            f"({len(block_indices)} blocks patched)"
        )
        return True

    replacements_applied = 0

    # ── Process bullet replacements ──
    for b_idx, new_lines in bullet_replacements.items():
        try:
            if b_idx >= len(bullets):
                continue
            bp = bullets[b_idx]
            # Only process bullets that have text lines on this page
            if not any(tl.page_num == page_num for tl in bp.text_lines):
                continue

            # Match the ENTIRE bullet text as one unit (not per-line)
            # Content stream blocks don't align with visual line boundaries
            # For cross-page bullets, only match text from lines on this page
            page_line_indices = [i for i, tl in enumerate(bp.text_lines) if tl.page_num == page_num]
            page_line_texts = [bp.line_texts[i] for i in page_line_indices if i < len(bp.line_texts)]
            page_new_lines = [new_lines[i] for i in page_line_indices if i < len(new_lines)]

            original_full_text = " ".join(t.strip() for t in page_line_texts if t.strip())
            new_full_text = " ".join(line.strip() for line in page_new_lines if line.strip())

            if not original_full_text or not new_full_text:
                continue

            # Get font from the first text line's spans
            first_text_line = bp.text_lines[0]
            text_spans = [s for s in first_text_line.spans
                          if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()]
            font = text_spans[0].font_name if text_spans else ""

            if _do_replacement(
                original_full_text, new_full_text, font,
                f"bullet {b_idx}"
            ):
                replacements_applied += 1
        except Exception as e:
            logger.warning(f"[PATCH] Failed to process bullet {b_idx}: {e}")

    # ── Process skill replacements ──
    for s_idx, new_content in skill_replacements.items():
        try:
            if s_idx >= len(skills):
                continue
            sk = skills[s_idx]
            # Only process skills on this page
            if sk.content_spans and sk.content_spans[0].page_num != page_num:
                continue
            orig_text = sk.content_text
            if not orig_text or not new_content:
                continue

            font = sk.content_spans[0].font_name if sk.content_spans else ""
            if _do_replacement(orig_text, new_content, font, f"skill {s_idx}"):
                replacements_applied += 1
        except Exception as e:
            logger.warning(f"[PATCH] Failed to process skill {s_idx}: {e}")

    # ── Process title skill replacements ──
    if title_skills and title_replacements:
        for t_idx, new_skills_part in title_replacements.items():
            try:
                if t_idx >= len(title_skills):
                    continue
                ts = title_skills[t_idx]
                # Only process title skills on this page
                if ts.full_spans and ts.full_spans[0].page_num != page_num:
                    continue
                # Use title+skills only (NOT full_text which includes dates)
                orig_text = f"{ts.title_part} ({ts.skills_part})"
                new_text = f"{ts.title_part} ({new_skills_part})"
                font = ts.full_spans[0].font_name if ts.full_spans else ""
                if _do_replacement(orig_text, new_text, font, f"title {t_idx}"):
                    replacements_applied += 1
            except Exception as e:
                logger.warning(f"[PATCH] Failed to process title {t_idx}: {e}")

    # Apply all patches per stream (sorted descending by offset)
    for xref, patches in stream_patches.items():
        try:
            stream = doc.xref_stream(xref)
            if not stream:
                logger.warning(f"[PATCH] Empty stream for xref {xref}, skipping")
                continue
            stream_text = stream.decode("latin-1", errors="replace")

            # Sort patches descending by offset (so earlier offsets stay valid)
            patches.sort(key=lambda p: p[0], reverse=True)

            for offset, old_len, new_bytes in patches:
                # Validate patch bounds
                if offset < 0 or offset + old_len > len(stream_text):
                    logger.warning(
                        f"[PATCH] Out-of-bounds patch: offset={offset} old_len={old_len} "
                        f"stream_len={len(stream_text)}, skipping"
                    )
                    continue
                new_text_str = new_bytes.decode("latin-1")
                stream_text = stream_text[:offset] + new_text_str + stream_text[offset + old_len:]

            # ── Reset Tc and Tz at the start of every BT text object ──
            # Both Tc (character spacing) and Tz (horizontal scaling) persist
            # across BT/ET blocks in the PDF graphics state. Without resets,
            # any Tc/Tz injected for a replacement leaks to ALL subsequent
            # text objects on the page (headers, titles, dates, etc.).
            # Insert "0 Tc 100 Tz" after every BT keyword to ensure every
            # text object starts with clean default state.
            stream_text = re.sub(
                r'((?:^|\s)BT)(?=\s)',
                r'\1\n0 Tc 100 Tz',
                stream_text,
            )

            doc.update_stream(xref, stream_text.encode("latin-1"))
        except Exception as e:
            logger.warning(f"[PATCH] Failed to apply patches to stream xref {xref}: {e}")

    logger.info(f"[PATCH] Applied {replacements_applied} content stream patches on page {page_num}")


def apply_changes_to_pdf(
    pdf_path: str,
    output_path: str,
    bullets: List[BulletPoint],
    skills: List[SkillLine],
    bullet_replacements: Dict[int, List[str]],
    skill_replacements: Dict[int, str],
    title_skills: Optional[List[TitleSkillLine]] = None,
    title_replacements: Optional[Dict[int, str]] = None,
) -> str:
    """Apply optimized text back to the PDF using content stream patching.

    Strategy: Parse BT/ET blocks in the content stream, decode CIDs via ToUnicode CMap,
    encode new text back to CIDs, and patch the hex strings in-place.
    Zero redaction. Zero new text insertion. Preserves 100% of original formatting.
    """
    doc = fitz.open(pdf_path)

    # Initialize engine components
    cmap_mgr = _CMapManager(doc)
    width_calc = _WidthCalculator(doc)
    font_aug = _FontAugmentor()

    # Rebuild classified lines from the input bullets/skills for matching
    # We need the full list of classified lines to map to content blocks
    spans = extract_spans_from_pdf(pdf_path)
    vis_lines = group_into_visual_lines(spans)
    classified_lines, _ = classify_lines(vis_lines)

    # Parse content streams and apply patches for each page
    pages_with_content = set()
    for bp in bullets:
        for tl in bp.text_lines:
            pages_with_content.add(tl.page_num)
    for sk in skills:
        if sk.content_spans:
            pages_with_content.add(sk.content_spans[0].page_num)
    if title_skills:
        for ts in title_skills:
            if ts.full_spans:
                pages_with_content.add(ts.full_spans[0].page_num)

    for page_num in sorted(pages_with_content):
        page = doc[page_num]
        content_xrefs = page.get_contents()

        all_blocks: List[ContentBlock] = []
        for xref in content_xrefs:
            try:
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap_mgr, page_num, xref)
                all_blocks.extend(blocks)
            except Exception as e:
                logger.warning(f"[APPLY] Failed to parse content stream xref {xref}: {e}")

        logger.info(
            f"[APPLY] Page {page_num}: parsed {len(all_blocks)} content blocks "
            f"from {len(content_xrefs)} stream(s)"
        )

        try:
            _patch_content_stream(
                doc, page_num, all_blocks, classified_lines,
                bullets, skills,
                bullet_replacements, skill_replacements,
                cmap_mgr, width_calc, font_aug,
                title_skills, title_replacements,
            )
        except Exception as e:
            logger.error(f"[APPLY] Failed to patch page {page_num}: {e}", exc_info=True)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    logger.info(f"[APPLY] Saved patched PDF to {output_path}")
    return output_path


def _int_to_rgb(color: int) -> Tuple[float, float, float]:
    """Convert integer color to RGB tuple (0-1 range)."""
    r = ((color >> 16) & 0xFF) / 255.0
    g = ((color >> 8) & 0xFF) / 255.0
    b = (color & 0xFF) / 255.0
    return (r, g, b)


# ─── Public API ────────────────────────────────────────────────────────────

def build_section_map(pdf_path: str) -> Dict[str, Any]:
    """Build a map of the PDF structure for preview."""
    spans = extract_spans_from_pdf(pdf_path)
    lines = group_into_visual_lines(spans)
    classified, _ = classify_lines(lines)
    bullets, skills, title_skills = group_bullet_points(classified)

    return {
        "total_spans": len(spans),
        "total_lines": len(lines),
        "sections": [
            {
                "name": "Bullet Points",
                "num_content_lines": len(bullets),
                "content_text": "\n".join(
                    f"● {bp.full_text}" for bp in bullets
                ),
                "char_count": sum(len(bp.full_text) for bp in bullets),
            },
            {
                "name": "Skills",
                "num_content_lines": len(skills),
                "content_text": "\n".join(
                    f"{sk.label_text} {sk.content_text}" for sk in skills
                ),
                "char_count": sum(len(sk.content_text) for sk in skills),
            },
            {
                "name": "Title Tech Stacks",
                "num_content_lines": len(title_skills),
                "content_text": "\n".join(
                    f"{ts.title_part} ({ts.skills_part})" for ts in title_skills
                ),
                "char_count": sum(len(ts.skills_part) for ts in title_skills),
            },
        ],
    }


async def _validate_and_retry(
    pdf_path: str,
    bullets: List[BulletPoint],
    skills: List[SkillLine],
    title_skills: Optional[List[TitleSkillLine]],
    bullet_replacements: Dict[int, List[str]],
    skill_replacements: Dict[int, str],
    title_replacements: Dict[int, str],
    job_description: str,
    char_constraint: str = "",
    width_budgets: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[int, List[str]], Dict[int, str], Dict[int, str]]:
    """Validate replacements and retry failed items with tighter constraints.

    Pass 1: Check character availability + rendered width for all replacements.
    Pass 2: For items that fail, re-prompt Claude with explicit max char counts.
    Fallback: If retry also fails, drop the replacement (keep original text).
    """
    from app.llm.claude_client import ClaudeClient

    # ── Pass 1: Validate all replacements ──
    doc = fitz.open(pdf_path)
    cmap_mgr = _CMapManager(doc)
    width_calc = _WidthCalculator(doc)
    detector = _OverflowDetector(doc, cmap_mgr, width_calc)
    fa = FontAnalyzer(cmap_mgr)

    # Parse content blocks for width validation
    all_blocks: List[ContentBlock] = []
    for pn in range(len(doc)):
        page = doc[pn]
        for xref in page.get_contents():
            try:
                stream = doc.xref_stream(xref)
                blks = _parse_content_stream(stream, cmap_mgr, pn, xref)
                all_blocks.extend(blks)
            except Exception:
                pass

    def _resolve_tag(font_name: str) -> Optional[str]:
        for tag, name in cmap_mgr.font_names.items():
            if name == font_name or font_name in name:
                return tag
        return None

    # Track failures for retry
    failed_bullets: Dict[int, str] = {}  # idx -> reason
    failed_skills: Dict[int, str] = {}
    failed_titles: Dict[int, str] = {}

    valid_bullets: Dict[int, List[str]] = {}
    valid_skills: Dict[int, str] = {}
    valid_titles: Dict[int, str] = {}

    # ── Validate bullets ──
    for idx, new_lines in bullet_replacements.items():
        if idx >= len(bullets):
            continue
        bp = bullets[idx]
        text_spans = [
            s for tl in bp.text_lines for s in tl.spans
            if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()
        ]
        if not text_spans:
            valid_bullets[idx] = new_lines
            continue

        font_tag = _resolve_tag(text_spans[0].font_name)
        font_size = text_spans[0].font_size
        x_start = text_spans[0].bbox[0]
        page_num = text_spans[0].page_num

        if not font_tag:
            valid_bullets[idx] = new_lines
            continue

        # Check character availability
        full_text = " ".join(new_lines)
        missing = fa.check_text(full_text, font_tag)
        if missing:
            failed_bullets[idx] = f"unavailable chars: {missing[:5]}"
            continue

        # Check rendered width — compare against original line width
        # Using original width avoids coordinate system issues with CTM
        overflow = False
        for li, new_line in enumerate(new_lines):
            orig_line = bp.line_texts[li] if li < len(bp.line_texts) else ""
            orig_w = detector.measure_text_width(orig_line, font_tag, font_size) if orig_line else 0
            text_w = detector.measure_text_width(new_line, font_tag, font_size)
            max_tc = detector.MAX_TC * len(new_line)
            if orig_w > 0 and text_w - max_tc > orig_w:
                failed_bullets[idx] = f"line {li} overflow: {text_w:.0f}pt > {orig_w:.0f}pt"
                overflow = True
                break

        if not overflow:
            valid_bullets[idx] = new_lines

    # ── Validate skills ──
    for idx, new_content in skill_replacements.items():
        if idx >= len(skills):
            continue
        sk = skills[idx]
        if not sk.content_spans:
            valid_skills[idx] = new_content
            continue

        font_tag = _resolve_tag(sk.content_spans[0].font_name)
        font_size = sk.content_spans[0].font_size
        x_start = sk.content_spans[0].bbox[0]
        page_num = sk.content_spans[0].page_num

        if not font_tag:
            valid_skills[idx] = new_content
            continue

        missing = fa.check_text(new_content, font_tag)
        if missing:
            failed_skills[idx] = f"unavailable chars: {missing[:5]}"
            continue

        orig_content = sk.content_text if hasattr(sk, 'content_text') else " ".join(s.text for s in sk.content_spans)
        orig_w = detector.measure_text_width(orig_content, font_tag, font_size)
        text_w = detector.measure_text_width(new_content, font_tag, font_size)
        max_tc = detector.MAX_TC * len(new_content)
        if orig_w > 0 and text_w - max_tc > orig_w:
            failed_skills[idx] = f"overflow: {text_w:.0f}pt > {orig_w:.0f}pt"
        else:
            valid_skills[idx] = new_content

    # ── Validate titles ──
    if title_skills and title_replacements:
        for idx, new_skills_part in title_replacements.items():
            if idx >= len(title_skills):
                continue
            ts = title_skills[idx]
            if not ts.full_spans:
                valid_titles[idx] = new_skills_part
                continue

            font_tag = _resolve_tag(ts.full_spans[0].font_name)
            font_size = ts.full_spans[0].font_size
            x_start = ts.full_spans[0].bbox[0]
            page_num = ts.full_spans[0].page_num

            if not font_tag:
                valid_titles[idx] = new_skills_part
                continue

            full_new = f"{ts.title_part} ({new_skills_part})"
            missing = fa.check_text(full_new, font_tag)
            if missing:
                failed_titles[idx] = f"unavailable chars: {missing[:5]}"
                continue

            full_orig = f"{ts.title_part} ({ts.skills_part})"
            orig_w = detector.measure_text_width(full_orig, font_tag, font_size)
            text_w = detector.measure_text_width(full_new, font_tag, font_size)
            max_tc = detector.MAX_TC * len(full_new)
            if orig_w > 0 and text_w - max_tc > orig_w:
                failed_titles[idx] = f"overflow: {text_w:.0f}pt > {orig_w:.0f}pt"
            else:
                valid_titles[idx] = new_skills_part
    elif title_replacements:
        valid_titles = dict(title_replacements)

    doc.close()

    total_failed = len(failed_bullets) + len(failed_skills) + len(failed_titles)
    if total_failed == 0:
        logger.info("[VALIDATE] All replacements passed validation on first pass")
        return valid_bullets, valid_skills, valid_titles

    logger.info(
        f"[VALIDATE] Pass 1: {len(failed_bullets)} bullets, {len(failed_skills)} skills, "
        f"{len(failed_titles)} titles failed validation — retrying with tighter constraints"
    )
    for idx, reason in failed_bullets.items():
        logger.info(f"  Bullet {idx} failed: {reason}")
    for idx, reason in failed_skills.items():
        logger.info(f"  Skill {idx} failed: {reason}")
    for idx, reason in failed_titles.items():
        logger.info(f"  Title {idx} failed: {reason}")

    # ── Pass 2: Retry failed items with explicit hard constraints ──
    claude = ClaudeClient()
    budgets = width_budgets or {}
    bullet_budgets = budgets.get("bullet_budgets", {})
    skill_budgets = budgets.get("skill_budgets", {})
    title_budgets = budgets.get("title_budgets", {})

    # Retry bullets
    for idx in list(failed_bullets.keys()):
        bp = bullets[idx]
        # Resolve font tag for character availability checking
        text_spans = []
        for cl in bp.text_lines:
            text_spans.extend(cl.spans)
        font_tag = _resolve_tag(text_spans[0].font_name) if text_spans else None

        line_maxes = bullet_budgets.get(idx, [])
        lines_desc = []
        for j, lt in enumerate(bp.line_texts):
            mc = line_maxes[j] if j < len(line_maxes) else len(lt)
            # Tighter constraint on retry: use 90% of budget
            mc_tight = int(mc * 0.90)
            lines_desc.append(f"  Line {j+1} ({len(lt)} chars, HARD MAX {mc_tight} chars): {lt}")

        # Build char constraint including per-font restrictions
        char_rule = f"\n- {char_constraint}" if char_constraint else ""
        if font_tag:
            unavail = fa.get_unavailable_standard_chars(font_tag)
            if unavail:
                char_rule += f"\n- Do NOT use these characters: {' '.join(repr(c) for c in unavail)}"
        retry_prompt = f"""Rewrite this bullet point to match the job description.
CRITICAL: Each line MUST be shorter than its HARD MAX character count. This is a strict limit.{char_rule}

JOB DESCRIPTION (summary):
{job_description[:1500]}

BULLET ({bp.section_name}):
{chr(10).join(lines_desc)}

Return ONLY JSON: {{"lines": ["line 1 text", "line 2 text"]}}"""

        try:
            response = await claude._send_request(
                "You are a resume optimizer. You MUST respect character limits exactly.",
                retry_prompt,
            )
            parsed = _parse_json_response(response)
            if parsed and "lines" in parsed:
                new_lines = parsed["lines"]
                if len(new_lines) == len(bp.line_texts):
                    # Verify length constraints
                    fits = True
                    for j, nl in enumerate(new_lines):
                        mc = line_maxes[j] if j < len(line_maxes) else len(bp.line_texts[j])
                        if len(nl) > mc:
                            fits = False
                            break
                    # Also re-check character availability
                    if fits and font_tag:
                        retry_missing = fa.check_text(" ".join(new_lines), font_tag)
                        if retry_missing:
                            fits = False
                            logger.warning(
                                f"[RETRY] Bullet {idx} still has unavailable chars "
                                f"{retry_missing[:5]} — dropping"
                            )
                    if fits:
                        valid_bullets[idx] = new_lines
                        logger.info(f"[RETRY] Bullet {idx} succeeded on retry")
                    else:
                        logger.warning(f"[RETRY] Bullet {idx} still exceeds limits after retry — dropping")
                else:
                    logger.warning(f"[RETRY] Bullet {idx} wrong line count — dropping")
        except Exception as e:
            logger.warning(f"[RETRY] Bullet {idx} retry failed: {e}")

    # Retry skills
    for idx in list(failed_skills.keys()):
        sk = skills[idx]
        mc = skill_budgets.get(idx, len(sk.content_text))
        mc_tight = int(mc * 0.90)
        char_rule = f"\n- {char_constraint}" if char_constraint else ""

        retry_prompt = f"""Rewrite this skill line to match the job description.
CRITICAL: The output MUST be {mc_tight} characters or fewer.{char_rule}

JOB DESCRIPTION (summary):
{job_description[:1500]}

SKILL LINE: {sk.label_text} {sk.content_text}

Return ONLY the skill values (not the label). Return ONLY JSON: {{"content": "skill1, skill2, skill3"}}"""

        try:
            response = await claude._send_request(
                "You are a resume skills optimizer. You MUST respect character limits exactly.",
                retry_prompt,
            )
            parsed = _parse_json_response(response)
            if parsed and "content" in parsed:
                content = parsed["content"]
                label = sk.label_text.strip()
                if label and content.startswith(label):
                    content = content[len(label):].strip()
                label_base = label.rstrip(": ").strip()
                if label_base and content.startswith(label_base):
                    content = content[len(label_base):].lstrip(": ").strip()
                if len(content) <= mc:
                    # Re-check character availability
                    sk_font_tag = _resolve_tag(sk.content_spans[0].font_name) if sk.content_spans else None
                    if sk_font_tag:
                        retry_missing = fa.check_text(content, sk_font_tag)
                        if retry_missing:
                            logger.warning(
                                f"[RETRY] Skill {idx} still has unavailable chars "
                                f"{retry_missing[:5]} — dropping"
                            )
                            continue
                    valid_skills[idx] = content
                    logger.info(f"[RETRY] Skill {idx} succeeded on retry")
                else:
                    logger.warning(f"[RETRY] Skill {idx} still too long ({len(content)} > {mc}) — dropping")
        except Exception as e:
            logger.warning(f"[RETRY] Skill {idx} retry failed: {e}")

    # Retry titles
    for idx in list(failed_titles.keys()):
        ts = title_skills[idx]
        mc = title_budgets.get(idx, len(ts.skills_part))
        mc_tight = int(mc * 0.90)
        char_rule = f"\n- {char_constraint}" if char_constraint else ""

        retry_prompt = f"""Replace the tech stack in this job title to match the job description.
CRITICAL: The skills text MUST be {mc_tight} characters or fewer.{char_rule}

JOB DESCRIPTION (summary):
{job_description[:1500]}

TITLE: {ts.title_part} ({ts.skills_part})

Return ONLY the skills part (not the title or parentheses). Return ONLY JSON: {{"skills": "Tech1, Tech2, Tech3"}}"""

        try:
            response = await claude._send_request(
                "You are a resume optimizer. You MUST respect character limits exactly.",
                retry_prompt,
            )
            parsed = _parse_json_response(response)
            if parsed and "skills" in parsed:
                new_skills = parsed["skills"]
                if len(new_skills) <= mc:
                    # Re-check character availability
                    ts_font_tag = _resolve_tag(ts.content_spans[0].font_name) if ts.content_spans else None
                    if ts_font_tag:
                        retry_missing = fa.check_text(new_skills, ts_font_tag)
                        if retry_missing:
                            logger.warning(
                                f"[RETRY] Title {idx} still has unavailable chars "
                                f"{retry_missing[:5]} — dropping"
                            )
                            continue
                    valid_titles[idx] = new_skills
                    logger.info(f"[RETRY] Title {idx} succeeded on retry")
                else:
                    logger.warning(f"[RETRY] Title {idx} still too long — dropping")
        except Exception as e:
            logger.warning(f"[RETRY] Title {idx} retry failed: {e}")

    final_dropped = total_failed - (
        len(valid_bullets) - len(bullet_replacements) + len(failed_bullets)
        + len(valid_skills) - len(skill_replacements) + len(failed_skills)
        + len(valid_titles) - len(title_replacements or {}) + len(failed_titles)
    )
    retry_recovered = sum(1 for idx in failed_bullets if idx in valid_bullets) + \
                      sum(1 for idx in failed_skills if idx in valid_skills) + \
                      sum(1 for idx in failed_titles if idx in valid_titles)
    final_dropped = total_failed - retry_recovered

    logger.info(
        f"[VALIDATE] Final: {retry_recovered}/{total_failed} recovered on retry, "
        f"{final_dropped} dropped (original text preserved)"
    )

    return valid_bullets, valid_skills, valid_titles


# ─── Post-Patch Verification ────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """Result of a single verification check."""
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    """Complete verification report for a tailored PDF."""
    text_extraction: VerificationResult
    protected_content: VerificationResult
    fonts: VerificationResult
    visual: VerificationResult
    garbled: VerificationResult
    overflow: VerificationResult

    @property
    def passed(self) -> bool:
        """Overall pass: all critical checks pass.
        Visual is a warning (doesn't block) since content changes are expected.
        """
        return (
            self.protected_content.passed
            and self.fonts.passed
            and self.garbled.passed
            and self.overflow.passed
        )

    @property
    def summary(self) -> str:
        checks = [
            ("text_extraction", self.text_extraction),
            ("protected_content", self.protected_content),
            ("fonts", self.fonts),
            ("visual", self.visual),
            ("garbled", self.garbled),
            ("overflow", self.overflow),
        ]
        lines = []
        for name, result in checks:
            status = "PASS" if result.passed else "FAIL"
            lines.append(f"  [{status}] {name}")
            for w in result.warnings:
                lines.append(f"    WARNING: {w}")
        return "\n".join(lines)


class PostPatchVerifier:
    """Verify tailored PDF quality before returning to user.

    Runs 6 verification layers:
    1. Text extraction — replacement text is extractable
    2. Protected content — dates, headers, contact info unchanged
    3. Font integrity — same fonts, same count
    4. Visual regression (SSIM) — overall + protected region similarity
    5. Garbled character detection — no mid-word symbols or replacement chars
    6. Text overflow detection — no text past page margins
    """

    # SSIM thresholds
    OVERALL_SSIM_MIN = 0.75  # Content changes expected, so lower threshold
    HEADER_SSIM_MIN = 0.95   # Header should be nearly identical
    HEADER_REGION_RATIO = 0.12  # Top 12% of page is header

    def verify(
        self,
        original_path: str,
        tailored_path: str,
        bullet_replacements: Optional[Dict[int, List[str]]] = None,
        skill_replacements: Optional[Dict[int, str]] = None,
        title_replacements: Optional[Dict[int, str]] = None,
    ) -> VerificationReport:
        """Run all verification checks and return a report."""
        # Layer 1: Text extraction
        text_result = self._check_text_extraction(
            tailored_path,
            bullet_replacements or {},
            skill_replacements or {},
            title_replacements or {},
        )

        # Layer 2: Protected content
        protected_result = self._check_protected_content(
            original_path, tailored_path
        )

        # Layer 3: Font integrity
        font_result = self._check_fonts(original_path, tailored_path)

        # Layer 4: Visual regression (SSIM)
        visual_result = self._check_visual_similarity(
            original_path, tailored_path
        )

        # Layer 5: Garbled characters
        garbled_result = self._check_garbled_chars(tailored_path)

        # Layer 6: Text overflow (relative to original)
        overflow_result = self._check_overflow(tailored_path, original_path)

        return VerificationReport(
            text_extraction=text_result,
            protected_content=protected_result,
            fonts=font_result,
            visual=visual_result,
            garbled=garbled_result,
            overflow=overflow_result,
        )

    def _check_text_extraction(
        self,
        tailored_path: str,
        bullet_replacements: Dict[int, List[str]],
        skill_replacements: Dict[int, str],
        title_replacements: Dict[int, str],
    ) -> VerificationResult:
        """Verify replacement text is extractable from the tailored PDF."""
        try:
            doc = fitz.open(tailored_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text("text")
            doc.close()

            # Normalize whitespace for matching
            full_norm = " ".join(full_text.split()).lower()

            found = 0
            total = 0
            missing = []

            # Check bullet replacements
            for idx, lines in bullet_replacements.items():
                for line in lines:
                    total += 1
                    # Check if significant words from the replacement appear
                    words = [w for w in line.split() if len(w) > 3]
                    if not words:
                        found += 1
                        continue
                    # At least 60% of significant words should be found
                    matched = sum(1 for w in words if w.lower() in full_norm)
                    if matched >= len(words) * 0.6:
                        found += 1
                    else:
                        missing.append(f"Bullet {idx}: '{line[:50]}...'")

            # Check skill replacements
            for idx, content in skill_replacements.items():
                total += 1
                words = [w.strip(",. ") for w in content.split() if len(w.strip(",. ")) > 2]
                if not words:
                    found += 1
                    continue
                matched = sum(1 for w in words if w.lower() in full_norm)
                if matched >= len(words) * 0.5:
                    found += 1
                else:
                    missing.append(f"Skill {idx}: '{content[:50]}...'")

            # Check title replacements
            for idx, skills_part in title_replacements.items():
                total += 1
                words = [w.strip(",. ") for w in skills_part.split(",") if len(w.strip()) > 1]
                if not words:
                    found += 1
                    continue
                matched = sum(1 for w in words if w.strip().lower() in full_norm)
                if matched >= len(words) * 0.5:
                    found += 1
                else:
                    missing.append(f"Title {idx}: '{skills_part[:50]}'")

            rate = found / total if total > 0 else 1.0
            warnings = missing[:5] if missing else []  # Cap at 5 warnings

            return VerificationResult(
                passed=rate >= 0.7,
                details={"found": found, "total": total, "rate": rate},
                warnings=warnings,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                details={"error": str(e)},
                warnings=[f"Text extraction failed: {e}"],
            )

    def _check_protected_content(
        self, original_path: str, tailored_path: str
    ) -> VerificationResult:
        """Verify dates, headers, contact info are unchanged."""
        try:
            orig_doc = fitz.open(original_path)
            tail_doc = fitz.open(tailored_path)

            orig_text = ""
            tail_text = ""
            for page in orig_doc:
                orig_text += page.get_text("text")
            for page in tail_doc:
                tail_text += page.get_text("text")
            orig_doc.close()
            tail_doc.close()

            # Extract dates from original
            date_patterns = [
                r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\.?\s*\d{4}\b',
                r'\b\d{4}\s*[-–—]\s*(?:\d{4}|Present|Current|Now)\b',
                r'\b\d{1,2}/\d{4}\b',
            ]

            original_dates = set()
            for pattern in date_patterns:
                original_dates.update(re.findall(pattern, orig_text, re.IGNORECASE))

            missing_dates = []
            for date in original_dates:
                if date not in tail_text:
                    # Try normalized comparison (whitespace differences)
                    date_norm = " ".join(date.split())
                    tail_norm = " ".join(tail_text.split())
                    if date_norm not in tail_norm:
                        missing_dates.append(date)

            # Check contact patterns (email, phone, LinkedIn)
            email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
            phone_re = re.compile(r'[\d\(\)\-\+\s]{7,15}')

            orig_emails = set(email_re.findall(orig_text))
            tail_emails = set(email_re.findall(tail_text))
            missing_emails = orig_emails - tail_emails

            warnings = []
            if missing_dates:
                warnings.extend([f"Missing date: {d}" for d in missing_dates[:5]])
            if missing_emails:
                warnings.extend([f"Missing email: {e}" for e in missing_emails])

            return VerificationResult(
                passed=len(missing_dates) == 0 and len(missing_emails) == 0,
                details={
                    "dates_found": len(original_dates),
                    "dates_missing": len(missing_dates),
                    "emails_found": len(orig_emails),
                    "emails_missing": len(missing_emails),
                },
                warnings=warnings,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                details={"error": str(e)},
                warnings=[f"Protected content check failed: {e}"],
            )

    def _check_fonts(
        self, original_path: str, tailored_path: str
    ) -> VerificationResult:
        """Verify font integrity — same fonts, same count."""
        try:
            orig_doc = fitz.open(original_path)
            tail_doc = fitz.open(tailored_path)

            orig_fonts = set()
            tail_fonts = set()

            for page in orig_doc:
                for f in page.get_fonts():
                    orig_fonts.add(f[3])  # font name
            for page in tail_doc:
                for f in page.get_fonts():
                    tail_fonts.add(f[3])

            orig_doc.close()
            tail_doc.close()

            # Fonts should be identical (we don't add new fonts)
            missing = orig_fonts - tail_fonts
            extra = tail_fonts - orig_fonts

            warnings = []
            if missing:
                warnings.append(f"Missing fonts: {missing}")
            if extra:
                warnings.append(f"Extra fonts: {extra}")

            return VerificationResult(
                passed=len(missing) == 0,
                details={
                    "original_count": len(orig_fonts),
                    "tailored_count": len(tail_fonts),
                    "missing": list(missing),
                    "extra": list(extra),
                },
                warnings=warnings,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                details={"error": str(e)},
                warnings=[f"Font check failed: {e}"],
            )

    def _check_visual_similarity(
        self, original_path: str, tailored_path: str
    ) -> VerificationResult:
        """Render both PDFs and compare with SSIM."""
        try:
            import numpy as np
            from skimage.metrics import structural_similarity

            orig_doc = fitz.open(original_path)
            tail_doc = fitz.open(tailored_path)

            overall_ssims = []
            header_ssims = []

            for pn in range(min(len(orig_doc), len(tail_doc))):
                # Render at 150 DPI (fast enough for comparison)
                orig_pix = orig_doc[pn].get_pixmap(dpi=150)
                tail_pix = tail_doc[pn].get_pixmap(dpi=150)

                orig_arr = np.frombuffer(orig_pix.samples, dtype=np.uint8).reshape(
                    orig_pix.h, orig_pix.w, orig_pix.n
                )
                tail_arr = np.frombuffer(tail_pix.samples, dtype=np.uint8).reshape(
                    tail_pix.h, tail_pix.w, tail_pix.n
                )

                # Ensure same dimensions (crop to smaller)
                h = min(orig_arr.shape[0], tail_arr.shape[0])
                w = min(orig_arr.shape[1], tail_arr.shape[1])
                c = min(orig_arr.shape[2], tail_arr.shape[2])
                orig_crop = orig_arr[:h, :w, :c]
                tail_crop = tail_arr[:h, :w, :c]

                # Convert to grayscale for SSIM
                if c >= 3:
                    orig_gray = np.mean(orig_crop[:, :, :3], axis=2).astype(np.uint8)
                    tail_gray = np.mean(tail_crop[:, :, :3], axis=2).astype(np.uint8)
                else:
                    orig_gray = orig_crop[:, :, 0]
                    tail_gray = tail_crop[:, :, 0]

                # Overall SSIM
                overall = structural_similarity(orig_gray, tail_gray)
                overall_ssims.append(overall)

                # Header region SSIM (top 12%)
                header_h = int(h * self.HEADER_REGION_RATIO)
                if header_h > 10:
                    header_ssim = structural_similarity(
                        orig_gray[:header_h, :],
                        tail_gray[:header_h, :],
                    )
                    header_ssims.append(header_ssim)

            orig_doc.close()
            tail_doc.close()

            avg_overall = sum(overall_ssims) / len(overall_ssims) if overall_ssims else 0
            avg_header = sum(header_ssims) / len(header_ssims) if header_ssims else 0

            warnings = []
            if avg_overall < self.OVERALL_SSIM_MIN:
                warnings.append(
                    f"Overall SSIM {avg_overall:.3f} below threshold {self.OVERALL_SSIM_MIN}"
                )
            if avg_header < self.HEADER_SSIM_MIN:
                warnings.append(
                    f"Header SSIM {avg_header:.3f} below threshold {self.HEADER_SSIM_MIN}"
                )

            return VerificationResult(
                passed=avg_overall >= self.OVERALL_SSIM_MIN,
                details={
                    "overall_ssim": round(avg_overall, 4),
                    "header_ssim": round(avg_header, 4),
                    "pages_compared": len(overall_ssims),
                },
                warnings=warnings,
            )
        except ImportError:
            return VerificationResult(
                passed=True,
                details={"skipped": "scikit-image not available"},
                warnings=["SSIM check skipped — scikit-image not installed"],
            )
        except Exception as e:
            return VerificationResult(
                passed=True,  # Don't block on visual check failure
                details={"error": str(e)},
                warnings=[f"Visual check failed: {e}"],
            )

    def _check_garbled_chars(self, pdf_path: str) -> VerificationResult:
        """Detect garbled or replacement characters in the PDF."""
        try:
            doc = fitz.open(pdf_path)
            issues = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")

                # Check for Unicode replacement character
                if '\ufffd' in text:
                    count = text.count('\ufffd')
                    issues.append(
                        f"Page {page_num}: {count} Unicode replacement character(s)"
                    )

                # Check for suspicious mid-word non-alpha characters
                # e.g., "archite&cture" or "devel#opment"
                # Allow: apostrophes, hyphens, slashes (min/max), plus (+),
                # digits, underscores (var_names), periods (acronyms)
                garbled_re = re.compile(
                    r'[a-z][^a-zA-Z0-9\u2019\'\-/+_.][a-z]'
                )
                words = text.split()
                for word in words:
                    clean = word.strip(".,;:!?()[]{}\"'-/")
                    if len(clean) > 4:
                        match = garbled_re.search(clean)
                        if match:
                            # Exclude common patterns: URLs, emails, filenames
                            if '@' in word or '://' in word:
                                continue
                            issues.append(
                                f"Page {page_num}: Suspicious word '{clean}'"
                            )

            doc.close()

            return VerificationResult(
                passed=len(issues) == 0,
                details={"issues_found": len(issues)},
                warnings=issues[:10],  # Cap warnings
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                details={"error": str(e)},
                warnings=[f"Garbled char check failed: {e}"],
            )

    def _check_overflow(
        self, pdf_path: str, original_path: Optional[str] = None
    ) -> VerificationResult:
        """Detect text extending past the original PDF's text boundaries.

        Uses a relative approach: finds the max right-edge and bottom-edge
        of text in the original PDF, then checks if the tailored PDF has
        any text beyond those bounds (plus a small tolerance).
        Falls back to absolute 10pt margin if no original is provided.
        """
        try:
            doc = fitz.open(pdf_path)
            overflow_issues = []

            # Determine bounds from original PDF if available
            orig_max_right = {}   # page_num -> max right x
            orig_max_bottom = {}  # page_num -> max bottom y
            tolerance = 5.0  # Small tolerance for font metrics rounding

            if original_path:
                orig_doc = fitz.open(original_path)
                for pn in range(len(orig_doc)):
                    page = orig_doc[pn]
                    max_r = 0.0
                    max_b = 0.0
                    blocks = page.get_text(
                        "dict", flags=fitz.TEXT_PRESERVE_WHITESPACE
                    )["blocks"]
                    for block in blocks:
                        if block["type"] != 0:
                            continue
                        for line in block["lines"]:
                            for span in line["spans"]:
                                if span["text"].strip():
                                    max_r = max(max_r, span["bbox"][2])
                                    max_b = max(max_b, span["bbox"][3])
                    orig_max_right[pn] = max_r
                    orig_max_bottom[pn] = max_b
                orig_doc.close()

            for page_num in range(len(doc)):
                page = doc[page_num]
                page_w = page.rect.width
                page_h = page.rect.height

                # Use original bounds + tolerance, or absolute 10pt margin
                right_limit = orig_max_right.get(
                    page_num, page_w - 10.0
                ) + tolerance
                bottom_limit = orig_max_bottom.get(
                    page_num, page_h - 10.0
                ) + tolerance

                blocks = page.get_text(
                    "dict", flags=fitz.TEXT_PRESERVE_WHITESPACE
                )["blocks"]
                for block in blocks:
                    if block["type"] != 0:
                        continue
                    for line in block["lines"]:
                        for span in line["spans"]:
                            bbox = span["bbox"]
                            text = span["text"].strip()
                            if not text:
                                continue

                            if bbox[2] > right_limit:
                                overflow_issues.append(
                                    f"Page {page_num}: Right overflow at "
                                    f"x={bbox[2]:.1f} (limit={right_limit:.1f})"
                                    f": '{text[:30]}'"
                                )
                            if bbox[3] > bottom_limit:
                                overflow_issues.append(
                                    f"Page {page_num}: Bottom overflow at "
                                    f"y={bbox[3]:.1f} (limit={bottom_limit:.1f})"
                                    f": '{text[:30]}'"
                                )

            doc.close()

            return VerificationResult(
                passed=len(overflow_issues) == 0,
                details={"overflow_count": len(overflow_issues)},
                warnings=overflow_issues[:5],
            )
        except Exception as e:
            return VerificationResult(
                passed=True,  # Don't block on overflow check failure
                details={"error": str(e)},
                warnings=[f"Overflow check failed: {e}"],
            )


async def optimize_pdf(
    pdf_path: str,
    output_path: str,
    job_description: str,
    resume_content: str,
) -> Dict[str, Any]:
    """
    Main entry point: optimize a resume PDF while preserving exact formatting.
    Only modifies bullet point text and skill values.
    """
    logger.info(f"Starting PDF format preservation for {pdf_path}")

    # Step 1: Extract and classify
    spans = extract_spans_from_pdf(pdf_path)
    lines = group_into_visual_lines(spans)
    classified, _ = classify_lines(lines)

    bullet_count = sum(1 for c in classified if c.line_type == LineType.BULLET_TEXT)
    skill_count = sum(1 for c in classified if c.line_type == LineType.SKILL_CONTENT)
    structure_count = sum(1 for c in classified if c.line_type == LineType.STRUCTURE)
    logger.info(f"Classified: {bullet_count} bullet text lines, {skill_count} skill lines, {structure_count} structure lines (untouched)")

    # Step 2: Group into bullet points, skill lines, and title skill lines
    bullets, skills, title_skills = group_bullet_points(classified)
    logger.info(f"Found {len(bullets)} bullet points, {len(skills)} skill lines, {len(title_skills)} title skill lines")

    # Step 2b: Font analysis — determine available characters BEFORE LLM generation
    # This prevents generating characters the PDF font cannot render (garbled text bug)
    char_constraint = ""
    font_analyzer = None
    try:
        doc_for_analysis = fitz.open(pdf_path)
        cmap_for_analysis = _CMapManager(doc_for_analysis)
        font_analyzer = FontAnalyzer(cmap_for_analysis)
        char_constraint = font_analyzer.build_char_constraint_string()
        if char_constraint:
            logger.info(f"[FONT] Character constraint: {char_constraint}")
        else:
            logger.info("[FONT] All standard characters available — no constraint needed")
        logger.info(f"[FONT] Font summary:\n{font_analyzer.get_font_summary()}")
        doc_for_analysis.close()
    except Exception as e:
        logger.warning(f"[FONT] Font analysis failed (continuing without constraints): {e}")

    # Step 2c: Calculate per-item width budgets for LLM prompts
    width_budgets = None
    try:
        width_budgets = calculate_width_budgets(pdf_path, bullets, skills, title_skills)
    except Exception as e:
        logger.warning(f"[BUDGET] Width budget calculation failed (continuing without budgets): {e}")

    # Step 3: Optimize with Claude (with character constraints + width budgets)
    bullet_replacements, skill_replacements, title_replacements = await generate_optimized_content(
        bullets, skills, job_description, title_skills,
        char_constraint=char_constraint,
        width_budgets=width_budgets,
    )
    bullet_replacements = sanitize_bullet_replacements(
        bullets, bullet_replacements, length_tolerance=0.15
    )
    logger.info(f"Optimized {len(bullet_replacements)} bullets, {len(skill_replacements)} skills, {len(title_replacements)} title skills")

    # Step 3b: Validate + retry loop
    # Validates character availability and rendered width for all replacements.
    # Failed items get one retry with tighter constraints. If retry fails,
    # the replacement is dropped (original text preserved).
    bullet_replacements, skill_replacements, title_replacements = await _validate_and_retry(
        pdf_path, bullets, skills, title_skills,
        bullet_replacements, skill_replacements, title_replacements,
        job_description, char_constraint, width_budgets,
    )

    # Step 4: Apply to PDF
    apply_changes_to_pdf(
        pdf_path, output_path,
        bullets, skills,
        bullet_replacements, skill_replacements,
        title_skills, title_replacements,
    )
    logger.info(f"Saved optimized PDF to {output_path}")

    # Step 5: Post-patch verification
    try:
        verifier = PostPatchVerifier()
        report = verifier.verify(
            pdf_path, output_path,
            bullet_replacements, skill_replacements, title_replacements,
        )
        logger.info(f"[VERIFY] Post-patch verification:\n{report.summary}")

        if not report.passed:
            logger.warning(
                "[VERIFY] Verification FAILED — returning original PDF to prevent corruption"
            )
            # Copy original to output path to prevent returning corrupted PDF
            import shutil
            shutil.copy2(pdf_path, output_path)
            return {
                "sections_found": ["Bullet Points", "Skills", "Title Tech Stacks"],
                "sections_optimized": [],
                "output_path": output_path,
                "changes": [],
                "verification_failed": True,
                "verification_report": report.summary,
            }
    except Exception as e:
        logger.warning(f"[VERIFY] Post-patch verification error (non-blocking): {e}")

    sections_optimized = []
    if bullet_replacements:
        sections_optimized.append("Bullet Points")
    if skill_replacements:
        sections_optimized.append("Skills")
    if title_replacements:
        sections_optimized.append("Title Tech Stacks")

    # Build text diff pairs: [{section, original, optimized}, ...]
    changes = []
    for idx, new_lines in bullet_replacements.items():
        if 0 <= idx < len(bullets):
            bp = bullets[idx]
            changes.append({
                "section": bp.section_name,
                "type": "bullet",
                "original": " ".join(bp.line_texts),
                "optimized": " ".join(new_lines),
            })
    for idx, new_content in skill_replacements.items():
        if 0 <= idx < len(skills):
            sk = skills[idx]
            changes.append({
                "section": sk.section_name,
                "type": "skill",
                "original": f"{sk.label_text}{sk.content_text}",
                "optimized": f"{sk.label_text}{new_content}",
            })
    for idx, new_skills_part in title_replacements.items():
        if 0 <= idx < len(title_skills):
            ts = title_skills[idx]
            changes.append({
                "section": "Title",
                "type": "title_skill",
                "original": ts.full_text,
                "optimized": f"{ts.title_part} ({new_skills_part})",
            })

    return {
        "sections_found": ["Bullet Points", "Skills", "Title Tech Stacks"],
        "sections_optimized": sections_optimized,
        "output_path": output_path,
        "changes": changes,
    }
