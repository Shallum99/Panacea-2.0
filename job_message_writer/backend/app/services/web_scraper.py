"""
Fetch a job listing URL and extract the job description text.
Detects known ATS platforms (Greenhouse, Lever) and uses their APIs directly.
Falls back to generic HTML scraping for other sites.
"""

import httpx
import re
import logging
from typing import Tuple, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ATS_PATTERNS = {
    "greenhouse": re.compile(r"boards\.greenhouse\.io/(\w[\w-]*)/jobs/(\d+)"),
    "greenhouse_alt": re.compile(r"job-boards\.greenhouse\.io/(\w[\w-]*)/jobs/(\d+)"),
    "lever": re.compile(r"jobs\.lever\.co/([\w-]+)/([\w-]+)"),
}


async def fetch_and_extract_jd(url: str) -> Tuple[str, str, Optional[str]]:
    """
    Fetch a URL and extract job description text.
    Returns: (title, content_text, company_name_or_none)
    Raises: ValueError on failure
    """
    for ats_name, pattern in ATS_PATTERNS.items():
        match = pattern.search(url)
        if match:
            if ats_name.startswith("greenhouse"):
                return await _extract_greenhouse(match.group(1), match.group(2))
            elif ats_name == "lever":
                return await _extract_lever(match.group(1), match.group(2))

    return await _extract_generic(url)


async def _extract_greenhouse(company: str, job_id: str) -> Tuple[str, str, Optional[str]]:
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(api_url, timeout=15.0)
        if resp.status_code != 200:
            raise ValueError(f"Greenhouse API returned {resp.status_code}")
        data = resp.json()

    title = data.get("title", "Untitled")
    content_html = data.get("content", "")
    location = data.get("location", {}).get("name", "")

    soup = BeautifulSoup(content_html, "html.parser")
    content_text = soup.get_text(separator="\n", strip=True)

    header = f"{title}\n"
    if location:
        header += f"Location: {location}\n"
    header += "\n"

    return title, header + content_text, company


async def _extract_lever(company: str, job_id: str) -> Tuple[str, str, Optional[str]]:
    api_url = f"https://api.lever.co/v0/postings/{company}/{job_id}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(api_url, timeout=15.0)
        if resp.status_code != 200:
            raise ValueError(f"Lever API returned {resp.status_code}")
        data = resp.json()

    title = data.get("text", "Untitled")
    description = data.get("descriptionPlain", "")
    categories = data.get("categories", {})
    location = categories.get("location", "")
    team = categories.get("team", "")

    parts = [title]
    if location:
        parts.append(f"Location: {location}")
    if team:
        parts.append(f"Team: {team}")
    parts.append("")
    parts.append(description)

    for section in data.get("lists", []):
        section_text = section.get("text", "")
        section_content = section.get("content", "")
        if section_text:
            parts.append(f"\n{section_text}")
        if section_content:
            soup = BeautifulSoup(section_content, "html.parser")
            parts.append(soup.get_text(separator="\n", strip=True))

    return title, "\n".join(parts), company


async def _extract_generic(url: str) -> Tuple[str, str, Optional[str]]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise ValueError(f"Failed to fetch URL (HTTP {resp.status_code})")

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
        tag.decompose()

    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find("div", class_=re.compile(r"job[-_]?(description|detail|content|posting)", re.I))
        or soup.find("div", id=re.compile(r"job[-_]?(description|detail|content|posting)", re.I))
    )

    content_element = main or soup.body or soup
    text = content_element.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if len(text) > 15000:
        text = text[:15000] + "\n\n[Content truncated]"

    title = ""
    title_tag = soup.find("h1")
    if title_tag:
        title = title_tag.get_text(strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)

    if len(text.strip()) < 50:
        raise ValueError("Could not extract meaningful text from the page")

    return title or "Untitled Job", text, None
