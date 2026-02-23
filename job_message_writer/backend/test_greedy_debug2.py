"""Quick test to debug greedy fill line breaking."""
import asyncio, os, sys, logging

# Setup env
sys.path.insert(0, os.path.dirname(__file__))
env_path = os.path.join(os.path.dirname(__file__), ".env")
for line in open(env_path):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.INFO, format="%(name)s:%(message)s")

from app.services.pdf_format_preserver import optimize_pdf

PDF = "uploads/resumes/2d425a7058c54b2aad6c8e29bc22ef81_Shallum Maryapanor - Full Stack Software Developer-1 (1).pdf"
JD = """Senior Software Engineer - Backend
Requirements: Python, SQL, REST APIs, cloud services (AWS/Azure),
containerization, CI/CD, data integration, ETL pipelines.
Experience with microservices architecture, message queues,
real-time data processing, and enterprise-scale systems."""

async def main():
    result = await optimize_pdf(PDF, "/tmp/tailored_debug2.pdf", JD, "")
    print(f"\nResult: {result.get('status')}, patches: {result.get('total_patches')}")

asyncio.run(main())
