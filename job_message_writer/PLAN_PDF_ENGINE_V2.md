# PDF Resume Tailoring Engine V2 — Bulletproof Implementation Plan

## Executive Summary

We're building a system that modifies resume PDFs in-place — replacing bullet text, skill lists, and job title tech stacks to match a target job description — while preserving **100% of the original formatting** (fonts, kerning, layout, positioning, dates, headers, contact info).

**No commercial tool does this.** Every existing resume tailoring product (Teal, Rezi, Kickresume, Enhancv) uses template-based generation — they import content, then export a NEW PDF from a template. Our approach is unique: we modify the original content stream, preserving the user's exact resume design.

**Current state:** The engine works ~70% correctly. It patches content streams, handles 3 font types (Type0/CID, TrueType, Type1), uses Tc character spacing for width adjustment, and supports font augmentation. BUT production testing revealed critical bugs: dates wiped, garbled characters, broken spacing.

**Target state:** 99% of resume PDFs, 100% format preservation rate, automated visual verification, zero garbled text, zero date/header corruption.

---

## Root Cause Analysis of Current Bugs

### Bug 1: Employment Dates Wiped
**What happened:** All 4 employment dates (e.g., "March 2025–Oct 2025") disappeared from the tailored PDF.
**Root cause:** Title replacement patches the entire BT/ET block containing both the job title AND the right-aligned date. The date is a separate text operation within the same block (same Y-coordinate, different X-coordinate via Tm matrix), but the replacement only contains the new title text — the date operations get overwritten.
**Fix needed:** Semantic boundary detection within BT/ET blocks. Split "title" text ops from "date" text ops based on X-position and content pattern matching before patching.

### Bug 2: Garbled "archite&cture"
**What happened:** The word "architecture" rendered with an "&" replacing the "c".
**Root cause:** `_FontAugmentor` attempted to add the missing glyph for "c" at a CID slot, but the CIDToGIDMap mapping was incorrect — it mapped the new CID to a GID corresponding to the "&" glyph in the embedded font's glyf table.
**Fix needed:** Validate CID→GID→glyph mapping before patching. Use a "character availability check" BEFORE generation, and constrain the LLM to only use available characters.

### Bug 3: Broken Spacing "3 rd"
**What happened:** "3rd" rendered as "3 rd" with an unwanted space.
**Root cause:** The TJ array split "3rd" across kerning adjustments. When replacement text was distributed across TJ entries, the kerning value between "3" and "rd" was preserved from the original text but no longer appropriate for the new content.
**Fix needed:** Rebuild TJ arrays from scratch for replacement text rather than distributing into existing TJ structure.

### Bug 4: Title Spillover
**What happened:** Text ran together on Synderion title line.
**Root cause:** Replacement text was longer than original, and Tc adjustment hit the ±0.15 clamp. The excess width wasn't handled — text just overflowed into the adjacent date region.
**Fix needed:** Pre-validation of replacement text width BEFORE patching. Reject replacements that would overflow, and ask LLM for a shorter alternative.

### Bug 5: Test Suite Fraud
**What happened:** All 8 tests passed despite these production bugs.
**Root cause:** Test replacements used `.upper()` — same characters, same length, same glyphs. Tests never exercised: different-length text, new characters, date preservation, visual verification, or real LLM-generated content.
**Fix needed:** Complete test suite rewrite with realistic replacements, visual regression testing, and semantic preservation checks.

---

## Architecture Overview

