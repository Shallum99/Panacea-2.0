#!/usr/bin/env python3
"""
Comprehensive PDF Content Stream Engine Test Harness

Tests the content stream engine against diverse resume formats:
- LaTeX-generated (Type1, CID fonts)
- Google Docs exported (TrueType)
- Microsoft Word exported (TrueType, CID)
- Canva exported (embedded fonts)
- Various template styles (Harvard, Europass, ATS-friendly, creative)

For each PDF, the test:
1. Extracts spans and classifies lines
2. Groups bullet points, skills, and title skills
3. Parses content stream (BT/ET blocks, CIDs)
4. Builds CMap (forward + reverse)
5. Attempts to encode replacement text for each bullet/skill
6. Patches the content stream in-place
7. Verifies font identity between original and patched PDF
8. Reports match rate and any failures
"""

import sys
import os
import json
import logging
import traceback
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fitz  # PyMuPDF

from app.services.pdf_format_preserver import (
    extract_spans_from_pdf,
    group_into_visual_lines,
    classify_lines,
    group_bullet_points,
    apply_changes_to_pdf,
    _CMapManager,
    _WidthCalculator,
    _FontAugmentor,
    _parse_content_stream,
    _patch_content_stream,
    _find_blocks_for_text,
    _texts_match,
    ContentBlock,
    TextOp,
    BulletPoint,
    SkillLine,
    TitleSkillLine,
    LineType,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


# ── Test Result Data ──────────────────────────────────────────────────────────

@dataclass
class PDFAnalysis:
    """Analysis of a single PDF's internal structure."""
    filename: str
    file_size: int
    num_pages: int
    # Font info
    fonts: List[Dict]  # [{name, type, encoding, subset, xref}]
    font_types: List[str]  # ["Type0", "TrueType", "Type1", ...]
    has_tounicode: Dict[str, bool]  # font_tag → has ToUnicode CMap
    cid_byte_widths: Dict[str, int]  # font_tag → byte_width (1 or 2)
    # Content structure
    total_spans: int
    total_lines: int
    bullet_count: int
    skill_count: int
    title_skill_count: int
    structure_count: int
    # Content stream
    content_blocks_per_page: Dict[int, int]  # page → num blocks
    total_content_blocks: int
    # Matching
    bullets_matchable: int  # bullets where content blocks were found
    skills_matchable: int
    # Encoding
    bullets_encodable: int  # bullets where ALL chars can be encoded
    skills_encodable: int
    # Patching
    bullets_patched: int
    skills_patched: int
    title_skills_patched: int
    # Font verification
    fonts_identical: bool
    font_diff: List[str]  # any font differences
    # Errors
    errors: List[str] = field(default_factory=list)


def analyze_pdf_structure(pdf_path: str) -> dict:
    """Deep analysis of PDF internal structure."""
    doc = fitz.open(pdf_path)
    info = {
        "pages": len(doc),
        "fonts": [],
        "font_types": set(),
        "has_images": False,
        "has_form_xobjects": False,
        "content_stream_count": {},
    }

    for page_idx in range(len(doc)):
        page = doc[page_idx]

        # Font analysis
        for f in page.get_fonts():
            xref, ext, subtype, basefont, name, encoding = f[0], f[1], f[2], f[3], f[4], f[5] if len(f) > 5 else ""
            is_subset = "+" in basefont
            clean_name = basefont.split("+", 1)[-1] if "+" in basefont else basefont

            font_info = {
                "xref": xref,
                "tag": name,
                "basefont": basefont,
                "clean_name": clean_name,
                "subtype": subtype,
                "ext": ext,
                "encoding": encoding,
                "is_subset": is_subset,
                "page": page_idx,
            }

            # Check for ToUnicode CMap
            try:
                tu_val = doc.xref_get_key(xref, "ToUnicode")
                font_info["has_tounicode"] = tu_val[0] != "null" and bool(tu_val[1])
            except:
                font_info["has_tounicode"] = False

            # Check font descriptor
            try:
                desc_val = doc.xref_get_key(xref, "FontDescriptor")
                font_info["has_descriptor"] = desc_val[0] != "null"
            except:
                font_info["has_descriptor"] = False

            # Check for DescendantFonts (Type0)
            try:
                df_val = doc.xref_get_key(xref, "DescendantFonts")
                font_info["has_descendants"] = df_val[0] != "null"
            except:
                font_info["has_descendants"] = False

            info["fonts"].append(font_info)
            info["font_types"].add(subtype)

        # Content stream analysis
        content_xrefs = page.get_contents()
        info["content_stream_count"][page_idx] = len(content_xrefs)

        # Check for images and form XObjects
        imgs = page.get_images()
        if imgs:
            info["has_images"] = True

    info["font_types"] = sorted(info["font_types"])
    doc.close()
    return info


def run_pdf_extraction(pdf_path: str) -> Tuple[int, int, int, int, int, List[str]]:
    """Test span extraction + classification on a PDF. Returns counts and errors."""
    errors = []
    try:
        spans = extract_spans_from_pdf(pdf_path)
    except Exception as e:
        return 0, 0, 0, 0, 0, [f"extract_spans failed: {e}"]

    try:
        lines = group_into_visual_lines(spans)
    except Exception as e:
        return len(spans), 0, 0, 0, 0, [f"group_into_visual_lines failed: {e}"]

    try:
        classified, section_map = classify_lines(lines)
    except Exception as e:
        return len(spans), len(lines), 0, 0, 0, [f"classify_lines failed: {e}"]

    bullet_count = sum(1 for c in classified if c.line_type == LineType.BULLET_TEXT)
    skill_count = sum(1 for c in classified if c.line_type == LineType.SKILL_CONTENT)
    structure_count = sum(1 for c in classified if c.line_type == LineType.STRUCTURE)

    try:
        bullets, skills, title_skills = group_bullet_points(classified)
    except Exception as e:
        return len(spans), len(lines), bullet_count, skill_count, structure_count, [f"group_bullet_points failed: {e}"]

    return len(spans), len(lines), len(bullets), len(skills), len(title_skills), errors


def run_content_stream_engine(pdf_path: str) -> PDFAnalysis:
    """Full content stream engine test on a single PDF."""
    filename = os.path.basename(pdf_path)
    file_size = os.path.getsize(pdf_path)

    analysis = PDFAnalysis(
        filename=filename,
        file_size=file_size,
        num_pages=0,
        fonts=[],
        font_types=[],
        has_tounicode={},
        cid_byte_widths={},
        total_spans=0,
        total_lines=0,
        bullet_count=0,
        skill_count=0,
        title_skill_count=0,
        structure_count=0,
        content_blocks_per_page={},
        total_content_blocks=0,
        bullets_matchable=0,
        skills_matchable=0,
        bullets_encodable=0,
        skills_encodable=0,
        bullets_patched=0,
        skills_patched=0,
        title_skills_patched=0,
        fonts_identical=False,
        font_diff=[],
    )

    # ── Step 1: PDF structure analysis ──
    try:
        struct = analyze_pdf_structure(pdf_path)
        analysis.num_pages = struct["pages"]
        analysis.fonts = struct["fonts"]
        analysis.font_types = struct["font_types"]
    except Exception as e:
        analysis.errors.append(f"Structure analysis failed: {e}")
        return analysis

    # ── Step 2: Extraction + classification ──
    try:
        spans = extract_spans_from_pdf(pdf_path)
        analysis.total_spans = len(spans)
    except Exception as e:
        analysis.errors.append(f"Span extraction failed: {e}")
        return analysis

    try:
        vis_lines = group_into_visual_lines(spans)
        analysis.total_lines = len(vis_lines)
    except Exception as e:
        analysis.errors.append(f"Visual line grouping failed: {e}")
        return analysis

    try:
        classified, section_map = classify_lines(vis_lines)
        analysis.structure_count = sum(1 for c in classified if c.line_type == LineType.STRUCTURE)
    except Exception as e:
        analysis.errors.append(f"Classification failed: {e}")
        return analysis

    try:
        bullets, skills, title_skills = group_bullet_points(classified)
        analysis.bullet_count = len(bullets)
        analysis.skill_count = len(skills)
        analysis.title_skill_count = len(title_skills)
    except Exception as e:
        analysis.errors.append(f"Grouping failed: {e}")
        return analysis

    if analysis.bullet_count == 0 and analysis.skill_count == 0:
        analysis.errors.append("No bullets or skills found — nothing to patch")
        return analysis

    # ── Step 3: Content stream engine ──
    doc = fitz.open(pdf_path)

    try:
        cmap_mgr = _CMapManager(doc)
        # Record CMap info
        for font_tag, font_data in cmap_mgr.font_cmaps.items():
            analysis.has_tounicode[font_tag] = bool(font_data.get("fwd"))
            analysis.cid_byte_widths[font_tag] = font_data.get("byte_width", 2)
    except Exception as e:
        analysis.errors.append(f"CMapManager failed: {e}")
        doc.close()
        return analysis

    try:
        width_calc = _WidthCalculator(doc)
    except Exception as e:
        analysis.errors.append(f"WidthCalculator failed: {e}")
        doc.close()
        return analysis

    # Parse content streams for each page
    all_blocks_per_page: Dict[int, List[ContentBlock]] = {}
    for page_num in range(len(doc)):
        page = doc[page_num]
        content_xrefs = page.get_contents()
        page_blocks = []
        for xref in content_xrefs:
            try:
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap_mgr, page_num, xref)
                page_blocks.extend(blocks)
            except Exception as e:
                analysis.errors.append(f"Content stream parse failed (page {page_num}, xref {xref}): {e}")
        all_blocks_per_page[page_num] = page_blocks
        analysis.content_blocks_per_page[page_num] = len(page_blocks)

    analysis.total_content_blocks = sum(len(b) for b in all_blocks_per_page.values())

    if analysis.total_content_blocks == 0:
        analysis.errors.append("No content blocks parsed from any page")
        doc.close()
        return analysis

    # ── Step 4: Test matching (bullets → content blocks) ──
    for b_idx, bp in enumerate(bullets):
        # Get page for this bullet
        if not bp.text_lines:
            continue

        # Handle cross-page bullets: match per-page portion
        bullet_pages = set(tl.page_num for tl in bp.text_lines)
        matched_any_page = False
        font_tag = ""

        for bpage in sorted(bullet_pages):
            page_blocks = all_blocks_per_page.get(bpage, [])
            if not page_blocks:
                continue

            # Build the text for this page only
            page_line_indices = [i for i, tl in enumerate(bp.text_lines) if tl.page_num == bpage]
            page_line_texts = [bp.line_texts[i] for i in page_line_indices if i < len(bp.line_texts)]
            original_text = " ".join(t.strip() for t in page_line_texts if t.strip())
            if not original_text:
                continue

            # Get font from the first text line's spans on this page
            first_tl = bp.text_lines[page_line_indices[0]]
            text_spans = [s for s in first_tl.spans
                          if not s.is_bullet_char and not s.is_zwsp_only and s.text.strip()]
            font = text_spans[0].font_name if text_spans else ""

            # Find matching font tag in CMap manager
            if not font_tag:
                for tag, name in cmap_mgr.font_names.items():
                    if name == font or font in name:
                        font_tag = tag
                        break
                if not font_tag and page_blocks:
                    font_tag = page_blocks[0].font_tag

            used_indices: set = set()
            block_indices = _find_blocks_for_text(page_blocks, original_text, font_tag, used_indices)
            if block_indices:
                matched_any_page = True

        if matched_any_page:
            analysis.bullets_matchable += 1
            # Try encoding full bullet text
            full_text = " ".join(t.strip() for t in bp.line_texts if t.strip())
            test_replacement = full_text.upper()
            hex_str, missing = cmap_mgr.encode_text(font_tag, test_replacement)
            if not missing:
                analysis.bullets_encodable += 1
            elif missing:
                analysis.errors.append(
                    f"Bullet {b_idx}: {len(missing)} missing chars for font {font_tag} "
                    f"({cmap_mgr.font_names.get(font_tag, '?')}): {missing[:5]}"
                )

    # ── Step 5: Test matching (skills → content blocks) ──
    for s_idx, sk in enumerate(skills):
        if not sk.content_spans:
            continue
        page_num = sk.content_spans[0].page_num
        page_blocks = all_blocks_per_page.get(page_num, [])
        if not page_blocks:
            continue

        original_text = sk.content_text
        if not original_text:
            continue

        # Get font tag for skills
        font_name = sk.content_spans[0].font_name if sk.content_spans else ""
        s_font_tag = ""
        for tag, name in cmap_mgr.font_names.items():
            if name == font_name or font_name in name:
                s_font_tag = tag
                break
        if not s_font_tag and page_blocks:
            s_font_tag = page_blocks[0].font_tag

        used_indices_s: set = set()
        block_indices = _find_blocks_for_text(page_blocks, original_text, s_font_tag, used_indices_s)
        if block_indices:
            analysis.skills_matchable += 1

            first_block = page_blocks[block_indices[0]]
            font_tag = first_block.font_tag
            test_replacement = original_text.upper()
            hex_str, missing = cmap_mgr.encode_text(font_tag, test_replacement)
            if not missing:
                analysis.skills_encodable += 1

    doc.close()

    # ── Step 6: Full patching test (creates output file) ──
    output_path = pdf_path.replace(".pdf", "_test_patched.pdf")
    try:
        # Create fake replacements — use original text with minor modifications
        # This tests the full pipeline without needing Claude
        bullet_replacements = {}
        for b_idx, bp in enumerate(bullets):
            texts = bp.line_texts
            if texts:
                # Simple replacement: toggle case of a word to test patching
                modified = []
                for t in texts:
                    mod = t
                    if mod.strip():
                        words = mod.split()
                        # Find first word with alpha chars that will change case
                        changed = False
                        start_idx = 1 if len(words) > 1 else 0
                        for wi in range(start_idx, len(words)):
                            w = words[wi]
                            toggled = w.upper() if w.islower() else w.lower()
                            if toggled != w:
                                words[wi] = toggled
                                changed = True
                                break
                        if not changed and words:
                            # Fallback: toggle first word
                            w = words[0]
                            toggled = w.upper() if w.islower() else w.lower()
                            if toggled != w:
                                words[0] = toggled
                        mod = " ".join(words)
                    modified.append(mod)
                bullet_replacements[b_idx] = modified

        skill_replacements = {}
        for s_idx, sk in enumerate(skills):
            if sk.content_text:
                skill_replacements[s_idx] = sk.content_text.upper()

        title_replacements = {}
        for t_idx, ts in enumerate(title_skills):
            if ts.skills_part:
                title_replacements[t_idx] = ts.skills_part.upper()

        apply_changes_to_pdf(
            pdf_path, output_path,
            bullets, skills,
            bullet_replacements, skill_replacements,
            title_skills, title_replacements,
        )

        # Count patches applied (from log output — or re-analyze)
        # We'll verify by comparing fonts
        if os.path.exists(output_path):
            # Compare original and patched PDFs
            orig_doc = fitz.open(pdf_path)
            patched_doc = fitz.open(output_path)

            font_diffs = []
            fonts_match = True

            for page_idx in range(min(len(orig_doc), len(patched_doc))):
                orig_fonts = sorted(orig_doc[page_idx].get_fonts(), key=lambda f: f[4])
                patched_fonts = sorted(patched_doc[page_idx].get_fonts(), key=lambda f: f[4])

                # Compare font names and types (ignore xrefs which change with garbage collection)
                orig_font_set = set((f[2], f[3].split("+")[-1] if "+" in f[3] else f[3]) for f in orig_fonts)
                patched_font_set = set((f[2], f[3].split("+")[-1] if "+" in f[3] else f[3]) for f in patched_fonts)

                if orig_font_set != patched_font_set:
                    fonts_match = False
                    missing = orig_font_set - patched_font_set
                    extra = patched_font_set - orig_font_set
                    if missing:
                        font_diffs.append(f"Page {page_idx}: missing fonts {missing}")
                    if extra:
                        font_diffs.append(f"Page {page_idx}: extra fonts {extra}")

            analysis.fonts_identical = fonts_match
            analysis.font_diff = font_diffs

            # Count how many patches actually applied by re-extracting text
            patched_spans = extract_spans_from_pdf(output_path)
            patched_lines = group_into_visual_lines(patched_spans)
            patched_classified, _ = classify_lines(patched_lines)
            patched_bullets, patched_skills, patched_title_skills = group_bullet_points(patched_classified)

            # Count bullets that changed
            for b_idx, bp in enumerate(bullets):
                if b_idx >= len(patched_bullets) or b_idx not in bullet_replacements:
                    continue
                orig_text = " ".join(bp.line_texts)
                patched_text = " ".join(patched_bullets[b_idx].line_texts) if b_idx < len(patched_bullets) else ""
                if orig_text != patched_text and patched_text:
                    analysis.bullets_patched += 1

            for s_idx, sk in enumerate(skills):
                if s_idx >= len(patched_skills) or s_idx not in skill_replacements:
                    continue
                if sk.content_text != patched_skills[s_idx].content_text:
                    analysis.skills_patched += 1

            for t_idx, ts in enumerate(title_skills):
                if t_idx >= len(patched_title_skills) or t_idx not in title_replacements:
                    continue
                if ts.skills_part != patched_title_skills[t_idx].skills_part:
                    analysis.title_skills_patched += 1

            orig_doc.close()
            patched_doc.close()

            # Clean up test output
            try:
                os.remove(output_path)
            except:
                pass

    except Exception as e:
        analysis.errors.append(f"Patching failed: {e}\n{traceback.format_exc()}")

    return analysis


