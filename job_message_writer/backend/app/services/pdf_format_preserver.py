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

import copy
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


def _redistribute_text(text: str, target_line_count: int, orig_char_counts: List[int]) -> List[str]:
    """Split text into target_line_count lines, distributing words proportionally
    to match original char counts per line."""
    words = text.split()
    if not words or target_line_count <= 0:
        return [text]
    if target_line_count == 1:
        return [text]

    total_orig = sum(orig_char_counts) or 1
    # Target chars per line based on original proportions
    targets = [max(1, int(c / total_orig * len(text))) for c in orig_char_counts]

    result_lines: List[str] = []
    word_idx = 0
    for line_i in range(target_line_count):
        if line_i == target_line_count - 1:
            # Last line gets remaining words
            result_lines.append(" ".join(words[word_idx:]))
            break
        target_len = targets[line_i]
        line_words: List[str] = []
        current_len = 0
        while word_idx < len(words):
            w = words[word_idx]
            new_len = current_len + len(w) + (1 if line_words else 0)
            if line_words and new_len > target_len:
                break
            line_words.append(w)
            current_len = new_len
            word_idx += 1
        result_lines.append(" ".join(line_words) if line_words else "")

    # Fill any empty trailing lines (shouldn't happen but safety)
    while len(result_lines) < target_line_count:
        result_lines.append("")

    return result_lines


# ─── Smart truncation utilities ─────────────────────────────────────────────

# ── POS-based incomplete-ending detection ──
#
# Instead of maintaining huge word lists (fragile, always misses edge cases),
# use NLTK POS tagging to determine if the last word is a valid sentence ending.
#
# TWO-TIER system:
#   strict=False (trim path): Only checks a tiny set of ~25 unambiguous function
#     words (articles, prepositions, conjunctions).  NO POS tagging overhead.
#     Must be conservative — the trimmer needs valid stopping points.
#   strict=True (quality gate): Full POS-based analysis.  Catches adjectives,
#     adverbs, dangling gerunds, incomplete noun phrases.  False positives OK
#     because the consequence is just an LLM re-prompt.

import nltk as _nltk

_NLTK_POS_READY = False

def _ensure_nltk_pos():
    """Download POS tagger data on first use (fast, cached after first call)."""
    global _NLTK_POS_READY
    if _NLTK_POS_READY:
        return
    try:
        _nltk.data.find('taggers/averaged_perceptron_tagger_eng')
    except LookupError:
        _nltk.download('averaged_perceptron_tagger_eng', quiet=True)
    try:
        _nltk.data.find('taggers/averaged_perceptron_tagger')
    except LookupError:
        _nltk.download('averaged_perceptron_tagger', quiet=True)
    _NLTK_POS_READY = True

# Tiny set of UNAMBIGUOUS function words — these NEVER end a valid sentence.
# Used by strict=False (trim path) where we need speed and zero false positives.
_FUNCTION_WORDS = frozenset({
    # Articles
    'a', 'an', 'the',
    # Prepositions
    'to', 'for', 'by', 'at', 'in', 'on', 'with', 'from', 'of', 'as',
    'into', 'onto', 'through', 'across', 'during', 'before', 'after',
    'between', 'among', 'over', 'under', 'within', 'without', 'upon',
    'against', 'about', 'toward', 'along', 'above', 'below', 'near',
    # Conjunctions
    'and', 'or', 'but', 'nor', 'yet', 'so', 'both', 'either', 'neither',
    # Subordinators / relative
    'that', 'which', 'who', 'whom', 'whose', 'where', 'when',
    'while', 'although', 'because', 'since', 'unless', 'until', 'if',
    # Determiners
    'this', 'these', 'those', 'such', 'each', 'every',
    'some', 'any', 'all', 'no', 'more', 'most', 'several',
})

# Backward-compat aliases (some code references these directly)
_TRIM_DANGLING_WORDS = _FUNCTION_WORDS
_DANGLING_WORDS = _FUNCTION_WORDS


def _has_incomplete_ending(text: str, strict: bool = True) -> bool:
    """Check if text ends with an incomplete thought.

    strict=False → fast path: only checks unambiguous function words.
                   Used by _trim_text_to_fit where speed matters and
                   we need valid stopping points.
    strict=True  → full POS-based analysis using NLTK.  Catches
                   adjectives, adverbs, dangling gerunds, incomplete
                   noun phrases like "an automated seller whitelisting".
                   Used by quality gate / re-prompt decisions.
    """
    clean = text.rstrip(' ,;:.!?')
    if not clean:
        return True

    words = clean.split()
    if len(words) < 2:
        return True

    last = words[-1].lower()

    # ── Quick short-circuits (no POS needed) ──

    # Ends with number/metric → always complete
    if re.match(r'^[\d,.]+%?$', last.rstrip('.')):
        return False

    # Unambiguous function words → always incomplete
    if last in _FUNCTION_WORDS:
        return True

    # ── strict=False stops here (fast path for trimmer) ──
    if not strict:
        return False

    # ── strict=True: full POS-based analysis ──
    _ensure_nltk_pos()

    # POS tag last 8 words for sentence context
    context = words[-8:] if len(words) > 8 else words
    try:
        tagged = _nltk.pos_tag(context)
    except Exception:
        # NLTK failed — fall back to function-word check only
        return False

    last_tag = tagged[-1][1]

    # Tags that ALWAYS indicate incomplete ending
    # DT=determiner, IN=preposition, CC=conjunction, TO=to-infinitive
    # RB/RBR/RBS=adverb, WDT/WP/WRB=wh-words, PDT=predeterminer, EX=existential
    if last_tag in ('DT', 'IN', 'CC', 'TO', 'RB', 'RBR', 'RBS',
                     'WDT', 'WP', 'WRB', 'PDT', 'EX'):
        return True

    # Adjectives — incomplete in resume context (need a following noun)
    # JJ="fast-paced", "manual", "deep", "critical"
    # JJR="better", JJS="best" — comparative/superlative always need a noun
    if last_tag in ('JJ', 'JJR', 'JJS'):
        return True

    # Gerunds (VBG) at end of multi-word text → usually dangling
    # "...and reducing", "...by improving", "...successfully cutting"
    # Exception: VBG after a proper noun (NNP) is likely a compound noun
    # e.g. "Salesforce logging", "Jenkins scripting", "Kafka streaming"
    if last_tag == 'VBG' and len(words) > 2:
        if len(tagged) >= 2 and tagged[-2][1] in ('NNP', 'NNPS'):
            pass  # Compound noun — "Salesforce logging" is complete
        else:
            return True

    # Base verbs without objects → incomplete
    # "...to solve", "...and reduce", "...to optimize"
    if last_tag in ('VB', 'VBP') and len(words) >= 2:
        return True

    # ── Supplementary: incomplete noun phrases ending in -ing ──
    # POS tagger marks "whitelisting" as NN, but in context like
    # "an automated seller whitelisting" it's a modifier missing its head noun.
    # Detect: DT + 2+ modifiers + NN-ending-in-ing → incomplete NP
    if (last_tag in ('NN', 'NNS') and last.endswith('ing')
            and len(last) > 4 and len(tagged) >= 3):
        for i in range(len(tagged) - 2, max(0, len(tagged) - 6) - 1, -1):
            if tagged[i][1] == 'DT':
                between = tagged[i + 1:-1]
                if len(between) >= 2 and all(
                    t[1] in ('JJ', 'VBN', 'NN', 'NNS', 'NNP')
                    for t in between
                ):
                    return True
                break

    return False


def _has_joined_sentences(text: str) -> bool:
    """Detect two sentences jammed together without proper punctuation.

    Looks for patterns like "recommendations This strategic" where a lowercase
    word is followed by a capitalized word mid-sentence (not a proper noun/acronym).
    """
    # Pattern: lowercase letter + space + uppercase letter followed by lowercase
    # This catches "recommendations This strategic" but not "using Docker and"
    matches = re.findall(r'[a-z]\s+([A-Z][a-z]{2,})', text)
    if not matches:
        return False
    # Filter out common proper nouns / tech names that appear mid-sentence
    _PROPER_NOUNS = frozenset({
        'Java', 'Python', 'Docker', 'Kubernetes', 'Jenkins', 'React',
        'Angular', 'Redux', 'Spring', 'Django', 'Flask', 'Node',
        'Linux', 'Windows', 'Azure', 'Google', 'Amazon', 'Oracle',
        'Kafka', 'Redis', 'Mongo', 'Postgres', 'MySQL', 'Jira',
        'Github', 'Bitbucket', 'Terraform', 'Ansible', 'Datadog',
        'Splunk', 'Grafana', 'Elasticsearch', 'Dynatrace',
        'English', 'Hindi', 'Spanish', 'French', 'German',
    })
    for match in matches:
        if match not in _PROPER_NOUNS:
            return True
    return False


def _bullet_similarity(text_a: str, text_b: str) -> float:
    """Compute word-level Jaccard similarity between two bullet texts."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union) if union else 0.0


def _smart_truncate(text: str, max_chars: int) -> str:
    """Truncate text at semantic boundaries, never leaving dangling words.

    Strategy:
      1. Try clause boundary (period / semicolon / comma) within budget
      2. Fall back to word boundary with dangling-word removal
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]

    # Strategy 1: clause boundary
    for delim in ['. ', '; ', ', ']:
        idx = truncated.rfind(delim)
        if idx > max_chars // 3:
            candidate = truncated[:idx].strip()
            if len(candidate.split()) >= 4:
                return candidate

    # Strategy 2: word boundary + incomplete-ending cleanup
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]

    words = truncated.split()
    while len(words) > 3 and _has_incomplete_ending(' '.join(words), strict=False):
        words.pop()

    result = ' '.join(words).rstrip(' ,;:')

    # Close unclosed parentheses
    open_p = result.count('(') - result.count(')')
    if open_p > 0:
        result += ')' * open_p

    return result


def sanitize_bullet_replacements(
    bullets: List[BulletPoint],
    bullet_replacements: Dict[int, List[str]],
    length_tolerance: float = 0.20,
    bullet_budgets: Optional[Dict[int, Dict]] = None,
) -> Dict[int, List[str]]:
    """
    Keep only bullet replacements that preserve shape closely enough for safe PDF reflow.

    Rules enforced:
    - replacement index must exist
    - line count mismatches are auto-fixed by redistributing text
    - no empty replacement lines
    - lines that are too long get smart-truncated at word boundary
    - Tc character spacing handles shorter text, so no min-length rejection
    """
    sanitized: Dict[int, List[str]] = {}

    for idx, lines in bullet_replacements.items():
        if idx < 0 or idx >= len(bullets):
            logger.warning(f"[SANITIZE] Bullet idx {idx} out of range, dropping")
            continue

        original_lines = bullets[idx].line_texts
        normalized = [line.strip() for line in lines]

        # Strip leading bullet characters that Claude may have included —
        # the PDF already has the bullet marker as a separate span/inline char.
        _STRIP_BULLETS = ("•", "●", "◦", "○", "■", "▪", "·", "▸", "▹", "–", "—")
        cleaned = []
        for line in normalized:
            for bc in _STRIP_BULLETS:
                if line.startswith(bc + " ") or line.startswith(bc + "\t"):
                    line = line[len(bc):].strip()
                    break
                if line.startswith(bc) and len(line) > len(bc):
                    line = line[len(bc):].strip()
                    break
            cleaned.append(line)
        normalized = cleaned

        # Auto-fix line count mismatch by redistributing text
        if len(normalized) != len(original_lines):
            full_text = " ".join(n for n in normalized if n)
            orig_char_counts = [len(l.strip()) for l in original_lines]
            logger.info(
                f"[SANITIZE] Bullet {idx}: line count mismatch "
                f"(orig={len(original_lines)}, new={len(normalized)}), redistributing"
            )
            normalized = _redistribute_text(full_text, len(original_lines), orig_char_counts)

        if any(not line for line in normalized):
            logger.warning(f"[SANITIZE] Bullet {idx}: empty replacement line, dropping")
            continue

        # Total-length check: compare combined text length (not per-line).
        # The PDF engine joins all lines and re-wraps, so per-line length
        # doesn't matter — only total content length.
        #
        # Use pixel-based budget if available — it's much larger than
        # orig_total for bullets where the continuation line is short in the
        # original (e.g., "and reducing API latency by 40%." is only 32 chars
        # but the pixel budget allows ~98 chars on that line).
        orig_total = sum(len(l.strip()) for l in original_lines)
        new_total = sum(len(n) for n in normalized)
        if bullet_budgets and idx in bullet_budgets:
            # Use pixel budget — the PDF engine can handle this much text.
            # Add 20% tolerance since pixel budget is an approximation.
            max_total = int(bullet_budgets[idx]["total"] * 1.2)
        else:
            max_total = int(orig_total * (1 + length_tolerance))

        if new_total > max_total:
            full_text = " ".join(normalized)
            full_text = _smart_truncate(full_text, max_total)
            orig_char_counts = [len(l.strip()) for l in original_lines]
            normalized = _redistribute_text(full_text, len(original_lines), orig_char_counts)
            logger.debug(
                f"[SANITIZE] Bullet {idx}: total truncated {new_total} → {len(full_text)} chars"
            )

        sanitized[idx] = normalized

    return sanitized


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

    # First pass: find all bullet marker y-positions.
    # Only consider bullet chars among the first 2 non-zwsp spans of each line.
    # Dashes in the middle/end of a line (e.g. "- Github Link") are separators.
    bullet_y_positions = set()
    for line in visual_lines:
        _leading = [s for s in line if not s.is_zwsp_only][:2]
        for span in _leading:
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
        # Lines with bullet markers are never section headers.
        # Only check the first 2 non-zwsp spans — dashes/bullets in the middle
        # of a line (e.g. "- Github Link" at x=500) are separators, not bullets.
        _leading_spans = [s for s in line if not s.is_zwsp_only][:2]
        has_bullet_in_line = any(s.is_bullet_char for s in _leading_spans) or any(
            s.text.replace("\u200b", "").lstrip()[:1] in ("●", "•", "◦", "○", "■", "▪", "·", "▸", "▹")
            for s in _leading_spans
        )
        clean_collapsed = re.sub(r'[^A-Z0-9&:]', '', clean_upper)  # strip all non-alpha
        is_header = False
        if not has_bullet_in_line:
            for header in SECTION_HEADERS:
                header_collapsed = re.sub(r'[^A-Z0-9&:]', '', header)
                # startswith on collapsed text is too greedy for lines like
                # "Technologies: Python, Java, ..." — it would match header
                # "TECHNOLOGIES" but the line is actually a skill content line.
                # Guard: collapsed text must not be much longer than the header.
                _startswith_ok = (
                    len(header_collapsed) > 3
                    and clean_collapsed.startswith(header_collapsed)
                    and len(clean_collapsed) < len(header_collapsed) * 2
                )
                if (clean_upper == header or clean_upper.startswith(header + " ")
                        or clean_collapsed == header_collapsed
                        or _startswith_ok):
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
        # Only consider bullet chars among the first 2 non-zwsp spans.
        # Dashes at the end of a line (e.g. "- Github Link") are link separators.
        _leading_for_bullet = [s for s in line if not s.is_zwsp_only][:2]
        has_bullet_span = any(s.is_bullet_char for s in _leading_for_bullet)
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
            # Fallback for uniform-weight fonts (e.g. LaTeX CMR10): detect "Label: val1, val2, ..."
            # where no bold/regular contrast exists but colon + commas indicate a skill line.
            if not (has_bold and has_regular) and non_bullet:
                _skill_line_text = " ".join(
                    s.text for s in non_bullet
                ).replace("\u200b", "").strip()
                _colon_match = re.match(
                    r'^([A-Za-z][A-Za-z\s&/\-]+)\s*[:]\s*(.+)', _skill_line_text
                )
                if _colon_match:
                    _values_part = _colon_match.group(2).strip()
                    if "," in _values_part and len(_values_part.split(",")) >= 2:
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

                # Check for intervening STRUCTURE lines between last bullet and this line.
                # If a STRUCTURE line (e.g. project title, company name) exists between them,
                # this is NOT a continuation — it's the start of a new section/entry.
                has_intervening_structure = False
                if same_page and (y_close or page_break_continuation):
                    for c in reversed(classified):
                        if c.line_type == LineType.BULLET_TEXT and c.page_num == page_num:
                            break  # reached the last bullet, no structure between
                        if c.line_type == LineType.STRUCTURE and c.page_num == page_num:
                            c_y = c.y_pos
                            if last_bullet_y < c_y < y_pos or last_bullet_y > c_y > y_pos:
                                has_intervening_structure = True
                                break

                # In PROJECTS sections, check if this line looks like a new project title
                # (starts bold, contains ":", "|", "–"). If so, it's a new entry, not continuation.
                looks_like_project_title = False
                if section_collapsed in ("PROJECTS", "PROJECTEXPERIENCE", "TECHNICALPROJECTS"):
                    if first_non_zwsp.is_bold:
                        _bold_text = first_non_zwsp.text.replace("\u200b", "").strip()
                        if ":" in _bold_text or "|" in _bold_text or "\u2013" in _bold_text:
                            looks_like_project_title = True

                if not has_intervening_structure and not looks_like_project_title and (y_close or page_break_continuation):
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
        # Use dynamic left margin: section header x + 50pt (handles different resume layouts)
        _proj_sections = ("PROJECTS", "PROJECT EXPERIENCE", "TECHNICAL PROJECTS")
        _proj_left_margin = 100  # default
        if current_section.upper() in _proj_sections:
            for c in reversed(classified):
                if c.line_type == LineType.STRUCTURE and c.spans:
                    _non_zwsp_c = [s for s in c.spans if not s.is_zwsp_only and s.text.strip()]
                    if _non_zwsp_c:
                        _proj_left_margin = _non_zwsp_c[0].origin[0] + 50
                        break
        if (current_section.upper() in _proj_sections
                and non_zwsp
                and non_zwsp[0].origin[0] < _proj_left_margin):
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

            # In PROJECTS sections, any STRUCTURE line (project title) terminates
            # the current bullet group to prevent cross-project merging.
            _grp_sec_upper = re.sub(r'[^A-Z0-9&:]', '', current_section.upper())
            if _grp_sec_upper in ("PROJECTS", "PROJECTEXPERIENCE", "TECHNICALPROJECTS"):
                if current_bullet and current_bullet.text_lines:
                    bullets.append(current_bullet)
                    current_bullet = None

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

            # Colon-split fallback for uniform-weight fonts (e.g. LaTeX CMR10):
            # When there are no bold spans, split at the first colon to create
            # label_spans (category name) and content_spans (skill values).
            if not label_spans and content_spans:
                _all_text = " ".join(s.text for s in content_spans).replace("\u200b", "").strip()
                _colon_idx = _all_text.find(":")
                if _colon_idx > 0:
                    # Walk through spans, accumulate into label until colon found
                    _colon_label = []
                    _colon_content = []
                    _found_colon = False
                    for span in content_spans:
                        if _found_colon:
                            _colon_content.append(span)
                        elif ":" in span.text:
                            # This span contains the colon — split it
                            _found_colon = True
                            _parts = span.text.split(":", 1)
                            if _parts[0].strip():
                                _colon_label.append(span)  # label includes this span
                            if len(_parts) > 1 and _parts[1].strip():
                                _colon_content.append(span)  # content also uses this span
                        else:
                            _colon_label.append(span)
                    if _colon_label and _colon_content:
                        label_spans = _colon_label
                        content_spans = _colon_content

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


# ─── Pixel-based character budget computation ────────────────────────────

