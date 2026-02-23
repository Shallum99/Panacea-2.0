#!/usr/bin/env python3
"""Thorough test of all 3 resumes against the YourCo JD."""
import asyncio
import sys
import os
import json
import traceback
from dotenv import load_dotenv

load_dotenv("backend/.env")
sys.path.insert(0, "backend")

from app.services.pdf_format_preserver import optimize_pdf

TEST_DIR = "/home/shallum/Panacea-2.0/job_message_writer/test_resume_jd"
OUTPUT_DIR = "/home/shallum/Panacea-2.0/job_message_writer/test_resume_jd/output"

JOB_DESCRIPTION = """Sr Backend Engineer at Yourco

At Yourco, we're bringing traditional industries into the future. AI unlocks the opportunity to empower frontline workforces and bring traditional industries into the future.

Yourco is hiring, and we are looking for the best of the best in Chicago.

What is Yourco? The "app-less" employee app built for the frontline workforce. All of the powerful functionality and security you expect in an enterprise mobile app, with the simplicity, distribution, and actual two-way engagement of SMS.

Who We Serve: From small businesses to Fortune 500 enterprises, organizations in traditional industries trust Yourco as their frontline communications and frontline intelligence platform. Some of our customers include Snap-on, Sherwin-Williams, Keg Restaurants, Indianapolis Airport Authority, Great Day Improvements, and Ozinga. We specialize in serving industries with the frontline, non-desk employees that make up 80% of the global workforce.

Tech Stack:
- Node (Express, Nest)
- MongoDB
- PostgreSQL
- Google Cloud Platform
"""

RESUMES = [
    {"name": "Shallum", "file": "Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"},
    {"name": "Archie", "file": "Archie-resume-SDE.pdf"},
    {"name": "Yasha", "file": "Yasha_Salesforce.pdf"},
]


async def run_one(resume):
    name = resume["name"]
    input_path = os.path.join(TEST_DIR, resume["file"])
    output_path = os.path.join(OUTPUT_DIR, f"{name}_Tailored_YourCo.pdf")

    print(f"\n{'='*80}")
    print(f"  TAILORING: {name}")
    print(f"  Input:  {input_path}")
    print(f"  Output: {output_path}")
    print(f"{'='*80}\n")

    try:
        result = await optimize_pdf(input_path, output_path, JOB_DESCRIPTION, "")

        print(f"\n{'='*80}")
        print(f"  RESULT: {name}")
        print(f"{'='*80}")
        for k, v in result.items():
            if k != "changes":
                print(f"  {k}: {v}")

        if "changes" in result:
            changes = result["changes"]
            if "bullets" in changes:
                print(f"\n  Bullets modified: {len(changes['bullets'])}")
                for idx, lines in changes["bullets"].items():
                    for line in lines:
                        print(f"    [{idx}]: {line[:120]}")

            if "skills" in changes:
                print(f"\n  Skills modified: {len(changes['skills'])}")
                for idx, text in changes["skills"].items():
                    print(f"    [{idx}]: {text[:150]}")

            if "title_skills" in changes:
                print(f"\n  Title skills modified: {len(changes['title_skills'])}")
                for idx, text in changes["title_skills"].items():
                    print(f"    [{idx}]: {text[:150]}")

        if os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) / 1024
            print(f"\n  Output saved: {output_path} ({size_kb:.1f} KB)")
        else:
            print(f"\n  ERROR: Output file not created!")

        return {"name": name, "status": "OK", "output": output_path, "result": result}

    except Exception as e:
        print(f"\n  FAILED: {name}")
        traceback.print_exc()
        return {"name": name, "status": "FAILED", "error": str(e)}


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    results = []
    for resume in RESUMES:
        r = await run_one(resume)
        results.append(r)

    print(f"\n\n{'='*80}")
    print("  SUMMARY")
    print(f"{'='*80}")
    for r in results:
        status = r["status"]
        name = r["name"]
        if status == "OK":
            print(f"  {name}: OK - {r.get('output', 'N/A')}")
        else:
            print(f"  {name}: FAILED - {r.get('error', 'unknown')}")


if __name__ == "__main__":
    asyncio.run(main())
