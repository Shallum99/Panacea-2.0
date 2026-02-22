# File: backend/app/services/resume_editor.py
"""
Resume editor service: form map extraction, prompt-based editing, diff generation.
Bypasses the chat agent — direct prompt → result pipeline.
"""

import json
import logging
import re
import copy
import difflib
from typing import Any, Dict, List, Optional, Tuple

import fitz

from app.services.pdf_format_preserver import (
    extract_spans_from_pdf,
    group_into_visual_lines,
    classify_lines,
    group_bullet_points,
    sanitize_bullet_replacements,
    apply_changes_to_pdf,
    BulletPoint,
    SkillLine,
    TitleSkillLine,
    ClassifiedLine,
    LineType,
)
from app.llm.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


# ── Form Map Builder ──────────────────────────────────────────────────

def build_form_map(pdf_path: str, resume_id: int = 0) -> Dict[str, Any]:
    """
    Parse a resume PDF and return a structured form map of all editable fields.
    Each field has a unique ID, type, current text, and character budget.

    Includes header/structure fields (name, contact, section headings) as
    editable "header" type fields for direct text replacement.
    """
    spans = extract_spans_from_pdf(pdf_path)
    lines = group_into_visual_lines(spans)
    classified, _ = classify_lines(lines)
    bullets, skills, title_skills = group_bullet_points(classified)

    fields: List[Dict[str, Any]] = []

    # Build header/structure fields from STRUCTURE classified lines
    # Include name, contact info, and other standalone text (not section headers)
    header_texts: List[Dict[str, Any]] = []
    for cl in classified:
        if cl.line_type != LineType.STRUCTURE:
            continue
        clean = "".join(s.text for s in cl.spans).replace("\u200b", "").strip()
        if not clean or len(clean) < 2:
            continue
        # Skip section header lines (all-caps short text like "SKILLS", "EXPERIENCE")
        alpha = [c for c in clean if c.isalpha()]
        is_section_header = (
            alpha and all(c.isupper() for c in alpha) and len(clean) < 40
        )
        if is_section_header:
            continue
        header_texts.append({
            "text": clean,
            "classified_line": cl,
        })

    for i, ht in enumerate(header_texts):
        fields.append({
            "id": f"header-{i}",
            "type": "header",
            "section": "HEADER",
            "text": ht["text"],
            "max_chars": len(ht["text"]) + 20,
            "protected": False,
            "_header_index": i,
            "_header_orig_text": ht["text"],
        })

    # Build bullet fields
    for i, bp in enumerate(bullets):
        section_slug = re.sub(r'[^a-z0-9]+', '-', bp.section_name.lower()).strip('-')
        fields.append({
            "id": f"{section_slug}-b{i}",
            "type": "bullet",
            "section": bp.section_name,
            "text": bp.full_text,
            "line_count": len(bp.text_lines),
            "char_per_line": bp.line_char_counts,
            "max_chars": sum(bp.line_char_counts),
            "protected": False,
            "_bullet_index": i,
        })

    # Build skill fields
    for i, sl in enumerate(skills):
        fields.append({
            "id": f"skill-{i}",
            "type": "skill",
            "section": sl.section_name,
            "text": sl.content_text,
            "label": sl.label_text,
            "max_chars": len(sl.content_text) + 20,
            "protected": False,
            "_skill_index": i,
        })

    # Build title fields
    for i, ts in enumerate(title_skills):
        fields.append({
            "id": f"title-{i}",
            "type": "title",
            "section": "EXPERIENCE",
            "text": ts.skills_part,
            "label": ts.title_part,
            "max_chars": len(ts.skills_part) + 10,
            "protected": False,
            "_title_index": i,
        })

    # Font quality heuristic: check if most fonts have ToUnicode CMaps
    font_coverage_pct = _estimate_font_coverage(pdf_path)
    font_quality = "good" if font_coverage_pct >= 80 else "limited"

    return {
        "fields": fields,
        "editable_fields": len(fields),
        "font_quality": font_quality,
        "font_coverage_pct": font_coverage_pct,
        "resume_id": resume_id,
        # Internal data for apply step (not sent to frontend)
        "_bullets": bullets,
        "_skills": skills,
        "_title_skills": title_skills,
        "_header_texts": header_texts,
    }