def print_analysis(a: PDFAnalysis):
    """Pretty-print a PDF analysis."""
    bullet_match_rate = (a.bullets_matchable / a.bullet_count * 100) if a.bullet_count > 0 else 0
    skill_match_rate = (a.skills_matchable / a.skill_count * 100) if a.skill_count > 0 else 0
    bullet_patch_rate = (a.bullets_patched / a.bullet_count * 100) if a.bullet_count > 0 else 0
    skill_patch_rate = (a.skills_patched / a.skill_count * 100) if a.skill_count > 0 else 0

    total_content = a.bullet_count + a.skill_count + a.title_skill_count
    total_patched = a.bullets_patched + a.skills_patched + a.title_skills_patched
    overall_rate = (total_patched / total_content * 100) if total_content > 0 else 0

    print(f"\n{'='*70}")
    print(f"  {a.filename}")
    print(f"  {a.file_size/1024:.1f} KB | {a.num_pages} page(s)")
    print(f"{'='*70}")

    # Font info
    unique_fonts = {}
    for f in a.fonts:
        key = f["clean_name"]
        if key not in unique_fonts:
            unique_fonts[key] = f
    print(f"\n  FONTS ({len(unique_fonts)} unique):")
    for name, f in unique_fonts.items():
        tounicode = "CMap" if a.has_tounicode.get(f["tag"]) else "NO CMap"
        bw = a.cid_byte_widths.get(f["tag"], "?")
        subset = "subset" if f["is_subset"] else "full"
        print(f"    {f['tag']:5s} {name:40s} {f['subtype']:10s} {tounicode:8s} {bw}-byte  {subset}")

    # Structure
    print(f"\n  STRUCTURE:")
    print(f"    Spans: {a.total_spans}  |  Lines: {a.total_lines}")
    print(f"    Bullets: {a.bullet_count}  |  Skills: {a.skill_count}  |  Title Skills: {a.title_skill_count}  |  Structure: {a.structure_count}")

    # Content stream
    print(f"\n  CONTENT STREAM:")
    for page, count in sorted(a.content_blocks_per_page.items()):
        print(f"    Page {page}: {count} BT/ET blocks")
    print(f"    Total: {a.total_content_blocks} blocks")

    # Matching
    print(f"\n  MATCHING:")
    print(f"    Bullets matched:  {a.bullets_matchable}/{a.bullet_count} ({bullet_match_rate:.0f}%)")
    print(f"    Skills matched:   {a.skills_matchable}/{a.skill_count} ({skill_match_rate:.0f}%)")
    print(f"    Bullets encodable: {a.bullets_encodable}/{a.bullet_count}")
    print(f"    Skills encodable:  {a.skills_encodable}/{a.skill_count}")

    # Patching
    print(f"\n  PATCHING:")
    print(f"    Bullets patched:  {a.bullets_patched}/{a.bullet_count} ({bullet_patch_rate:.0f}%)")
    print(f"    Skills patched:   {a.skills_patched}/{a.skill_count} ({skill_patch_rate:.0f}%)")
    print(f"    Title skills:     {a.title_skills_patched}/{a.title_skill_count}")
    print(f"    Fonts identical:  {'YES' if a.fonts_identical else 'NO'}")
    if a.font_diff:
        for d in a.font_diff:
            print(f"      ! {d}")

    # Overall
    status = "PASS" if overall_rate >= 90 and a.fonts_identical else "PARTIAL" if overall_rate >= 50 else "FAIL"
    print(f"\n  OVERALL: {status} — {total_patched}/{total_content} ({overall_rate:.0f}%) patched, fonts {'identical' if a.fonts_identical else 'DIFFERENT'}")

    # Errors
    if a.errors:
        print(f"\n  ERRORS ({len(a.errors)}):")
        for err in a.errors[:10]:
            print(f"    - {err[:120]}")

    print()