```
                        +-----------------------+
                        |   Input: Resume PDF   |
                        |   + Job Description   |
                        +-----------+-----------+
                                    |
                    +---------------v---------------+
                    |     Phase 1: PDF Analysis     |
                    |  - Font inventory + metrics    |
                    |  - Character availability set   |
                    |  - Content stream parsing       |
                    |  - Semantic classification       |
                    |  - Boundary detection (dates!)   |
                    +---------------+---------------+
                                    |
                    +---------------v---------------+
                    |  Phase 2: Constrained LLM Gen  |
                    |  - Claude Structured Outputs    |
                    |  - Per-line character budgets    |
                    |  - Regex character whitelist     |
                    |  - Width-aware generation        |
                    +---------------+---------------+
                                    |
                    +---------------v---------------+
                    |   Phase 3: Pre-Patch Validation |
                    |  - Character availability check  |
                    |  - Width measurement (exact)      |
                    |  - Line count verification        |
                    |  - Retry failures with feedback   |
                    +---------------+---------------+
                                    |
                    +---------------v---------------+
                    |   Phase 4: Content Stream Patch |
                    |  - Hex-level byte replacement    |
                    |  - Tc width adjustment           |
                    |  - BT-level state reset          |
                    |  - Boundary-aware patching       |
                    +---------------+---------------+
                                    |
                    +---------------v---------------+
                    |   Phase 5: Post-Patch Verify   |
                    |  - Text extraction check        |
                    |  - Visual regression (SSIM)      |
                    |  - Font integrity check          |
                    |  - Date/header preservation       |
                    |  - Claude Vision QA (optional)    |
                    +---------------+---------------+
                                    |
                        +-----------v-----------+
                        |   Output: Tailored PDF |
                        +-----------------------+
```

---

## Phase 1: PDF Analysis & Semantic Boundary Detection

### 1.1 Font Inventory & Character Availability

**Goal:** Before asking the LLM to generate ANY text, know exactly which characters the embedded fonts can render.

**Implementation:**

```python
class FontAnalyzer:
    """Analyze all fonts in a PDF and build character availability maps."""

    def analyze(self, doc, page) -> Dict[str, FontInfo]:
        """Returns {font_tag: FontInfo} with available chars, widths, type."""
        # For each font on the page:
        # 1. Parse ToUnicode CMap → get unicode→CID mapping
        # 2. Parse /Widths or /W array → get CID→width mapping
        # 3. Check /FontFile2 embedded font → get actual glyph count
        # 4. Build available_chars: Set[str] (characters this font can render)
        # 5. Build char_widths: Dict[str, float] (character → width in font units)
```

**Key data produced:**
- `available_chars`: Set of Unicode characters that have glyphs in the embedded font
- `char_widths`: Dict mapping each character to its width in font units (1/1000 of font size)
- `font_type`: One of Type0_CID, TrueType, Type1, Type1C, Type3
- `byte_width`: 1 or 2 (from CMap codespace range)

**How character availability is determined:**
1. Parse ToUnicode CMap → every `beginbfchar`/`beginbfrange` entry = available character
2. For TrueType without ToUnicode: parse Encoding + Differences array
3. For Type1: parse Encoding dictionary
4. Cross-reference with /Widths array — a character with width 0 or missing width = unavailable

### 1.2 Semantic Classification (Improved)

Current classification categories work but need refinement:

| Category | What It Is | Example | Modifiable? |
|----------|-----------|---------|-------------|
| STRUCTURE | Section headers, horizontal rules, decorative elements | "EXPERIENCE", "EDUCATION" | NO |
| BULLET_TEXT | Experience bullet point content | "Developed microservices using Python" | YES |
| SKILL_CONTENT | Skill list values (after label) | "Python, JavaScript, SQL" | YES |
| TITLE_SKILLS | Tech stack in job title parentheses | "(Python, React, AWS)" | YES |
| BULLET_MARKER | Bullet point character (U+2022, -, etc.) | "•" | NO |
| ZWS_PADDING | Zero-width space padding | "\u200b" | NO |
| **DATE_TEXT** (NEW) | Employment dates, education dates | "March 2025 - Present" | **NO** |
| **CONTACT_INFO** (NEW) | Name, email, phone, LinkedIn, location | "john@email.com" | **NO** |
| **COMPANY_NAME** (NEW) | Employer/school names | "Google", "MIT" | **NO** |

### 1.3 Boundary Detection Within BT/ET Blocks (CRITICAL FIX)

**The #1 bug** — dates being wiped — happens because a single BT/ET block contains both the job title AND the date, positioned at different X-coordinates via Tm matrices.

