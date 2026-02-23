#!/usr/bin/env python3
"""One-off script to run the PDF tailoring pipeline."""

import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv("backend/.env")
sys.path.insert(0, "backend")

from app.services.pdf_format_preserver import optimize_pdf

RESUME = "/home/shallum/Downloads/Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"
OUTPUT = "/home/shallum/Downloads/Shallum_Tailored_YourCo.pdf"

JOB_DESCRIPTION = """Sr Backend Engineer at Yourco

At Yourco, we're bringing traditional industries into the future. AI unlocks the opportunity to empower frontline workforces and bring traditional industries into the future.

Yourco is hiring, and we are looking for the best of the best in Chicago.

What is Yourco? The "app-less" employee app built for the frontline workforce. All of the powerful functionality and security you expect in an enterprise mobile app, with the simplicity, distribution, and actual two-way engagement of SMS.

Who We Serve: From small businesses to Fortune 500 enterprises, organizations in traditional industries trust Yourco as their frontline communications and frontline intelligence platform. Some of our customers include Snap-on, Sherwin-Williams, Keg Restaurants, Indianapolis Airport Authority, Great Day Improvements, and Ozinga. We specialize in serving industries with the frontline, non-desk employees that make up 80% of the global workforce.

You might be a fit if the below describes you...
- You dislike over-engineering and can design simple solutions to complex problems.
- You have experience planning your own work. You prefer planning work before coding.
- You enjoy working with and learning from other people.
- You value criticism and always seek the truth. (Facts > Opinions)
- You can think on your feet and navigate changing requirements quickly.
- You thrive when you have autonomy and own as many of the details as possible.

Tech Stack:
- Node (Express, Nest)
- MongoDB
- PostgreSQL
- Google Cloud Platform
"""


async def main():
    print(f"Resume: {RESUME}")
    print(f"Output: {OUTPUT}")
    print(f"JD length: {len(JOB_DESCRIPTION)} chars")
    print("Running optimize_pdf...")
    print()

    result = await optimize_pdf(RESUME, OUTPUT, JOB_DESCRIPTION, "")

    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)

    for k, v in result.items():
        if k != "changes":
            print(f"  {k}: {v}")

    if "changes" in result:
        changes = result["changes"]
        if "bullets" in changes:
            print(f"\n  Bullets modified: {len(changes['bullets'])}")
            for idx, lines in changes["bullets"].items():
                preview = " | ".join(l[:80] for l in lines)
                print(f"    [{idx}]: {preview}")

        if "skills" in changes:
            print(f"\n  Skills modified: {len(changes['skills'])}")
            for idx, text in changes["skills"].items():
                print(f"    [{idx}]: {text[:120]}")

        if "title_skills" in changes:
            print(f"\n  Title skills modified: {len(changes['title_skills'])}")
            for idx, text in changes["title_skills"].items():
                print(f"    [{idx}]: {text[:120]}")

    if os.path.exists(OUTPUT):
        size_kb = os.path.getsize(OUTPUT) / 1024
        print(f"\nOutput saved: {OUTPUT} ({size_kb:.1f} KB)")
    else:
        print("\nERROR: Output file not created")


if __name__ == "__main__":
    asyncio.run(main())