def run_all_tests(pdf_dir: str = None):
    """Run tests on all PDFs in a directory (or default locations)."""
    search_dirs = []

    if pdf_dir:
        search_dirs.append(pdf_dir)
    else:
        # Default: check uploads and test samples
        base = os.path.dirname(os.path.dirname(__file__))
        search_dirs.append(os.path.join(base, "uploads", "resumes"))
        search_dirs.append(os.path.join(base, "tests", "resume_samples"))

    pdf_files = []
    for d in search_dirs:
        if os.path.isdir(d):
            for root, dirs, files in os.walk(d):
                for f in files:
                    if f.lower().endswith(".pdf") and "_test_patched" not in f:
                        pdf_files.append(os.path.join(root, f))
        elif os.path.isfile(d) and d.lower().endswith(".pdf"):
            pdf_files.append(d)

    if not pdf_files:
        print("No PDF files found to test!")
        return

    print(f"\n{'#'*70}")
    print(f"  PDF Content Stream Engine — Format Compatibility Test")
    print(f"  Testing {len(pdf_files)} PDF files")
    print(f"{'#'*70}")

    results = []
    for pdf_path in sorted(pdf_files):
        print(f"\nTesting: {os.path.basename(pdf_path)}...")
        try:
            analysis = run_content_stream_engine(pdf_path)
            results.append(analysis)
            print_analysis(analysis)
        except Exception as e:
            print(f"  CRASH: {e}")
            traceback.print_exc()

    # Summary
    print(f"\n{'#'*70}")
    print(f"  SUMMARY")
    print(f"{'#'*70}")

    total_pdfs = len(results)
    passed = sum(1 for r in results if (r.bullets_patched + r.skills_patched) > 0 and r.fonts_identical)
    partial = sum(1 for r in results if (r.bullets_patched + r.skills_patched) > 0 and not r.fonts_identical)
    failed = sum(1 for r in results if (r.bullets_patched + r.skills_patched) == 0 and (r.bullet_count + r.skill_count) > 0)
    no_content = sum(1 for r in results if r.bullet_count == 0 and r.skill_count == 0)

    print(f"\n  Total PDFs tested:  {total_pdfs}")
    print(f"  PASS (patched + fonts identical): {passed}")
    print(f"  PARTIAL (patched but fonts differ): {partial}")
    print(f"  FAIL (no patches applied): {failed}")
    print(f"  NO CONTENT (no bullets/skills found): {no_content}")

    # Detailed failure analysis
    if failed > 0 or partial > 0:
        print(f"\n  FAILURE DETAILS:")
        for r in results:
            total = r.bullet_count + r.skill_count
            patched = r.bullets_patched + r.skills_patched
            if total > 0 and (patched == 0 or not r.fonts_identical):
                status = "FAIL" if patched == 0 else "PARTIAL"
                print(f"    [{status}] {r.filename}: {patched}/{total} patched, fonts={'OK' if r.fonts_identical else 'DIFF'}")
                print(f"           Font types: {r.font_types}")
                if r.errors:
                    print(f"           Errors: {r.errors[0][:100]}")

    # Font type coverage
    all_font_types = set()
    for r in results:
        all_font_types.update(r.font_types)
    print(f"\n  Font types encountered: {sorted(all_font_types)}")

    # CID encoding coverage
    all_byte_widths = set()
    for r in results:
        all_byte_widths.update(r.cid_byte_widths.values())
    print(f"  CID byte widths: {sorted(all_byte_widths)}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test PDF content stream engine against various formats")
    parser.add_argument("path", nargs="?", help="PDF file or directory to test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    run_all_tests(args.path)
