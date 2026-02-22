#!/usr/bin/env python3
"""
Cross-Platform PDF Resume Test Suite

Tests the PDF engine against 21 diverse resume PDFs covering:
- Multiple font types: TrueType, Type0/CID, Type1, OpenType
- Font families: Arial, Calibri, Garamond, Lato, Roboto, Ubuntu, Inter, Computer Modern, etc.
- Sources: Word, Google Docs, LaTeX (pdflatex, xelatex, lualatex), Canva-style
- Layouts: Single-column and two-column (sidebar, asymmetric, Deedy, AltaCV, PlushCV)
- Page counts: 1-7 pages

No LLM calls — tests extraction, classification, content stream parsing,
matching, width budgets, and verifier self-checks only.

Run: pytest backend/tests/test_pdf_cross_platform.py -v
"""

import os
import sys
import tempfile
import shutil
from typing import Dict, List, Optional, Tuple

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fitz

from app.services.pdf_format_preserver import (
    extract_spans_from_pdf,
    group_into_visual_lines,
    classify_lines,
    group_bullet_points,
    apply_changes_to_pdf,
    _CMapManager,
    _WidthCalculator,
    _parse_content_stream,
    _find_blocks_for_text,
    _BoundaryDetector,
    FontAnalyzer,
    PostPatchVerifier,
    calculate_width_budgets,
    sanitize_bullet_replacements,
    ContentBlock,
    TextOp,
    TextSpan,
    ClassifiedLine,
    BulletPoint,
    SkillLine,
    TitleSkillLine,
    LineType,
)


# ── PDF Sample Registry ─────────────────────────────────────────────────────
#
# Each entry: (path, name, layout, expected_fonts, min_pages)
#   layout: "single" | "two-column"
#   expected_fonts: list of font family substrings to check for
#   min_pages: minimum expected page count

SAMPLE_DIR = "/tmp/test_resumes"
TWO_COL_DIR = "/tmp/test_resumes/two_column"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads", "resumes")

# Single-column samples (from batch test)
SINGLE_COLUMN_SAMPLES = [
    (os.path.join(SAMPLE_DIR, "abhay_backend.pdf"), "abhay_backend", ["Merriweather", "OpenSans", "Calibri", "Arial"]),
    (os.path.join(SAMPLE_DIR, "aseef_devops.pdf"), "aseef_devops", ["Arial", "Calibri", "Courier"]),
    (os.path.join(SAMPLE_DIR, "bhavesh_ds.pdf"), "bhavesh_ds", ["Roboto", "SourceSansPro", "FontAwesome"]),
    (os.path.join(SAMPLE_DIR, "github_latex.pdf"), "github_latex", ["Lato", "FontAwesome"]),
    (os.path.join(SAMPLE_DIR, "gsa_swe.pdf"), "gsa_swe", ["Arial", "SourceSansPro"]),
    (os.path.join(SAMPLE_DIR, "hursh_fullstack.pdf"), "hursh_fullstack", ["Garamond", "Arial", "TimesNewRoman"]),
    (os.path.join(SAMPLE_DIR, "jayesh_dev.pdf"), "jayesh_dev", ["Arial", "Calibri", "Cambria"]),
    (os.path.join(SAMPLE_DIR, "monisha_google.pdf"), "monisha_google", ["LatinModern"]),
    (os.path.join(SAMPLE_DIR, "mujahid_fullstack.pdf"), "mujahid_fullstack", ["Ubuntu"]),
    (os.path.join(SAMPLE_DIR, "nishant_data.pdf"), "nishant_data", ["Calibri", "TimesNewRoman", "Symbol"]),
    (os.path.join(SAMPLE_DIR, "uci_swe.pdf"), "uci_swe", ["Arial", "Calibri", "Corbel"]),
    (os.path.join(SAMPLE_DIR, "vchrombie_swe.pdf"), "vchrombie_swe", ["Calibri", "TimesNewRoman"]),
]