def _compute_bullet_char_budgets(
    bullets: List[BulletPoint],
    classified_lines: List[ClassifiedLine],
) -> Dict[int, Dict]:
    """Compute smart character budgets per bullet based on available pixel space.

    Uses font-level average character width (computed from ALL spans in the same
    font across the document) for a robust estimate independent of any single
    line's text content.  Also computes a structural minimum that guarantees
    text overflows onto every visual line of a multi-line bullet.

    Returns {bullet_idx: {"total": int, "per_line": [int, ...],
                          "min_overflow": int}}
    """
    # Compute per-page right margin from all classified lines
    page_margins: Dict[int, float] = {}
    for cl in classified_lines:
        pn = cl.page_num
        for s in cl.spans:
            if s.text.strip():
                page_margins.setdefault(pn, 0.0)
                page_margins[pn] = max(page_margins[pn], s.bbox[2])

    # ── Build font-level average character widths ──
    # Aggregate pixel width and char count across ALL spans per font_name.
    # This gives a robust avg_char_w that isn't skewed by one line's content.
    font_total_px: Dict[str, float] = {}   # font_name → total pixel width
    font_total_ch: Dict[str, int] = {}     # font_name → total char count
    for cl in classified_lines:
        for s in cl.spans:
            t = s.text.strip()
            if not t or s.is_bullet_char or s.is_zwsp_only:
                continue
            fname = s.font_name
            w = s.bbox[2] - s.bbox[0]
            if w > 0 and len(t) > 0:
                font_total_px[fname] = font_total_px.get(fname, 0.0) + w
                font_total_ch[fname] = font_total_ch.get(fname, 0) + len(t)

    font_avg_char_w: Dict[str, float] = {}
    for fname, px in font_total_px.items():
        ch = font_total_ch.get(fname, 1)
        if ch > 0:
            font_avg_char_w[fname] = px / ch

    budgets: Dict[int, Dict] = {}

    for bp_idx, bp in enumerate(bullets):
        per_line: List[int] = []

        for tl in bp.text_lines:
            # Get text spans (excluding bullet markers and ZWS)
            text_spans = [s for s in tl.spans
                          if not s.is_bullet_char and not s.is_zwsp_only
                          and s.text.strip()]

            if not text_spans:
                per_line.append(len(tl.clean_text))
                continue

            # x0 = left edge of first text span
            x0 = text_spans[0].bbox[0]
            right_margin = page_margins.get(tl.page_num, 580.0)
            available_width_pts = max(0, right_margin - x0)

            # Use font-level avg_char_w (robust across all document text).
            # Fall back to this line's own spans if font not found.
            primary_font = text_spans[0].font_name
            avg_char_w = font_avg_char_w.get(primary_font, 0.0)
            if avg_char_w <= 0:
                total_text_width = sum(s.bbox[2] - s.bbox[0] for s in text_spans)
                total_chars = sum(len(s.text) for s in text_spans)
                avg_char_w = (total_text_width / total_chars) if total_chars > 0 else 6.0

            char_budget = int(available_width_pts / avg_char_w)
            char_budget = max(char_budget, len(tl.clean_text))
            per_line.append(char_budget)

        total = sum(per_line)
        num_lines = len(per_line)

        # ── Structural minimum: guarantee overflow onto every line ──
        # For multi-line bullets the replacement text must exceed the capacity
        # of lines 1..N-1 so greedy-fill spills onto the last line.
        # A narrow-char safety factor accounts for the LLM potentially using
        # narrower characters than the font average (more i/l/t → more chars
        # fit per line → need even more chars to force overflow).
        NARROW_CHAR_FACTOR = 0.78  # assume replacement could be 22% narrower
        MIN_LAST_LINE_CHARS = 12   # at least a few words on the last line
        if num_lines > 1:
            first_n_minus_1 = sum(per_line[:-1])
            min_overflow = int(first_n_minus_1 / NARROW_CHAR_FACTOR) + MIN_LAST_LINE_CHARS
            # Don't exceed total capacity
            min_overflow = min(min_overflow, total)
        else:
            min_overflow = max(20, int(total * 0.50))

        budgets[bp_idx] = {
            "total": total,
            "per_line": per_line,
            "min_overflow": min_overflow,
        }

    return budgets


# ─── Step 5: Claude optimization ──────────────────────────────────────────

async def generate_optimized_content(
    bullets: List[BulletPoint],
    skills: List[SkillLine],
    job_description: str,
    title_skills: Optional[List[TitleSkillLine]] = None,
    bullet_budgets: Optional[Dict[int, Dict]] = None,
) -> Tuple[Dict[int, List[str]], Dict[int, str], Dict[int, str]]:
    """
    Send bullet points, skills, and title tech stacks to Claude for optimization.
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
        bullet_texts = []
        for i, bp in enumerate(bullets):
            if bp.section_name.upper().strip() in SKIP_SECTIONS:
                continue
            lines_info = []
            for j, lt in enumerate(bp.line_texts):
                lines_info.append(f"    Line {j+1}: {lt}")

            # Compute character budget using structural overflow guarantee.
            # min_overflow ensures the LLM generates enough text to spill
            # onto EVERY visual line (preventing empty-line gaps).
            # max is the full line capacity — the PDF engine's _trim_text_to_fit
            # and greedy-fill handle any overflow safely with Tc=0 (no squeeze).
            if bullet_budgets and i in bullet_budgets:
                bb = bullet_budgets[i]
                min_total = bb["min_overflow"]
                max_total = bb["total"]
            else:
                # Fallback: sum of original line lengths
                total_chars = sum(len(lt.strip()) for lt in bp.line_texts)
                min_total = max(20, int(total_chars * 0.85))
                max_total = total_chars

            bullet_texts.append(
                f"  BULLET {i+1} ({bp.section_name}) "
                f"[{len(bp.line_texts)} lines, total {min_total}-{max_total} chars]:\n"
                + "\n".join(lines_info)
            )

        if not bullet_texts:
            return replacements

        sys_prompt = (
            "You are an expert resume optimizer specializing in ATS-optimized, metric-driven tailoring. "
            "You tailor resume bullet points to match specific job descriptions by incorporating relevant "
            "keywords, rephrasing to emphasize relevant experience, and using terminology from the job posting. "
            "Every bullet must be a COMPLETE, MEANINGFUL statement — never leave fragments or dangling phrases. "
            "You must make REAL, MEANINGFUL changes that make the resume clearly targeted to the specific job."
        )

        async def _process_bullet_batch(batch_texts: List[str], batch_max_tokens: int) -> Dict[int, List[str]]:
            """Process a batch of bullets — same prompt, same parsing, same rules."""
            batch_result: Dict[int, List[str]] = {}
            usr_prompt = f"""Rewrite these resume bullet points to be tailored for the job description below.

RULES:
1. Rephrase to emphasize skills, experience, and outcomes most relevant to this specific role
2. Use action verbs and domain terminology that align with the job posting's language
3. PRESERVE: company names, metrics, percentages, dates, and all factual claims — do NOT fabricate
4. NEVER add technologies, tools, frameworks, or platforms that are NOT already mentioned in the bullet. You may rephrase existing tech to match JD terminology (e.g., "AWS Lambda" → "serverless Lambda functions"), but NEVER introduce completely new technologies the candidate didn't use. If the JD asks for "Node.js" but the bullet mentions "Python/Django", keep "Python/Django" — do NOT swap it for Node.js.
5. Each bullet must have EXACTLY the same number of lines as the original
6. CHARACTER BUDGET: Total characters across ALL lines must be within [min-max]. AIM FOR THE UPPER END of this range — filling more space is ALWAYS better than leaving it empty. The PDF engine handles overflow safely, but short text creates ugly gaps. Add specific metrics, technologies, scope, or impact details to fill the budget. Per-line length doesn't matter — only the TOTAL.
7. SEMANTIC COMPLETENESS — THE MOST IMPORTANT RULE:
   - Each bullet (ALL lines combined) must be exactly ONE complete, grammatically correct sentence
   - NEVER write two separate thoughts in one bullet. BAD: "...product recommendations This strategic enhancement improved the user" — this is TWO sentences jammed together
   - The LAST LINE is especially critical — it must complete the thought, not trail off
   - NEVER end with: a preposition (to, for, by, with, from, across, through), conjunction (and, or), article (a, an, the), adjective without a noun (critical, robust, secure, seamless, scalable, efficient, fast-paced), adverb (highly, efficiently, effectively), or a transitive verb without its object (solve, reduce, improve, enhance, create, develop, address, prevent)
   - BAD: "...optimizing 60% of data flow through efficient Jenkins" (Jenkins WHAT?)
   - BAD: "...system rollbacks, eliminating critical" (critical WHAT?)
   - BAD: "...to reduce downtime and solve" (solve WHAT?)
   - BAD: "...to support fast-paced" (fast-paced WHAT?)
   - GOOD: "...optimizing 60% of data flow through efficient Jenkins CI/CD pipelines"
   - GOOD: "...system rollbacks, eliminating critical downtime risks"
   - GOOD: "...to reduce downtime and solve production issues"
   - GOOD: "...to support fast-paced development cycles"
   - End every bullet with a CONCRETE NOUN, METRIC, or DELIVERABLE
8. NO DUPLICATE CONTENT: Each bullet must describe a DIFFERENT accomplishment. Never repeat the same action, tool, or outcome across multiple bullets. If two original bullets are similar, differentiate them by emphasizing different aspects.
9. Every bullet MUST be modified — do not return any bullet unchanged
10. NEVER include bullet point characters (•, ●, ◦, ■, -, –, —) at the start of your text. The PDF already has bullet markers. Return ONLY the text content.
11. Focus on transferable themes: if the JD emphasizes "backend scalability" and the bullet describes building scalable services (in any tech), emphasize the scalability angle — do NOT change the tech stack

JOB DESCRIPTION:
{job_description[:3000]}

BULLET POINTS TO OPTIMIZE:
{chr(10).join(batch_texts)}

IMPORTANT: Tailor by emphasizing RELEVANT THEMES from the JD (scalability, real-time, enterprise, etc.) — NOT by swapping in the JD's specific tech stack. The candidate's actual technologies must be preserved.
"""
            # JSON schema for guaranteed structured output
            bullet_schema = {
                "type": "object",
                "properties": {
                    "bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "lines": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["index", "lines"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["bullets"],
                "additionalProperties": False,
            }
            try:
                parsed = await claude._send_request_json(
                    sys_prompt, usr_prompt, json_schema=bullet_schema, max_tokens=batch_max_tokens,
                )
                if parsed and "bullets" in parsed:
                    for item in parsed["bullets"]:
                        idx = item.get("index", 0) - 1  # Original 0-based index
                        lines = item.get("lines", [])
                        if 0 <= idx < len(bullets) and lines:
                            # Validate semantic completeness: combined text
                            # must not end with an incomplete thought
                            combined = " ".join(l.strip() for l in lines if l.strip())
                            if _has_incomplete_ending(combined, strict=False):
                                last_word = combined.rstrip(" ,;:.").split()[-1].lower() if combined.strip() else ""
                                logger.warning(
                                    f"[BULLET OPT] Bullet {idx+1} has incomplete ending "
                                    f"'{last_word}': ...{combined[-60:]}"
                                )
                                # Trim incomplete ending words (conservative set only)
                                words = combined.rstrip(" ,;:.").split()
                                while len(words) > 3 and _has_incomplete_ending(' '.join(words), strict=False):
                                    words.pop()
                                combined = " ".join(words)
                                # Redistribute back to original line count
                                orig_counts = [len(l.strip()) for l in bullets[idx].line_texts]
                                lines = _redistribute_text(combined, len(orig_counts), orig_counts)
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
            # Each bullet can produce ~300 tokens of JSON output; generous buffer
            # prevents mid-JSON truncation that loses entire batches.
            tokens_per_batch = 8192
            logger.info(f"[BULLET OPT] Splitting {len(bullet_texts)} bullets into {len(batches)} parallel batches")

            batch_results = await asyncio.gather(
                *[_process_bullet_batch(batch, tokens_per_batch) for batch in batches]
            )
            for batch_result in batch_results:
                replacements.update(batch_result)
            logger.info(f"[BULLET OPT] Parsed {len(replacements)} bullet replacements from {len(batches)} batches")

        # ── LLM-based quality gate: intelligent semantic validation ──
        # Instead of regex/word-set heuristics, use a fast LLM call to check
        # each bullet for completeness, coherence, grammar, and uniqueness.
        # This catches issues like "improved the user" (semantically incomplete
        # even though "user" is a valid noun) that heuristics miss.
        all_combined = {}
        for idx, lines in replacements.items():
            all_combined[idx] = " ".join(l.strip() for l in lines if l.strip())

        incomplete_idxs: Dict[int, str] = {}

        if all_combined:
            # Build validation prompt
            bullet_list = []
            for idx in sorted(all_combined.keys()):
                bullet_list.append(f"  {idx+1}. {all_combined[idx]}")

            validate_sys = (
                "You are a strict resume quality checker. You ONLY flag bullets that are BROKEN — "
                "do not flag bullets that are merely imperfect or could be worded better. "
                "A bullet passes if it is a complete, grammatically correct sentence that makes sense on its own."
            )
            validate_usr = f"""Check each resume bullet for quality issues. Flag ONLY bullets that are BROKEN.

CHECK FOR:
1. INCOMPLETE: Sentence trails off — ends with an adjective needing a noun ("fast-paced", "high-quality", "critical"), a preposition ("to", "for", "with"), a conjunction ("and", "or"), a verb missing its object ("solve", "reduce", "improve the user"), or any fragment that leaves the reader asking "...what?"
2. INCOHERENT: Two separate sentences jammed together without proper punctuation or transition. Look for abrupt topic changes or capitalized words mid-sentence that start a new thought.
3. DUPLICATE: Two or more bullets describe essentially the same accomplishment with very similar wording.
4. NONSENSICAL: Text that doesn't make grammatical sense or has garbled wording.

A bullet PASSES if it is ONE complete sentence that makes full sense. Minor stylistic imperfections are NOT failures.

BULLETS:
{chr(10).join(bullet_list)}

Return the indices (1-based) of ONLY the bullets that FAIL, with the specific issue. Return empty array if all pass."""

            validate_schema = {
                "type": "object",
                "properties": {
                    "failed_bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "issue": {"type": "string", "enum": ["INCOMPLETE", "INCOHERENT", "DUPLICATE", "NONSENSICAL"]},
                                "explanation": {"type": "string"},
                            },
                            "required": ["index", "issue", "explanation"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["failed_bullets"],
                "additionalProperties": False,
            }

            try:
                validate_result = await claude._send_request_json(
                    validate_sys, validate_usr,
                    json_schema=validate_schema,
                    max_tokens=2048,
                    model=claude.fast_model,
                )
                if validate_result and "failed_bullets" in validate_result:
                    for item in validate_result["failed_bullets"]:
                        vidx = item.get("index", 0) - 1  # Convert to 0-based
                        issue = item.get("issue", "UNKNOWN")
                        explanation = item.get("explanation", "")
                        if vidx in all_combined:
                            incomplete_idxs[vidx] = all_combined[vidx]
                            logger.info(
                                f"[BULLET QA] Bullet {vidx+1} FAILED ({issue}): {explanation}"
                            )
                    logger.info(
                        f"[BULLET QA] LLM validation: {len(incomplete_idxs)}/{len(all_combined)} "
                        f"bullets flagged for re-prompt"
                    )
            except Exception as e:
                logger.warning(f"[BULLET QA] LLM validation failed, falling back to heuristics: {e}")

            # ALWAYS run heuristic checks as supplement (not just fallback).
            # The LLM quality gate can miss obvious issues like joined
            # sentences ("...scripts. This critical initiative...") or
            # incomplete endings that heuristics catch reliably.
            for idx, combined in all_combined.items():
                if idx in incomplete_idxs:
                    continue  # Already flagged
                if _has_incomplete_ending(combined):
                    incomplete_idxs[idx] = combined
                    logger.info(f"[BULLET QA] Bullet {idx+1} flagged by heuristic: incomplete ending")
                elif _has_joined_sentences(combined):
                    incomplete_idxs[idx] = combined
                    logger.info(f"[BULLET QA] Bullet {idx+1} flagged by heuristic: joined sentences")

            # Also check for near-duplicate bullets (heuristic supplement)
            sorted_idxs = sorted(all_combined.keys())
            for i in range(len(sorted_idxs)):
                for j in range(i + 1, len(sorted_idxs)):
                    idx_a, idx_b = sorted_idxs[i], sorted_idxs[j]
                    sim = _bullet_similarity(all_combined[idx_a], all_combined[idx_b])
                    if sim > 0.55:
                        if idx_b not in incomplete_idxs:
                            incomplete_idxs[idx_b] = all_combined[idx_b]
                            logger.info(
                                f"[BULLET QA] Bullet {idx_b+1} flagged: "
                                f"near-duplicate of bullet {idx_a+1} (sim={sim:.2f})"
                            )

        if incomplete_idxs:
            logger.info(
                f"[BULLET QA] {len(incomplete_idxs)} bullets need fixing, re-prompting"
            )
            retry_texts = []
            for idx, text in incomplete_idxs.items():
                bp = bullets[idx]
                if bullet_budgets and idx in bullet_budgets:
                    tight_budget = int(bullet_budgets[idx]["total"] * 0.90)
                else:
                    tight_budget = int(len(text) * 0.85)

                retry_texts.append(
                    f"  BULLET {idx+1} ({bp.section_name}) "
                    f"[{len(bp.line_texts)} lines, max {tight_budget} chars]:\n"
                    f"    CURRENT: {text}\n"
                    f"    REWRITE as ONE complete sentence in ≤{tight_budget} chars."
                )

            retry_sys = (
                "You are a resume editor. These bullet points have quality issues — "
                "some are incomplete, some are incoherent, some are duplicates. "
                "Rewrite each as a SINGLE, COMPLETE, self-contained sentence that ends with "
                "a concrete noun, metric, or deliverable — NEVER an adjective, adverb, or preposition. "
                "Each bullet must express exactly ONE clear idea."
            )
            retry_usr = f"""Fix these resume bullets.

RULES:
- Every bullet must be exactly ONE complete sentence ending with a concrete noun, metric, or outcome
- NEVER end with an adjective ("fast-paced", "high-quality"), adverb ("efficiently"), preposition ("to", "with"), or dangling verb ("solve", "reduce", "improve")
- Keep the same meaning, metrics, and facts — just make it a COMPLETE, COHERENT sentence
- Stay within the character budget shown
- Do NOT add technologies not already mentioned
- Each bullet must have EXACTLY the number of lines shown
- If a bullet is similar to another, rewrite to emphasize a DIFFERENT aspect

{chr(10).join(retry_texts)}