**New: `_BoundaryDetector` class**

```python
class _BoundaryDetector:
    """Detect semantic boundaries within BT/ET blocks.

    A single BT/ET block may contain multiple semantic segments:
    - Job title (left-aligned) + Date (right-aligned) on same line
    - Company name (left) + Location (right) on same line

    This class identifies which text operations within a block
    are modifiable vs protected.
    """

    DATE_PATTERNS = [
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b',
        r'\b\d{4}\s*[-–—]\s*(?:\d{4}|Present|Current)\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\s*[-–—]',
    ]

    def segment_block(self, block: ContentBlock) -> List[BlockSegment]:
        """Split a BT/ET block into semantic segments.

        Returns segments with is_modifiable flag.
        Segments at significantly different X-positions (>50% page width apart)
        on the same Y-position are likely title+date pairs.
        """
```

**Algorithm:**
1. Group text ops by Y-position (within ±2 units tolerance)
2. Within each Y-group, check if there are ops at significantly different X-positions
3. For each group, check if any text matches date patterns → mark as protected
4. For title lines: the left-side text ops are modifiable, right-side date ops are protected
5. When patching, ONLY replace modifiable ops; protected ops pass through unchanged

### 1.4 Resume Format Detection

Detect the PDF generator to apply generator-specific parsing strategies:

| Generator | Detection Method | Content Stream Pattern |
|-----------|-----------------|----------------------|
| Microsoft Word | Producer contains "Microsoft" | Tm absolute positioning, TJ with kerning |
| Google Docs/Skia | Producer contains "Skia" | Glyph-ID encoding, multi-segment fonts |
| LaTeX/pdflatex | Producer contains "pdfTeX" or "MiKTeX" | Type1 fonts, heavy TJ kerning |
| XeLaTeX/LuaLaTeX | Producer contains "xdvipdfmx" or "LuaTeX" | CID TrueType, Identity-H |
| Chromium/Puppeteer | Producer contains "Skia/PDF" + "Chrome" | Same as Google Docs |
| Canva | Producer contains "Canva" | **WARN: likely vectorized text** |
| Figma | Custom detection | **REJECT: always vectorized** |

**Unsupported PDFs (early detection + user warning):**
- Vectorized text (no BT/ET blocks) → "This PDF has text as vector graphics. Please re-export from your design tool."
- Scanned/image PDFs (no text content) → "This appears to be a scanned document. Please use a text-based PDF."
- Type3 fonts (rare, Google Docs fallback) → Fall through to redact+re-render strategy

---

## Phase 2: Constrained LLM Generation

### 2.1 Switch to Claude Structured Outputs

**Replace** current `_parse_json_response()` hack with Claude's guaranteed JSON schema output.

```python
# Schema for resume optimization output
OPTIMIZATION_SCHEMA = {
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
                        "items": {
                            "type": "string",
                            # Dynamic regex built from font's available chars
                            "pattern": "^[A-Za-z0-9 .,;:!?()\\-/&@#$%+'\"]+$"
                        }
                    }
                },
                "required": ["index", "lines"],
                "additionalProperties": False
            }
        },
        "skills": { ... },
        "titles": { ... }
    },
    "required": ["bullets", "skills", "titles"],
    "additionalProperties": False
}
```

**Key benefits:**
- Zero JSON parsing errors (guaranteed valid JSON)
- Character whitelist enforced via regex `pattern` on string fields
- No retry loops for malformed output
- Available on Sonnet 4.5 (our current model)

### 2.2 Smart Character Budgets

**Replace** the current `±15% character count` heuristic with font-metric-aware budgets.

```python
def calculate_line_budget(original_text: str, font_metrics: FontMetrics) -> int:
    """Calculate character budget based on actual font widths."""
    original_width = sum(font_metrics.get_width(c) for c in original_text)
    avg_char_width = original_width / len(original_text)
    # Allow 5% tolerance for Tc adjustment
    budget = int((original_width * 1.05) / avg_char_width)
    return budget
```

