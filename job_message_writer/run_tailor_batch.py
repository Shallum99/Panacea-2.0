#!/usr/bin/env python3
"""Tailor multiple resumes against a single JD."""
import asyncio
import sys
import os
from dotenv import load_dotenv

load_dotenv("backend/.env")
sys.path.insert(0, "backend")

from app.services.pdf_format_preserver import optimize_pdf

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

RESUMES = [
    {
        "input": "/home/shallum/Downloads/Archie-resume-SDE.pdf",
        "output": "/home/shallum/Downloads/Archie_Tailored_YourCo.pdf",
        "name": "Archie",
    },
    {
        "input": "/home/shallum/Downloads/Yasha_Salesforce.pdf",
        "output": "/home/shallum/Downloads/Yasha_Tailored_YourCo.pdf",
        "name": "Yasha",
    },
]


async def tailor_one(resume: dict) -> dict:
    """Tailor a single resume."""
    print(f"\n{'='*60}")
    print(f"TAILORING: {resume['name']}")
    print(f"  Input:  {resume['input']}")
    print(f"  Output: {resume['output']}")
    print(f"{'='*60}\n")

    try:
        result = await optimize_pdf(
            resume["input"], resume["output"], JOB_DESCRIPTION, ""
        )
        size_kb = os.path.getsize(resume["output"]) / 1024 if os.path.exists(resume["output"]) else 0
        print(f"\n{'='*60}")
        print(f"RESULT: {resume['name']}")
        print(f"{'='*60}")
        for k, v in result.items():
            if k != "changes":
                print(f"  {k}: {v}")
        if os.path.exists(resume["output"]):
            print(f"  Output: {resume['output']} ({size_kb:.1f} KB)")
        return {"name": resume["name"], "status": "OK", "result": result}
    except Exception as e:
        print(f"\nERROR tailoring {resume['name']}: {e}")
        import traceback
        traceback.print_exc()
        return {"name": resume["name"], "status": "FAILED", "error": str(e)}


async def main():
    # Run sequentially to avoid rate limits and resource contention
    results = []
    for resume in RESUMES:
        r = await tailor_one(resume)
        results.append(r)

    print(f"\n\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['name']}: {r['status']}")


if __name__ == "__main__":
    asyncio.run(main())
