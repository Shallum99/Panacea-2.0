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
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


UNICODE_REPLACEMENTS = {
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2015": "-",  # horizontal bar
    "\u2212": "-",  # minus sign
    "\u00ad": "",   # soft hyphen
    "\u2022": "•",
    "\u00a0": " ",  # nbsp
    "\u2007": " ",  # figure space
    "\u202f": " ",  # narrow nbsp
    "\u2009": " ",  # thin space
    "\u200a": " ",  # hair space
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u00b7": "·",
    "\u037e": ";",  # greek question mark visually similar to semicolon
}

ZERO_WIDTH_CHARS = {
    "\u200b", "\u200c", "\u200d", "\ufeff", "\u2060",
}

UNICODE_FALLBACKS = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u00b7": ".",
    "\u2122": "TM",
    "\u00ae": "(R)",
    "\u00a9": "(C)",
}

# Strict formatting defaults: do not change font family or font size.
ALLOW_BASE14_FONT_FALLBACK = False
MAX_FONT_SIZE_REDUCTION = 0.0


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
        return clean in ("●", "•", "◦", "○", "■", "▪")

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

    @property
    def line_texts(self) -> List[str]:
        """Get text for each line, stripping bullet characters."""
        result = []
        for line in self.text_lines:
            # Join only non-bullet, non-ZWS spans
            parts = [s.text for s in line.spans
                     if not s.is_bullet_char and not s.is_zwsp_only]
            text = " ".join(parts).replace("\u200b", "").strip()
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
    """Group spans by y-position into visual lines."""
    if not spans:
        return []

    sorted_spans = sorted(spans, key=lambda s: (s.page_num, s.origin[1], s.origin[0]))
    lines: List[List[TextSpan]] = []
    current: List[TextSpan] = [sorted_spans[0]]

    for span in sorted_spans[1:]:
        prev = current[-1]
        if span.page_num == prev.page_num and abs(span.origin[1] - prev.origin[1]) < 3:
            current.append(span)
        else:
            lines.append(current)
            current = [span]

    if current:
        lines.append(current)

    return lines


# ─── Step 3: Classify lines ───────────────────────────────────────────────