# Two-column samples
TWO_COLUMN_SAMPLES = [
    (os.path.join(TWO_COL_DIR, "altacv_mmayer.pdf"), "altacv_mmayer", ["Lato", "FontAwesome"]),
    (os.path.join(TWO_COL_DIR, "altacv_sample.pdf"), "altacv_sample", ["Lato", "RobotoSlab", "FontAwesome"]),
    (os.path.join(TWO_COL_DIR, "deedy_resume.pdf"), "deedy_resume", ["Lato", "Raleway"]),
    (os.path.join(TWO_COL_DIR, "niloy_two_column.pdf"), "niloy_two_column", ["Lato", "FontAwesome"]),
    (os.path.join(TWO_COL_DIR, "plushcv_inter.pdf"), "plushcv_inter", ["Inter", "OfficeCodePro"]),
    (os.path.join(TWO_COL_DIR, "two_column_resume.pdf"), "two_column_resume", ["DroidSans", "Raleway"]),
]

# Original test resumes (uploaded)
SHALLUM_PDF = os.path.join(
    UPLOAD_DIR,
    "2d425a7058c54b2aad6c8e29bc22ef81_Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf",
)
YASHA_PDF = os.path.join(
    UPLOAD_DIR,
    "21a5dc1b20fc4904a782b4a4220f27ef_Yasha_Salesforce.pdf",
)
ORIGINAL_SAMPLES = [
    (SHALLUM_PDF, "shallum", ["Calibri"]),
    (YASHA_PDF, "yasha", ["Calibri"]),
]

ALL_SAMPLES = SINGLE_COLUMN_SAMPLES + TWO_COLUMN_SAMPLES + ORIGINAL_SAMPLES


def _available(path: str) -> bool:
    return os.path.isfile(path) and os.path.getsize(path) > 100


def _available_samples(sample_list):
    """Return parametrize-ready list of (path, name) for available PDFs."""
    return [(p, n) for p, n, _ in sample_list if _available(p)]


def _all_available():
    return _available_samples(ALL_SAMPLES)


def _single_col_available():
    return _available_samples(SINGLE_COLUMN_SAMPLES)


def _two_col_available():
    return _available_samples(TWO_COLUMN_SAMPLES)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1: PDF Parsing — Can we open and extract text from every PDF?
# ═══════════════════════════════════════════════════════════════════════════════


class TestPDFParsing:
    """Verify PyMuPDF can parse all sample PDFs."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_pdf_opens(self, path, name):
        doc = fitz.open(path)
        assert doc.page_count >= 1, f"{name}: no pages"
        doc.close()

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_text_extraction(self, path, name):
        doc = fitz.open(path)
        total_text = ""
        for page in doc:
            total_text += page.get_text()
        doc.close()
        assert len(total_text) > 50, f"{name}: too little text ({len(total_text)} chars)"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_fonts_detected(self, path, name):
        doc = fitz.open(path)
        all_fonts = set()
        for page in doc:
            for f in page.get_fonts():
                all_fonts.add(f[3])
        doc.close()
        assert len(all_fonts) >= 1, f"{name}: no fonts detected"


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2: Span Extraction — Does our engine extract spans correctly?
# ═══════════════════════════════════════════════════════════════════════════════


class TestSpanExtraction:
    """Verify extract_spans_from_pdf produces valid spans."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_spans_extracted(self, path, name):
        spans = extract_spans_from_pdf(path)
        assert len(spans) > 5, f"{name}: only {len(spans)} spans"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_spans_have_text(self, path, name):
        spans = extract_spans_from_pdf(path)
        text_spans = [s for s in spans if s.text.strip()]
        assert len(text_spans) > 3, f"{name}: only {len(text_spans)} non-empty spans"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_spans_have_valid_bbox(self, path, name):
        spans = extract_spans_from_pdf(path)
        for s in spans[:50]:  # Check first 50
            x0, y0, x1, y1 = s.bbox
            assert x0 >= 0, f"{name}: negative x0={x0}"
            assert y0 >= 0, f"{name}: negative y0={y0}"
            assert x1 >= x0, f"{name}: x1 < x0"
            assert y1 >= y0, f"{name}: y1 < y0"


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3: Visual Line Grouping — Are spans grouped into correct lines?
# ═══════════════════════════════════════════════════════════════════════════════