JOB DESCRIPTION (for context):
{job_description[:1500]}"""

            try:
                retry_schema = {
                    "type": "object",
                    "properties": {
                        "bullets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {"type": "integer"},
                                    "lines": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["index", "lines"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["bullets"],
                    "additionalProperties": False,
                }
                retry_parsed = await claude._send_request_json(
                    retry_sys, retry_usr, json_schema=retry_schema, max_tokens=4096,
                )
                if retry_parsed and "bullets" in retry_parsed:
                    fixed_count = 0
                    for item in retry_parsed["bullets"]:
                        ridx = item.get("index", 0) - 1
                        rlines = item.get("lines", [])
                        if ridx in incomplete_idxs and rlines:
                            r_combined = " ".join(l.strip() for l in rlines if l.strip())
                            # Quick sanity check: at least no obvious dangling words
                            still_bad = _has_incomplete_ending(r_combined, strict=False)
                            if not still_bad and len(r_combined.split()) >= 4:
                                # Fix line count if needed
                                orig_count = len(bullets[ridx].line_texts)
                                if len(rlines) != orig_count:
                                    orig_counts = [len(l.strip()) for l in bullets[ridx].line_texts]
                                    rlines = _redistribute_text(r_combined, orig_count, orig_counts)
                                replacements[ridx] = [l.strip() for l in rlines]
                                fixed_count += 1
                                logger.info(
                                    f"[BULLET QA] Fixed bullet {ridx+1}: ...{r_combined[-50:]}"
                                )
                            else:
                                logger.warning(
                                    f"[BULLET QA] Retry still bad for bullet {ridx+1}, keeping original"
                                )
                    logger.info(f"[BULLET QA] Re-prompt fixed {fixed_count}/{len(incomplete_idxs)} bullets")
            except Exception as e:
                logger.warning(f"[BULLET OPT] Re-prompt failed: {e}")

        return replacements

    async def _optimize_skills() -> Dict[int, str]:
        replacements: Dict[int, str] = {}
        if not skills:
            return replacements

        skill_texts = []
        for i, sk in enumerate(skills):
            skill_texts.append(f"  {i+1}. {sk.label_text} {sk.content_text}")

        sys_prompt = (
            "You are an expert resume skills optimizer. You reorder, substitute, and emphasize "
            "skills to strongly match a specific job description."
        )

        usr_prompt = f"""Optimize these skill lines to best match the job description below.

RULES:
1. REORDER skills WITHIN each line only — do NOT move skills between lines. Each line's bold label describes the category. Keep skills semantically aligned with their category.
2. Substitute equivalent terms to match JD language (e.g., "PostgreSQL" → "Postgres", "JS" → "JavaScript", "REST" → "RESTful APIs") — but ONLY rename, never replace one technology with a completely different one.
3. NEVER add technologies that are not already listed on the resume. Do NOT infer skills the candidate "probably" has. If the JD asks for "Node.js" but it's not on the resume, do NOT add it. Only work with what is already listed.
4. You may remove less relevant skills to make room, or reorder to put the most JD-relevant skills first.
5. Keep the SAME comma-separated format.
6. Each line should be SIMILAR length to the original (±15% character count).
7. Return ONLY the values after the label (e.g., for "Languages: Python, R, SQL" return "Python, R, SQL" — NOT "Languages: Python, R, SQL").
8. The ordering within each line should CLEARLY reflect what this specific job prioritizes — put matching skills first.
9. CRITICAL: Line N's output replaces Line N's content only. Do NOT move content between lines. A "Programming" skill should not appear in a "Cloud" category, etc.
10. NEVER strip qualifiers from technology names. "AWS DynamoDB" must stay as "AWS DynamoDB" or "DynamoDB" — NOT just "AWS". "Google Cloud Platform" must stay complete or use "GCP" — NOT just "Google".

JOB DESCRIPTION:
{job_description[:3000]}

SKILL LINES:
{chr(10).join(skill_texts)}

Return the optimized skill values for each line.
"""
        skill_schema = {
            "type": "object",
            "properties": {
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "content": {"type": "string"},
                        },
                        "required": ["index", "content"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["skills"],
            "additionalProperties": False,
        }
        try:
            parsed = await claude._send_request_json(sys_prompt, usr_prompt, json_schema=skill_schema)
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
                        # Clean trailing punctuation artifacts
                        content = content.rstrip(" ,;:")
                        replacements[idx] = content

                # ── Garbled output detection ──
                # Transient LLM API issue: tokens returned with spaces inside
                # words (e.g., "Ret ri eval" instead of "Retrieval").
                # Detect by checking if comma-separated terms have abnormally
                # many short (1-3 char) word fragments.
                import re as _re_garble
                _SHORT_WORD_EXCEPTIONS = {
                    # Common tech abbreviations (1-3 chars)
                    "ai", "ml", "r", "c", "go", "c++", "c#", ".net", "sql",
                    "s3", "ec2", "ci", "cd", "js", "ts", "api", "aws", "gcp",
                    "db", "ui", "ux", "qa", "os", "vm", "ip", "io", "rds",
                    "sqs", "sns", "iam", "vpc", "dns", "ssl", "tls", "ssh",
                    "pub", "sub", "git", "npm", "pip", "drf", "jwt", "xml",
                    "ms", "no", "vs", "de", "cdk", "sdk", "ecs", "eks", "ecr",
                    "ses", "sso", "cdn", "emr", "gke", "gcr", "edi", "etl",
                    "erp", "crm", "sap", "iot", "cli", "rag", "llm", "nlp",
                    "sla", "slo", "sli", "tcp", "udp", "csv", "pdf",
                }
                for ri, rcontent in list(replacements.items()):
                    terms = [t.strip() for t in rcontent.split(",") if t.strip()]
                    garbled_count = 0
                    for term in terms:
                        words = term.split()
                        if len(words) <= 1:
                            continue  # Single-word terms like "Docker" are fine
                        short_words = [
                            w for w in words
                            if len(w) <= 3 and w.lower().strip("()") not in _SHORT_WORD_EXCEPTIONS
                        ]
                        # For 2-word terms: if ANY word is a short non-exception fragment
                        # For 3+ word terms: if >40% of words are short fragments
                        if len(words) == 2:
                            if short_words:
                                garbled_count += 1
                        elif len(short_words) / len(words) > 0.4:
                            garbled_count += 1
                    if garbled_count > 0 and garbled_count / max(len(terms), 1) > 0.3:
                        logger.warning(
                            f"Skill line {ri}: garbled LLM output detected "
                            f"({garbled_count}/{len(terms)} terms garbled), reverting to original"
                        )
                        del replacements[ri]

                # ── Cross-category validation ──
                # Build set of original terms per skill line, then check
                # if any replacement "stole" a term from another line.
                original_terms_by_idx: Dict[int, set] = {}
                for si, sk in enumerate(skills):
                    terms = {t.strip().lower() for t in sk.content_text.split(",") if t.strip()}
                    original_terms_by_idx[si] = terms

                indices_to_drop: List[int] = []
                for ri, rcontent in list(replacements.items()):
                    new_terms = {t.strip().lower() for t in rcontent.split(",") if t.strip()}
                    orig_terms = original_terms_by_idx.get(ri, set())
                    # Check each new term: if it was originally in ANOTHER line
                    # but NOT in this line, it's a cross-category steal.
                    stolen = set()
                    for nt in new_terms:
                        if nt in orig_terms:
                            continue  # was already here
                        for oi, oterms in original_terms_by_idx.items():
                            if oi != ri and nt in oterms:
                                stolen.add(nt)
                                break
                    if len(stolen) >= 2:
                        # Too many stolen terms — drop this replacement
                        logger.warning(
                            f"Skill line {ri}: dropped replacement (stole {stolen} from other lines)"
                        )
                        indices_to_drop.append(ri)

                for di in indices_to_drop:
                    del replacements[di]

                # ── Fabrication detection ──
                # Build full original resume text from bullets + skills to check
                # if replacement terms actually exist on the candidate's resume.
                import re as _re
                resume_text_parts = []
                for bp in bullets:
                    resume_text_parts.extend(bp.line_texts)
                for sk in skills:
                    resume_text_parts.append(sk.content_text)
                    resume_text_parts.append(sk.label_text)
                full_resume_lower = " ".join(resume_text_parts).lower()
                # Extract clean words (strip punctuation) using regex
                # Matches tech terms like "node.js", "c++", "c#", ".net"
                resume_word_set = set(_re.findall(r'[a-z0-9][a-z0-9.+#]*', full_resume_lower))

                # Also build set of all original comma-separated terms (normalized)
                all_orig_terms = set()
                for oterms in original_terms_by_idx.values():
                    all_orig_terms.update(oterms)

                for ri, rcontent in list(replacements.items()):
                    # Clean up parentheses artifacts before splitting
                    clean_content = _re.sub(r'\)\s*$', ')', rcontent)
                    new_terms = [t.strip().strip(')').strip() for t in clean_content.split(",") if t.strip()]
                    new_terms = [t for t in new_terms if t]  # remove empties

                    valid_terms = []
                    fabricated = []
                    for nt in new_terms:
                        nt_lower = nt.strip().lower()
                        # 1. Exact full-term match against any original skill line
                        if nt_lower in all_orig_terms:
                            valid_terms.append(nt)
                            continue
                        # 2. Extract significant words from the new term
                        term_words = _re.findall(r'[a-z0-9][a-z0-9.+#]*', nt_lower)
                        sig_words = [w for w in term_words if len(w) > 2]
                        if not sig_words:
                            valid_terms.append(nt)
                            continue
                        # 3. ALL significant words must appear as exact words in resume
                        #    Also check tech abbreviations: "Node" matches "node.js"
                        _TECH_SUFFIXES = ('.js', '.ts', '.py', '.net')
                        def _word_on_resume(w):
                            if w in resume_word_set:
                                return True
                            # Check if word + tech suffix exists (e.g., "node" → "node.js")
                            return any((w + s) in resume_word_set for s in _TECH_SUFFIXES)
                        all_found = all(_word_on_resume(w) for w in sig_words)
                        if all_found:
                            valid_terms.append(nt)
                        else:
                            fabricated.append(nt)

                    if fabricated:
                        logger.warning(
                            f"Skill line {ri}: removed fabricated terms not on resume: {fabricated}"
                        )
                        if valid_terms:
                            replacements[ri] = ", ".join(valid_terms)
                        else:
                            # All terms fabricated — revert to original
                            del replacements[ri]

                # ── Post-fabrication length safety net ──
                # If fabrication validator stripped so many terms that the
                # replacement is <40% of original length, the LLM output
                # was too damaged — revert to original.
                for ri, rcontent in list(replacements.items()):
                    if 0 <= ri < len(skills):
                        orig_len = len(skills[ri].content_text)
                        if orig_len > 0 and len(rcontent) / orig_len < 0.4:
                            logger.warning(
                                f"Skill line {ri}: replacement too short after validation "
                                f"({len(rcontent)}/{orig_len} chars = "
                                f"{len(rcontent)/orig_len:.0%}), reverting to original"
                            )
                            del replacements[ri]

        except Exception as e:
            logger.error(f"Failed to optimize skills: {e}")
        return replacements

    async def _optimize_titles() -> Dict[int, str]:
        replacements: Dict[int, str] = {}
        if not title_skills:
            return replacements

        title_texts = []
        for i, ts in enumerate(title_skills):
            title_texts.append(f"  {i+1}. {ts.title_part} ({ts.skills_part})")

        sys_prompt = (
            "You are a resume title optimizer. You replace the tech stack in job title "
            "parentheses to match a target job description's technology requirements."
        )

        usr_prompt = f"""Replace the tech stacks in these job title parentheses to match the job description.

RULES:
1. ONLY change the technologies inside the parentheses — do NOT change the job title itself
2. Use technologies from the JD that the candidate ACTUALLY LISTS in their Skills section or bullet points. Never put a technology in the title that doesn't appear somewhere else on the resume.
3. Keep the SAME number of technologies (same comma-separated count)
4. Return ONLY the parenthesized content (e.g., "Node, Express, MongoDB, PostgreSQL, GCP")

JOB DESCRIPTION:
{job_description[:3000]}

TITLE LINES:
{chr(10).join(title_texts)}

