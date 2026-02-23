#!/usr/bin/env python3
"""Debug script — saves tailored PDF before verification can revert it."""

import asyncio
import sys
import os
import shutil
from dotenv import load_dotenv

load_dotenv("backend/.env")
sys.path.insert(0, "backend")

import fitz
from app.services.pdf_format_preserver import (
    extract_spans_from_pdf, group_into_visual_lines, classify_lines,
    group_bullet_points, apply_changes_to_pdf, generate_optimized_content,
    FontAnalyzer, _CMapManager, calculate_width_budgets, _validate_and_retry,
    PostPatchVerifier,
)

RESUME = "/home/shallum/Downloads/Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"
OUTPUT = "/home/shallum/Downloads/Shallum_Tailored_YourCo.pdf"
DEBUG_OUTPUT = "/home/shallum/Downloads/Shallum_Tailored_YourCo_DEBUG.pdf"

JOB_DESCRIPTION = """Sr Backend Engineer at Yourco

At Yourco, we're bringing traditional industries into the future. AI unlocks the opportunity to empower frontline workforces.

What is Yourco? The "app-less" employee app built for the frontline workforce. All of the powerful functionality and security you expect in an enterprise mobile app, with the simplicity, distribution, and actual two-way engagement of SMS.

Who We Serve: From small businesses to Fortune 500 enterprises, organizations in traditional industries trust Yourco as their frontline communications and frontline intelligence platform.

Tech Stack:
- Node (Express, Nest)
- MongoDB
- PostgreSQL
- Google Cloud Platform

You might be a fit if:
- You dislike over-engineering and can design simple solutions to complex problems.
- You have experience planning your own work.
- You can think on your feet and navigate changing requirements quickly.
- You thrive when you have autonomy.
"""


async def main():
    # Step 1: Extract and classify
    spans = extract_spans_from_pdf(RESUME)
    lines = group_into_visual_lines(spans)
    classified, _ = classify_lines(lines)
    bullets, skills, title_skills = group_bullet_points(classified)
    print(f"Found {len(bullets)} bullets, {len(skills)} skills, {len(title_skills)} title skills")

    # Step 2: Font analysis
    doc = fitz.open(RESUME)
    cmap = _CMapManager(doc)
    analyzer = FontAnalyzer(cmap)
    char_constraint = analyzer.build_char_constraint_string()
    doc.close()

    # Step 2c: Width budgets
    width_budgets = calculate_width_budgets(RESUME, bullets, skills, title_skills)

    # Step 3: Generate optimized content
    bullet_reps, skill_reps, title_reps = await generate_optimized_content(
        bullets, skills, JOB_DESCRIPTION,
        title_skills=title_skills,
        char_constraint=char_constraint,
        width_budgets=width_budgets,
    )
    print(f"\nGenerated: {len(bullet_reps)} bullet, {len(skill_reps)} skill, {len(title_reps)} title replacements")

    # Step 3b: Validate and retry
    bullet_reps, skill_reps, title_reps = await _validate_and_retry(
        RESUME, bullets, skills, title_skills,
        bullet_reps, skill_reps, title_reps,
        JOB_DESCRIPTION, char_constraint, width_budgets,
    )
    print(f"After validation: {len(bullet_reps)} bullet, {len(skill_reps)} skill, {len(title_reps)} title replacements")

    # Step 4: Apply
    apply_changes_to_pdf(
        RESUME, OUTPUT,
        bullets, skills,
        bullet_reps, skill_reps,
        title_skills, title_reps,
    )
    # Save debug copy before verification
    shutil.copy2(OUTPUT, DEBUG_OUTPUT)
    print(f"\nSaved debug copy: {DEBUG_OUTPUT}")

    # Step 5: Verify
    verifier = PostPatchVerifier()
    report = verifier.verify(RESUME, OUTPUT, bullet_reps, skill_reps, title_reps)
    print(f"\n{'='*60}")
    print("VERIFICATION REPORT")
    print(f"{'='*60}")
    print(report.summary)
    print(f"\nOverall: {'PASS' if report.passed else 'FAIL'}")

    # Check dates in the debug output
    print(f"\n{'='*60}")
    print("DATE EXTRACTION COMPARISON")
    print(f"{'='*60}")
    import re
    date_patterns = [
        r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\.?\s*\d{4}\b',
        r'\b\d{4}\s*[-\u2013\u2014]\s*(?:\d{4}|Present|Current|Now)\b',
    ]
    orig_doc = fitz.open(RESUME)
    tail_doc = fitz.open(DEBUG_OUTPUT)
    orig_text = "".join(p.get_text("text") for p in orig_doc)
    tail_text = "".join(p.get_text("text") for p in tail_doc)
    orig_doc.close()
    tail_doc.close()

    orig_dates = set()
    for p in date_patterns:
        orig_dates.update(re.findall(p, orig_text, re.IGNORECASE))
    print(f"\nOriginal dates: {sorted(orig_dates)}")

    tail_dates = set()
    for p in date_patterns:
        tail_dates.update(re.findall(p, tail_text, re.IGNORECASE))
    print(f"Tailored dates: {sorted(tail_dates)}")

    missing = orig_dates - tail_dates
    if missing:
        print(f"\nMISSING dates: {sorted(missing)}")
    else:
        print("\nAll dates preserved!")

    print(f"\nFiles:")
    print(f"  Original: {RESUME}")
    print(f"  Tailored: {OUTPUT} ({os.path.getsize(OUTPUT)/1024:.1f} KB)")
    print(f"  Debug:    {DEBUG_OUTPUT} ({os.path.getsize(DEBUG_OUTPUT)/1024:.1f} KB)")


if __name__ == "__main__":
    asyncio.run(main())