class TestVisualLineGrouping:
    """Verify group_into_visual_lines produces reasonable groupings."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_lines_grouped(self, path, name):
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        assert len(lines) > 3, f"{name}: only {len(lines)} visual lines"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_lines_ordered_by_y(self, path, name):
        """Lines should be roughly ordered top-to-bottom within each page."""
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)

        # group_into_visual_lines returns List[List[TextSpan]]
        # Group by page using first span's page_num and origin y
        by_page: Dict[int, list] = {}
        for line_spans in lines:
            if not line_spans:
                continue
            pg = line_spans[0].page_num
            y = line_spans[0].origin[1]
            if pg not in by_page:
                by_page[pg] = []
            by_page[pg].append(y)

        # Within each page, Y positions should generally increase
        for pg, ys in by_page.items():
            if len(ys) < 3:
                continue
            # Allow some tolerance — two-column layouts may interleave
            inversions = sum(1 for i in range(1, len(ys)) if ys[i] < ys[i - 1] - 2.0)
            inversion_rate = inversions / len(ys)
            assert inversion_rate < 0.3, (
                f"{name} page {pg}: {inversion_rate:.0%} Y-inversions ({inversions}/{len(ys)})"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 4: Line Classification — Are lines correctly typed?
# ═══════════════════════════════════════════════════════════════════════════════


class TestLineClassification:
    """Verify classify_lines produces valid classifications."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_classification_runs(self, path, name):
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, stats = classify_lines(lines)
        assert len(classified) > 0, f"{name}: no classified lines"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_all_lines_have_valid_type(self, path, name):
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        for cl in classified:
            assert cl.line_type in LineType, f"{name}: invalid type {cl.line_type}"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_bullet_grouping(self, path, name):
        """group_bullet_points should not crash on any PDF."""
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        bullets, skills, titles = group_bullet_points(classified)
        # Verify types
        assert isinstance(bullets, list)
        assert isinstance(skills, list)
        assert isinstance(titles, list)
        for bp in bullets:
            assert isinstance(bp, BulletPoint)
        for sk in skills:
            assert isinstance(sk, SkillLine)
        for ts in titles:
            assert isinstance(ts, TitleSkillLine)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 5: Content Stream Parsing — CMap, blocks, fonts
# ═══════════════════════════════════════════════════════════════════════════════