SECTION_HEADERS = {
    "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "TECHNOLOGIES",
    "EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE", "EMPLOYMENT",
    "PROJECTS", "PROJECT EXPERIENCE", "TECHNICAL PROJECTS",
    "EDUCATION", "CERTIFICATIONS", "CERTIFICATES",
    "SUMMARY", "PROFESSIONAL SUMMARY", "OBJECTIVE", "ABOUT",
    "ACHIEVEMENTS", "AWARDS", "PUBLICATIONS", "VOLUNTEER",
    "LANGUAGES", "INTERESTS", "REFERENCES",
    "CONTACT", "CONTACT INFORMATION",
    "AWARDS & ACHIEVEMENTS", "AWARDS & ACHIEVEMENTS:",
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
        is_header = False
        for header in SECTION_HEADERS:
            if clean_upper == header or clean_upper.startswith(header + " "):
                is_header = True
                current_section = clean
                break

        # Also detect by formatting: bold + short + larger font
        if not is_header:
            non_zwsp = [s for s in line if not s.is_zwsp_only]
            if non_zwsp and len(clean) < 40:
                first = non_zwsp[0]
                if first.is_bold and first.font_size > median_size + 0.5:
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

        # Check if this line IS a standalone bullet marker (● only, no text)
        if non_zwsp and all(s.is_bullet_char for s in non_zwsp):
            classified.append(ClassifiedLine(
                spans=line, line_type=LineType.BULLET_MARKER,
                page_num=page_num, y_pos=y_pos,
            ))
            continue

        # ── SKILLS CHECK (must come before bullet_text check) ──
        # Skills lines: ● Languages: Python, R, SQL... → has bullet + bold label + regular content
        is_skill_section = current_section.upper() in (
            "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "TECHNOLOGIES",
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
        is_bullet_section = current_section.upper().strip() in (
            "WORK EXPERIENCE", "EXPERIENCE", "PROFESSIONAL EXPERIENCE",
            "PROJECTS", "PROJECT EXPERIENCE", "TECHNICAL PROJECTS",
            "AWARDS", "ACHIEVEMENTS", "AWARDS & ACHIEVEMENTS", "AWARDS & ACHIEVEMENTS:",
            "CERTIFICATIONS", "PUBLICATIONS",
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
            for header in SECTION_HEADERS:
                if clean_upper == header or clean_upper.startswith(header + " "):
                    current_section = cl.clean_text
                    break

            # Detect title skill lines: "(Tech1, Tech2, ...)" pattern in STRUCTURE
            clean = cl.clean_text
            paren_match = re.search(r'\(([^)]*,\s*[^)]+)\)', clean)
            if paren_match and current_section.upper().strip() in (
                "WORK EXPERIENCE", "EXPERIENCE", "PROFESSIONAL EXPERIENCE",
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
            has_bullet_char = any(s.is_bullet_char for s in cl.spans)
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
                max_chars = max(8, len(lt))
                min_chars = max(4, int(max_chars * 0.65))
                lines_info.append(
                    f"    Line {j+1} (target={len(lt)} chars, min={min_chars}, max={max_chars}): {lt}"
                )
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
            usr_prompt = f"""Rewrite these resume bullet points to be strongly tailored for the job description below.

RULES:
1. Incorporate keywords, phrases, and terminology directly from the job description
2. Rephrase to emphasize skills and experience most relevant to this specific role
3. Use action verbs and terminology that mirror the job posting's language
4. PRESERVE: company names, metrics, percentages, dates, and factual claims — do NOT fabricate
5. Each bullet must have EXACTLY the same number of lines as the original
6. Each line must stay within the provided min/max character range for that line (hard constraint)
7. Every bullet MUST be modified — do not return any bullet unchanged
8. Focus on what the job description specifically asks for and weave those themes into each bullet
9. Use plain ASCII punctuation only: use "-" instead of en/em dashes, ";" instead of unusual semicolons, and no soft hyphens.

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

        skill_texts = []
        for i, sk in enumerate(skills):
            skill_texts.append(f"  {i+1}. {sk.label_text} {sk.content_text}")

        sys_prompt = (
            "You are an expert resume skills optimizer. You reorder, substitute, and emphasize "
            "skills to strongly match a specific job description."
        )

        usr_prompt = f"""Optimize these skill lines to best match the job description below.

RULES:
1. REORDER skills to put the most job-relevant ones FIRST
2. Substitute equivalent terms to match JD language (e.g., "PostgreSQL" → "Postgres", "JS" → "JavaScript", "REST" → "RESTful APIs")
3. You may add 1-2 closely related skills if they appear in the JD and the candidate likely has them based on their other skills
4. You may remove less relevant skills to make room for more relevant ones
5. Keep the SAME comma-separated format
6. Each line should be SIMILAR length to the original (±15% character count)
7. Return ONLY the values after the label (e.g., for "Languages: Python, R, SQL" return "Python, R, SQL" — NOT "Languages: Python, R, SQL")
8. The ordering should CLEARLY reflect what this specific job prioritizes

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
2. Use technologies from the JD that the candidate actually knows (based on their current tech stacks)
3. Keep the SAME number of technologies (same comma-separated count)
4. Return ONLY the parenthesized content (e.g., "Node, Express, MongoDB, PostgreSQL, GCP")

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


# ─── Step 6: Apply changes to PDF ─────────────────────────────────────────

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
    """Apply optimized text back to the PDF.

    Strategy: redact original text → clean_contents → insert_text at original coords.
    clean_contents() normalizes the content stream so insert_text coordinates work correctly.
    """
    doc = fitz.open(pdf_path)
    # Extract embedded fonts for reuse (avoids Base14 substitution)
    font_cache = _build_font_cache(doc)

    # Collect operations per page: redactions and insertions
    page_ops: Dict[int, Dict] = {}  # {page_num: {"redacts": [...], "inserts": [...]}}

    def ensure_page(pn: int):
        if pn not in page_ops:
            page_ops[pn] = {"redacts": [], "inserts": []}

    def add_replacement(page_num: int, spans: List[TextSpan], new_text: str) -> bool:
        """Queue a text replacement: redact spans, then insert new text."""
        ensure_page(page_num)
        normalized_text = _normalize_replacement_text(new_text)
        if not normalized_text:
            logger.warning("[APPLY] Skipping replacement: normalized text is empty")
            return False

        # Redact each span individually
        for s in spans:
            page_ops[page_num]["redacts"].append(s.bbox)

        # Queue insertion at first span's origin
        first = spans[0]
        font_name, font_buffer, font_obj, insert_text, used_fallback_font = _resolve_font(
            first.font_name, normalized_text, font_cache
        )
        if used_fallback_font and not ALLOW_BASE14_FONT_FALLBACK:
            logger.warning(
                f"[APPLY] Skipping replacement: preserving original font failed for '{first.font_name}'"
            )
            return False
        color = _int_to_rgb(first.color)
        # Fit to the original span envelope, not page margin, to avoid layout bleed.
        original_right = max(s.bbox[2] for s in spans)
        available_width = max((original_right - first.origin[0]) + 1.0, 20.0)
        fit_result = _fit_text(
            insert_text,
            font_name,
            first.font_size,
            available_width,
            font_obj=font_obj,
            max_size_reduction=MAX_FONT_SIZE_REDUCTION,
        )
        if not fit_result:
            compacted = _compact_text_to_fit(
                insert_text, available_width, font_name, first.font_size, font_obj=font_obj
            )
            if not compacted:
                logger.warning("[APPLY] Skipping replacement: cannot fit text without changing style")
                return False
            fit_result = _fit_text(
                compacted,
                font_name,
                first.font_size,
                available_width,
                font_obj=font_obj,
                max_size_reduction=MAX_FONT_SIZE_REDUCTION,
            )
            if not fit_result:
                logger.warning("[APPLY] Skipping replacement after compaction: still cannot fit")
                return False
        fitted_text, fitted_size = fit_result

        # Guardrail: if text still cannot fit, keep original text in place (skip replacement).
        try:
            fitted_width = _measure_text_width(
                fitted_text, font_name, fitted_size, font_obj=font_obj
            )
            if fitted_width > (available_width + 0.5):
                logger.warning(
                    f"[APPLY] Skipping replacement: fitted text width {fitted_width:.2f} "
                    f"exceeds available {available_width:.2f}"
                )
                return False
        except Exception as e:
            logger.warning(f"[APPLY] Width validation failed, skipping replacement: {e}")
            return False

        page_ops[page_num]["inserts"].append({
            "point": first.origin,
            "text": fitted_text,
            "font": font_name,
            "size": fitted_size,
            "color": color,
            "font_buffer": font_buffer,
        })
        return True

    # ── Process bullet replacements ──
    bullet_ops_count = 0
    for idx, new_lines in bullet_replacements.items():
        if idx >= len(bullets):
            logger.warning(f"[APPLY] Bullet idx {idx} >= len(bullets) {len(bullets)}, skipping")
            continue
        bp = bullets[idx]
        original_line_texts = bp.line_texts
        if len(new_lines) != len(original_line_texts):
            logger.warning(
                f"[APPLY] Bullet {idx}: line count mismatch "
                f"(orig={len(original_line_texts)}, new={len(new_lines)}), skipping bullet"
            )
            continue

        # Hard stop on large line-length divergence to avoid wrapping/collisions.
        oversize = False
        for line_idx, (orig, new_line) in enumerate(zip(original_line_texts, new_lines)):
            orig_len = len(orig.strip())
            new_len = len(new_line.strip())
            if orig_len == 0:
                continue
            delta = abs(new_len - orig_len) / orig_len
            if delta > 0.15:
                logger.warning(
                    f"[APPLY] Bullet {idx} line {line_idx}: length delta {delta:.2f} > 0.15, skipping bullet"
                )
                oversize = True
                break
        if oversize:
            continue

        logger.info(f"[APPLY] Bullet {idx}: {len(bp.text_lines)} text_lines, {len(new_lines)} new_lines")

        for line_idx, text_line in enumerate(bp.text_lines):
            new_text = new_lines[line_idx].strip()
            if not new_text:
                logger.warning(f"[APPLY] Bullet {idx} line {line_idx}: empty new_text")
                continue

            # Get the text spans to replace (skip bullet chars and ZWS)
            text_spans = [s for s in text_line.spans
                          if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()]
            if not text_spans:
                logger.warning(f"[APPLY] Bullet {idx} line {line_idx}: NO text_spans found! Span details:")
                for s in text_line.spans:
                    logger.warning(f"  span: bullet={s.is_bullet_char}, zwsp={s.is_zwsp_only}, text='{s.text[:50]}', font={s.font_name}")
                continue

            logger.info(f"[APPLY] Bullet {idx} line {line_idx}: replacing {len(text_spans)} spans with '{new_text[:60]}...'")
            if add_replacement(text_spans[0].page_num, text_spans, new_text):
                bullet_ops_count += 1

    logger.info(f"[APPLY] Total bullet text replacements queued: {bullet_ops_count}")

    # ── Process skill replacements ──
    for idx, new_content in skill_replacements.items():
        if idx >= len(skills):
            continue
        sk = skills[idx]
        if not sk.content_spans:
            continue

        add_replacement(sk.content_spans[0].page_num, sk.content_spans, new_content)

    # ── Process title skill replacements ──
    if title_skills and title_replacements:
        for idx, new_skills in title_replacements.items():
            if idx >= len(title_skills):
                continue
            ts = title_skills[idx]
            if not ts.full_spans:
                continue

            # Rebuild the full title text with new skills in parentheses
            new_full = f"{ts.title_part} ({new_skills})"
            logger.info(f"[APPLY] Title {idx}: '{ts.full_text[:60]}' -> '{new_full[:60]}'")
            add_replacement(ts.full_spans[0].page_num, ts.full_spans, new_full)

    # ── Apply all operations per page: redact → clean → insert ──
    for page_num in sorted(page_ops.keys()):
        ops = page_ops[page_num]
        page = doc[page_num]

        # Phase 1: Add all redaction annotations (white fill, no replacement text)
        for bbox in ops["redacts"]:
            rect = fitz.Rect(bbox)
            rect.y0 -= 0.5
            rect.y1 += 0.5
            rect.x1 += 1  # small expansion to fully cover
            page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)

        # Phase 2: Apply redactions (removes original text, paints white)
        page.apply_redactions()

        # Phase 3: Normalize content stream so insert_text coords work
        page.clean_contents()

        # Phase 4: Install extracted fonts and insert replacement text
        installed_fonts: set = set()
        for ins in ops["inserts"]:
            # Install custom font on this page if not already done
            if ins["font_buffer"] and ins["font"] not in installed_fonts:
                try:
                    page.insert_font(fontname=ins["font"], fontbuffer=ins["font_buffer"])
                    installed_fonts.add(ins["font"])
                except Exception as e:
                    logger.warning(f"[FONTS] Failed to install font '{ins['font']}' on page {page_num}: {e}")
                    # Fall back to Base14 for this insert
                    ins["font"] = "helv"
                    ins["font_buffer"] = None

            page.insert_text(
                fitz.Point(ins["point"][0], ins["point"][1]),
                ins["text"],
                fontname=ins["font"],
                fontsize=ins["size"],
                color=ins["color"],
            )

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return output_path


def _int_to_rgb(color: int) -> Tuple[float, float, float]:
    """Convert integer color to RGB tuple (0-1 range)."""
    r = ((color >> 16) & 0xFF) / 255.0
    g = ((color >> 8) & 0xFF) / 255.0
    b = (color & 0xFF) / 255.0
    return (r, g, b)


def _build_font_cache(doc) -> Dict[str, Dict[str, Any]]:
    """Extract all embedded fonts from the PDF for reuse during text insertion.

    Returns a dict mapping clean font names to their extracted data:
        {font_name: {"xref": int, "buffer": bytes, "ext": str, "font_obj": fitz.Font}}
    """
    cache: Dict[str, Dict[str, Any]] = {}
    seen_xrefs: set = set()

    for page in doc:
        for f in page.get_fonts():
            xref = f[0]
            if xref in seen_xrefs or xref == 0:
                continue
            seen_xrefs.add(xref)

            basefont = f[3]  # e.g. "ABCDEF+Calibri-Bold"
            try:
                _, font_ext, _, buffer = doc.extract_font(xref)
            except Exception:
                continue

            if font_ext == "n/a" or not buffer:
                continue

            # Create a Font object for glyph validation and text measurement
            try:
                font_obj = fitz.Font(fontbuffer=buffer)
            except Exception:
                continue

            num_glyphs = len(font_obj.valid_codepoints())
            entry = {
                "xref": xref,
                "buffer": buffer,
                "ext": font_ext,
                "font_obj": font_obj,
                "num_glyphs": num_glyphs,
            }

            # Store by clean name (without subset prefix like "ABCDEF+")
            # When duplicate names exist, keep the subset with more glyphs
            clean = basefont.split("+", 1)[-1] if "+" in basefont else basefont
            existing = cache.get(clean)
            if not existing or num_glyphs > existing.get("num_glyphs", 0):
                cache[clean] = entry
            # Also store by full basefont name
            if basefont != clean:
                cache[basefont] = entry

    logger.info(f"[FONTS] Extracted {len(seen_xrefs)} font xrefs, {len(cache)} cache entries: {list(cache.keys())}")
    return cache


def _normalize_replacement_text(text: str) -> str:
    """Normalize replacement text to reduce glyph fallback/font substitution issues."""
    if not text:
        return ""

    normalized = unicodedata.normalize("NFKC", text)
    for bad, good in UNICODE_REPLACEMENTS.items():
        normalized = normalized.replace(bad, good)
    for z in ZERO_WIDTH_CHARS:
        normalized = normalized.replace(z, "")

    # Remove control chars and normalize whitespace.
    normalized = "".join(
        ch for ch in normalized
        if ch == "\n" or ch == "\t" or unicodedata.category(ch)[0] != "C"
    )
    normalized = normalized.replace("\n", " ").replace("\t", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _coerce_text_for_font(text: str, font_obj: Any) -> Tuple[str, bool]:
    """
    Replace unsupported glyphs with ASCII-safe fallbacks to preserve the original font.
    Returns (coerced_text, changed).
    """
    changed = False
    out: List[str] = []
    has_question = font_obj.has_glyph(ord("?"))

    for ch in text:
        if ch.isspace():
            out.append(ch)
            continue

        if font_obj.has_glyph(ord(ch)):
            out.append(ch)
            continue

        fallback = UNICODE_FALLBACKS.get(ch)
        if fallback and all(c.isspace() or font_obj.has_glyph(ord(c)) for c in fallback):
            out.append(fallback)
            changed = True
            continue

        if has_question:
            out.append("?")
            changed = True
            continue

        # Drop last-resort unsupported glyph to avoid forcing a full font fallback.
        changed = True

    return "".join(out), changed


def _measure_text_width(
    text: str,
    font_name: str,
    font_size: float,
    font_obj: Optional[Any] = None,
) -> float:
    if font_obj:
        return font_obj.text_length(text, fontsize=font_size)
    return fitz.get_text_length(text, fontname=font_name, fontsize=font_size)


def _compact_text_to_fit(
    text: str,
    max_width: float,
    font_name: str,
    font_size: float,
    font_obj: Optional[Any] = None,
) -> Optional[str]:
    """
    Deterministically shorten text while preserving meaning as much as possible.
    Returns a fitted string or None if no safe compaction fits.
    """
    original = _normalize_replacement_text(text)
    if not original:
        return None

    def width(s: str) -> float:
        return _measure_text_width(s, font_name, font_size, font_obj=font_obj)

    if width(original) <= max_width:
        return original

    def apply_replacements(s: str, replacements: List[Tuple[str, str]]) -> str:
        out = s
        for src, dst in replacements:
            out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", out).strip()

    phrase_replacements = [
        ("application programming interfaces", "APIs"),
        ("application programming interface", "API"),
        ("machine learning", "ML"),
        ("artificial intelligence", "AI"),
        ("with respect to", "for"),
        ("in order to", "to"),
        ("as well as", "and"),
        ("real-time", "realtime"),
        ("real time", "realtime"),
        ("approximately", "~"),
        ("percent", "%"),
        ("through", "via"),
    ]
    word_replacements = [
        ("implemented", "built"),
        ("implementation", "build"),
        ("developed", "built"),
        ("utilized", "used"),
        ("leveraged", "used"),
        ("optimized", "improved"),
        ("facilitated", "enabled"),
    ]
    filler_words = [
        "the", "a", "an", "that", "which", "very", "really", "successfully",
    ]

    candidates: List[str] = []

    c1 = apply_replacements(original, phrase_replacements)
    candidates.append(c1)

    c2 = apply_replacements(c1, word_replacements)
    candidates.append(c2)

    c3 = c2
    for fw in filler_words:
        c3 = re.sub(rf"\b{re.escape(fw)}\b\s*", "", c3, flags=re.IGNORECASE)
    c3 = re.sub(r"\s+", " ", c3).strip(" ,;")
    candidates.append(c3)

    # Clause trimming as a last resort.
    # Preserve at least 70% of original character length to avoid semantic collapse.
    min_chars = max(8, int(len(original) * 0.7))
    c4 = c3
    for sep in ["; ", ", ", " - "]:
        if width(c4) <= max_width:
            break
        parts = c4.split(sep)
        while len(parts) > 1 and len(sep.join(parts[:-1])) >= min_chars:
            trial = sep.join(parts[:-1]).strip(" ,;")
            if trial and width(trial) <= max_width:
                return trial
            parts = parts[:-1]
        c4 = sep.join(parts)
    candidates.append(c4)

    for cand in candidates:
        cand = _normalize_replacement_text(cand)
        if cand and len(cand) >= min_chars and width(cand) <= max_width:
            return cand

    return None


def _resolve_font(
    original_font_name: str,
    new_text: str,
    font_cache: Dict[str, Dict[str, Any]],
) -> Tuple[str, Optional[bytes], Optional[Any], str, bool]:
    """Try to reuse the original embedded font. Falls back to Base14.

    Returns (fontname_for_insert, font_buffer_or_None, font_obj_or_None, text_for_insert, used_fallback_font).
    When font_buffer is not None, the caller must call page.insert_font() before insert_text().
    """
    # Try exact match
    info = font_cache.get(original_font_name)

    # Try without subset prefix
    if not info and "+" in original_font_name:
        clean = original_font_name.split("+", 1)[-1]
        info = font_cache.get(clean)

    # Try partial match (e.g. span says "Calibri" but cache has "Calibri-Bold")
    if not info:
        name_lower = original_font_name.lower()
        for cached_name, cached_info in font_cache.items():
            if name_lower in cached_name.lower() or cached_name.lower() in name_lower:
                info = cached_info
                break

    if info and info.get("num_glyphs", 0) > 0:
        try:
            font_obj = info["font_obj"]
            # Validate every non-whitespace character is present in the subset font
            missing = [c for c in new_text if not c.isspace() and not font_obj.has_glyph(ord(c))]
            if not missing:
                ref_name = f"f{info['xref']}"
                return ref_name, info["buffer"], font_obj, new_text, False
            else:
                coerced_text, changed = _coerce_text_for_font(new_text, font_obj)
                missing_after = [c for c in coerced_text if not c.isspace() and not font_obj.has_glyph(ord(c))]
                if not missing_after:
                    if changed:
                        logger.info(
                            f"[FONTS] Coerced {len(missing)} unsupported glyph(s) for '{original_font_name}' "
                            f"to preserve original font"
                        )
                    ref_name = f"f{info['xref']}"
                    return ref_name, info["buffer"], font_obj, coerced_text, False
                logger.info(
                    f"[FONTS] Font '{original_font_name}' missing {len(missing_after)} glyphs after coercion, "
                    f"falling back to Base14"
                )
        except Exception as e:
            logger.warning(f"[FONTS] Glyph check failed for '{original_font_name}': {e}")

    # Fallback to Base14
    return _map_to_base14(original_font_name), None, None, new_text, True


def _map_to_base14(font_name: str) -> str:
    """Map an original font name to a PyMuPDF Base14 font (fallback only)."""
    name_lower = font_name.lower()

    if "times" in name_lower or "serif" in name_lower:
        if "bold" in name_lower and "italic" in name_lower:
            return "tibi"
        elif "bold" in name_lower:
            return "tibo"
        elif "italic" in name_lower:
            return "tiit"
        return "tiro"

    if "arial" in name_lower or "helvetica" in name_lower or "sans" in name_lower:
        if "bold" in name_lower and "italic" in name_lower:
            return "hebi"
        elif "bold" in name_lower:
            return "hebo"
        elif "italic" in name_lower or "oblique" in name_lower:
            return "heit"
        return "helv"

    if "courier" in name_lower or "mono" in name_lower:
        if "bold" in name_lower:
            return "cobo"
        elif "italic" in name_lower or "oblique" in name_lower:
            return "coit"
        return "cour"

    if "calibri" in name_lower or "cambria" in name_lower:
        if "bold" in name_lower:
            return "hebo"
        return "helv"

    if "garamond" in name_lower:
        if "bold" in name_lower:
            return "tibo"
        return "tiro"

    # Default
    if "bold" in name_lower:
        return "tibo"
    if "italic" in name_lower:
        return "tiit"
    return "tiro"


def _fit_text(
    text: str,
    font: str,
    size: float,
    max_width: float,
    font_obj: Optional[Any] = None,
    max_size_reduction: float = 0.0,
) -> Optional[Tuple[str, float]]:
    """
    Fit text to available width. Returns (text, font_size) or None if it cannot fit.
    Uses font_obj.text_length() for extracted fonts, fitz.get_text_length() for Base14.
    Never truncates content.
    """
    try:
        text_width = _measure_text_width(text, font, size, font_obj=font_obj)
        if text_width <= max_width:
            return text, size

        if max_size_reduction <= 0:
            return None

        # Controlled reductions if explicitly allowed.
        step = 0.1
        reduction = step
        while reduction <= max_size_reduction + 1e-9:
            smaller = size - reduction
            if smaller < 6:
                break
            if _measure_text_width(text, font, smaller, font_obj=font_obj) <= max_width:
                return text, smaller
            reduction += step
        return None

    except Exception:
        return None


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

    # Step 3: Optimize with Claude
    bullet_replacements, skill_replacements, title_replacements = await generate_optimized_content(
        bullets, skills, job_description, title_skills,
    )
    bullet_replacements = sanitize_bullet_replacements(
        bullets, bullet_replacements, length_tolerance=0.15
    )
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
