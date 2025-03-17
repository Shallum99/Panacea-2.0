# File: backend/app/utils/ats_scorer.py
import re
import logging
from typing import Dict, List, Any, Set
import json

logger = logging.getLogger(__name__)


async def extract_keywords_from_job_description(job_description: str) -> Dict[str, Set[str]]:
    """Extract important keywords from job description categorized by type."""
    try:
        # Initialize keyword categories
        keywords = {
            "skills": set(),
            "qualifications": set(),
            "tools": set(),
            "education": set(),
            "experience": set(),
            "responsibilities": set()
        }
        
        # Lowercase for better matching
        job_desc_lower = job_description.lower()
        
        # Common technical skills to look for
        tech_skills = [
            "python", "java", "javascript", "react", "angular", "vue", "node", "express",
            "django", "flask", "fastapi", "spring", "ruby", "rails", "php", "laravel",
            "html", "css", "sql", "nosql", "mongodb", "postgresql", "mysql", "oracle",
            "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins", "ci/cd",
            "git", "agile", "scrum", "jira", "confluence", "devops", "data science",
            "machine learning", "ai", "artificial intelligence", "nlp", "deep learning"
        ]
        
        # Extract skills
        for skill in tech_skills:
            if skill in job_desc_lower:
                keywords["skills"].add(skill)
        
        # Look for years of experience
        experience_pattern = r'(\d+)[+]?\s+years?(?:\s+of)?\s+experience'
        experience_matches = re.findall(experience_pattern, job_desc_lower)
        if experience_matches:
            for match in experience_matches:
                keywords["experience"].add(f"{match} years experience")
        
        # Look for education requirements
        education_terms = ["bachelor", "master", "phd", "degree", "bs", "ms", "mba", "b.s.", "m.s."]
        for term in education_terms:
            if term in job_desc_lower:
                # Get the context around the term
                context_pattern = r'(?:\w+\s+){0,5}' + re.escape(term) + r'(?:\s+\w+){0,5}'
                context_matches = re.findall(context_pattern, job_desc_lower)
                for context in context_matches:
                    keywords["education"].add(context.strip())
        
        # Extract tools or software mentioned
        tools_pattern = r'(?:familiarity|experience|proficiency)(?:\s+\w+){0,3}\s+(?:with|in|using)(?:\s+\w+){0,3}\s+([\w\s/,]+)'
        tools_matches = re.findall(tools_pattern, job_desc_lower)
        for match in tools_matches:
            for tool in match.split(','):
                cleaned_tool = tool.strip()
                if cleaned_tool and cleaned_tool not in ["and", "or"]:
                    keywords["tools"].add(cleaned_tool)
        
        return keywords
    
    except Exception as e:
        logger.error(f"Error extracting keywords from job description: {str(e)}")
        return {"skills": set(), "qualifications": set(), "tools": set(), 
                "education": set(), "experience": set(), "responsibilities": set()}


async def calculate_match_score(resume_content: str, job_description: str) -> float:
    """Calculate overall ATS match score between resume and job description."""
    try:
        # Extract keywords from job description
        jd_keywords = await extract_keywords_from_job_description(job_description)
        
        # Calculate match percentage for each category
        resume_lower = resume_content.lower()
        
        total_keywords = 0
        matched_keywords = 0
        
        # Check for keyword matches in each category
        for category, keywords in jd_keywords.items():
            for keyword in keywords:
                total_keywords += 1
                if keyword.lower() in resume_lower:
                    matched_keywords += 1
        
        # Calculate overall match score
        match_score = (matched_keywords / total_keywords * 100) if total_keywords > 0 else 0
        
        # Cap at 100%
        match_score = min(match_score, 100)
        
        return round(match_score, 1)
    
    except Exception as e:
        logger.error(f"Error calculating match score: {str(e)}")
        return 0.0


async def get_keyword_match(resume_content: str, job_description: str) -> Dict[str, Any]:
    """Get detailed keyword match information."""
    try:
        jd_keywords = await extract_keywords_from_job_description(job_description)
        resume_lower = resume_content.lower()
        
        # Calculate matches by category
        match_details = {}
        matched_keywords = []
        missing_keywords = []
        
        for category, keywords in jd_keywords.items():
            category_matches = 0
            category_total = len(keywords)
            
            for keyword in keywords:
                if keyword.lower() in resume_lower:
                    category_matches += 1
                    matched_keywords.append(keyword)
                else:
                    missing_keywords.append(keyword)
            
            if category_total > 0:
                match_details[category] = round((category_matches / category_total) * 100, 1)
            else:
                match_details[category] = 0
        
        return {
            "breakdown": match_details,
            "matched_keywords": list(set(matched_keywords)),
            "missing_keywords": list(set(missing_keywords))
        }
    
    except Exception as e:
        logger.error(f"Error getting keyword match details: {str(e)}")
        return {
            "breakdown": {},
            "matched_keywords": [],
            "missing_keywords": []
        }


async def get_section_scores(resume_sections: Dict[str, str], job_description: str) -> Dict[str, float]:
    """Calculate ATS match score for each resume section."""
    try:
        section_scores = {}
        
        for section_name, section_content in resume_sections.items():
            if section_content:
                section_score = await calculate_match_score(section_content, job_description)
                section_scores[section_name] = section_score
        
        return section_scores
    
    except Exception as e:
        logger.error(f"Error calculating section scores: {str(e)}")
        return {}


async def generate_improvement_suggestions(keyword_match: Dict[str, Any], job_description: str) -> List[str]:
    """Generate suggestions for improving ATS score."""
    try:
        suggestions = []
        
        # Suggest adding missing keywords
        if keyword_match.get("missing_keywords"):
            missing_skills = [k for k in keyword_match["missing_keywords"] if len(k.split()) <= 3]
            if missing_skills:
                suggestions.append(f"Consider adding these keywords to your resume: {', '.join(missing_skills[:5])}")
        
        # Suggest section improvements based on breakdown
        breakdown = keyword_match.get("breakdown", {})
        
        if "skills" in breakdown and breakdown["skills"] < 70:
            suggestions.append("Your skills section needs improvement. Add more relevant technical skills mentioned in the job description.")
        
        if "experience" in breakdown and breakdown["experience"] < 70:
            suggestions.append("Enhance your experience section by using terminology from the job description to describe your achievements.")
        
        if "education" in breakdown and breakdown["education"] < 70:
            suggestions.append("Make sure your education section aligns with the job requirements.")
        
        if "tools" in breakdown and breakdown["tools"] < 70:
            suggestions.append("Include more tools and technologies mentioned in the job description that you're familiar with.")
        
        # General suggestion if all specific ones are missing
        if not suggestions:
            suggestions.append("Try tailoring your resume more specifically to match keywords in the job description.")
        
        return suggestions
    
    except Exception as e:
        logger.error(f"Error generating improvement suggestions: {str(e)}")
        return ["Customize your resume to include more keywords from the job description."]