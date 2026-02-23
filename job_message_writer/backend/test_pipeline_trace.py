"""
Trace exactly what happens to each bullet through the FULL pipeline.
Compare: LLM output → sanitized → greedy fill → trim → final render.
"""
import asyncio, os, sys, logging, fitz

sys.path.insert(0, os.path.dirname(__file__))
env_path = os.path.join(os.path.dirname(__file__), ".env")
for line in open(env_path):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.DEBUG, format="%(name)s:%(message)s",
                    handlers=[logging.FileHandler("/tmp/pipeline_trace.log", mode="w"),
                              logging.StreamHandler()])

PDF = "uploads/resumes/2d425a7058c54b2aad6c8e29bc22ef81_Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"
OUT = "/tmp/tailored_trace.pdf"
JD = """Senior Software Engineer - Backend
Requirements: Python, SQL, REST APIs, cloud services (AWS/Azure),
containerization, CI/CD, data integration, ETL pipelines.
Experience with microservices architecture, message queues,
real-time data processing, and enterprise-scale systems."""

async def main():
    from app.services.pdf_format_preserver import optimize_pdf
    result = await optimize_pdf(PDF, OUT, JD, "")
    print(f"\nResult: {result.get('status')}, patches: {result.get('total_patches')}")

    # Now compare original and output PDFs - show each bullet line's visual fill
    print("\n" + "="*80)
    print("VISUAL LINE ANALYSIS - OUTPUT PDF")
    print("="*80)
    doc = fitz.open(OUT)
    page = doc[0]
    page_w = page.rect.width
    td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    # Find the rightmost text span
    max_right = 0
    for b in td["blocks"]:
        if b.get("type") != 0: continue
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    max_right = max(max_right, s["bbox"][2])
    print(f"Page width: {page_w:.1f}pt, Max text right: {max_right:.1f}pt")
    print()

    # Show each visual line with fill percentage
    for b in td["blocks"]:
        if b.get("type") != 0: continue
        for l in b.get("lines", []):
            spans = l.get("spans", [])
            if not spans: continue
            text = "".join(s["text"] for s in spans).strip()
            if not text or len(text) < 5: continue
            x0 = spans[0]["bbox"][0]
            x1 = max(s["bbox"][2] for s in spans if s["text"].strip())
            fill_pct = (x1 - x0) / (max_right - x0) * 100 if max_right > x0 else 0
            marker = ""
            if fill_pct < 80 and x0 > 60:  # Bullet text that doesn't fill
                marker = " <<<< SHORT"
            elif fill_pct < 60 and x0 > 60:
                marker = " <<<< VERY SHORT"
            # Only show bullet-area lines
            if x0 > 45 and x0 < 110:
                print(f"  x0={x0:5.1f}  x1={x1:5.1f}  fill={fill_pct:5.1f}%  |{text[:85]}{marker}")

    doc.close()

    # Also show original PDF for comparison
    print("\n" + "="*80)
    print("VISUAL LINE ANALYSIS - ORIGINAL PDF")
    print("="*80)
    doc_orig = fitz.open(PDF)
    page_orig = doc_orig[0]
    td_orig = page_orig.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
    max_right_orig = 0
    for b in td_orig["blocks"]:
        if b.get("type") != 0: continue
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                if s["text"].strip():
                    max_right_orig = max(max_right_orig, s["bbox"][2])
    print(f"Page width: {page_orig.rect.width:.1f}pt, Max text right: {max_right_orig:.1f}pt")
    print()
    for b in td_orig["blocks"]:
        if b.get("type") != 0: continue
        for l in b.get("lines", []):
            spans = l.get("spans", [])
            if not spans: continue
            text = "".join(s["text"] for s in spans).strip()
            if not text or len(text) < 5: continue
            x0 = spans[0]["bbox"][0]
            x1 = max(s["bbox"][2] for s in spans if s["text"].strip())
            fill_pct = (x1 - x0) / (max_right_orig - x0) * 100 if max_right_orig > x0 else 0
            if x0 > 45 and x0 < 110:
                print(f"  x0={x0:5.1f}  x1={x1:5.1f}  fill={fill_pct:5.1f}%  |{text[:85]}")
    doc_orig.close()

asyncio.run(main())