**Prompt template (improved):**
```
BULLET {i} ({num_lines} lines):
  Line 1 (budget: {budget_1} chars): {original_line_1}
  Line 2 (budget: {budget_2} chars): {original_line_2}

RULES:
- Each replacement line MUST have fewer characters than its budget
- Use ONLY these characters: {available_chars_display}
- DO NOT change: company names, dates, percentages, or metrics
- ONLY change: technical terms, action verbs, descriptive language
```

### 2.3 Dynamic Character Whitelist

Build the regex pattern dynamically from the font's glyph set:

```python
def build_font_regex(available_chars: Set[str]) -> str:
    """Build regex character class from available font glyphs."""
    # Common resume characters that should always be available
    REQUIRED = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,;:!?()-/&@#$%+\'\"')

    # Intersect with what's actually available
    usable = available_chars & REQUIRED

    # Escape regex-special chars
    escaped = []
    for c in sorted(usable):
        if c in r'[](){}.*+?^$|\\':
            escaped.append(f'\\{c}')
        else:
            escaped.append(c)

    return f'^[{"".join(escaped)}]+$'
```

**If font is missing common characters** (< 60 of the REQUIRED set): this is a red flag that the font encoding is exotic or the ToUnicode CMap is incomplete. Fall back to prompt-only character guidance without regex enforcement.

---

## Phase 3: Pre-Patch Validation

### 3.1 Validation Pipeline

After LLM generates replacement text but BEFORE patching the PDF:

```python
class ReplacementValidator:
    """Validate LLM-generated replacements before patching."""

    def validate(self, replacements, font_metrics, original_blocks):
        results = []
        for rep in replacements:
            issues = []

            # 1. Character availability
            for char in rep.text:
                if char not in font_metrics.available_chars:
                    issues.append(f"char '{char}' (U+{ord(char):04X}) not in font")

            # 2. Width check (exact, using font metrics)
            actual_width = font_metrics.measure_width(rep.text)
            max_width = original_blocks[rep.index].total_width * 1.05
            if actual_width > max_width:
                overage_chars = int((actual_width - max_width) / font_metrics.avg_width) + 1
                issues.append(f"too wide by ~{overage_chars} chars")

            # 3. Line count
            if rep.line_count != original_blocks[rep.index].line_count:
                issues.append(f"line count {rep.line_count} != original {original_blocks[rep.index].line_count}")

            results.append(ValidationResult(rep, issues))

        return results
```

### 3.2 Selective Retry

Only retry failed replacements (typically 10-20% of items):

```python
async def retry_failures(failures, original_context, job_description):
    """Re-generate only the failed replacements with specific error feedback."""

    retry_prompt = f"""Some replacements failed validation. Please fix ONLY these:

{format_failures(failures)}

SPECIFIC FIXES NEEDED:
{format_error_feedback(failures)}

Keep the same optimization intent but fix the constraint violations."""

    # Use same structured output schema
    return await claude._send_request(system_prompt, retry_prompt,
                                       output_schema=OPTIMIZATION_SCHEMA)
```

### 3.3 Deterministic Fallback

For the <5% of replacements that fail even after retry:

```python
def deterministic_fallback(text: str, font_metrics: FontMetrics, max_width: float) -> str:
    """Last-resort text fixing without LLM."""

    # 1. Replace unavailable characters with ASCII equivalents
    CHAR_SUBS = {'é': 'e', 'ë': 'e', 'ü': 'u', 'ö': 'o', '—': '-',
                 '\u2019': "'", '\u201c': '"', '\u201d': '"', '\u2013': '-'}
    for bad, good in CHAR_SUBS.items():
        if bad in text and bad not in font_metrics.available_chars:
            text = text.replace(bad, good)

    # 2. Truncate if still too wide
    while font_metrics.measure_width(text) > max_width:
        # Remove last word
        text = text.rsplit(' ', 1)[0]
        if ' ' not in text:
            break

    return text
```

---

## Phase 4: Content Stream Patching (Improved)

### 4.1 Boundary-Aware Patching

The patching function must respect semantic boundaries identified in Phase 1:

