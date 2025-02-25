# File: backend/app/api/endpoints/test.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict
import logging

from app.db.database import get_db
from app.schemas.job_description import JobDescriptionBase
from app.llm.tiny_llama_client import TinyLlamaClient

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/analyze-jd-test")
async def analyze_job_description_test(
    job_desc: JobDescriptionBase
) -> Dict[str, Any]:
    """Test endpoint to extract company information from a job description using TinyLlama."""
    try:
        tiny_llama_client = TinyLlamaClient()
        result = await tiny_llama_client.extract_company_info(job_desc.content)
        
        print(result, "<--------this is the result")
        # Ensure we're returning a dictionary
        if not isinstance(result, dict):
            logger.error(f"Result is not a dictionary: {type(result)}, value: {result}")
            return {
                "company_name": "Unknown",
                "industry": "Unknown",
                "company_size": "Unknown",
                "company_culture": [],
                "technologies": [],
                "location": "Unknown",
                "mission": "Unknown"
            }
        
        return result
    except Exception as e:
        logger.error(f"Error in analyze_job_description_test: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/quick-message-test")
async def generate_quick_message_test(
    job_desc: JobDescriptionBase
) -> Dict[str, Any]:
    """Generate a quick LinkedIn message using a simplified approach."""
    try:
        tiny_llama_client = TinyLlamaClient()
        
        # Extract basic company info
        company_info = await tiny_llama_client.extract_company_info(job_desc.content)
        
        # Use a sample resume for testing
        sample_resume = """
        Experienced software developer with 5 years of experience in Python, React, and FastAPI.
        Skilled in database design, API development, and frontend implementation.
        Previous experience at tech startups and healthcare companies.
        Bachelor's degree in Computer Science.
        """
        
        # Generate a LinkedIn message
        message = await tiny_llama_client.generate_message(
            sample_resume,
            job_desc.content,
            company_info,
            "linkedin"
        )
        
        return {
            "company_info": company_info,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error in generate_quick_message_test: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))