Return the replacement tech stacks for each title line.
"""
        title_schema = {
            "type": "object",
            "properties": {
                "titles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "skills": {"type": "string"},
                        },
                        "required": ["index", "skills"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["titles"],
            "additionalProperties": False,
        }
        try:
            parsed = await claude._send_request_json(sys_prompt, usr_prompt, json_schema=title_schema)
            if parsed and "titles" in parsed:
                for item in parsed["titles"]:
                    idx = item.get("index", 0) - 1
                    new_skills = item.get("skills", "")
                    if 0 <= idx < len(title_skills) and new_skills:
                        replacements[idx] = new_skills

                # ── Title fabrication detection ──
                # Same approach as skill fabrication: check each term against resume text
                import re as _re
                resume_text_parts = []
                for bp in bullets:
                    resume_text_parts.extend(bp.line_texts)
                for sk in skills:
                    resume_text_parts.append(sk.content_text)
                    resume_text_parts.append(sk.label_text)
                full_resume_lower = " ".join(resume_text_parts).lower()
                resume_word_set = set(_re.findall(r'[a-z0-9][a-z0-9.+#]*', full_resume_lower))

                for ri, rcontent in list(replacements.items()):
                    new_terms = [t.strip() for t in rcontent.split(",") if t.strip()]
                    valid_terms = []
                    fabricated = []
                    for nt in new_terms:
                        nt_lower = nt.strip().lower()
                        term_words = _re.findall(r'[a-z0-9][a-z0-9.+#]*', nt_lower)
                        sig_words = [w for w in term_words if len(w) > 2]
                        if not sig_words:
                            valid_terms.append(nt)
                            continue
                        # Check tech abbreviations: "Node" matches "node.js"
                        _TECH_SUFFIXES = ('.js', '.ts', '.py', '.net')
                        def _word_on_resume_t(w):
                            if w in resume_word_set:
                                return True
                            return any((w + s) in resume_word_set for s in _TECH_SUFFIXES)
                        all_found = all(_word_on_resume_t(w) for w in sig_words)
                        if all_found:
                            valid_terms.append(nt)
                        else:
                            fabricated.append(nt)
                    if fabricated:
                        logger.warning(
                            f"Title line {ri}: removed fabricated tech not on resume: {fabricated}"
                        )
                        if valid_terms:
                            replacements[ri] = ", ".join(valid_terms)
                        else:
                            del replacements[ri]
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
        # font_tag → font_xref (PDF object number for the font dictionary)
        self.font_xrefs: Dict[str, int] = {}
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
                self.font_xrefs[font_tag] = font_xref
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

    # CTM transform tracking (cm operator)
    # CTM is a 6-element matrix [a, b, c, d, e, f] — we only track translation (e, f)
    ctm_tx, ctm_ty = 0.0, 0.0
    # Graphics state stack for q/Q save/restore
    gstate_stack: List[Tuple[float, float]] = []

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
            gstate_stack.append((ctm_tx, ctm_ty))
            pos += 1
            continue

        # Check for Q (restore graphics state)
        if not in_bt and text[pos] == "Q" and (pos + 1 >= length or text[pos + 1] in " \t\r\n"):
            if gstate_stack:
                ctm_tx, ctm_ty = gstate_stack.pop()
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
                blocks.append(ContentBlock(
                    font_tag=current_font,
                    font_size=current_size,
                    x=tx,
                    y=ty,
                    text_ops=list(text_ops),
                    stream_xref=stream_xref,
                    page_num=page_num,
                ))
            in_bt = False
            pos += 2
            continue

        if not in_bt:
            # Skip to next token
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
                    # Tm sets text matrix: a b c d tx ty
                    tx = nums[4]
                    ty = nums[5]
                    pos = scan_pos + 2
                    continue
                # Check for Td (2 numbers)
                elif len(nums) >= 2 and scan_pos + 1 < length and text[scan_pos:scan_pos + 2] == "Td":
                    # Flush current block before position change
                    if text_ops and current_font:
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
                    tx += nums[0]
                    ty += nums[1]
                    pos = scan_pos + 2
                    continue
                # Check for TD (2 numbers, like Td but also sets leading)
                elif len(nums) >= 2 and scan_pos + 1 < length and text[scan_pos:scan_pos + 2] == "TD":
                    if text_ops and current_font:
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
                    tx += nums[0]
                    ty += nums[1]
                    pos = scan_pos + 2
                    continue
                # Check for cm (coordinate transform, 6 numbers) — outside BT/ET
                elif not in_bt and len(nums) >= 6 and scan_pos + 1 < length and text[scan_pos:scan_pos + 2] == "cm":
                    # cm concatenates a matrix to the CTM: [a b c d e f]
                    # We track translation (e, f) to adjust text positions
                    ctm_tx += nums[4]
                    ctm_ty += nums[5]
                    pos = scan_pos + 2
                    continue

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


def _load_embedded_ttfont(doc, font_xref: int):
    """Load the embedded TTFont from a PDF font's FontFile2 stream.

    Handles both Type0/CID fonts (via DescendantFonts) and simple TrueType.
    Returns (TTFont, basefont_name, ff2_xref, is_simple_truetype) or (None, "", -1, False).
    """
    try:
        from fontTools.ttLib import TTFont
        from io import BytesIO

        fd_xref = None
        basefont_name = ""
        is_simple_truetype = False

        # Strategy 1: Type0/CID font (via DescendantFonts)
        desc_val = doc.xref_get_key(font_xref, "DescendantFonts")
        if desc_val[0] != "null" and desc_val[1]:
            desc_text = desc_val[1].strip().strip("[]").strip()
            ref_match = re.match(r'(\d+)\s+0\s+R', desc_text)
            if ref_match:
                cidfont_xref = int(ref_match.group(1))
                fd_val = doc.xref_get_key(cidfont_xref, "FontDescriptor")
                if fd_val[0] != "null":
                    fd_match = re.match(r'(\d+)\s+0\s+R', fd_val[1].strip())
                    if fd_match:
                        fd_xref = int(fd_match.group(1))
                bf_val = doc.xref_get_key(cidfont_xref, "BaseFont")
                if bf_val[0] != "null":
                    basefont_name = bf_val[1].strip().lstrip("/")
                    if "+" in basefont_name:
                        basefont_name = basefont_name.split("+", 1)[1]

        # Strategy 2: Simple TrueType (FontDescriptor directly on font dict)
        if fd_xref is None:
            fd_val = doc.xref_get_key(font_xref, "FontDescriptor")
            if fd_val[0] == "null":
                return None, "", -1, False
            fd_match = re.match(r'(\d+)\s+0\s+R', fd_val[1].strip())
            if not fd_match:
                return None, "", -1, False
            fd_xref = int(fd_match.group(1))
            is_simple_truetype = True
            bf_val = doc.xref_get_key(font_xref, "BaseFont")
            if bf_val[0] != "null":
                basefont_name = bf_val[1].strip().lstrip("/")
                if "+" in basefont_name:
                    basefont_name = basefont_name.split("+", 1)[1]

        # Get FontFile2
        ff2_val = doc.xref_get_key(fd_xref, "FontFile2")
        if ff2_val[0] == "null":
            return None, "", -1, False
        ff2_match = re.match(r'(\d+)\s+0\s+R', ff2_val[1].strip())
        if not ff2_match:
            return None, "", -1, False
        ff2_xref = int(ff2_match.group(1))

        # Read and parse the embedded font
        font_bytes = doc.xref_stream(ff2_xref)
        ttfont = TTFont(BytesIO(font_bytes))
        return ttfont, basefont_name, ff2_xref, is_simple_truetype

    except ImportError:
        return None, "", -1, False
    except Exception as e:
        logger.debug(f"[FONT] Failed to load embedded TTFont for xref {font_xref}: {e}")
        return None, "", -1, False


class _KerningReader:
    """Reads GPOS/kern tables from embedded or system fonts for per-pair kerning.

    Provides TJ array adjustment values (in 1/1000 text space units) for
    consecutive character pairs, enabling natural typographic spacing instead
    of uniform Tc character spacing.
    """

    def __init__(self, doc, cmap_mgr: '_CMapManager'):
        self._doc = doc
        self._cmap_mgr = cmap_mgr
        # font_tag → {(cid_a, cid_b): tj_adjustment_value}
        self._font_kerns: Dict[str, Dict[tuple, float]] = {}
        # Fonts we already know have no kerning data
        self._no_kern_fonts: set = set()

    def get_pair_kern(self, font_tag: str, cid_a: int, cid_b: int) -> float:
        """Get TJ adjustment value for a CID pair (in 1/1000 text space units).

        Positive = shift left (tighter), negative = shift right (looser).
        Returns 0.0 if no kerning data exists.
        """
        if font_tag in self._no_kern_fonts:
            return 0.0
        if font_tag not in self._font_kerns:
            self._load_font_kerning(font_tag)
        return self._font_kerns.get(font_tag, {}).get((cid_a, cid_b), 0.0)

    def _load_font_kerning(self, font_tag: str):
        """Load kerning pairs for a font from its GPOS/kern tables."""
        font_xref = self._cmap_mgr.font_xrefs.get(font_tag)
        if font_xref is None:
            self._no_kern_fonts.add(font_tag)
            return

        # Try embedded font first
        ttfont, basefont_name, _, _ = _load_embedded_ttfont(self._doc, font_xref)

        # Fall back to system font if embedded has no kerning tables
        if ttfont is not None:
            has_kern = ("GPOS" in ttfont) or ("kern" in ttfont)
            if not has_kern:
                ttfont = None

        if ttfont is None:
            font_name = self._cmap_mgr.font_names.get(font_tag, basefont_name or "")
            augmentor = _FontAugmentor()
            ttfont = augmentor._load_system_font(font_name)

        if ttfont is None:
            self._no_kern_fonts.add(font_tag)
            logger.debug(f"[KERN] No kerning data available for font {font_tag}")
            return

        pairs = self._extract_kern_pairs(font_tag, ttfont)
        if pairs:
            self._font_kerns[font_tag] = pairs
            logger.info(f"[KERN] Font {font_tag}: loaded {len(pairs)} kerning pairs")
        else:
            self._no_kern_fonts.add(font_tag)
            logger.debug(f"[KERN] Font {font_tag}: no kerning pairs found")

    def _extract_kern_pairs(self, font_tag: str, ttfont) -> Dict[tuple, float]:
        """Extract kerning pairs from a TTFont and map to CID pairs.

        Returns {(cid_a, cid_b): tj_value} where tj_value is in 1/1000 text space units.
        """
        try:
            upm = ttfont["head"].unitsPerEm if "head" in ttfont else 1000

            # Build glyph_name → CID mapping via:
            #   ttfont cmap: unicode_codepoint → glyph_name
            #   cmap_mgr rev: unicode_char → cid
            ttfont_cmap = ttfont.getBestCmap()
            if not ttfont_cmap:
                return {}

            # Invert ttfont cmap: glyph_name → unicode_codepoint
            glyph_to_unicode: Dict[str, int] = {}
            for codepoint, glyph_name in ttfont_cmap.items():
                if glyph_name not in glyph_to_unicode:
                    glyph_to_unicode[glyph_name] = codepoint

            # Get CMap manager's reverse map (char → cid)
            font_data = self._cmap_mgr.font_cmaps.get(font_tag, {})
            char_to_cid = font_data.get("rev", {})
            if not char_to_cid:
                return {}

            # Build glyph_name → cid
            glyph_to_cid: Dict[str, int] = {}
            for glyph_name, codepoint in glyph_to_unicode.items():
                ch = chr(codepoint)
                cid = char_to_cid.get(ch)
                if cid is not None:
                    glyph_to_cid[glyph_name] = cid

            # Extract raw kerning pairs from GPOS (preferred) or kern table
            raw_pairs: Dict[tuple, float] = {}  # (glyph_a, glyph_b) → kern_value_font_units

            if "GPOS" in ttfont:
                raw_pairs = self._extract_gpos_kerning(ttfont, glyph_to_cid)

            if not raw_pairs and "kern" in ttfont:
                raw_pairs = self._extract_legacy_kerning(ttfont)

            if not raw_pairs:
                return {}

            # Convert glyph-name pairs → CID pairs with TJ values
            cid_pairs: Dict[tuple, float] = {}
            for (glyph_a, glyph_b), kern_val in raw_pairs.items():
                cid_a = glyph_to_cid.get(glyph_a)
                cid_b = glyph_to_cid.get(glyph_b)
                if cid_a is not None and cid_b is not None:
                    # Convert: positive font kern = looser → negative TJ = looser
                    # TJ positive = shift left = tighter
                    tj_val = -kern_val * 1000.0 / upm
                    if abs(tj_val) >= 1.0:  # Skip sub-unit adjustments
                        cid_pairs[(cid_a, cid_b)] = round(tj_val, 1)

            return cid_pairs

        except Exception as e:
            logger.debug(f"[KERN] Failed to extract kern pairs for {font_tag}: {e}")
            return {}

    def _extract_gpos_kerning(self, ttfont, glyph_to_cid: Dict[str, int]) -> Dict[tuple, float]:
        """Extract kerning from GPOS PairPos subtables (Format 1 and 2)."""
        pairs: Dict[tuple, float] = {}
        try:
            gpos = ttfont["GPOS"].table
            if not gpos.LookupList:
                return pairs

            for lookup in gpos.LookupList.Lookup:
                subtables = lookup.SubTable
                # Handle Extension lookups (type 9) — unwrap to actual subtable
                if lookup.LookupType == 9:
                    subtables = [st.ExtSubTable for st in subtables
                                 if hasattr(st, 'ExtSubTable')]

                for subtable in subtables:
                    if not hasattr(subtable, 'Format'):
                        continue

                    # Only process PairPos (type 2)
                    if getattr(subtable, 'LookupType', 0) not in (0, 2) and lookup.LookupType != 2:
                        continue
                    if not hasattr(subtable, 'Format'):
                        continue

                    if subtable.Format == 1:
                        # Individual pair positioning
                        self._extract_pairpos_format1(subtable, pairs)
                    elif subtable.Format == 2:
                        # Class-based pair positioning
                        self._extract_pairpos_format2(subtable, pairs)

        except Exception as e:
            logger.debug(f"[KERN] GPOS extraction error: {e}")
        return pairs

    def _extract_pairpos_format1(self, subtable, pairs: Dict[tuple, float]):
        """Extract Format 1 (individual) pair positioning."""
        try:
            coverage_glyphs = subtable.Coverage.glyphs
            for i, first_glyph in enumerate(coverage_glyphs):
                if i >= len(subtable.PairSet):
                    break
                for pvr in subtable.PairSet[i].PairValueRecord:
                    second_glyph = pvr.SecondGlyph
                    val = pvr.Value1
                    if val and hasattr(val, 'XAdvance') and val.XAdvance:
                        pairs[(first_glyph, second_glyph)] = val.XAdvance
        except Exception:
            pass

    def _extract_pairpos_format2(self, subtable, pairs: Dict[tuple, float]):
        """Extract Format 2 (class-based) pair positioning."""
        try:
            # Build class → glyph list mappings
            class1_glyphs: Dict[int, list] = {}
            class2_glyphs: Dict[int, list] = {}

            if subtable.ClassDef1 and hasattr(subtable.ClassDef1, 'classDefs'):
                for glyph, cls in subtable.ClassDef1.classDefs.items():
                    class1_glyphs.setdefault(cls, []).append(glyph)
            # Class 0 = all glyphs NOT in ClassDef1 (coverage glyphs)
            if subtable.Coverage:
                for g in subtable.Coverage.glyphs:
                    if subtable.ClassDef1 and g not in subtable.ClassDef1.classDefs:
                        class1_glyphs.setdefault(0, []).append(g)

            if subtable.ClassDef2 and hasattr(subtable.ClassDef2, 'classDefs'):
                for glyph, cls in subtable.ClassDef2.classDefs.items():
                    class2_glyphs.setdefault(cls, []).append(glyph)

            # Extract values for each class pair
            for c1_idx, c1_record in enumerate(subtable.Class1Record):
                c1_list = class1_glyphs.get(c1_idx, [])
                if not c1_list:
                    continue
                for c2_idx, c2_record in enumerate(c1_record.Class2Record):
                    val = c2_record.Value1
                    if not val or not hasattr(val, 'XAdvance') or not val.XAdvance:
                        continue
                    c2_list = class2_glyphs.get(c2_idx, [])
                    for g1 in c1_list:
                        for g2 in c2_list:
                            pairs[(g1, g2)] = val.XAdvance
        except Exception:
            pass

    def _extract_legacy_kerning(self, ttfont) -> Dict[tuple, float]:
        """Extract kerning from legacy kern table."""
        pairs: Dict[tuple, float] = {}
        try:
            kern = ttfont["kern"]
            for subtable in kern.kernTables:
                if hasattr(subtable, 'kernTable') and subtable.kernTable:
                    for (left, right), value in subtable.kernTable.items():
                        if value != 0:
                            pairs[(left, right)] = value
        except Exception as e:
            logger.debug(f"[KERN] Legacy kern extraction error: {e}")
        return pairs


class _FontAugmentor:
    """Handles missing characters by loading system fonts and creating new CMap entries."""

    # Fallback substitutions for characters that can't be augmented.
    # Maps Unicode chars to safe ASCII equivalents that are likely in any font.
    _CHAR_FALLBACKS: Dict[str, str] = {
        "\u2013": "-",   # en-dash → hyphen
        "\u2014": "-",   # em-dash → hyphen
        "\u2018": "'",   # left single quote → apostrophe
        "\u2019": "'",   # right single quote → apostrophe
        "\u201c": '"',   # left double quote → straight quote
        "\u201d": '"',   # right double quote → straight quote
        "\u00a0": " ",   # non-breaking space → space
        "\u2022": "-",   # bullet → hyphen
        "\u2026": "...", # ellipsis → three dots
        "\u00b7": ".",   # middle dot → period
        "\u2010": "-",   # hyphen → ASCII hyphen
        "\u2011": "-",   # non-breaking hyphen → ASCII hyphen
        "\u2212": "-",   # minus sign → ASCII hyphen
    }

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
            # Apply fallback substitutions for any known chars
            return self._apply_fallbacks(unique_chars, font_tag, cmap_mgr, width_calc)

        try:
            from fontTools.ttLib import TTFont
            cmap_table = system_font.getBestCmap()
            if not cmap_table:
                logger.warning(f"[FONT_AUG] System font has no cmap table")
                return self._apply_fallbacks(unique_chars, font_tag, cmap_mgr, width_calc)

            # Get existing CMap to find unused CID range
            existing_fwd = cmap_mgr.font_cmaps.get(font_tag, {}).get("fwd", {})
            max_existing_cid = max(existing_fwd.keys()) if existing_fwd else 100

            # Get the hmtx table for widths
            hmtx = system_font.get("hmtx")
            glyf_order = system_font.getGlyphOrder()

            # Build glyph_name → gid (int) mapping
            name_to_gid = {name: idx for idx, name in enumerate(glyf_order)}

            all_resolved = True
            fallback_chars = []  # chars that couldn't be found in system font
            for ch in unique_chars:
                code_point = ord(ch)
                glyph_name = cmap_table.get(code_point)
                if glyph_name is None:
                    logger.warning(f"[FONT_AUG] Char '{ch}' (U+{code_point:04X}) not in system font")
                    fallback_chars.append(ch)
                    continue

                # Convert glyph name to numeric GID
                gid = name_to_gid.get(glyph_name, -1)
                if gid < 0:
                    logger.warning(f"[FONT_AUG] Glyph '{glyph_name}' for '{ch}' has no GID")
                    fallback_chars.append(ch)
                    continue

                # Assign a new CID (use the GID from system font if possible,
                # otherwise use max_existing + 1)
                new_cid = gid if gid not in existing_fwd else max_existing_cid + 1
                max_existing_cid = max(max_existing_cid, new_cid)

                # Add to CMap manager
                cmap_mgr.add_mapping(font_tag, ch, new_cid)

                # Get width from system font and convert to PDF 1/1000 em units
                if hmtx:
                    try:
                        advance_width = hmtx[glyph_name][0]  # (width, lsb) in font units
                    except (KeyError, IndexError):
                        advance_width = 500
                    # Convert from font units (UPM) to PDF width units (1/1000 em)
                    upm = system_font["head"].unitsPerEm if "head" in system_font else 1000
                    pdf_width = advance_width * 1000.0 / upm
                    # Add to width calculator
                    if font_tag not in width_calc.font_widths:
                        width_calc.font_widths[font_tag] = {}
                    width_calc.font_widths[font_tag][new_cid] = pdf_width

                logger.info(
                    f"[FONT_AUG] Mapped '{ch}' (U+{code_point:04X}) → CID {new_cid} "
                    f"in font {font_tag}"
                )

            # Try fallback substitution for any chars that couldn't be resolved
            if fallback_chars:
                fb_ok = self._apply_fallbacks(fallback_chars, font_tag, cmap_mgr, width_calc)
                if not fb_ok:
                    all_resolved = False

            return all_resolved

        except ImportError:
            logger.warning("[FONT_AUG] fontTools not available, cannot augment fonts")
            return False
        except Exception as e:
            logger.warning(f"[FONT_AUG] Font augmentation failed: {e}")
            return False

    def _apply_fallbacks(
        self,
        chars: List[str],
        font_tag: str,
        cmap_mgr: _CMapManager,
        width_calc: _WidthCalculator,
    ) -> bool:
        """Apply fallback character substitutions for chars that can't be augmented.
        Maps Unicode chars to ASCII equivalents that are already in the font."""
        all_resolved = True
        rev = cmap_mgr.font_cmaps.get(font_tag, {}).get("rev", {})
        for ch in chars:
            fallback = self._CHAR_FALLBACKS.get(ch)
            if fallback and fallback in rev:
                # Use the existing CID for the fallback character
                fallback_cid = rev[fallback]
                cmap_mgr.add_mapping(font_tag, ch, fallback_cid)
                # Copy width from fallback
                fb_width = width_calc.font_widths.get(font_tag, {}).get(fallback_cid, 500)
                if font_tag not in width_calc.font_widths:
                    width_calc.font_widths[font_tag] = {}
                width_calc.font_widths[font_tag][fallback_cid] = fb_width
                logger.info(f"[FONT_AUG] Fallback: '{ch}' → '{fallback}' (CID {fallback_cid})")
            else:
                logger.warning(f"[FONT_AUG] No fallback for '{ch}' (U+{ord(ch):04X})")
                all_resolved = False
        return all_resolved

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

            # Detect byte width from existing codespace range
            cid_hex_chars = 4  # default 2-byte
            cs_match = re.search(r'begincodespacerange\s*<([0-9A-Fa-f]+)>', old_text)
            if cs_match:
                cid_hex_chars = len(cs_match.group(1))  # 2 for 1-byte, 4 for 2-byte

            # Build new bfchar entries
            new_entries = []
            for char, cid in new_mappings.items():
                unicode_hex = f"{ord(char):04X}"
                new_entries.append(f"<{cid:0{cid_hex_chars}X}> <{unicode_hex}>")

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

    # 2. Update width structures
    try:
        desc_val = doc.xref_get_key(font_xref, "DescendantFonts")
        if desc_val[0] != "null" and desc_val[1]:
            # Type0/CID: update W array
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
            # Simple TrueType: update /Widths, /FirstChar, /LastChar
            _update_truetype_widths(doc, font_xref, new_widths)
    except Exception as e:
        logger.debug(f"[FONT_AUG] Width update skipped (non-critical): {e}")

    # 3. Update the font's FontFile2 with augmented subset
    try:
        _augment_font_file(doc, font_xref, font_tag, new_mappings)
    except Exception as e:
        logger.warning(f"[FONT_AUG] Failed to augment FontFile2 for {font_tag}: {e}")


def _update_truetype_widths(doc, font_xref: int, new_widths: Dict[int, float]) -> None:
    """Update /Widths, /FirstChar, /LastChar for simple TrueType fonts."""
    try:
        fc_val = doc.xref_get_key(font_xref, "FirstChar")
        lc_val = doc.xref_get_key(font_xref, "LastChar")
        w_val = doc.xref_get_key(font_xref, "Widths")

        if fc_val[0] == "null" or lc_val[0] == "null" or w_val[0] == "null":
            return

        first_char = int(fc_val[1].strip())
        last_char = int(lc_val[1].strip())

        # Parse existing widths array
        w_text = w_val[1].strip()
        if w_val[0] == "xref":
            ref_m = re.match(r'(\d+)\s+0\s+R', w_text)
            if ref_m:
                w_xref = int(ref_m.group(1))
                w_text = doc.xref_object(w_xref).strip()

        # Parse [w1 w2 w3 ...] into list
        inner = w_text.strip("[]").strip()
        widths = [float(x) for x in inner.split()] if inner else []

        # Extend widths array to cover new CIDs
        max_new_cid = max(new_widths.keys()) if new_widths else last_char
        if max_new_cid > last_char:
            # Extend with 0-width entries up to the new max
            extra = max_new_cid - last_char
            widths.extend([0] * extra)
            last_char = max_new_cid

        # Set widths for new CIDs
        for cid, width in new_widths.items():
            idx = cid - first_char
            if 0 <= idx < len(widths):
                widths[idx] = width

        # Write back
        new_w = "[" + " ".join(str(int(w)) for w in widths) + "]"
        doc.xref_set_key(font_xref, "Widths", new_w)
        doc.xref_set_key(font_xref, "LastChar", str(last_char))
        logger.info(f"[FONT_AUG] Updated TrueType /Widths (LastChar {first_char}→{last_char})")
    except Exception as e:
        logger.debug(f"[FONT_AUG] TrueType width update skipped: {e}")


def _augment_font_file(doc, font_xref: int, font_tag: str, new_mappings: Dict[str, int]):
    """
    Augment the embedded font's FontFile2 with glyphs from the system font.
    This ensures new CIDs actually render correctly.
    Handles both Type0/CID fonts (via DescendantFonts) and simple TrueType fonts.
    """
    try:
        from fontTools.ttLib import TTFont
        from io import BytesIO

        embedded_font, basefont_name, ff2_xref, is_simple_truetype = _load_embedded_ttfont(doc, font_xref)
        if embedded_font is None:
            return

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

        sys_name_to_gid = {name: idx for idx, name in enumerate(sys_glyph_order)}

        # Get the embedded font's cmap table for updating
        emb_cmap_table = embedded_font.get("cmap")
        emb_cmap_subtables = []
        if emb_cmap_table:
            for subtable in emb_cmap_table.tables:
                if hasattr(subtable, 'cmap') and subtable.cmap:
                    emb_cmap_subtables.append(subtable)

        # Detect glyph naming convention from existing font
        # e.g. "glyph00001" vs "gid00001" vs "cid00001"
        glyph_prefix = "glyph"
        glyph_digits = 5
        for name in emb_glyph_order[1:5]:  # skip .notdef
            import re as _re
            m = _re.match(r'^([a-zA-Z]+)(\d+)$', name)
            if m:
                glyph_prefix = m.group(1)
                glyph_digits = len(m.group(2))
                break

        def _make_glyph_name(idx):
            return f"{glyph_prefix}{idx:0{glyph_digits}d}"

        for char, cid in new_mappings.items():
            code_point = ord(char)
            sys_glyph_name = sys_cmap.get(code_point)
            if sys_glyph_name is None:
                continue

            # Target glyph name in embedded font (by CID/GID)
            if cid < len(emb_glyph_order):
                target_name = emb_glyph_order[cid]
            else:
                target_name = _make_glyph_name(cid)

            # Ensure target slot exists — add placeholder glyphs to glyf/hmtx
            # IMMEDIATELY so the glyf table's internal order matches the font's
            # global glyph order (required for correct loca table compilation).
            if target_name not in emb_glyph_order:
                from fontTools.ttLib.tables._g_l_y_f import Glyph as _Glyph
                while len(emb_glyph_order) <= cid:
                    placeholder = _make_glyph_name(len(emb_glyph_order))
                    emb_glyph_order.append(placeholder)
                    # Add empty glyph to glyf table NOW (not later)
                    empty_g = _Glyph()
                    empty_g.numberOfContours = 0
                    emb_glyf[placeholder] = empty_g
                    emb_hmtx[placeholder] = (0, 0)

            try:
                # Copy glyph outline (deepcopy to avoid cross-font references)
                if sys_glyph_name in sys_glyf:
                    emb_glyf[target_name] = copy.deepcopy(sys_glyf[sys_glyph_name])

                # Copy metrics
                if sys_glyph_name in sys_hmtx.metrics:
                    emb_hmtx[target_name] = sys_hmtx[sys_glyph_name]

                # Update the embedded font's internal cmap to map CID → glyph
                # The CID (not Unicode code point) is used as the byte value in
                # the content stream, so the font's cmap must map CID → glyph.
                for subtable in emb_cmap_subtables:
                    subtable.cmap[cid] = target_name
            except Exception as e:
                logger.debug(f"[FONT_AUG] Failed to copy glyph '{char}': {e}")

        # Verify augmented glyphs have valid metrics (width > 0)
        for char, cid in new_mappings.items():
            if cid < len(emb_glyph_order):
                gname = emb_glyph_order[cid]
                if gname in emb_hmtx.metrics:
                    w, _ = emb_hmtx[gname]
                    if w <= 0:
                        logger.warning(
                            f"[FONT_AUG] Glyph '{char}' (CID {cid}) has zero width after augmentation"
                        )

        # Update font's global glyph order to match extended order
        if len(emb_glyph_order) > len(embedded_font.getGlyphOrder()):
            embedded_font.setGlyphOrder(emb_glyph_order)

        # Save augmented font back to PDF
        try:
            buf = BytesIO()
            embedded_font.save(buf)
            new_font_bytes = buf.getvalue()
            doc.update_stream(ff2_xref, new_font_bytes)
            # Update Length1 if present
            doc.xref_set_key(ff2_xref, "Length1", str(len(new_font_bytes)))
            logger.info(f"[FONT_AUG] Updated FontFile2 → {len(new_font_bytes)} bytes")
        except Exception as e:
            logger.warning(f"[FONT_AUG] Failed to save augmented font: {e}")

    except ImportError:
        logger.debug("[FONT_AUG] fontTools not available for FontFile2 augmentation")
    except Exception as e:
        logger.warning(f"[FONT_AUG] FontFile2 augmentation failed: {e}")


def _pad_skill_replacement(original_content: str, replacement_content: str) -> str:
    """Pad a skill replacement that's too short by appending original skills.

    When the LLM's replacement is significantly shorter than the original,
    continuation lines in the PDF get zeroed, leaving visible gaps.
    Padding the replacement with skills from the original that weren't
    included ensures the text fills the same visual space.
    """
    orig_len = len(original_content)
    rep_len = len(replacement_content)

    if rep_len >= orig_len * 0.85:
        return replacement_content  # Close enough, no padding needed

    # Extract comma-separated skills from both
    orig_skills = [s.strip() for s in original_content.split(",")]
    rep_lower = replacement_content.lower()

    # Find skills in original that aren't already in the replacement
    missing = []
    for skill in orig_skills:
        skill_clean = skill.strip()
        if skill_clean and skill_clean.lower() not in rep_lower:
            missing.append(skill_clean)

    # Append missing skills until we reach 85% of original length
    padded = replacement_content
    for skill in missing:
        if len(padded) >= orig_len * 0.85:
            break
        padded += f", {skill}"

    return padded


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
                    if raw_len >= target_len * threshold:
                        return block_indices
                    # Extend: keep collecting blocks until raw covers the target
                    for k in range(j + 1, min(start + 300, len(content_blocks))):
                        if raw_len >= target_len * threshold:
                            break
                        if k in used_block_indices:
                            continue
                        bk = content_blocks[k]
                        if not bk.text_ops:
                            continue
                        tk = bk.full_text
                        if not tk:
                            continue
                        concat_raw += tk
                        block_indices.append(k)
                        raw_len = len(" ".join(concat_raw.replace("\u200b", "").split()).strip())
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


def replace_text_in_pdf(pdf_path: str, replacements: Dict[str, str]) -> bool:
    """Replace arbitrary text in a PDF using content-stream-level patching.

    Unlike fitz redaction, this preserves:
    - Original fonts (no font substitution)
    - Adjacent text on the same line
    - Exact positioning

    Uses fitz for reading/parsing (CMap, widths, content streams) and
    pikepdf for the actual byte-level patching.

    Args:
        pdf_path: Path to PDF file (modified in place)
        replacements: Dict of {original_text: new_text}

    Returns:
        True if any replacements were made.
    """
    import fitz
    import pikepdf

    # Phase 1: Use fitz to build CMap/width data and parse content blocks
    fitz_doc = fitz.open(pdf_path)
    cmap_mgr = _CMapManager(fitz_doc)
    width_calc = _WidthCalculator(fitz_doc)

    if not cmap_mgr.font_cmaps:
        fitz_doc.close()
        return False

    # Phase 2: Use pikepdf for content stream parsing and patching
    pike_doc = pikepdf.open(pdf_path, allow_overwriting_input=True)
    modified = False

    for page_num in range(len(pike_doc.pages)):
        pike_page = pike_doc.pages[page_num]

        # Parse content streams for this page
        all_blocks: List[ContentBlock] = []
        if hasattr(pike_page, "Contents"):
            contents = pike_page.Contents
            if isinstance(contents, pikepdf.Array):
                for item in contents:
                    xref = item.objgen[0]
                    raw = item.read_bytes()
                    blocks = _parse_content_stream(raw, cmap_mgr, page_num, xref)
                    all_blocks.extend(blocks)
            else:
                xref = contents.objgen[0]
                raw = contents.read_bytes()
                all_blocks = _parse_content_stream(raw, cmap_mgr, page_num, xref)

        if not all_blocks:
            continue

        used_indices: set = set()
        stream_patches: Dict[int, List[Tuple[int, int, bytes]]] = {}

        for orig_text, new_text in replacements.items():
            block_indices = _find_blocks_for_text(
                all_blocks, orig_text, "", used_indices
            )
            if not block_indices:
                continue

            first_block = all_blocks[block_indices[0]]
            actual_font = first_block.font_tag
            font_data = cmap_mgr.font_cmaps.get(actual_font, {})
            byte_width = font_data.get("byte_width", 2)
            hex_per_char = byte_width * 2

            # Encode new text
            hex_encoded, missing = cmap_mgr.encode_text(actual_font, new_text)
            if missing:
                # Try font augmentation for missing chars
                font_aug = _FontAugmentor()
                font_name = cmap_mgr.font_names.get(actual_font, "")
                fitz_page = fitz_doc[page_num]
                resolved = font_aug.resolve_missing_chars(
                    fitz_doc, fitz_page, actual_font, font_name, missing,
                    cmap_mgr, width_calc,
                )
                if resolved:
                    hex_encoded, still_missing = cmap_mgr.encode_text(actual_font, new_text)
                    if still_missing:
                        logger.warning(f"[HEADER] Still missing chars for '{orig_text}' → '{new_text}', skipping")
                        continue
                else:
                    logger.warning(f"[HEADER] Font augmentation failed for '{orig_text}' → '{new_text}', skipping")
                    continue

            if not hex_encoded:
                continue

            # Collect original hex from matched blocks
            orig_hex_parts = []
            for bi in block_indices:
                for op in all_blocks[bi].text_ops:
                    orig_hex_parts.append(op.hex_string)
            orig_hex = "".join(orig_hex_parts)

            # Calculate width adjustment (Tc)
            widths_map = width_calc.font_widths.get(actual_font, {})
            default_w = width_calc._default_widths.get(actual_font, 1000.0)

            def _calc_w(h: str) -> float:
                t = 0.0
                for ci in range(0, len(h), hex_per_char):
                    if ci + hex_per_char > len(h):
                        break
                    cid = int(h[ci:ci + hex_per_char], 16)
                    t += widths_map.get(cid, default_w)
                return t

            orig_w = _calc_w(orig_hex)
            new_w = _calc_w(hex_encoded)
            font_size = first_block.font_size or 12.0
            n_chars = max(1, len(hex_encoded) // hex_per_char)

            tc_val = 0.0
            if n_chars > 0 and orig_w > 0:
                tc_val = font_size * (orig_w - new_w) / (1000.0 * n_chars)
                # Tight clamp matching the main distribution path.
                # Only negative Tc (squeeze) — never stretch shorter text.
                tc_limit = 0.02 * font_size
                tc_val = max(-tc_limit, min(0, tc_val))

            # Trim trailing words if replacement is too wide for Tc to handle
            if n_chars > 0 and orig_w > 0 and new_w > orig_w:
                budget_w = orig_w + tc_limit * n_chars * 1000.0 / font_size
                if new_w > budget_w:
                    trim_words = new_text.split()
                    while len(trim_words) > 1:
                        trim_words.pop()
                        trimmed = " ".join(trim_words)
                        t_hex, _ = cmap_mgr.encode_text(actual_font, trimmed)
                        if t_hex:
                            t_w = _calc_w(t_hex)
                            if t_w <= budget_w:
                                new_text = trimmed
                                hex_encoded = t_hex
                                new_w = t_w
                                n_chars = max(1, len(hex_encoded) // hex_per_char)
                                tc_val = font_size * (orig_w - new_w) / (1000.0 * n_chars)
                                tc_val = max(-tc_limit, min(0, tc_val))
                                break

            # Build replacement bytes
            tc_prefix = f"{tc_val:.4f} Tc ".encode() if abs(tc_val) > 0.001 else b""
            tc_reset = b"0 Tc " if abs(tc_val) > 0.001 else b""
            uses_literal = first_block.text_ops[0].is_literal if first_block.text_ops else False

            if uses_literal:
                # Type1 literal string replacement
                words = new_text.split()
                if len(words) <= 1:
                    w_hex, _ = cmap_mgr.encode_text(actual_font, new_text)
                    lit_bytes = b"(" + bytes(
                        int(w_hex[i:i+2], 16) for i in range(0, len(w_hex), 2)
                    ) + b")"
                else:
                    parts = []
                    for wi, word in enumerate(words):
                        w_hex, _ = cmap_mgr.encode_text(actual_font, word)
                        if w_hex:
                            parts.append(b"(" + bytes(
                                int(w_hex[i:i+2], 16) for i in range(0, len(w_hex), 2)
                            ) + b")")
                            if wi < len(words) - 1:
                                parts.append(b" -333 ")
                    lit_bytes = b"".join(parts) if parts else b"()"

                first_op = first_block.text_ops[0]
                new_content = tc_prefix + lit_bytes + b" " + tc_reset
                xref = first_block.stream_xref
                if xref not in stream_patches:
                    stream_patches[xref] = []
                stream_patches[xref].append((first_op.byte_offset, first_op.byte_length, new_content))
            else:
                # Hex string replacement
                new_hex_bytes = tc_prefix + b"<" + hex_encoded.encode() + b">" + b" " + tc_reset

                first_op = first_block.text_ops[0]
                xref = first_block.stream_xref
                if xref not in stream_patches:
                    stream_patches[xref] = []
                stream_patches[xref].append((first_op.byte_offset, first_op.byte_length, new_hex_bytes))

                # Zero out subsequent blocks
                for bi in block_indices[1:]:
                    blk = all_blocks[bi]
                    for op in blk.text_ops:
                        empty = b"<" + b"0" * len(op.hex_string) + b">"
                        if blk.stream_xref not in stream_patches:
                            stream_patches[blk.stream_xref] = []
                        stream_patches[blk.stream_xref].append((op.byte_offset, op.byte_length, empty))

            used_indices.update(block_indices)
            modified = True
            logger.info(f"[HEADER] Replaced '{orig_text}' → '{new_text}' using font {actual_font}")

        # Apply all patches for this page
        for xref, patches in stream_patches.items():
            raw = bytes(pike_doc.get_object(xref).read_bytes())
            patches.sort(key=lambda p: p[0], reverse=True)
            for offset, old_len, new_bytes in patches:
                raw = raw[:offset] + new_bytes + raw[offset + old_len:]
            pike_doc.get_object(xref).write(raw, filter=pikepdf.Name("/FlateDecode"))

    fitz_doc.close()
    if modified:
        pike_doc.save(pdf_path)
    pike_doc.close()
    return modified


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
    kern_reader: Optional[_KerningReader] = None,
    header_replacements: Optional[Dict[str, str]] = None,
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

    # ── Compute right text margin from PyMuPDF bboxes (accurate) ──
    # PyMuPDF's text extraction accounts for actual font metrics, CTM
    # transforms, and all rendering details — far more accurate than
    # computing from our content stream width maps (which can overestimate
    # by 30%+ due to default_w fallback and missing CID-to-width mappings).
    page_w = page.rect.width
    right_margin_pts = page_w - 36.0  # Default: 0.5" right margin

    _max_right_pymupdf = 0.0
    try:
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for tblock in text_dict.get("blocks", []):
            if tblock.get("type") != 0:  # Skip image blocks
                continue
            for tline in tblock.get("lines", []):
                for tspan in tline.get("spans", []):
                    if tspan.get("text", "").strip():
                        span_right = tspan["bbox"][2]
                        # Sanity: must be within page bounds
                        if 0 < span_right <= page_w + 1:
                            _max_right_pymupdf = max(_max_right_pymupdf, span_right)
    except Exception as e:
        logger.warning(f"[PATCH] PyMuPDF text extraction failed: {e}")

    if _max_right_pymupdf > 0:
        right_margin_pts = _max_right_pymupdf
    logger.info(f"[PATCH] Page {page_num}: right_margin_pts={right_margin_pts:.1f} (page_w={page_w:.1f})")

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

        if extension:
            logger.info(
                f"[PATCH] {label}: extended by {len(extension)} tail-end blocks"
            )
            block_indices.extend(extension)

        # Mark blocks as used
        used_block_indices.update(block_indices)

        # Determine the font from the first matching block
        first_block = all_content_blocks[block_indices[0]]
        actual_font = first_block.font_tag

        # Encode new text to hex CIDs
        hex_encoded, missing_chars = cmap_mgr.encode_text(actual_font, new_text)

        # Handle missing characters via font augmentation
        if missing_chars:
            font_name = cmap_mgr.font_names.get(actual_font, "")
            logger.info(
                f"[PATCH] Font {actual_font} ({font_name}) missing {len(missing_chars)} chars "
                f"for {label}"
            )
            resolved = font_aug.resolve_missing_chars(
                doc, page, actual_font, font_name, missing_chars,
                cmap_mgr, width_calc,
            )
            if resolved:
                hex_encoded, still_missing = cmap_mgr.encode_text(actual_font, new_text)
                if still_missing:
                    logger.warning(f"[PATCH] Still missing chars after augmentation, skipping")
                    return False
                # Update PDF font structures
                new_mappings = {
                    ch: cmap_mgr.font_cmaps[actual_font]["rev"][ch]
                    for ch in missing_chars
                    if ch in cmap_mgr.font_cmaps.get(actual_font, {}).get("rev", {})
                }
                new_widths = {
                    cid: width_calc.font_widths.get(actual_font, {}).get(cid, 500.0)
                    for cid in new_mappings.values()
                }
                _update_pdf_font_structures(doc, page, actual_font, new_mappings, new_widths)
            else:
                logger.warning(f"[PATCH] Font augmentation failed, skipping {label}")
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

        def _trim_text_to_fit(
            text: str, orig_hex: str, font_tag: str, font_size: float,
            orig_w_override: float = 0.0,
            use_kerned_tj: bool = False,
        ) -> str:
            """Smart-trim text to fit within width budget.

            Zero-Tc policy: text must fit within budget (no Tc squeeze).
            Uses clause-level truncation (prefer commas/semicolons) and
            dangling-word removal so the result is always a complete thought.

            If orig_w_override > 0, use that as the target width instead
            of computing from orig_hex.
            """
            if not text or (not orig_hex and orig_w_override <= 0):
                return text
            full_hex, _ = cmap_mgr.encode_text(font_tag, text)
            if not full_hex:
                return text
            orig_w = orig_w_override if orig_w_override > 0 else _calc_hex_width(orig_hex)
            new_w = _calc_hex_width(full_hex)
            if orig_w <= 0:
                return text
            # Zero-Tc policy: text must fit within original width.
            # Allow 3% tolerance for per-pair kerning TJ adjustments.
            tolerance = orig_w * 0.03 if use_kerned_tj else 0
            if new_w <= orig_w + tolerance:
                return text  # Fits fine
            def _fits(t: str) -> bool:
                h, _ = cmap_mgr.encode_text(font_tag, t)
                return bool(h) and _calc_hex_width(h) <= orig_w + tolerance

            # Strategy 1: clause boundary (only if preserves >60% of text)
            # Cuts at the last comma/semicolon that produces a complete thought.
            text_len = len(text)
            for delim in ['; ', ', ']:
                didx = text.rfind(delim)
                if didx > text_len * 0.6:  # Must preserve >60%
                    candidate = text[:didx].strip()
                    if len(candidate.split()) >= 4 and not _has_incomplete_ending(candidate, strict=False):
                        if _fits(candidate):
                            logger.debug(f"[TRIM] Clause boundary: {text_len}→{len(candidate)}")
                            return candidate

            # Strategy 2: word-by-word removal with CONSERVATIVE dangling cleanup
            # Uses strict=False so only true function words (prepositions, articles,
            # conjunctions) are stripped.  This prevents the trimmer from rejecting
            # valid stopping points like "...data transfer process" or "...technical support".
            best_fit = None
            words = text.split()
            while len(words) > 1:
                words.pop()
                # Remove trailing function words only (conservative set)
                while len(words) > 2 and _has_incomplete_ending(' '.join(words), strict=False):
                    words.pop()
                trimmed = " ".join(words).rstrip(" ,;:")
                # Close unclosed parentheses
                open_parens = trimmed.count("(") - trimmed.count(")")
                if open_parens > 0:
                    trimmed += ")" * open_parens
                if not trimmed or len(trimmed.split()) < 2:
                    continue
                if _fits(trimmed):
                    logger.debug(f"[TRIM] Word removal: {text_len}→{len(trimmed)}")
                    return trimmed

            # Strategy 3: HARD fallback with best-effort completeness.
            # Pop words until text fits, but still try to avoid dangling
            # prepositions/articles at the end.
            words = text.split()
            while len(words) > 1:
                words.pop()
                # Try to clean up the ending (best effort, not mandatory)
                candidate_words = list(words)
                while (len(candidate_words) > 2
                       and candidate_words[-1].lower().rstrip(" ,;:") in _TRIM_DANGLING_WORDS):
                    candidate_words.pop()
                trimmed = " ".join(candidate_words).rstrip(" ,;:")
                if trimmed and _fits(trimmed):
                    logger.warning(f"[TRIM] Hard fallback (cleaned): {text_len}→{len(trimmed)}")
                    return trimmed
                # If cleaned version doesn't fit, try uncleaned
                trimmed = " ".join(words).rstrip(" ,;:")
                if not trimmed:
                    continue
                if _fits(trimmed):
                    logger.warning(f"[TRIM] Hard fallback: {text_len}→{len(trimmed)}")
                    return trimmed
            return text

        def _build_kerned_hex_content(
            text: str, font_tag: str, hex_encoded: str,
            orig_width_1000: float, font_size: float,
        ) -> tuple:
            """Build TJ array content with per-pair kerning from GPOS/kern tables.

            Instead of a monolithic <hex_blob>, produces content like:
              <seg1> 25 <seg2> -10 <seg3>
            where numbers are TJ adjustment values (1/1000 text space units).

            Returns (content_bytes, used_kerning: bool).
            If used_kerning is False, caller should fall back to Tc approach.
            """
            if kern_reader is None:
                return f"<{hex_encoded}>".encode("latin-1"), False

            # Split hex into per-character CID chunks
            chars = [hex_encoded[i:i + hex_per_char]
                     for i in range(0, len(hex_encoded), hex_per_char)]
            if len(chars) <= 1:
                return f"<{hex_encoded}>".encode("latin-1"), False

            # Look up per-pair kerning values
            kern_values = []
            has_any_kern = False
            for i in range(len(chars) - 1):
                cid_a = int(chars[i], 16)
                cid_b = int(chars[i + 1], 16)
                k = kern_reader.get_pair_kern(font_tag, cid_a, cid_b)
                kern_values.append(k)
                if abs(k) > 0.01:
                    has_any_kern = True

            # If font has NO kerning data at all, return monolithic hex blob.
            # Splitting into per-character segments with synthetic residual
            # kerning destroys the natural glyph spacing and causes visual
            # squeeze/expansion artifacts.  Let the font's built-in /Widths
            # handle spacing naturally (zero-Tc policy trims text to fit).
            if not has_any_kern:
                return f"<{hex_encoded}>".encode("latin-1"), False

            # Calculate natural width (in 1/1000 text space units)
            glyph_widths = [widths_map.get(int(c, 16), default_w) for c in chars]
            # TJ positive = shift left = reduces rendered width
            natural_width = sum(glyph_widths) - sum(kern_values)

            # Distribute residual across gaps
            num_gaps = len(chars) - 1
            if orig_width_1000 > 0 and num_gaps > 0:
                residual = (natural_width - orig_width_1000) / num_gaps
                # Clamp per-gap adjustment: ±30 in 1/1000 units (~0.3pt at 10pt)
                residual = max(-30.0, min(30.0, residual))
            else:
                residual = 0.0

            # Build compact TJ content: merge consecutive near-zero-kern chars
            # into single hex segments for compactness
            segments = []  # list of (hex_chunk, kern_after_or_None)
            current_hex = chars[0]
            for i in range(num_gaps):
                total_k = kern_values[i] + residual
                if abs(total_k) < 5:
                    # Near-zero: merge into same segment
                    current_hex += chars[i + 1]
                else:
                    segments.append((current_hex, int(round(total_k))))
                    current_hex = chars[i + 1]
            segments.append((current_hex, None))  # Last segment, no trailing kern

            # Serialize to bytes
            parts = []
            for hex_chunk, kern_after in segments:
                parts.append(f"<{hex_chunk}>")
                if kern_after is not None:
                    parts.append(str(kern_after))
            content = " ".join(parts)
            return content.encode("latin-1"), True

        def _inject_width_adjustment(
            op: TextOp, xref: int, orig_hex: str, new_hex: str,
            content_bytes: bytes, font_size: float = 10.0,
            orig_w_override: float = 0.0,
            use_kerned_content: bool = False,
        ) -> bytes:
            """Reset Tc to zero for all replacements (zero-squeeze policy).

            Text is pre-trimmed by _trim_text_to_fit() to fit within original
            width. Per-pair kerning (when available) handles natural spacing
            via TJ array values. No Tc compensation is ever applied.

            The 0 Tc reset prevents any inherited Tc from the original content
            stream from affecting our replacement text.
            """
            adj_bytes = b" 0 Tc "
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
        #
        # MULTI-FONT SAFETY: If matched blocks span multiple fonts, check
        # CMap compatibility. Compatible fonts (same CID encoding, e.g. Bold
        # and Regular variants of the same CID font) can be encoded normally.
        # Incompatible fonts (different CID mappings, e.g. 1-byte TrueType
        # subsets) must be skipped to avoid garbled text.
        empty_bytes = b"()" if uses_literal else b"<>"
        y_groups: Dict[float, List[int]] = {}  # rounded_y → [block_index, ...]
        other_font_blocks: List[int] = []  # blocks in incompatible fonts

        # Helper: check if two fonts have compatible CMaps
        def _cmaps_compatible(font_a: str, font_b: str) -> bool:
            rev_a = cmap_mgr.font_cmaps.get(font_a, {}).get("rev", {})
            rev_b = cmap_mgr.font_cmaps.get(font_b, {}).get("rev", {})
            if not rev_a or not rev_b:
                return False
            # Compare CIDs for common characters
            test_chars = "aeioustrnl0123456789 .,;:-"
            matches = checked = 0
            for ch in test_chars:
                if ch in rev_a and ch in rev_b:
                    checked += 1
                    if rev_a[ch] == rev_b[ch]:
                        matches += 1
            # Need at least 5 shared chars, 80%+ same CID = compatible
            return checked >= 5 and matches / checked >= 0.8

        has_incompatible_fonts = False
        for bi in block_indices:
            block = all_content_blocks[bi]
            if block.font_tag != actual_font:
                if _cmaps_compatible(actual_font, block.font_tag):
                    pass  # Compatible CMap — safe to encode with primary font
                else:
                    other_font_blocks.append(bi)
                    has_incompatible_fonts = True
            y_key = round(block.y, 1)
            if y_key not in y_groups:
                y_groups[y_key] = []
            y_groups[y_key].append(bi)

        if has_incompatible_fonts:
            logger.info(
                f"[PATCH] {label}: {len(other_font_blocks)} blocks in incompatible "
                f"fonts — will zero them and write text to primary-font blocks only"
            )

        # If ALL blocks were filtered out, we can't patch anything
        if not y_groups:
            logger.warning(f"[PATCH] {label}: no blocks in primary font {actual_font}, skipping")
            return False

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

        if len(sorted_y_keys) > 1:
            # Multi-line: GREEDY WORD-FILL across y-groups.
            # Fills each visual line to its width budget before moving to
            # the next line.  Only the LAST line may be short.  This matches
            # how word processors reflow text and eliminates the "every line
            # equally short" artefact of proportional distribution.

            # ── Step 1: Build per-line width budgets ──
            # The budget for each y-group must include ALL blocks on the line
            # (including incompatible-font blocks), because those blocks will
            # be zeroed and their visual space is available for our text.
            # We compute each block's width using its OWN font's width map.
            y_budgets: List[dict] = []  # one dict per y-group
            for y_key in sorted_y_keys:
                group_blocks = y_groups[y_key]

                # Collect primary-font hex (for Tc reference in same-font lines)
                line_orig_hex = ""
                for bi in group_blocks:
                    if bi in other_font_blocks:
                        continue
                    block = all_content_blocks[bi]
                    for op in block.text_ops:
                        line_orig_hex += op.hex_string

                primary_w = _calc_hex_width(line_orig_hex)

                # Compute FULL line width across ALL fonts (for budget).
                # Incompatible-font blocks use their own font's width map.
                full_line_w = primary_w
                for bi in group_blocks:
                    if bi not in other_font_blocks:
                        continue  # Already counted in primary_w
                    block = all_content_blocks[bi]
                    blk_font = block.font_tag
                    blk_widths = width_calc.font_widths.get(blk_font, {})
                    blk_default = width_calc._default_widths.get(blk_font, default_w)
                    for op in block.text_ops:
                        for ci in range(0, len(op.hex_string), hex_per_char):
                            if ci + hex_per_char > len(op.hex_string):
                                break
                            cid = int(op.hex_string[ci:ci + hex_per_char], 16)
                            full_line_w += blk_widths.get(cid, blk_default)

                # Write target = prefer LEFTMOST block, but inject font switch
                # if it's not the primary font.  Compatible fonts (e.g. Bold
                # and Regular variants) may share CMap encoding but have
                # different font-file SUBSETS — the bold subset might lack
                # glyphs like "3" that the regular subset has.  A font switch
                # tells the renderer to use the primary font's glyphs.
                write_bi = group_blocks[0]
                write_blk = all_content_blocks[write_bi]
                fs = write_blk.font_size if write_blk.text_ops else 10.0
                needs_font_switch = (write_blk.font_tag != actual_font)

                y_budgets.append({
                    "y_key": y_key,
                    "blocks": group_blocks,
                    "orig_hex": line_orig_hex,
                    "primary_w": primary_w,
                    "full_line_w": full_line_w,
                    "fs": fs,
                    "write_bi": write_bi,
                    "needs_font_switch": needs_font_switch,
                })

            # ── Compute width budgets ──
            # We compute margin_w_real from PyMuPDF right margin (accurate).
            # We also have full_line_w from content stream hex (may over- or
            # under-estimate due to default_w fallback).
            #
            # The ratio = full_line_w / margin_w_real tells us the width map
            # distortion:
            #   ratio > 1 → width map overestimates → word measurements also
            #     overestimate → budget must be inflated to match
            #   ratio <= 1 → width map is accurate or underestimates →
            #     margin_w_real is trustworthy, use it directly
            #
            # CRITICAL: Use MAX ratio across ALL y-groups, not just the first.
            # The first line often doesn't fill to the margin (natural word-wrap),
            # giving a misleadingly low ratio (e.g. 0.76 instead of 0.91).
            # The fullest line gives the most accurate width calibration.
            if y_budgets:
                _width_ratio = 0.0
                for _ref in y_budgets:
                    _ref_x = all_content_blocks[_ref["write_bi"]].x
                    _ref_margin_real = (right_margin_pts - _ref_x) * 1000.0 / max(_ref["fs"], 1.0)
                    if _ref_margin_real > 0 and _ref["full_line_w"] > 0:
                        _ratio = _ref["full_line_w"] / _ref_margin_real
                        if _ratio > _width_ratio:
                            _width_ratio = _ratio
                if _width_ratio <= 0:
                    _width_ratio = 1.0
            else:
                _width_ratio = 1.0

            for _bud in y_budgets:
                _bud_x = all_content_blocks[_bud["write_bi"]].x
                _bud_avail = max(0, right_margin_pts - _bud_x)
                _margin_w_real = _bud_avail * 1000.0 / max(_bud["fs"], 1.0)
                if _width_ratio > 1.0:
                    # Width map overestimates — inflate budget to match
                    _inflation = min(_width_ratio, 2.0)
                    _bud["max_w"] = max(_bud["full_line_w"], _margin_w_real * _inflation)
                else:
                    # ratio <= 1.0 means the CID width map is accurate (or slightly
                    # under-reports).  The original text not filling to the margin is
                    # normal word-wrap, NOT a width calibration signal.
                    # Use full margin_w_real so the greedy fill can use all available
                    # space.  Downstream Tc correction (±0.15/char) and _trim_text_to_fit
                    # handle any minor overflows.
                    _bud["max_w"] = _margin_w_real

            # Log budget summary
            if y_budgets:
                logger.info(
                    f"[PATCH] {label}: {len(y_budgets)} y-groups, "
                    f"max_w=[{', '.join(str(int(b['max_w'])) for b in y_budgets)}], "
                    f"width_ratio={_width_ratio:.2f}"
                )

            # ── Step 2: Measure space width in font units ──
            space_hex, _ = cmap_mgr.encode_text(actual_font, " ")
            space_w = _calc_hex_width(space_hex) if space_hex else default_w

            # ── Step 2b: Pre-distribution pixel check ──
            # The LLM generates text based on CHARACTER budget, but character
            # count is a poor proxy for pixel width (proportional fonts).
            # BEFORE greedy fill, measure the full text's pixel width and
            # compare to total available budget.  If it overflows, truncate
            # at a sentence/clause boundary to preserve a complete thought.
            _total_budget = sum(b["max_w"] for b in y_budgets)
            _full_hex, _ = cmap_mgr.encode_text(actual_font, new_text)
            _full_w = _calc_hex_width(_full_hex) if _full_hex else 0
            if _full_w > _total_budget and _total_budget > 0:
                _overflow_pct = (_full_w / _total_budget - 1) * 100
                logger.info(
                    f"[PRE-TRIM] {label}: text pixel width {_full_w:.0f} exceeds "
                    f"total budget {_total_budget:.0f} by {_overflow_pct:.1f}%, "
                    f"truncating to clause boundary"
                )
                # Try sentence boundary first (period followed by space or end)
                _best = None
                for _delim in ['. ', '; ', ', ']:
                    _pos = new_text.rfind(_delim)
                    while _pos > len(new_text) * 0.3:
                        _candidate = new_text[:_pos].rstrip(" ,;:")
                        if _delim == '. ':
                            _candidate = new_text[:_pos + 1]  # Keep the period
                        _c_hex, _ = cmap_mgr.encode_text(actual_font, _candidate)
                        _c_w = _calc_hex_width(_c_hex) if _c_hex else 0
                        if (_c_w <= _total_budget
                                and len(_candidate.split()) >= 4
                                and not _has_incomplete_ending(_candidate, strict=False)):
                            _best = _candidate
                            break
                        # Try next occurrence of this delimiter
                        _pos = new_text.rfind(_delim, 0, _pos)
                    if _best:
                        break
                if _best:
                    logger.info(
                        f"[PRE-TRIM] {label}: truncated {len(new_text)}→{len(_best)} chars: "
                        f"'...{_best[-40:]}'"
                    )
                    new_text = _best
                else:
                    # Fallback: word-by-word removal with dangling cleanup
                    _words = new_text.split()
                    while len(_words) > 3:
                        _words.pop()
                        while (len(_words) > 2
                               and _has_incomplete_ending(' '.join(_words), strict=False)):
                            _words.pop()
                        _try = " ".join(_words).rstrip(" ,;:")
                        _t_hex, _ = cmap_mgr.encode_text(actual_font, _try)
                        _t_w = _calc_hex_width(_t_hex) if _t_hex else 0
                        if _t_w <= _total_budget:
                            new_text = _try
                            logger.info(
                                f"[PRE-TRIM] {label}: word-trim {len(new_text)}→{len(_try)} chars"
                            )
                            break

            # ── Step 3: Greedy word-fill distribution ──
            # Uses _calc_hex_width for per-word measurement (CID-based, same
            # coordinate system as _trim_text_to_fit). The budget max_w is
            # also in CID units (inflated by _width_ratio when > 1.0).
            words = new_text.split()
            line_assignments: List[Optional[str]] = [None] * len(y_budgets)
            word_idx = 0
            num_groups = len(y_budgets)

            for gi in range(num_groups):
                if word_idx >= len(words):
                    break
                budget = y_budgets[gi]
                is_last = (gi == num_groups - 1)
                line_words: List[str] = []
                line_w = 0.0

                while word_idx < len(words):
                    word = words[word_idx]
                    w_hex, _ = cmap_mgr.encode_text(actual_font, word)
                    word_w = _calc_hex_width(w_hex) if w_hex else default_w * len(word)

                    if not line_words:
                        line_words.append(word)
                        line_w = word_w
                        word_idx += 1
                    else:
                        test_w = line_w + space_w + word_w
                        if test_w <= budget["max_w"]:
                            line_words.append(word)
                            line_w = test_w
                            word_idx += 1
                        else:
                            break  # Budget exceeded — stop filling this line

                if line_words:
                    line_assignments[gi] = " ".join(line_words)
                    logger.debug(
                        f"[GREEDY] {label} line {gi}: {len(line_words)} words, "
                        f"line_w={line_w:.0f}, max_w={budget['max_w']:.0f}, "
                        f"fill={line_w/budget['max_w']*100:.1f}%"
                    )

            # If words remain after all groups filled, drop them.
            # Blindly appending overflow to the last line caused 25-135%
            # width overflow → _trim_text_to_fit chopped sentences mid-thought.
            # Dropping overflow words loses a few words at the end, but
            # _trim_text_to_fit can handle minor adjustments without
            # destroying sentence completeness.
            if word_idx < len(words):
                dropped = words[word_idx:]
                logger.info(
                    f"[GREEDY] {label}: dropping {len(dropped)} overflow words "
                    f"({' '.join(dropped[:5])}{'...' if len(dropped) > 5 else ''})"
                )
                # Clean up the last used line's ending — dropping words may
                # leave it ending mid-sentence.
                for gi in range(num_groups - 1, -1, -1):
                    if line_assignments[gi] is not None:
                        _last_text = line_assignments[gi]
                        if len(dropped) > 3:
                            # Heavy overflow (>3 words dropped): sentence is badly
                            # broken.  Cut at last clause boundary (comma/semicolon)
                            # which produces a shorter but COMPLETE thought.
                            for _delim in ['; ', ', ']:
                                _cidx = _last_text.rfind(_delim)
                                if _cidx > len(_last_text) * 0.3:
                                    _candidate = _last_text[:_cidx].rstrip(" ,;:")
                                    if (len(_candidate.split()) >= 3
                                            and not _has_incomplete_ending(_candidate, strict=False)):
                                        _last_text = _candidate
                                        logger.info(
                                            f"[GREEDY] {label}: clause-cut last line "
                                            f"after {len(dropped)} words dropped"
                                        )
                                        break
                        # Always clean up dangling words as final pass
                        _last_words = _last_text.split()
                        while (len(_last_words) > 2
                               and _has_incomplete_ending(' '.join(_last_words), strict=False)):
                            _last_words.pop()
                        line_assignments[gi] = " ".join(_last_words).rstrip(" ,;:")
                        break

            # ── Step 3b: Balanced redistribution if text underflows ──
            # If greedy fill left empty y-groups, the zeroed lines create
            # visible vertical gaps (their positioning operators still
            # occupy space).  Redistribute text across ALL y-groups so
            # every line gets content and no phantom gaps appear.
            #
            # BUT: don't redistribute if it would create orphan lines
            # (< 3 words on any line).  A 1-word orphan ("improvements",
            # "50%") looks far worse than a small vertical gap.
            MIN_WORDS_PER_LINE = 3
            used_count = sum(1 for la in line_assignments if la is not None)
            # Also check: is there enough total text to fill at least 60% of
            # each line? If not, redistribution spreads thin text even thinner
            # (e.g., 15 words → 12 + 3, where line 1 gets "microservices workflows").
            # In that case, keep text on line 0 where it at least fills one line fully.
            _total_text_w = sum(
                (_calc_hex_width(cmap_mgr.encode_text(actual_font, w)[0])
                 if cmap_mgr.encode_text(actual_font, w)[0] else default_w * len(w))
                for w in words
            ) + space_w * max(0, len(words) - 1)
            _total_budget_w = sum(b["max_w"] for b in y_budgets)
            _fill_ratio = _total_text_w / _total_budget_w if _total_budget_w > 0 else 0
            if (used_count < num_groups
                    and len(words) >= num_groups * MIN_WORDS_PER_LINE
                    and _fill_ratio >= 0.60):
                # Pre-compute per-word widths (CID-based, same as greedy fill)
                word_widths_list: List[float] = []
                for w in words:
                    w_hex, _ = cmap_mgr.encode_text(actual_font, w)
                    word_widths_list.append(
                        _calc_hex_width(w_hex) if w_hex else default_w * len(w)
                    )
                total_available_w = sum(b["max_w"] for b in y_budgets)
                target_per_line = total_available_w / num_groups

                line_assignments = [None] * num_groups
                word_idx = 0
                for gi in range(num_groups):
                    if word_idx >= len(words):
                        break
                    is_last_group = (gi == num_groups - 1)
                    line_words_b: List[str] = []
                    line_w_b = 0.0

                    while word_idx < len(words):
                        ww = word_widths_list[word_idx]

                        if not line_words_b:
                            line_words_b.append(words[word_idx])
                            line_w_b = ww
                            word_idx += 1
                            continue

                        if is_last_group:
                            line_words_b.append(words[word_idx])
                            line_w_b += space_w + ww
                            word_idx += 1
                            continue

                        # Must save at least MIN_WORDS_PER_LINE words per future line
                        words_left = len(words) - word_idx
                        lines_after = num_groups - gi - 1
                        if words_left <= lines_after * MIN_WORDS_PER_LINE:
                            break

                        # Break when past target width for this line
                        new_w = line_w_b + space_w + ww
                        if new_w > target_per_line:
                            break

                        line_words_b.append(words[word_idx])
                        line_w_b = new_w
                        word_idx += 1

                    if line_words_b:
                        line_assignments[gi] = " ".join(line_words_b)

                logger.info(
                    f"[PATCH] {label}: Balanced redistribution — "
                    f"{used_count}/{num_groups} lines used → "
                    f"{sum(1 for la in line_assignments if la is not None)}"
                    f"/{num_groups} lines"
                )

            # ── Step 3c: Rebalance orphan last lines ──
            # After greedy fill, the last line may have just 1-2 words
            # (e.g. "reliability.") while the previous line is packed.
            # Move words from earlier lines to the last to balance.
            last_used = -1
            for gi in range(num_groups - 1, -1, -1):
                if line_assignments[gi] is not None:
                    last_used = gi
                    break
            if last_used > 0 and line_assignments[last_used] is not None:
                last_words = line_assignments[last_used].split()
                prev_words = (line_assignments[last_used - 1] or "").split()
                # If last line has < 3 words and previous line has > 5 words,
                # shift words from prev to last to balance
                if len(last_words) < 3 and len(prev_words) > 5:
                    # Target: move enough words so last line has >= 3 words
                    # but prev line keeps >= 4 words
                    words_to_move = min(3, len(prev_words) - 4)
                    if words_to_move > 0:
                        moved = prev_words[-words_to_move:]
                        prev_words = prev_words[:-words_to_move]
                        line_assignments[last_used - 1] = " ".join(prev_words)
                        line_assignments[last_used] = " ".join(moved + last_words)
                        logger.info(
                            f"[PATCH] {label}: Rebalanced orphan last line — "
                            f"moved {words_to_move} words, "
                            f"prev={len(prev_words)} words, last={len(moved + last_words)} words"
                        )

            # ── Step 3d: Dangling-word cleanup on last used line ──
            # After distribution, the last line may end with a dangling
            # preposition/conjunction/article. Strip it so bullets
            # always end with a complete thought.
            for gi in range(num_groups - 1, -1, -1):
                if line_assignments[gi] is not None:
                    _la_words = line_assignments[gi].split()
                    changed = False
                    while (len(_la_words) > 2
                           and _has_incomplete_ending(' '.join(_la_words), strict=False)):
                        _la_words.pop()
                        changed = True
                    if changed:
                        line_assignments[gi] = " ".join(_la_words).rstrip(" ,;:")
                        logger.debug(f"[PATCH] {label}: Removed dangling word from last line")
                    break

            # ── Step 4: Apply patches ──
            for gi, budget in enumerate(y_budgets):
                group_blocks = budget["blocks"]
                line_text = line_assignments[gi]

                if not line_text:
                    # Zero out all blocks in this unused y-group
                    for bi in group_blocks:
                        block = all_content_blocks[bi]
                        for op in block.text_ops:
                            queue_patch(block.stream_xref, op.byte_offset,
                                        op.byte_length, empty_bytes)
                    continue

                write_bi = budget["write_bi"]
                write_blk = all_content_blocks[write_bi]
                fs_line = budget["fs"]
                line_orig_hex = budget["orig_hex"]
                full_line_w = budget["full_line_w"]
                needs_font_switch = budget["needs_font_switch"]

                # Trim text if too wide for margin-based budget.
                # Use max_w (margin-based) so continuation lines can fill
                # available space to the right margin.
                _will_use_kerned = (
                    not uses_literal and write_blk.text_ops
                    and write_blk.text_ops[0].operator == "TJ" and kern_reader is not None
                )
                # Debug: check if greedy fill sum matches full-text encoding
                _pre_hex, _ = cmap_mgr.encode_text(actual_font, line_text)
                _pre_w = _calc_hex_width(_pre_hex) if _pre_hex else 0
                if _pre_w > budget["max_w"] * 1.01:
                    logger.info(
                        f"[TRIM-PRE] {label} line {gi}: greedy assigned text that's TOO WIDE: "
                        f"full_encode_w={_pre_w:.0f} > max_w={budget['max_w']:.0f} "
                        f"(overflow={(_pre_w/budget['max_w']-1)*100:.1f}%), "
                        f"chars={len(line_text)}, text='{line_text[:60]}...'"
                    )
                _pre_text = line_text
                line_text = _trim_text_to_fit(
                    line_text, line_orig_hex, actual_font, fs_line,
                    orig_w_override=budget["max_w"],
                    use_kerned_tj=_will_use_kerned,
                )
                if line_text != _pre_text:
                    logger.debug(
                        f"[TRIM-CUT] {label} line {gi}: "
                        f"{len(_pre_text)}→{len(line_text)} chars"
                    )
                    # If this is the last line with content, clean up
                    # incomplete endings caused by trimming.
                    is_last_content = all(
                        line_assignments[k] is None
                        for k in range(gi + 1, num_groups)
                    ) if gi < num_groups - 1 else True
                    if is_last_content or gi == num_groups - 1:
                        _trim_words = line_text.split()
                        while (len(_trim_words) > 2
                               and _has_incomplete_ending(' '.join(_trim_words), strict=False)):
                            _trim_words.pop()
                        line_text = " ".join(_trim_words).rstrip(" ,;:")

                # Encode this line's text
                line_hex, line_missing = cmap_mgr.encode_text(actual_font, line_text)
                if not line_hex:
                    for bi in group_blocks:
                        block = all_content_blocks[bi]
                        for op in block.text_ops:
                            queue_patch(block.stream_xref, op.byte_offset,
                                        op.byte_length, empty_bytes)
                    continue

                # Build content bytes for this line.
                # Use per-pair kerned TJ content for TJ operators (hex fonts)
                use_kerned = False
                if not uses_literal and write_blk.text_ops and write_blk.text_ops[0].operator == "TJ":
                    line_content, use_kerned = _build_kerned_hex_content(
                        line_text, actual_font, line_hex, full_line_w, fs_line,
                    )
                elif uses_literal:
                    line_content = _build_literal_content(line_text, actual_font)
                else:
                    line_content = f"<{line_hex}>".encode("latin-1")

                # Put in write target block, Tc adjust targeting FULL line width.
                # This prevents Tc from squeezing text that should fill the
                # space freed by zeroed incompatible-font blocks.
                if write_blk.text_ops:
                    first_op = write_blk.text_ops[0]

                    # If write target is in an incompatible font, inject a
                    # font switch to the primary font.  For TJ arrays the
                    # switch MUST go before the '[', not inside the array.
                    if needs_font_switch:
                        fs_bytes = f"/{actual_font} {fs_line:.1f} Tf ".encode("latin-1")
                        if first_op.operator == "TJ" and first_op.tj_array_start >= 0:
                            queue_patch(write_blk.stream_xref, first_op.tj_array_start, 0, fs_bytes)
                        else:
                            line_content = fs_bytes + line_content

                    line_content = _inject_width_adjustment(
                        first_op, write_blk.stream_xref,
                        line_orig_hex, line_hex, line_content,
                        font_size=fs_line,
                        orig_w_override=full_line_w,
                        use_kerned_content=use_kerned,
                    )
                    queue_patch(write_blk.stream_xref, first_op.byte_offset,
                                first_op.byte_length, line_content)
                    for op in write_blk.text_ops[1:]:
                        queue_patch(write_blk.stream_xref, op.byte_offset,
                                    op.byte_length, empty_bytes)

                for bi in group_blocks:
                    if bi == write_bi:
                        continue
                    block = all_content_blocks[bi]
                    for op in block.text_ops:
                        queue_patch(block.stream_xref, op.byte_offset,
                                    op.byte_length, empty_bytes)

        else:
            # Single y-line (any number of blocks).
            sole_y = sorted_y_keys[0]
            sorted_blocks = y_groups[sole_y]

            # Calculate original hex from primary-font blocks (for Tc reference)
            all_orig_hex = ""
            for bi in sorted_blocks:
                if bi in other_font_blocks:
                    continue
                block = all_content_blocks[bi]
                for op in block.text_ops:
                    all_orig_hex += op.hex_string

            # Compute FULL line width across ALL fonts (for budget)
            primary_w_single = _calc_hex_width(all_orig_hex)
            full_line_w_single = primary_w_single
            for bi in sorted_blocks:
                if bi not in other_font_blocks:
                    continue
                block = all_content_blocks[bi]
                blk_font = block.font_tag
                blk_widths = width_calc.font_widths.get(blk_font, {})
                blk_default = width_calc._default_widths.get(blk_font, default_w)
                for op in block.text_ops:
                    for ci in range(0, len(op.hex_string), hex_per_char):
                        if ci + hex_per_char > len(op.hex_string):
                            break
                        cid = int(op.hex_string[ci:ci + hex_per_char], 16)
                        full_line_w_single += blk_widths.get(cid, blk_default)

            # ── Single-write-target path ──
            # Use LEFTMOST block as write target, inject font switch if
            # it's in any different font (even "compatible" ones may have
            # different subset glyphs).
            write_bi = sorted_blocks[0]
            write_blk = all_content_blocks[write_bi]
            needs_font_switch_single = (write_blk.font_tag != actual_font)

            fs_single = write_blk.font_size if write_blk.text_ops else 10.0

            # Margin-based width budget for single-line path
            write_x_pts = write_blk.x
            available_pts = max(0, right_margin_pts - write_x_pts)
            margin_w_real = available_pts * 1000.0 / max(fs_single, 1.0)
            # Same ratio-based logic as multi-line path
            if margin_w_real > 0 and full_line_w_single > 0:
                _sl_ratio = full_line_w_single / margin_w_real
            else:
                _sl_ratio = 1.0
            if _sl_ratio > 1.0:
                # Width map overestimates — inflate to match
                effective_w = max(full_line_w_single, margin_w_real * min(_sl_ratio, 2.0))
            else:
                # Width map accurate — trust margin_w_real
                effective_w = max(full_line_w_single, margin_w_real)

            _will_use_kerned = (
                not uses_literal and write_blk.text_ops
                and write_blk.text_ops[0].operator == "TJ" and kern_reader is not None
            )
            trimmed_text = _trim_text_to_fit(
                new_text, all_orig_hex, actual_font, fs_single,
                orig_w_override=effective_w,
                use_kerned_tj=_will_use_kerned,
            )
            # Incomplete-ending cleanup on single-line result
            _sl_words = trimmed_text.split()
            while (len(_sl_words) > 2
                   and _has_incomplete_ending(' '.join(_sl_words), strict=False)):
                _sl_words.pop()
            trimmed_text = " ".join(_sl_words).rstrip(" ,;:")

            if trimmed_text != new_text:
                hex_encoded, _ = cmap_mgr.encode_text(actual_font, trimmed_text)
                new_text = trimmed_text

            # Use per-pair kerned TJ content for TJ operators (hex fonts)
            use_kerned = False
            if not uses_literal and write_blk.text_ops and write_blk.text_ops[0].operator == "TJ":
                new_content_bytes, use_kerned = _build_kerned_hex_content(
                    new_text, actual_font, hex_encoded, effective_w, fs_single,
                )
            elif uses_literal:
                new_content_bytes = _build_literal_content(new_text, actual_font)
            else:
                new_content_bytes = f"<{hex_encoded}>".encode("latin-1")

            if write_blk.text_ops:
                first_op = write_blk.text_ops[0]

                # Font switch for incompatible-font write target
                if needs_font_switch_single:
                    fs_bytes = f"/{actual_font} {fs_single:.1f} Tf ".encode("latin-1")
                    if first_op.operator == "TJ" and first_op.tj_array_start >= 0:
                        queue_patch(write_blk.stream_xref, first_op.tj_array_start, 0, fs_bytes)
                    else:
                        new_content_bytes = fs_bytes + new_content_bytes

                new_content_bytes = _inject_width_adjustment(
                    first_op, write_blk.stream_xref,
                    all_orig_hex, hex_encoded, new_content_bytes,
                    font_size=fs_single,
                    orig_w_override=effective_w,
                    use_kerned_content=use_kerned,
                )
                queue_patch(write_blk.stream_xref, first_op.byte_offset,
                            first_op.byte_length, new_content_bytes)
                for op in write_blk.text_ops[1:]:
                    queue_patch(write_blk.stream_xref, op.byte_offset,
                                op.byte_length, empty_bytes)

            for bi in sorted_blocks:
                if bi == write_bi:
                    continue
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

            # Pad short replacements to prevent visual gaps from zeroed
            # continuation lines (when original wraps but replacement doesn't)
            new_content = _pad_skill_replacement(orig_text, new_content)

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
                orig_text = ts.full_text
                new_text = f"{ts.title_part} ({new_skills_part})"
                font = ts.full_spans[0].font_name if ts.full_spans else ""
                if _do_replacement(orig_text, new_text, font, f"title {t_idx}"):
                    replacements_applied += 1
            except Exception as e:
                logger.warning(f"[PATCH] Failed to process title {t_idx}: {e}")

    # ── Process header replacements (arbitrary text) ──
    if header_replacements:
        for orig_text, new_text in header_replacements.items():
            try:
                if not orig_text or not new_text:
                    continue
                # Headers don't have a known font — pass empty to let
                # _do_replacement discover the font from matched blocks.
                if _do_replacement(orig_text, new_text, "", f"header '{orig_text[:30]}'"):
                    replacements_applied += 1
            except Exception as e:
                logger.warning(f"[PATCH] Failed to process header '{orig_text[:30]}': {e}")

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

            # ── Tc/Tz leak prevention ──
            # Tc/Tz persist across BT/ET blocks in the PDF graphics state.
            # The within-block reset (injected after each replacement's last
            # patched op) ensures our Tc values don't leak to subsequent text.
            # We do NOT inject resets into unmodified BT blocks — doing so
            # adds unnecessary bytes and can subtly alter rendering in some
            # PDF viewers (especially for PDFs with per-character Td positioning
            # like Google Docs output).

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
    header_replacements: Optional[Dict[str, str]] = None,
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
    kern_reader = _KerningReader(doc, cmap_mgr)

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
    if header_replacements:
        # Headers can be on any page — include all pages
        for pg in range(len(doc)):
            pages_with_content.add(pg)

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
                kern_reader,
                header_replacements,
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


# ─── Boundary Detection (Date/Location Protection) ────────────────────────

class _BoundaryDetector:
    """Detect semantic boundaries within content blocks to protect dates,
    contact info, and other immutable content from being overwritten."""

    DATE_PATTERNS = [
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\.?\s*\d{4}\b',
        r'\b\d{4}\s*[-–—]\s*(?:\d{4}|Present|Current|Now)\b',
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\.?\s*\d{4}\s*[-–—]',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b',
        r'^(?:Present|Current|Now)$',
        r'\b\d{1,2}/\d{4}\b',
    ]

    DATE_FRAGMENT_PATTERNS = [
        r'^(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?$',
        r'^20[12]\d$',
        r'^20[12]\d\s*[-–—]\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*$',
        r'^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s*[-–—]$',
    ]

    _date_re = [re.compile(p, re.IGNORECASE) for p in DATE_PATTERNS]
    _date_fragment_re = [re.compile(p, re.IGNORECASE) for p in DATE_FRAGMENT_PATTERNS]

    LOCATION_PATTERNS = [
        r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+)*,\s*[A-Z]{2}$',
        r'^Remote$',
    ]

    _location_re = [re.compile(p, re.IGNORECASE) for p in LOCATION_PATTERNS]

    @classmethod
    def is_date_text(cls, text: str) -> bool:
        clean = text.strip()
        if not clean:
            return False
        for pattern in cls._date_re:
            if pattern.search(clean):
                return True
        return False

    @classmethod
    def is_date_fragment(cls, text: str) -> bool:
        clean = text.strip()
        if not clean:
            return False
        for pattern in cls._date_fragment_re:
            if pattern.search(clean):
                return True
        return False

    @classmethod
    def is_location_text(cls, text: str) -> bool:
        clean = text.strip()
        if not clean:
            return False
        for pattern in cls._location_re:
            if pattern.search(clean):
                return True
        return False

    @classmethod
    def is_protected(cls, text: str) -> bool:
        return cls.is_date_text(text) or cls.is_date_fragment(text) or cls.is_location_text(text)

    @classmethod
    def filter_extension_blocks(
        cls,
        all_blocks: List['ContentBlock'],
        extension_candidates: List[int],
        matched_block_indices: Optional[List[int]] = None,
    ) -> List[int]:
        matched_max_x = 0.0
        if matched_block_indices:
            for mi in matched_block_indices:
                b = all_blocks[mi]
                matched_max_x = max(matched_max_x, b.x)

        filtered = []
        for bi in extension_candidates:
            block = all_blocks[bi]
            text = block.full_text.strip()

            if text and cls.is_protected(text):
                logger.info(
                    f"[BOUNDARY] Protected block (text pattern) at "
                    f"x={block.x:.1f} y={block.y:.1f}: '{text[:60]}'"
                )
                continue

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

            block_text_lower = block_text.lower().strip()
            if block_text_lower in orig_clean:
                filtered.append(bi)
                continue

            if cls.is_protected(block_text):
                logger.info(
                    f"[BOUNDARY] Removed matched block with protected text: "
                    f"'{block_text[:60]}'"
                )
                continue

            filtered.append(bi)

        return filtered


# ─── Font Analysis (Character Availability) ────────────────────────────────

class FontAnalyzer:
    """Analyze PDF fonts and build character availability maps."""

    def __init__(self, cmap_mgr: '_CMapManager'):
        self._cmap = cmap_mgr

    def get_available_chars(self, font_tag: str) -> set:
        font_data = self._cmap.font_cmaps.get(font_tag, {})
        fwd = font_data.get("fwd", {})
        chars = set()
        for cid, char_str in fwd.items():
            for ch in char_str:
                chars.add(ch)
        return chars

    def get_all_available_chars(self) -> set:
        all_chars = set()
        for font_tag in self._cmap.font_cmaps:
            all_chars.update(self.get_available_chars(font_tag))
        return all_chars

    def get_unavailable_standard_chars(self, font_tag: str) -> List[str]:
        available = self.get_available_chars(font_tag)
        if not available:
            return []
        standard = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,;:!?-/()&%+')
        missing = sorted(ch for ch in standard if ch not in available)
        return missing

    def check_text(self, text: str, font_tag: str) -> List[str]:
        available = self.get_available_chars(font_tag)
        if not available:
            return []
        missing = []
        seen = set()
        for ch in text:
            if ch not in available and ch not in seen and ch != ' ':
                missing.append(ch)
                seen.add(ch)
        return missing

    def build_char_constraint_string(self) -> str:
        if not self._cmap.font_cmaps:
            return ""

        largest_set = set()
        for ft in self._cmap.font_cmaps:
            chars = self.get_available_chars(ft)
            if len(chars) > len(largest_set):
                largest_set = chars

        if not largest_set or len(largest_set) < 30:
            return ""

        common = largest_set

        ascii_letters = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
        ascii_digits = set('0123456789')
        common_punct = set('.,;:!?()-/&@#$%+\'"')

        missing_letters = ascii_letters - common
        missing_digits = ascii_digits - common
        missing_punct = common_punct - common

        if not missing_letters and not missing_digits:
            if missing_punct:
                return f"AVOID these characters (not in font): {' '.join(sorted(missing_punct))}"
            return ""

        all_missing = sorted(missing_letters | missing_digits | missing_punct)
        if len(all_missing) <= 30:
            avoid_desc = []
            if missing_letters:
                avoid_desc.append(f"letters: {' '.join(sorted(missing_letters))}")
            if missing_digits:
                avoid_desc.append(f"digits: {' '.join(sorted(missing_digits))}")
            if missing_punct:
                avoid_desc.append(f"punctuation: {' '.join(sorted(missing_punct))}")
            return f"AVOID these characters (not in font): {'; '.join(avoid_desc)}"

        avail_printable = sorted(c for c in common if c.isprintable() and c != ' ')
        if len(avail_printable) > 80:
            return ""

        return f"ONLY use these characters: {''.join(avail_printable)} and space"

    def get_font_summary(self) -> str:
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


# ─── Overflow Detection ───────────────────────────────────────────────────

class _OverflowDetector:
    """Detects and prevents text overflow by measuring rendered widths."""

    MAX_TC = 0.15

    def __init__(self, doc, cmap_mgr: '_CMapManager', width_calc: '_WidthCalculator'):
        self._doc = doc
        self._cmap = cmap_mgr
        self._wc = width_calc
        self._page_dims: Dict[int, Tuple[float, float]] = {}
        self._page_bounds: Dict[int, Tuple[float, float, float, float]] = {}

    def _get_page_dims(self, page_num: int) -> Tuple[float, float]:
        if page_num not in self._page_dims:
            page = self._doc[page_num]
            rect = page.rect
            self._page_dims[page_num] = (rect.width, rect.height)
        return self._page_dims[page_num]

    def measure_text_width(self, text: str, font_tag: str, font_size: float) -> float:
        hex_encoded, _ = self._cmap.encode_text(font_tag, text)
        if not hex_encoded:
            return len(text) * font_size * 0.5
        byte_width = self._cmap.get_byte_width(font_tag)
        return self._wc.text_width_from_hex(font_tag, hex_encoded, font_size, byte_width)

    def measure_hex_width(self, hex_string: str, font_tag: str, font_size: float) -> float:
        if not hex_string:
            return 0.0
        byte_width = self._cmap.get_byte_width(font_tag)
        return self._wc.text_width_from_hex(font_tag, hex_string, font_size, byte_width)

    def get_available_width(
        self, x_start: float, page_num: int,
        all_blocks: Optional[List['ContentBlock']] = None,
    ) -> float:
        page_w, _ = self._get_page_dims(page_num)

        if page_num in self._page_bounds:
            _, right_x, _, _ = self._page_bounds[page_num]
            return right_x - x_start

        if all_blocks:
            page_blocks = [b for b in all_blocks if b.page_num == page_num and b.text_ops]
            if page_blocks:
                max_right = 0.0
                for block in page_blocks:
                    block_text = block.full_text
                    if block_text and block.font_tag:
                        block_w = self.measure_text_width(
                            block_text, block.font_tag, block.font_size
                        )
                        max_right = max(max_right, block.x + block_w)

                if max_right > x_start:
                    right_bound = max_right + 2.0
                    left_x = min(b.x for b in page_blocks)
                    self._page_bounds[page_num] = (left_x, right_bound, 0, 0)
                    return right_bound - x_start

        return page_w - 36.0 - x_start

    def would_overflow(
        self, new_text: str, font_tag: str, font_size: float,
        x_start: float, page_num: int,
        all_blocks: Optional[List['ContentBlock']] = None,
    ) -> Tuple[bool, float, float]:
        text_w = self.measure_text_width(new_text, font_tag, font_size)
        avail_w = self.get_available_width(x_start, page_num, all_blocks)
        num_chars = len(new_text)
        max_tc_savings = self.MAX_TC * num_chars
        effective_width = text_w - max_tc_savings
        return effective_width > avail_w, text_w, avail_w

    def wrap_text(
        self, text: str, max_width: float,
        font_tag: str, font_size: float,
    ) -> List[str]:
        words = text.split()
        if not words:
            return [text]

        lines: List[str] = []
        current_line: List[str] = []
        current_width = 0.0
        space_w = self.measure_text_width(" ", font_tag, font_size)
        if space_w < 0.1:
            space_w = font_size * 0.25

        for word in words:
            word_w = self.measure_text_width(word, font_tag, font_size)
            if current_line:
                test_width = current_width + space_w + word_w
                if test_width > max_width:
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
        page_blocks = sorted(
            [b for b in blocks if b.page_num == page_num and b.text_ops],
            key=lambda b: -b.y
        )
        if len(page_blocks) < 2:
            return page_blocks[0].font_size * 1.2 if page_blocks else 12.0

        deltas: List[float] = []
        for i in range(len(page_blocks) - 1):
            b1, b2 = page_blocks[i], page_blocks[i + 1]
            if abs(b1.x - b2.x) < 20:
                dy = b1.y - b2.y
                if 4 < dy < 30:
                    deltas.append(dy)

        if deltas:
            return sum(deltas) / len(deltas)
        return page_blocks[0].font_size * 1.2


# ─── Width Budget Calculator ──────────────────────────────────────────────

def calculate_width_budgets(
    pdf_path: str,
    bullets: List['BulletPoint'],
    skills: List['SkillLine'],
    title_skills: Optional[List['TitleSkillLine']] = None,
) -> Dict[str, Any]:
    """Calculate per-item max character counts based on rendered font widths."""
    doc = fitz.open(pdf_path)
    cmap_mgr = _CMapManager(doc)
    width_calc = _WidthCalculator(doc)
    detector = _OverflowDetector(doc, cmap_mgr, width_calc)

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
            orig_line_w = detector.measure_text_width(lt, font_tag, font_size)
            tc_headroom = detector.MAX_TC * max(len(lt), 1)
            effective_w = orig_line_w + tc_headroom

            avg_cw = _avg_char_width(lt, font_tag, font_size)
            max_chars = int(effective_w / avg_cw) if avg_cw > 0 else len(lt)
            max_chars = max(max_chars, len(lt))
            line_budgets.append(max_chars)

        bullet_budgets[idx] = line_budgets

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

    if title_skills:
        for idx, ts in enumerate(title_skills):
            if not ts.full_spans:
                continue
            font_tag = _resolve_font_tag(ts.full_spans[0].font_name)
            if not font_tag:
                continue

            font_size = ts.full_spans[0].font_size

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

    OVERALL_SSIM_MIN = 0.75
    HEADER_SSIM_MIN = 0.95
    HEADER_REGION_RATIO = 0.12

    def verify(
        self,
        original_path: str,
        tailored_path: str,
        bullet_replacements: Optional[Dict[int, List[str]]] = None,
        skill_replacements: Optional[Dict[int, str]] = None,
        title_replacements: Optional[Dict[int, str]] = None,
    ) -> VerificationReport:
        text_result = self._check_text_extraction(
            tailored_path,
            bullet_replacements or {},
            skill_replacements or {},
            title_replacements or {},
        )
        protected_result = self._check_protected_content(original_path, tailored_path)
        font_result = self._check_fonts(original_path, tailored_path)
        visual_result = self._check_visual_similarity(original_path, tailored_path)
        garbled_result = self._check_garbled_chars(tailored_path)
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
        try:
            doc = fitz.open(tailored_path)
            full_text = ""
            for page in doc:
                full_text += page.get_text("text")
            doc.close()

            full_norm = " ".join(full_text.split()).lower()

            found = 0
            total = 0
            missing = []

            for idx, lines in bullet_replacements.items():
                for line in lines:
                    total += 1
                    words = [w for w in line.split() if len(w) > 3]
                    if not words:
                        found += 1
                        continue
                    matched = sum(1 for w in words if w.lower() in full_norm)
                    if matched >= len(words) * 0.6:
                        found += 1
                    else:
                        missing.append(f"Bullet {idx}: '{line[:50]}...'")

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
            warnings = missing[:5] if missing else []

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
                    date_norm = " ".join(date.split())
                    tail_norm = " ".join(tail_text.split())
                    if date_norm not in tail_norm:
                        missing_dates.append(date)

            email_re = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')

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
        try:
            orig_doc = fitz.open(original_path)
            tail_doc = fitz.open(tailored_path)

            orig_fonts = set()
            tail_fonts = set()

            for page in orig_doc:
                for f in page.get_fonts():
                    orig_fonts.add(f[3])
            for page in tail_doc:
                for f in page.get_fonts():
                    tail_fonts.add(f[3])

            orig_doc.close()
            tail_doc.close()

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
        try:
            import numpy as np
            from skimage.metrics import structural_similarity

            orig_doc = fitz.open(original_path)
            tail_doc = fitz.open(tailored_path)

            overall_ssims = []
            header_ssims = []

            for pn in range(min(len(orig_doc), len(tail_doc))):
                orig_pix = orig_doc[pn].get_pixmap(dpi=150)
                tail_pix = tail_doc[pn].get_pixmap(dpi=150)

                orig_arr = np.frombuffer(orig_pix.samples, dtype=np.uint8).reshape(
                    orig_pix.h, orig_pix.w, orig_pix.n
                )
                tail_arr = np.frombuffer(tail_pix.samples, dtype=np.uint8).reshape(
                    tail_pix.h, tail_pix.w, tail_pix.n
                )

                h = min(orig_arr.shape[0], tail_arr.shape[0])
                w = min(orig_arr.shape[1], tail_arr.shape[1])
                c = min(orig_arr.shape[2], tail_arr.shape[2])
                orig_crop = orig_arr[:h, :w, :c]
                tail_crop = tail_arr[:h, :w, :c]

                if c >= 3:
                    orig_gray = np.mean(orig_crop[:, :, :3], axis=2).astype(np.uint8)
                    tail_gray = np.mean(tail_crop[:, :, :3], axis=2).astype(np.uint8)
                else:
                    orig_gray = orig_crop[:, :, 0]
                    tail_gray = tail_crop[:, :, 0]

                overall = structural_similarity(orig_gray, tail_gray)
                overall_ssims.append(overall)

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
                passed=True,
                details={"error": str(e)},
                warnings=[f"Visual check failed: {e}"],
            )

    def _check_garbled_chars(self, pdf_path: str) -> VerificationResult:
        try:
            doc = fitz.open(pdf_path)
            issues = []

            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")

                if '\ufffd' in text:
                    count = text.count('\ufffd')
                    issues.append(
                        f"Page {page_num}: {count} Unicode replacement character(s)"
                    )

                garbled_re = re.compile(
                    r'[a-z][^a-zA-Z0-9\u2019\'\-/+_.][a-z]'
                )
                words = text.split()
                for word in words:
                    clean = word.strip(".,;:!?()[]{}\"'-/")
                    if len(clean) > 4:
                        match = garbled_re.search(clean)
                        if match:
                            if '@' in word or '://' in word:
                                continue
                            issues.append(
                                f"Page {page_num}: Suspicious word '{clean}'"
                            )

            doc.close()

            return VerificationResult(
                passed=len(issues) == 0,
                details={"issues_found": len(issues)},
                warnings=issues[:10],
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
        try:
            doc = fitz.open(pdf_path)
            overflow_issues = []

            orig_max_right = {}
            orig_max_bottom = {}
            tolerance = 5.0

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
                passed=True,
                details={"error": str(e)},
                warnings=[f"Overflow check failed: {e}"],
            )


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

    # Step 3: Compute pixel-based budgets and optimize with Claude
    bullet_budgets = _compute_bullet_char_budgets(bullets, classified)
    logger.info(f"Computed budgets for {len(bullet_budgets)} bullets (total chars: {sum(b['total'] for b in bullet_budgets.values())})")
    bullet_replacements, skill_replacements, title_replacements = await generate_optimized_content(
        bullets, skills, job_description, title_skills,
        bullet_budgets=bullet_budgets,
    )
    raw_bullet_count = len(bullet_replacements)
    raw_bullet_keys = set(bullet_replacements.keys())
    bullet_replacements = sanitize_bullet_replacements(
        bullets, bullet_replacements, length_tolerance=0.20,
        bullet_budgets=bullet_budgets,
    )
    dropped_indices = raw_bullet_keys - set(bullet_replacements.keys())
    dropped_count = len(dropped_indices)
    if dropped_count > 0:
        logger.info(f"[SANITIZE] Dropped {dropped_count}/{raw_bullet_count} bullets after first pass")

    # Retry for bullets that are too SHORT — the LLM generated too little text
    # to fill the available pixel space. These bullets would leave ugly half-empty
    # continuation lines. Re-prompt with explicit "write MORE text" instruction.
    short_indices: List[int] = []
    if bullet_budgets:
        for idx, lines in bullet_replacements.items():
            if idx in bullet_budgets:
                budget_total = bullet_budgets[idx]["total"]
                actual_total = sum(len(l.strip()) for l in lines)
                if actual_total < budget_total * 0.80:  # Less than 80% of pixel budget
                    short_indices.append(idx)
                    logger.info(
                        f"[SHORT] Bullet {idx}: {actual_total} chars but budget allows {budget_total} "
                        f"({actual_total/budget_total*100:.0f}% fill)"
                    )

    if short_indices and len(short_indices) <= 8:
        logger.info(f"[SHORT-RETRY] Retrying {len(short_indices)} short bullets")
        from app.llm.claude_client import ClaudeClient
        short_claude = ClaudeClient()
        short_bullet_texts = []
        for idx in sorted(short_indices):
            bp = bullets[idx]
            budget_total = bullet_budgets[idx]["total"]
            current_text = " ".join(l.strip() for l in bullet_replacements[idx])
            short_bullet_texts.append(
                f"  BULLET {idx+1} ({bp.section_name}) "
                f"[{len(bp.line_texts)} lines, total {budget_total}-{int(budget_total * 1.3)} chars]:\n"
                f"    Current (TOO SHORT at {len(current_text)} chars): {current_text}\n"
                f"    Original:\n" + "\n".join(f"      {lt}" for lt in bp.line_texts)
            )
        if short_bullet_texts:
            short_prompt = f"""The following resume bullet points are TOO SHORT. They need to be LONGER to fill the available space in the PDF.