```python
def _patch_with_boundaries(block, segments, replacement_text, font_metrics):
    """Patch only modifiable segments within a BT/ET block.

    Protected segments (dates, company names) pass through unchanged.
    Only modifiable segments receive replacement text.
    """
    for segment in segments:
        if not segment.is_modifiable:
            # Keep original hex bytes for this segment's text ops
            continue

        # Patch only this segment's text ops with replacement content
        # Distribute replacement text proportionally across this segment's ops
```

### 4.2 TJ Array Reconstruction

Instead of distributing replacement text into existing TJ entries (which preserves inappropriate kerning), rebuild TJ arrays from scratch:

```python
def _rebuild_tj_array(replacement_text: str, font_metrics: FontMetrics,
                       original_width: float) -> str:
    """Build a new TJ array for replacement text.

    Calculates per-character positioning using font metrics,
    then adds Tc adjustment if needed.
    """
    # For CID fonts: encode each char as 2-byte hex
    # For TrueType: encode as 1-byte hex
    # For Type1: encode as literal string with word-spacing kerning

    # Width adjustment via Tc (clamped ±0.15)
    new_width = font_metrics.measure_width(replacement_text)
    if abs(new_width - original_width) > 0.01:
        num_chars = len(replacement_text)
        tc = (original_width - new_width) / (1000 * num_chars)
        tc = max(-0.15, min(0.15, tc))
    else:
        tc = 0
```

### 4.3 BT-Level State Reset (Keep Current)

The current approach of injecting `0 Tc 100 Tz` after every BT keyword and after the last patched op per replacement is correct and must be preserved. This prevents Tc/Tz cascading to unpatched text.

### 4.4 Skip FontAugmentor When Possible

**Critical insight:** FontAugmentor (adding new glyphs to embedded fonts) is the source of garbled text bugs. The safest approach is to **never need it** — constrain the LLM to only use characters already in the font.

```python
# In the generation pipeline:
if not font_metrics.has_all_chars(replacement_text):
    # Option A: Retry with stricter character constraint (preferred)
    # Option B: Fall back to FontAugmentor (risky)
    # Option C: Reject and use original text
```

FontAugmentor should only be used as a last resort, and only after verifying the CID→GID mapping is correct by checking the actual glyf table.

---

## Phase 5: Post-Patch Verification

### 5.1 Automated Verification Pipeline

Every tailored PDF goes through this verification before being returned to the user:

```python
class PostPatchVerifier:
    """Verify tailored PDF quality before returning to user."""

    def verify(self, original_path, tailored_path, replacements):
        results = {}

        # Layer 1: Text extraction check
        results['text_extraction'] = self._check_text_extraction(
            tailored_path, replacements)

        # Layer 2: Date/header preservation
        results['protected_content'] = self._check_protected_content(
            original_path, tailored_path)

        # Layer 3: Font integrity
        results['fonts'] = self._check_fonts(original_path, tailored_path)

        # Layer 4: Visual regression (SSIM)
        results['visual'] = self._check_visual_similarity(
            original_path, tailored_path)

        # Layer 5: Garbled character detection
        results['garbled'] = self._check_garbled_chars(tailored_path)

        # Layer 6: Text overflow detection
        results['overflow'] = self._check_overflow(tailored_path)

        return VerificationReport(results)
```

### 5.2 Protected Content Check

```python
def _check_protected_content(self, original_path, tailored_path):
    """Verify dates, headers, contact info are unchanged."""
    orig_text = extract_text(original_path)
    tail_text = extract_text(tailored_path)

    # Extract all date-like patterns from original
    date_patterns = [
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\b',
        r'\b\d{4}\s*[-–—]\s*(?:\d{4}|Present|Current)\b',
    ]

    original_dates = set()
    for pattern in date_patterns:
        original_dates.update(re.findall(pattern, orig_text))

    missing_dates = []
    for date in original_dates:
        if date not in tail_text:
            missing_dates.append(date)

    return {'passed': len(missing_dates) == 0, 'missing_dates': missing_dates}
```

### 5.3 Visual Regression (SSIM)

