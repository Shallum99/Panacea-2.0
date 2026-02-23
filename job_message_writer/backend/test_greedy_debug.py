"""Quick test to capture greedy fill debug output."""
import asyncio
import sys
import logging
import os

# Load .env
from pathlib import Path
env_path = Path("/home/shallum/Panacea-2.0/job_message_writer/backend/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, val = line.partition('=')
            os.environ[key.strip()] = val.strip()

logging.basicConfig(level=logging.INFO)

sys.path.insert(0, "/home/shallum/Panacea-2.0/job_message_writer/backend")

from app.services.pdf_format_preserver import optimize_pdf

JOB_DESC = """
Senior Software Engineer at TechCorp.
Requirements: Python, FastAPI, PostgreSQL, Docker, AWS, CI/CD, REST APIs.
Experience with distributed systems, microservices, and cloud infrastructure.
Strong problem-solving skills and attention to detail.
"""

RESUME_CONTENT = "Shallum Maryapanor - Full Stack Software Developer. Experienced in Python, FastAPI, React, PostgreSQL."

async def main():
    pdf_path = "/home/shallum/Panacea-2.0/job_message_writer/backend/uploads/resumes/Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"
    output_path = "/tmp/tailored_debug.pdf"
    result = await optimize_pdf(pdf_path, output_path, JOB_DESC, RESUME_CONTENT)
    print(f"Result: {result}")

asyncio.run(main())