Each bullet MUST be within the character range shown in brackets. AIM FOR THE MAXIMUM.

RULES:
1. EXPAND the bullet — add more detail, context, impact, or metrics. Do NOT just pad with filler words.
2. The TOTAL character count across ALL lines must be within the range in brackets. COUNT CAREFULLY.
3. Each bullet must have the SAME number of lines as the original.
4. Every bullet MUST be a COMPLETE, MEANINGFUL statement — no fragments.
5. PRESERVE all technologies, metrics, and factual claims from the current text.
6. NEVER include bullet point characters at the start.

JOB DESCRIPTION:
{job_description[:2000]}

BULLETS TO EXPAND:
{chr(10).join(short_bullet_texts)}
"""
            short_schema = {
                "type": "object",
                "properties": {
                    "bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "lines": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["index", "lines"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["bullets"],
                "additionalProperties": False,
            }
            try:
                short_parsed = await short_claude._send_request_json(
                    "You are an expert resume optimizer. Bullets are too short — EXPAND them to fill the character budget.",
                    short_prompt,
                    json_schema=short_schema,
                    max_tokens=8192,
                )
                if short_parsed and "bullets" in short_parsed:
                    short_raw: Dict[int, List[str]] = {}
                    for item in short_parsed["bullets"]:
                        s_idx = item.get("index", 0) - 1
                        s_lines = item.get("lines", [])
                        if 0 <= s_idx < len(bullets) and s_lines:
                            short_raw[s_idx] = s_lines
                    short_sanitized = sanitize_bullet_replacements(
                        bullets, short_raw, length_tolerance=0.30,
                        bullet_budgets=bullet_budgets,
                    )
                    # Only accept if actually longer
                    for s_idx, s_lines in short_sanitized.items():
                        new_total = sum(len(l.strip()) for l in s_lines)
                        old_total = sum(len(l.strip()) for l in bullet_replacements.get(s_idx, []))
                        if new_total > old_total:
                            bullet_replacements[s_idx] = s_lines
                            logger.info(f"[SHORT-RETRY] Bullet {s_idx}: expanded {old_total}→{new_total} chars")
                        else:
                            logger.info(f"[SHORT-RETRY] Bullet {s_idx}: retry not longer ({new_total} vs {old_total}), keeping original")
            except Exception as e:
                logger.warning(f"[SHORT-RETRY] Retry failed: {e}")

    # Retry loop: re-prompt Claude for dropped bullets with stricter constraints
    if 0 < dropped_count <= 5:
        logger.info(f"[RETRY] Attempting retry for {dropped_count} dropped bullets")
        from app.llm.claude_client import ClaudeClient
        retry_claude = ClaudeClient()

        retry_bullet_texts = []
        for idx in sorted(dropped_indices):
            if idx < len(bullets):
                bp = bullets[idx]
                lines_info = []
                for j, lt in enumerate(bp.line_texts):
                    lines_info.append(f"    Line {j+1}: {lt}")

                # Use pixel-based budget if available (inflated)
                if bullet_budgets and idx in bullet_budgets:
                    total_budget = bullet_budgets[idx]["total"]
                    min_total = total_budget  # MINIMUM = actual pixel budget
                    max_total = int(total_budget * 1.3)
                else:
                    total_chars = sum(len(lt.strip()) for lt in bp.line_texts)
                    min_total = max(20, int(total_chars * 0.85))
                    max_total = int(total_chars * 1.15)

                retry_bullet_texts.append(
                    f"  BULLET {idx+1} ({bp.section_name}) "
                    f"[{len(bp.line_texts)} lines, total {min_total}-{max_total} chars]:\n"
                    + "\n".join(lines_info)
                )

        if retry_bullet_texts:
            retry_prompt = f"""Rewrite these resume bullet points for the job description below.