```python
def _check_visual_similarity(self, original_path, tailored_path):
    """Render both PDFs at 300 DPI and compare with SSIM."""
    orig_img = render_pdf_page(original_path, dpi=300)
    tail_img = render_pdf_page(tailored_path, dpi=300)

    # Overall SSIM (should be > 0.80 since content changes are expected)
    overall_ssim = compute_ssim(orig_img, tail_img)

    # Protected region SSIM (header, dates — should be > 0.99)
    # Header region: top 12% of page
    header_ssim = compute_ssim(
        orig_img[:int(h*0.12), :],
        tail_img[:int(h*0.12), :])

    return {
        'overall_ssim': overall_ssim,
        'header_ssim': header_ssim,
        'passed': overall_ssim > 0.80 and header_ssim > 0.98
    }
```

### 5.4 Garbled Character Detection

```python
def _check_garbled_chars(self, pdf_path):
    """Detect garbled or replacement characters in the PDF."""
    doc = fitz.open(pdf_path)
    issues = []

    for page_num, page in enumerate(doc):
        text = page.get_text("text")

        # Check for Unicode replacement character
        if '\ufffd' in text:
            issues.append(f"Page {page_num}: Unicode replacement character found")

        # Check for suspicious character sequences
        # (e.g., "archite&cture" — non-word characters in the middle of words)
        words = text.split()
        for word in words:
            if len(word) > 3 and re.search(r'[a-z][^a-zA-Z\'-][a-z]', word):
                # Non-alpha char between lowercase letters
                issues.append(f"Page {page_num}: Suspicious word '{word}'")

    doc.close()
    return {'passed': len(issues) == 0, 'issues': issues}
```

---

## Phase 6: Test Suite Rewrite

### 6.1 Test Categories

| Test Category | What It Tests | How |
|--------------|--------------|-----|
| **Unit: Font Analysis** | Character availability detection | Known fonts with known glyph sets |
| **Unit: Boundary Detection** | Date/title separation | Mock BT/ET blocks with dates |
| **Unit: Width Calculation** | Accurate width measurement | Known text + known font metrics |
| **Integration: Realistic Replacements** | Full pipeline with real LLM text | Pre-recorded LLM responses + real PDFs |
| **Visual Regression** | Pixel-level comparison | Golden PDFs + SSIM thresholds |
| **Semantic Preservation** | Dates, headers, contact info intact | Text extraction + pattern matching |
| **Multi-Format** | Different PDF generators | Test corpus from Word, Docs, LaTeX, resume builders |

### 6.2 Test Corpus

Build a corpus of 15-20 test PDFs covering:

| # | Source | Font Types | Layout | Priority |
|---|--------|-----------|--------|----------|
| 1 | Microsoft Word (Calibri) | CID TrueType, Identity-H | Single column | HIGH |
| 2 | Microsoft Word (Times New Roman) | TrueType, WinAnsi | Single column | HIGH |
| 3 | Google Docs (default) | CID TrueType (Skia) | Single column | HIGH |
| 4 | LaTeX/Overleaf (Computer Modern) | Type1 | Single column | HIGH |
| 5 | LaTeX/Overleaf (Lato/FiraSans) | TrueType | Single column | MEDIUM |
| 6 | Resume.io / FlowCV | CID TrueType | Two column | HIGH |
| 7 | Canva (text-based export) | CID TrueType | Designer layout | MEDIUM |
| 8 | User's resume (current test file) | CID TrueType | Single column | HIGH |
| 9 | Word with mixed bold/italic | Multiple TrueType variants | Single column | MEDIUM |
| 10 | Google Docs with bullet symbols | CID TrueType + Symbol | Single column | MEDIUM |

### 6.3 Test Replacement Strategy

**NEVER use `.upper()` for test replacements again.** Instead:

```python
# Realistic test replacements (pre-computed, deterministic)
TEST_REPLACEMENTS = {
    "Developed scalable microservices": "Built distributed backend systems",
    "Python, JavaScript, SQL": "Go, TypeScript, PostgreSQL",
    "Led cross-functional team of 8": "Managed engineering squad of 12",
}
```