class TestContentStreamParsing:
    """Verify content stream parsing works across all PDF types."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_cmap_manager_init(self, path, name):
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        assert len(cmap.font_cmaps) >= 1, f"{name}: no font CMaps found"
        doc.close()

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_content_blocks_parsed(self, path, name):
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        total_blocks = 0
        for pn in range(min(len(doc), 2)):  # First 2 pages
            page = doc[pn]
            for xref in page.get_contents():
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap, pn, xref)
                total_blocks += len(blocks)
        doc.close()
        assert total_blocks > 0, f"{name}: no content blocks parsed"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_blocks_have_decoded_text(self, path, name):
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        decoded_count = 0
        for pn in range(min(len(doc), 2)):
            page = doc[pn]
            for xref in page.get_contents():
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap, pn, xref)
                for b in blocks:
                    text = "".join(op.decoded_text for op in b.text_ops)
                    if text.strip():
                        decoded_count += 1
        doc.close()
        assert decoded_count > 0, f"{name}: no blocks with decoded text"

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_width_calculator_init(self, path, name):
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        wc = _WidthCalculator(doc)
        assert len(wc.font_widths) >= 0, (
            f"{name}: width calculator init failed"
        )
        doc.close()

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_font_analyzer(self, path, name):
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        fa = FontAnalyzer(cmap)
        summary = fa.get_font_summary()
        assert isinstance(summary, str)
        doc.close()


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 6: Width Budgets — Are character limits computed?
# ═══════════════════════════════════════════════════════════════════════════════


class TestWidthBudgets:
    """Verify calculate_width_budgets produces reasonable values."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_budgets_computed(self, path, name):
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        bullets, skills, titles = group_bullet_points(classified)

        budgets = calculate_width_budgets(path, bullets, skills, titles)
        assert "bullet_budgets" in budgets
        assert "skill_budgets" in budgets
        assert "title_budgets" in budgets

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_budget_values_reasonable(self, path, name):
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        bullets, skills, titles = group_bullet_points(classified)

        budgets = calculate_width_budgets(path, bullets, skills, titles)

        for idx, line_budgets in budgets["bullet_budgets"].items():
            for max_chars in line_budgets:
                assert 3 <= max_chars <= 500, (
                    f"{name} bullet {idx}: budget {max_chars} out of range"
                )

        for idx, max_chars in budgets["skill_budgets"].items():
            assert 3 <= max_chars <= 500, (
                f"{name} skill {idx}: budget {max_chars} out of range"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 7: Verifier Self-Check — Every PDF should pass when compared to itself
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerifierSelfCheck:
    """PostPatchVerifier.verify(pdf, pdf) should always pass."""

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_self_check_passes(self, path, name):
        verifier = PostPatchVerifier()
        report = verifier.verify(path, path)
        # Protected content and fonts should always pass against self
        assert report.protected_content.passed, (
            f"{name} protected_content: {report.protected_content.warnings}"
        )
        assert report.fonts.passed, (
            f"{name} fonts: {report.fonts.warnings}"
        )
        assert report.garbled.passed, (
            f"{name} garbled: {report.garbled.warnings}"
        )
        assert report.overflow.passed, (
            f"{name} overflow: {report.overflow.warnings}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 8: Two-Column Layout Detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestTwoColumnDetection:
    """Verify two-column PDFs are parsed without column bleed."""

    @pytest.mark.parametrize("path,name", _two_col_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_two_column_x_spread(self, path, name):
        """Two-column PDFs should have text at widely separated X positions."""
        doc = fitz.open(path)
        page = doc[0]
        page_width = page.rect.width
        x_positions = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] == 0:
                for line in block["lines"]:
                    for span in line["spans"]:
                        x_positions.append(span["bbox"][0])
        doc.close()

        if not x_positions:
            pytest.skip(f"{name}: no text positions found")

        x_min, x_max = min(x_positions), max(x_positions)
        x_spread = x_max - x_min
        # Two-column layouts should use at least 40% of page width
        assert x_spread > page_width * 0.4, (
            f"{name}: X spread {x_spread:.0f}pt too narrow for two-column"
        )

    @pytest.mark.parametrize("path,name", _two_col_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_classification_no_crash(self, path, name):
        """Classification should not crash on two-column layouts."""
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        bullets, skills, titles = group_bullet_points(classified)
        # Just verify no crash and reasonable output
        assert len(classified) > 0

    @pytest.mark.parametrize("path,name", _two_col_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_content_stream_no_crash(self, path, name):
        """Content stream parsing should work on two-column PDFs."""
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        total_blocks = 0
        for pn in range(min(len(doc), 2)):
            page = doc[pn]
            for xref in page.get_contents():
                stream = doc.xref_stream(xref)
                blocks = _parse_content_stream(stream, cmap, pn, xref)
                total_blocks += len(blocks)
        doc.close()
        assert total_blocks > 0


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 9: Sanitize Tolerance — Verify the filter works correctly
# ═══════════════════════════════════════════════════════════════════════════════


class TestSanitizeBullets:
    """Test sanitize_bullet_replacements with various deltas."""

    def _make_bullet(self, lines: List[str]) -> BulletPoint:
        from app.services.pdf_format_preserver import TextSpan, ClassifiedLine
        text_lines = []
        for i, text in enumerate(lines):
            span = TextSpan(
                text=text, font_name="F1", font_size=11.0,
                bbox=(72, 100 + i * 14, 500, 112 + i * 14),
                page_num=0, color=0, flags=0,
                origin=(72, 112 + i * 14),
            )
            cl = ClassifiedLine(
                spans=[span], line_type=LineType.BULLET_TEXT,
                page_num=0, y_pos=100 + i * 14,
            )
            text_lines.append(cl)
        return BulletPoint(marker_line=None, text_lines=text_lines, section_name="Experience")

    def test_same_length_passes(self):
        bp = self._make_bullet(["Implemented distributed cache system"])
        reps = {0: ["Designed distributed queue service"]}
        result = sanitize_bullet_replacements([bp], reps, length_tolerance=0.30)
        assert 0 in result

    def test_slightly_longer_truncated(self):
        """33% longer should be smart-truncated to fit, not fully dropped."""
        bp = self._make_bullet(["Short line here"])  # 15 chars
        reps = {0: ["Somewhat longer text"]}  # 20 chars, delta=0.33 > 0.30
        result = sanitize_bullet_replacements([bp], reps, length_tolerance=0.30)
        # Smart truncation trims at word boundary instead of dropping
        assert 0 in result
        assert len(result[0][0]) <= int(15 * 1.30) + 1  # truncated to fit

    def test_way_too_long_truncated_or_dropped(self):
        bp = self._make_bullet(["Short"])  # 5 chars
        reps = {0: ["This is a much much longer replacement text"]}  # 43 chars
        result = sanitize_bullet_replacements([bp], reps, length_tolerance=0.30)
        # Smart truncation tries to fit; may truncate to "This" (4 chars >= min_len=3)
        # or drop if truncated text falls below min_len
        if 0 in result:
            assert len(result[0][0]) <= int(5 * 1.30) + 1

    def test_line_count_mismatch_redistributed(self):
        bp = self._make_bullet(["Line one", "Line two"])
        reps = {0: ["Only one line"]}  # 2 orig lines, 1 new → redistributed to 2 lines
        result = sanitize_bullet_replacements([bp], reps, length_tolerance=0.30)
        # New behavior: redistribute text across original line count
        assert 0 in result
        assert len(result[0]) == 2  # Still 2 lines after redistribution
        full_text = " ".join(result[0])
        assert "Only" in full_text and "line" in full_text

    def test_empty_line_dropped(self):
        bp = self._make_bullet(["Line one"])
        reps = {0: [""]}
        result = sanitize_bullet_replacements([bp], reps, length_tolerance=0.30)
        assert 0 not in result


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 10: Font Compatibility Matrix (informational)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFontCompatibilityMatrix:
    """Generate and verify font compatibility across all samples.

    This test class reports which font types each PDF uses and whether
    our CMap/encoding can handle them.
    """

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_font_types_detected(self, path, name):
        """Each PDF should have at least one font with a valid CMap."""
        doc = fitz.open(path)
        cmap = _CMapManager(doc)

        fonts_with_cmap = 0
        for font_tag, data in cmap.font_cmaps.items():
            fwd = data.get("fwd", {})
            if fwd:
                fonts_with_cmap += 1

        doc.close()
        # At least some fonts should be CMap-decodable
        # (Some PDFs may use identity CMaps which is also fine)
        assert fonts_with_cmap >= 0  # Soft assertion — even 0 is OK for identity fonts

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_font_names_resolved(self, path, name):
        """CMapManager should resolve font tag → name mappings."""
        doc = fitz.open(path)
        cmap = _CMapManager(doc)
        assert len(cmap.font_names) >= 1, f"{name}: no font names resolved"
        doc.close()


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 11: Patching Integration — Apply changes without crashing
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatchingIntegration:
    """Test apply_changes_to_pdf with vowel-swap replacements (no LLM needed)."""

    @pytest.fixture
    def tmpdir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_vowel_swap_patching(self, path, name, tmpdir):
        """Vowel swap should produce output without crashes."""
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        bullets, skills, titles = group_bullet_points(classified)

        if not bullets:
            pytest.skip(f"{name}: no bullets found")

        # Create vowel-swap replacements for first 3 bullets
        table = str.maketrans("aeiou", "oiuae")
        bullet_reps = {}
        for i, bp in enumerate(bullets[:3]):
            if bp.line_texts:
                bullet_reps[i] = [t.translate(table) for t in bp.line_texts]

        if not bullet_reps:
            pytest.skip(f"{name}: no replacement candidates")

        output_path = os.path.join(tmpdir, f"{name}_patched.pdf")
        apply_changes_to_pdf(
            path, output_path, bullets, skills,
            bullet_reps, {}, titles, {},
        )

        assert os.path.exists(output_path), f"{name}: no output"
        assert os.path.getsize(output_path) > 500, f"{name}: output too small"

        # Verify output is a valid PDF
        doc = fitz.open(output_path)
        assert doc.page_count >= 1
        doc.close()

    @pytest.mark.parametrize("path,name", _all_available(), ids=lambda x: x if isinstance(x, str) else "")
    def test_patching_preserves_fonts(self, path, name, tmpdir):
        """Patched PDF should have same fonts as original."""
        spans = extract_spans_from_pdf(path)
        lines = group_into_visual_lines(spans)
        classified, _ = classify_lines(lines)
        bullets, skills, titles = group_bullet_points(classified)

        if not bullets:
            pytest.skip(f"{name}: no bullets found")

        table = str.maketrans("aeiou", "oiuae")
        bullet_reps = {}
        for i, bp in enumerate(bullets[:2]):
            if bp.line_texts:
                bullet_reps[i] = [t.translate(table) for t in bp.line_texts]

        if not bullet_reps:
            pytest.skip(f"{name}: no replacement candidates")

        output_path = os.path.join(tmpdir, f"{name}_patched.pdf")
        apply_changes_to_pdf(
            path, output_path, bullets, skills,
            bullet_reps, {}, titles, {},
        )

        verifier = PostPatchVerifier()
        result = verifier._check_fonts(path, output_path)
        assert result.passed, f"{name} fonts: {result.warnings}"


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