CRITICAL RULES:
1. The TOTAL character count across ALL lines must be within the range in brackets.
2. Each bullet must have the SAME number of lines as the original. Split text evenly.
3. PRESERVE: company names, metrics, percentages, dates, and ALL technologies/tools — do NOT fabricate.
4. Every bullet must be a COMPLETE, MEANINGFUL statement — no dangling words or fragments.
5. Emphasize themes from the job description (scalability, real-time, enterprise, etc.) but do NOT swap in the JD's tech stack.

JOB DESCRIPTION:
{job_description[:2000]}

BULLETS:
{chr(10).join(retry_bullet_texts)}
"""
            retry_schema = {
                "type": "object",
                "properties": {
                    "bullets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                                "lines": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["index", "lines"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["bullets"],
                "additionalProperties": False,
            }
            try:
                retry_parsed = await retry_claude._send_request_json(
                    "You are an expert resume optimizer. Follow character count rules precisely.",
                    retry_prompt,
                    json_schema=retry_schema,
                    max_tokens=4096,
                )
                if retry_parsed and "bullets" in retry_parsed:
                    retry_raw: Dict[int, List[str]] = {}
                    for item in retry_parsed["bullets"]:
                        idx = item.get("index", 0) - 1
                        lines = item.get("lines", [])
                        if 0 <= idx < len(bullets) and lines:
                            retry_raw[idx] = lines
                    # Sanitize with relaxed tolerance
                    retry_sanitized = sanitize_bullet_replacements(
                        bullets, retry_raw, length_tolerance=0.25,
                        bullet_budgets=bullet_budgets,
                    )
                    recovered = len(retry_sanitized)
                    bullet_replacements.update(retry_sanitized)
                    logger.info(f"[RETRY] Recovered {recovered}/{dropped_count} bullets on retry")
            except Exception as e:
                logger.warning(f"[RETRY] Retry failed: {e}")

    logger.info(f"Optimized {len(bullet_replacements)} bullets, {len(skill_replacements)} skills, {len(title_replacements)} title skills")

    # Step 4: Apply to PDF
    apply_changes_to_pdf(
        pdf_path, output_path,
        bullets, skills,
        bullet_replacements, skill_replacements,
        title_skills, title_replacements,
    )
    logger.info(f"Saved optimized PDF to {output_path}")

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