Each test replacement:
- Uses different characters than original
- Has different width than original (tests Tc adjustment)
- May introduce characters not in original text (tests character availability)
- Preserves roughly similar length (±20%)

### 6.4 Golden File Manifest

Each test PDF gets a JSON manifest:

```json
{
    "source": "Microsoft Word 2021",
    "font_types": ["CID TrueType"],
    "encoding": "Identity-H",
    "layout": "single_column",
    "protected_texts": [
        "John Doe",
        "john.doe@email.com",
        "Senior Software Engineer",
        "Jan 2020 - Present",
        "Jun 2018 - Dec 2019"
    ],
    "modifiable_sections": ["experience_bullets", "skills"],
    "expected_replacements": {
        "0": "Built distributed backend systems using Go and gRPC",
        "1": "Implemented real-time data pipeline processing 10M events daily"
    },
    "thresholds": {
        "min_overall_ssim": 0.82,
        "min_header_ssim": 0.99,
        "max_garbled_chars": 0
    }
}
```

---

## Implementation Order

### Sprint 1: Foundation (Critical Fixes)
**Goal: Fix the 5 production bugs**

1. **Boundary Detection** — `_BoundaryDetector` class
   - Detect title+date pairs within same BT/ET block
   - Mark date text ops as protected
   - Modify `_patch_content_stream` to skip protected ops
   - Test: User's resume, verify all 4 dates preserved

2. **Character Availability Check** — `FontAnalyzer` class
   - Extract available character set from each font
   - Pass to LLM prompt as constraint
   - Reject replacements with unavailable characters
   - Test: Verify no garbled characters in production output

3. **Width Pre-Validation** — `ReplacementValidator` class
   - Measure replacement text width using exact font metrics
   - Reject replacements that would overflow
   - Retry with "shorten by N chars" feedback
   - Test: Verify no text spillover in production output

### Sprint 2: LLM Pipeline Upgrade
**Goal: Reliable, constrained text generation**

4. **Claude Structured Outputs** — Replace `_parse_json_response`
   - Define JSON schema with `output_config`
   - Add regex pattern for character whitelist
   - Test: Zero JSON parsing errors over 50 runs

5. **Smart Character Budgets** — Font-metric-aware prompts
   - Calculate per-line budgets from font widths
   - Include in prompt template
   - Test: 85%+ first-pass width compliance

6. **Multi-Pass Pipeline** — Generate → Validate → Retry
   - Implement selective retry for failed items
   - Add deterministic fallback
   - Test: 100% of replacements pass validation

### Sprint 3: Visual Verification
**Goal: Automated quality assurance**

7. **Post-Patch Verifier** — `PostPatchVerifier` class
   - SSIM comparison (overall + protected regions)
   - Date/header preservation check
   - Garbled character detection
   - Text overflow detection
   - Test: Catches all 5 original bugs on pre-fix PDFs

8. **Test Suite Rewrite** — Realistic tests
   - Replace `.upper()` with real replacement text
   - Add visual regression tests
   - Add semantic preservation tests
   - Collect test corpus (8-10 PDFs from different generators)
   - Test: All tests pass on fixed engine

### Sprint 4: Multi-Format Support
**Goal: Handle 99% of resume PDFs**

9. **Format Detection** — Generator-specific parsing
   - Detect PDF generator from Producer metadata
   - Apply generator-specific content stream parsing strategies
   - Handle Skia/Chrome multi-segment fonts
   - Warn/reject unsupported formats (vectorized text)
   - Test: Successful patching on Word, Docs, LaTeX, resume builder PDFs

10. **TJ Array Reconstruction** — Better width handling
    - Rebuild TJ arrays from scratch for replaced text
    - Proper kerning values from font metrics
    - Handle Type1 literal string word spacing
    - Test: No "3 rd" style spacing artifacts

### Sprint 5: Hardening
**Goal: Production-ready reliability**

