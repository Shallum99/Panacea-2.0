"""
Job board search — search Greenhouse + Lever public APIs for tech job listings.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
import httpx
import logging
from bs4 import BeautifulSoup

from app.core.supabase_auth import get_current_user
from app.db import models
from app.schemas.job_description import JobSearchResult, JobSearchResponse, JobDetailResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Popular tech companies on Greenhouse
GREENHOUSE_COMPANIES = [
    "airbnb", "figma", "stripe", "notion", "databricks", "brex",
    "discord", "netlify", "vercel", "linear", "anthropic",
    "hashicorp", "cloudflare", "datadog", "gitlab", "twilio",
    "plaid", "coinbase", "robinhood", "instacart", "doordash",
    "lyft", "pinterest", "snap", "reddit", "duolingo",
    "asana", "airtable", "mongodb", "elastic", "confluent",
    "gusto", "rippling", "ramp", "mercury", "scale",
]

# Popular tech companies on Lever
LEVER_COMPANIES = [
    "sourcegraph", "retool", "replit", "supabase",
    "dbt-labs", "temporal", "cockroachlabs",
    "planetscale", "grafana", "axiom",
]


@router.get("/search", response_model=JobSearchResponse)
async def search_jobs(
    q: Optional[str] = Query(None, description="Search keyword for job titles"),
    company: Optional[str] = Query(None, description="Specific company slug"),
    location: Optional[str] = Query(None, description="Filter by location"),
    source: Optional[str] = Query(None, description="'greenhouse' or 'lever'"),
    current_user: models.User = Depends(get_current_user),
):
    """Search public Greenhouse and Lever job boards."""
    results: List[JobSearchResult] = []

    companies_to_search = []
    if company:
        if source != "lever":
            companies_to_search.append(("greenhouse", company))
        if source != "greenhouse":
            companies_to_search.append(("lever", company))
    else:
        if source != "lever":
            for c in GREENHOUSE_COMPANIES[:15]:
                companies_to_search.append(("greenhouse", c))
        if source != "greenhouse":
            for c in LEVER_COMPANIES[:10]:
                companies_to_search.append(("lever", c))

    async with httpx.AsyncClient(timeout=10.0) as client:
        for src, comp in companies_to_search:
            try:
                if src == "greenhouse":
                    jobs = await _fetch_greenhouse_jobs(client, comp, q, location)
                    results.extend(jobs)
                else:
                    jobs = await _fetch_lever_jobs(client, comp, q, location)
                    results.extend(jobs)
            except Exception as e:
                logger.debug(f"Skipping {src}/{comp}: {e}")
                continue

    if q:
        q_lower = q.lower()
        results.sort(key=lambda r: (q_lower not in r.title.lower(), r.title.lower()))

    return JobSearchResponse(results=results[:100], total=len(results))


@router.get("/detail/{source}/{company}/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(
    source: str,
    company: str,
    job_id: str,
    current_user: models.User = Depends(get_current_user),
):
    """Get full job details from a specific ATS."""
    if source not in ("greenhouse", "lever"):
        raise HTTPException(status_code=400, detail="Source must be 'greenhouse' or 'lever'")

    async with httpx.AsyncClient(timeout=15.0) as client:
        if source == "greenhouse":
            return await _fetch_greenhouse_detail(client, company, job_id)
        else:
            return await _fetch_lever_detail(client, company, job_id)


async def _fetch_greenhouse_jobs(
    client: httpx.AsyncClient, company: str, q: Optional[str], location: Optional[str]
) -> List[JobSearchResult]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"
    resp = await client.get(url)
    if resp.status_code != 200:
        return []

    data = resp.json()
    results = []
    for job in data.get("jobs", []):
        title = job.get("title", "")
        loc = job.get("location", {}).get("name", "")
        departments = ", ".join(d.get("name", "") for d in job.get("departments", []))

        if q and q.lower() not in title.lower() and q.lower() not in departments.lower():
            continue
        if location and location.lower() not in loc.lower():
            continue

        results.append(JobSearchResult(
            id=str(job["id"]),
            title=title,
            company=company,
            location=loc or None,
            department=departments or None,
            url=job.get("absolute_url", f"https://boards.greenhouse.io/{company}/jobs/{job['id']}"),
            source="greenhouse",
            updated_at=job.get("updated_at"),
        ))
    return results


async def _fetch_lever_jobs(
    client: httpx.AsyncClient, company: str, q: Optional[str], location: Optional[str]
) -> List[JobSearchResult]:
    url = f"https://api.lever.co/v0/postings/{company}?mode=json"
    resp = await client.get(url)
    if resp.status_code != 200:
        return []

    data = resp.json()
    if not isinstance(data, list):
        return []

    results = []
    for job in data:
        title = job.get("text", "")
        categories = job.get("categories", {})
        loc = categories.get("location", "")
        team = categories.get("team", "")

        if q and q.lower() not in title.lower() and q.lower() not in (team or "").lower():
            continue
        if location and location.lower() not in (loc or "").lower():
            continue

        salary = job.get("salaryRange")
        salary_str = None
        if salary and isinstance(salary, dict):
            s_min = salary.get("min", "")
            s_max = salary.get("max", "")
            if s_min or s_max:
                salary_str = f"${s_min}-${s_max}"

        results.append(JobSearchResult(
            id=job.get("id", ""),
            title=title,
            company=company,
            location=loc or None,
            department=team or None,
            url=job.get("hostedUrl", ""),
            source="lever",
            workplace_type=job.get("workplaceType"),
            salary_range=salary_str,
        ))
    return results


async def _fetch_greenhouse_detail(
    client: httpx.AsyncClient, company: str, job_id: str
) -> JobDetailResponse:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
    resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Job not found on Greenhouse")

    data = resp.json()
    content_html = data.get("content", "")
    soup = BeautifulSoup(content_html, "html.parser")
    content_text = soup.get_text(separator="\n", strip=True)

    return JobDetailResponse(
        id=str(data["id"]),
        title=data.get("title", "Untitled"),
        company=company,
        location=data.get("location", {}).get("name"),
        department=", ".join(d.get("name", "") for d in data.get("departments", [])) or None,
        content=content_text,
        url=data.get("absolute_url", ""),
        source="greenhouse",
        apply_url=data.get("absolute_url"),
    )


async def _fetch_lever_detail(
    client: httpx.AsyncClient, company: str, job_id: str
) -> JobDetailResponse:
    url = f"https://api.lever.co/v0/postings/{company}/{job_id}"
    resp = await client.get(url)
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail="Job not found on Lever")

    data = resp.json()
    categories = data.get("categories", {})

    parts = [data.get("descriptionPlain", "")]
    for section in data.get("lists", []):
        section_title = section.get("text", "")
        section_content = section.get("content", "")
        if section_title:
            parts.append(f"\n{section_title}")
        if section_content:
            s = BeautifulSoup(section_content, "html.parser")
            parts.append(s.get_text(separator="\n", strip=True))

    salary = data.get("salaryRange")
    salary_str = None
    if salary and isinstance(salary, dict):
        s_min = salary.get("min", "")
        s_max = salary.get("max", "")
        if s_min or s_max:
            salary_str = f"${s_min}-${s_max}"

    return JobDetailResponse(
        id=data.get("id", ""),
        title=data.get("text", "Untitled"),
        company=company,
        location=categories.get("location"),
        department=categories.get("team"),
        content="\n".join(parts),
        url=data.get("hostedUrl", ""),
        source="lever",
        apply_url=data.get("applyUrl"),
        workplace_type=data.get("workplaceType"),
        salary_range=salary_str,
    )