def _estimate_font_coverage(pdf_path: str) -> float:
    """Estimate what percentage of fonts have ToUnicode CMaps."""
    try:
        doc = fitz.open(pdf_path)
        total_fonts = 0
        fonts_with_cmap = 0
        for page in doc:
            font_list = page.get_fonts(full=True)
            for font_info in font_list:
                total_fonts += 1
                # Check if font has encoding info
                if font_info[3]:  # encoding field
                    fonts_with_cmap += 1
        doc.close()
        return (fonts_with_cmap / total_fonts * 100) if total_fonts > 0 else 100.0
    except Exception:
        return 100.0


def strip_internal_fields(form_map: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal fields before sending to frontend."""
    public_fields = []
    for f in form_map["fields"]:
        pf = {k: v for k, v in f.items() if not k.startswith("_")}
        public_fields.append(pf)
    return {
        "fields": public_fields,
        "editable_fields": form_map["editable_fields"],
        "font_quality": form_map["font_quality"],
        "font_coverage_pct": form_map["font_coverage_pct"],
        "resume_id": form_map["resume_id"],
    }


# ── Prompt-Based Edit ─────────────────────────────────────────────────

async def apply_prompt_edits(
    pdf_path: str,
    output_path: str,
    form_map: Dict[str, Any],
    prompt: str,
    field_targets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Apply user prompt edits to a PDF.

    1. Build resume context from form_map
    2. Send to Claude with edit instructions
    3. Parse response, map field_ids back to indices
    4. Apply changes via apply_changes_to_pdf() + direct replacement for headers
    5. Return structured changes (only those that were actually applied)
    """
    bullets = form_map["_bullets"]
    skills = form_map["_skills"]
    title_skills = form_map["_title_skills"]
    header_texts = form_map.get("_header_texts", [])
    fields = form_map["fields"]

    # Build field-id to index mappings
    field_id_to_bullet = {}
    field_id_to_skill = {}
    field_id_to_title = {}
    field_id_to_header = {}
    for f in fields:
        if f["type"] == "bullet":
            field_id_to_bullet[f["id"]] = f["_bullet_index"]
        elif f["type"] == "skill":
            field_id_to_skill[f["id"]] = f["_skill_index"]
        elif f["type"] == "title":
            field_id_to_title[f["id"]] = f["_title_index"]
        elif f["type"] == "header":
            field_id_to_header[f["id"]] = f["_header_index"]

    # Build resume map for Claude
    resume_map_parts = []
    for f in fields:
        if field_targets and f["id"] not in field_targets:
            continue
        if f["type"] == "header":
            resume_map_parts.append(
                f'HEADER [{f["id"]}]: "{f["text"]}"'
            )
        elif f["type"] == "bullet":
            bp = bullets[f["_bullet_index"]]
            chars = bp.line_char_counts
            resume_map_parts.append(
                f'BULLET [{f["id"]}] ({f["section"]}, {len(bp.text_lines)} lines, chars/line: {chars}):\n  "{bp.full_text}"'
            )
        elif f["type"] == "skill":
            resume_map_parts.append(
                f'SKILL [{f["id"]}] ({f["section"]}): label="{f.get("label", "")}" content="{f["text"]}"'
            )
        elif f["type"] == "title":
            resume_map_parts.append(
                f'TITLE [{f["id"]}]: title="{f.get("label", "")}" skills="{f["text"]}"'
            )

    resume_map = "\n".join(resume_map_parts)

    # Send to Claude
    claude = ClaudeClient()
    edit_prompt = f"""You are editing a resume PDF. Below are the editable fields with their IDs.

The user wants: {prompt}

RESUME FIELDS:
{resume_map}

RULES:
- Only change what the user asked for. Leave everything else untouched.
- For HEADER fields: return a single string replacement. You CAN change names, contact info, etc.
- For bullets: each replacement MUST have the SAME number of lines as the original.
- For bullets: each line should be SIMILAR length to the original line (some variation is OK).
- For skills: return only the content part (not the bold label).
- For title skills: return only the skills part (not the title).
- Preserve all metrics, dates, company names unless the user explicitly asked to change them.

Return JSON with ONLY the fields you changed:
{{
  "changes": [
    {{
      "field_id": "<field_id from above>",
      "new_text": "replacement text" ,
      "reasoning": "brief explanation of change"
    }}
  ]
}}

For HEADER fields: "new_text" is a single string.
For BULLET fields: "new_text" must be an ARRAY of strings (one per line), matching the original line count.
For SKILL and TITLE fields: "new_text" is a single string.

Return ONLY the JSON object, nothing else. If nothing should change, return {{"changes": []}}"""

    logger.info(f"[EDITOR] Sending edit prompt to Claude: {prompt[:100]}...")
    edit_text = await claude._send_request(
        system_prompt="You make precise, targeted edits to resume text. Return only valid JSON.",
        user_prompt=edit_prompt,
        max_tokens=4096,
    )

    # Parse response
    match = re.search(r'\{[\s\S]*\}', edit_text)
    if match:
        edits = json.loads(match.group())
    else:
        edits = json.loads(edit_text)

    raw_changes = edits.get("changes", [])
    if not raw_changes:
        return {"changes": [], "bullet_replacements": {}, "skill_replacements": {}, "title_replacements": {}, "header_replacements": {}}

    # Map field_ids back to indices
    bullet_replacements: Dict[int, List[str]] = {}
    skill_replacements: Dict[int, str] = {}
    title_replacements: Dict[int, str] = {}
    header_replacements: Dict[str, str] = {}  # orig_text → new_text
    structured_changes = []

    for change in raw_changes:
        fid = change.get("field_id", "")
        new_text = change.get("new_text", "")
        reasoning = change.get("reasoning", "")

        if fid in field_id_to_header:
            idx = field_id_to_header[fid]
            content = str(new_text).strip() if not isinstance(new_text, list) else " ".join(new_text)
            orig_field = next((f for f in fields if f["id"] == fid), None)
            orig_text = orig_field["_header_orig_text"] if orig_field else ""
            header_replacements[orig_text] = content
            structured_changes.append({
                "field_id": fid,
                "field_type": "header",
                "section": "HEADER",
                "original_text": orig_text,
                "new_text": content,
                "reasoning": reasoning,
            })

        elif fid in field_id_to_bullet:
            idx = field_id_to_bullet[fid]
            # new_text should be a list of strings for bullets
            if isinstance(new_text, list):
                lines = new_text
            elif isinstance(new_text, str):
                # Single string — split into original line count
                bp = bullets[idx]
                orig_lines = len(bp.text_lines)
                if orig_lines == 1:
                    lines = [new_text]
                else:
                    # Try to split at sentence boundaries
                    lines = _split_text_to_lines(new_text, bp.line_char_counts)
            else:
                continue
            bullet_replacements[idx] = lines
            # Find original text from field
            orig_field = next((f for f in fields if f["id"] == fid), None)
            structured_changes.append({
                "field_id": fid,
                "field_type": "bullet",
                "section": orig_field["section"] if orig_field else None,
                "original_text": orig_field["text"] if orig_field else "",
                "new_text": " ".join(lines),
                "reasoning": reasoning,
            })

        elif fid in field_id_to_skill:
            idx = field_id_to_skill[fid]
            content = str(new_text).strip() if not isinstance(new_text, list) else " ".join(new_text)
            skill_replacements[idx] = content
            orig_field = next((f for f in fields if f["id"] == fid), None)
            structured_changes.append({
                "field_id": fid,
                "field_type": "skill",
                "section": orig_field["section"] if orig_field else None,
                "original_text": orig_field["text"] if orig_field else "",
                "new_text": content,
                "reasoning": reasoning,
            })

        elif fid in field_id_to_title:
            idx = field_id_to_title[fid]
            content = str(new_text).strip() if not isinstance(new_text, list) else " ".join(new_text)
            title_replacements[idx] = content
            orig_field = next((f for f in fields if f["id"] == fid), None)
            structured_changes.append({
                "field_id": fid,
                "field_type": "title",
                "section": orig_field["section"] if orig_field else None,
                "original_text": orig_field["text"] if orig_field else "",
                "new_text": content,
                "reasoning": reasoning,
            })
        else:
            logger.warning(f"[EDITOR] Unknown field_id in Claude response: {fid}")

    # Sanitize bullet replacements with higher tolerance for editor
    # (PDF engine handles width via Tc character spacing, so we can be lenient)
    if bullet_replacements:
        bullet_replacements = sanitize_bullet_replacements(
            bullets, bullet_replacements, length_tolerance=0.50
        )

    # Validate skill/title indices
    skill_replacements = {
        idx: content for idx, content in skill_replacements.items()
        if 0 <= idx < len(skills)
    }
    title_replacements = {
        idx: content for idx, content in title_replacements.items()
        if 0 <= idx < len(title_skills)
    }

    has_any_changes = (
        bool(bullet_replacements) or bool(skill_replacements)
        or bool(title_replacements) or bool(header_replacements)
    )

    if not has_any_changes:
        logger.warning("[EDITOR] All edits were dropped during sanitization")
        return {"changes": [], "bullet_replacements": {}, "skill_replacements": {}, "title_replacements": {}, "header_replacements": {}}

    # Filter structured_changes to only include changes that survived sanitization
    surviving_bullet_ids = set()
    for idx in bullet_replacements:
        for f in fields:
            if f.get("_bullet_index") == idx:
                surviving_bullet_ids.add(f["id"])
    surviving_skill_ids = set()
    for idx in skill_replacements:
        for f in fields:
            if f.get("_skill_index") == idx:
                surviving_skill_ids.add(f["id"])
    surviving_title_ids = set()
    for idx in title_replacements:
        for f in fields:
            if f.get("_title_index") == idx:
                surviving_title_ids.add(f["id"])
    surviving_header_ids = set()
    for orig_text in header_replacements:
        for f in fields:
            if f.get("_header_orig_text") == orig_text:
                surviving_header_ids.add(f["id"])

    all_surviving = surviving_bullet_ids | surviving_skill_ids | surviving_title_ids | surviving_header_ids
    structured_changes = [c for c in structured_changes if c["field_id"] in all_surviving]

    # Apply bullet/skill/title changes to PDF
    if bullet_replacements or skill_replacements or title_replacements:
        logger.info(f"[EDITOR] Applying: {len(bullet_replacements)} bullets, {len(skill_replacements)} skills, {len(title_replacements)} titles")
        apply_changes_to_pdf(
            pdf_path, output_path,
            bullets, skills,
            bullet_replacements, skill_replacements,
            title_skills, title_replacements,
        )
    else:
        # No bullet/skill/title changes — copy source PDF for header-only edits
        import shutil
        shutil.copy2(pdf_path, output_path)

    # Apply header replacements via direct content stream patching
    if header_replacements:
        logger.info(f"[EDITOR] Applying {len(header_replacements)} header replacements")
        _apply_header_replacements(output_path, header_replacements)

    return {
        "changes": structured_changes,
        "bullet_replacements": bullet_replacements,
        "skill_replacements": skill_replacements,
        "title_replacements": title_replacements,
        "header_replacements": header_replacements,
    }


def _apply_header_replacements(pdf_path: str, replacements: Dict[str, str]):
    """
    Apply header text replacements using PyMuPDF redaction.
    For each replacement: find exact text location, detect font/size/color,
    redact original, and insert new text with matching appearance.
    """
    doc = fitz.open(pdf_path)
    modified = False

    for page in doc:
        for orig_text, new_text in replacements.items():
            # Search for exact text on this page
            rects = page.search_for(orig_text)
            if not rects:
                continue

            # Get font info from the text at that location
            font_name = "helv"  # fallback
            font_size = 12.0
            text_color = (0, 0, 0)

            # Extract font details from the page's text dict
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
            for block in blocks:
                if block.get("type") != 0:  # text block
                    continue
                for line in block.get("lines", []):
                    line_text = "".join(s["text"] for s in line.get("spans", []))
                    if orig_text in line_text:
                        # Found the line — get font info from the first matching span
                        for span in line.get("spans", []):
                            if span["text"].strip() and any(
                                c in orig_text for c in span["text"].strip()[:5]
                            ):
                                font_name = span.get("font", "helv")
                                font_size = span.get("size", 12.0)
                                # Color is an int — convert to RGB tuple
                                color_int = span.get("color", 0)
                                text_color = (
                                    ((color_int >> 16) & 0xFF) / 255.0,
                                    ((color_int >> 8) & 0xFF) / 255.0,
                                    (color_int & 0xFF) / 255.0,
                                )
                                break
                        break

            # Apply redaction for each found rect
            for rect in rects:
                # Use the built-in font name mapping for fitz
                fitz_font = _map_to_fitz_font(font_name)
                page.add_redact_annot(
                    rect,
                    text=new_text,
                    fontname=fitz_font,
                    fontsize=font_size,
                    text_color=text_color,
                    fill=(1, 1, 1),  # white background to cover original
                )

            page.apply_redactions()
            modified = True
            logger.info(f"[EDITOR] Header replaced: '{orig_text}' → '{new_text}' "
                        f"(font={font_name}, size={font_size})")

    if modified:
        import tempfile, shutil, os
        # fitz can't save to the same path it opened — use a temp file
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        doc.save(tmp_path, garbage=4, deflate=True)
        doc.close()
        shutil.move(tmp_path, pdf_path)
    else:
        doc.close()


def _map_to_fitz_font(pdf_font_name: str) -> str:
    """Map PDF font name to a fitz built-in font name for redaction."""
    name = pdf_font_name.lower()
    if "times" in name:
        if "bold" in name and "italic" in name:
            return "tibi"
        if "bold" in name:
            return "tibo"
        if "italic" in name:
            return "tiit"
        return "tiro"
    if "arial" in name or "helvetica" in name:
        if "bold" in name and ("italic" in name or "oblique" in name):
            return "hebi"
        if "bold" in name:
            return "hebo"
        if "italic" in name or "oblique" in name:
            return "heit"
        return "helv"
    if "courier" in name:
        if "bold" in name and ("italic" in name or "oblique" in name):
            return "cobi"
        if "bold" in name:
            return "cobo"
        if "italic" in name or "oblique" in name:
            return "coit"
        return "cour"
    # Default to helvetica for sans-serif-like fonts
    return "helv"


def _split_text_to_lines(text: str, target_char_counts: List[int]) -> List[str]:
    """Split a single string into multiple lines matching target character counts."""
    if len(target_char_counts) <= 1:
        return [text]

    words = text.split()
    lines = []
    current_line: List[str] = []
    current_len = 0
    target_idx = 0

    for word in words:
        word_len = len(word)
        target = target_char_counts[target_idx] if target_idx < len(target_char_counts) else target_char_counts[-1]

        if current_len + word_len + (1 if current_line else 0) > target * 1.15 and current_line and target_idx < len(target_char_counts) - 1:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = word_len
            target_idx += 1
        else:
            if current_line:
                current_len += 1  # space
            current_line.append(word)
            current_len += word_len

    if current_line:
        lines.append(" ".join(current_line))

    # Pad to match expected line count
    while len(lines) < len(target_char_counts):
        lines.append("")
    # Truncate if too many
    if len(lines) > len(target_char_counts):
        # Merge excess into last line
        excess = lines[len(target_char_counts) - 1:]
        lines = lines[:len(target_char_counts) - 1]
        lines.append(" ".join(excess))

    return lines


# ── Diff PDF Generator ────────────────────────────────────────────────

def generate_diff_pdf(original_path: str, edited_bytes: bytes) -> bytes:
    """
    Generate a diff PDF with green highlights on changed words.
    Compares original PDF with edited PDF word by word per line.
    Returns the diff PDF as bytes.
    """
    orig_doc = fitz.open(original_path)
    diff_doc = fitz.open(stream=edited_bytes, filetype="pdf")
    green = fitz.utils.getColor("green")

    def _group_words_by_line(words, y_tolerance=3):
        lines: Dict[float, list] = {}
        for w in words:
            y_key = round(w[1] / y_tolerance) * y_tolerance
            if y_key not in lines:
                lines[y_key] = []
            lines[y_key].append(w)
        for y_key in lines:
            lines[y_key].sort(key=lambda w: w[0])
        return lines

    for page_idx in range(min(len(diff_doc), len(orig_doc))):
        orig_page = orig_doc[page_idx]
        diff_page = diff_doc[page_idx]
        orig_words = orig_page.get_text("words")
        opt_words = diff_page.get_text("words")
        orig_lines = _group_words_by_line(orig_words)
        opt_lines = _group_words_by_line(opt_words)
        orig_y_keys = sorted(orig_lines.keys())

        for y_key, opt_line_words in opt_lines.items():
            closest_y = min(orig_y_keys, key=lambda oy: abs(oy - y_key)) if orig_y_keys else None
            if closest_y is None or abs(closest_y - y_key) > 6:
                for w in opt_line_words:
                    rect = fitz.Rect(w[0], w[1], w[2], w[3])
                    annot = diff_page.add_highlight_annot(rect)
                    annot.set_colors(stroke=green)
                    annot.set_opacity(0.35)
                    annot.update()
                continue
            orig_line_words = orig_lines[closest_y]
            orig_texts = [w[4] for w in orig_line_words]
            opt_texts = [w[4] for w in opt_line_words]
            if orig_texts == opt_texts:
                continue
            matcher = difflib.SequenceMatcher(None, orig_texts, opt_texts)
            for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
                if tag in ("replace", "insert"):
                    for wi in range(j1, j2):
                        w = opt_line_words[wi]
                        rect = fitz.Rect(w[0], w[1], w[2], w[3])
                        annot = diff_page.add_highlight_annot(rect)
                        annot.set_colors(stroke=green)
                        annot.set_opacity(0.35)
                        annot.update()

    orig_doc.close()
    diff_bytes = diff_doc.tobytes()
    diff_doc.close()
    return diff_bytes