11. **Error Recovery** — Graceful degradation
    - If patching fails on one bullet, skip it (patch others)
    - If font analysis fails, fall back to prompt-only constraints
    - If visual verification fails, return original PDF with warning
    - Never return a corrupted PDF to the user

12. **Performance Optimization**
    - Cache font analysis across pages (same fonts)
    - Batch LLM calls (all bullets + skills in one structured output call)
    - Parallel page processing for multi-page resumes

13. **Claude Vision QA** (optional, premium feature)
    - Send before/after renders to Claude Vision
    - Get structured quality assessment
    - Use as final gate for high-stakes applications

---

## Coverage Estimation

| Resume Category | % of Market | Our Support | Notes |
|----------------|------------|-------------|-------|
| Word (Calibri/Arial/TNR) | ~45% | Full | Most common, CID TrueType |
| Google Docs | ~15% | Full | Skia/Chrome engine, CID TrueType |
| Resume builders (Resume.io, etc.) | ~15% | Full | Chromium-based, CID TrueType |
| LaTeX/Overleaf | ~10% | Full | Type1 or TrueType |
| Apple Pages/LibreOffice | ~5% | Full | TrueType |
| Canva (text-based) | ~3% | Partial | May have encoding issues |
| Canva/Figma (vectorized) | ~3% | Reject + Warn | No text to modify |
| Scanned/image PDFs | ~3% | Reject + Warn | No text to modify |
| Other (InDesign, exotic) | ~1% | Best effort | May work, may not |

**Estimated coverage: 93% full support + 3% partial + 4% reject with user guidance = 96% of all resumes handled (93% perfectly, 3% with fallbacks)**

The remaining 4% (vectorized/scanned) is a fundamental limitation — there is no text in the content stream to modify. For these, we'd need to either OCR + rebuild (lossy) or guide the user to re-export their resume as a text-based PDF.

---

## Risk Assessment

### High Risk (Must Mitigate)
1. **FontAugmentor producing garbled text** → Mitigated by constraining LLM to available characters
2. **Dates being overwritten** → Mitigated by boundary detection within BT/ET blocks
3. **Test suite not catching real bugs** → Mitigated by realistic replacements + visual verification

### Medium Risk (Monitor)
4. **Exotic font encodings** → Some PDFs may have incomplete ToUnicode CMaps. Fallback: prompt-only constraints
5. **Multi-page resumes** → Content blocks may span pages. Current engine handles this but needs more testing
6. **Two-column layouts** → Content stream order may not match visual order. Needs generator-specific handling

### Low Risk (Accept)
7. **API cost** → ~$0.02-0.05/resume with Sonnet 4.5. Acceptable.
8. **Processing time** → ~5-15 seconds per resume. Acceptable for the use case.
9. **Tc clamp at ±0.15** → Very rarely hit with proper character budgets. When it does, retry with shorter text.

---

## Key Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| PyMuPDF (fitz) | >=1.23.0 | PDF rendering, text extraction, visual verification |
| anthropic | >=0.25.0 | Claude API with structured outputs |
| fonttools | >=4.0 | Font analysis, glyph inspection (already installed) |
| scikit-image | >=0.21.0 | SSIM calculation (new dependency) |
| opencv-python-headless | >=4.8.0 | Image comparison (new dependency) |
| numpy | >=1.24.0 | Pixel array operations (new dependency) |
| Pillow | >=10.0 | Image handling (already installed) |

---

## Success Criteria

The engine is "done" when:

1. **Zero garbled characters** across all test corpus PDFs
2. **Zero date/header/contact info corruption** across all test corpus PDFs
3. **Zero text overflow** (all replacement text fits within original bounds)
4. **Visual SSIM > 0.80** overall and **> 0.98** for protected regions across all tests
5. **Text extraction works** — replacement text is correctly extractable by ATS systems
6. **8+ PDF formats pass** — Word, Google Docs, LaTeX, resume builders, Pages, LibreOffice
7. **Production test passes** — User's actual resume tailored against a real JD with zero defects
8. **Font fidelity** — No new fonts introduced, no font substitution, all original fonts preserved
