# File: backend/app/api/endpoints/messages.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
import logging
import json

from app.db.database import get_db
from app.db import models
from app.schemas.message import MessageRequest, MessageResponse
from app.llm.claude_client import ClaudeClient

# Import the helper function from resumes
from app.api.endpoints.resumes import get_or_create_default_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate", response_model=MessageResponse)
async def generate_message(
    request: MessageRequest, 
    db: Session = Depends(get_db)
) -> Any:
    """Generate a personalized message based on resume ID (or active profile), job description, and message type."""
    try:
        # Get or create default user
        user = get_or_create_default_user(db)
        
        # Get resume from database - either the specified one or the active one
        if request.resume_id:
            resume = db.query(models.Resume).filter(
                models.Resume.id == request.resume_id,
                models.Resume.owner_id == user.id
            ).first()
            
            if not resume:
                raise HTTPException(status_code=404, detail=f"Resume with ID {request.resume_id} not found")
        else:
            # Get the active resume
            resume = db.query(models.Resume).filter(
                models.Resume.owner_id == user.id,
                models.Resume.is_active == True
            ).first()
            
            if not resume:
                # If no active resume, get the most recent one
                resume = db.query(models.Resume).filter(
                    models.Resume.owner_id == user.id
                ).order_by(models.Resume.created_at.desc()).first()
                
                if not resume:
                    raise HTTPException(status_code=404, detail="No resume profiles found. Please create a resume first.")
                
                # Set it as active
                resume.is_active = True
                db.commit()
        
        # Get resume content
        resume_content = resume.content
        
        # Parse extracted resume info
        try:
            resume_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
        except:
            resume_info = {}
        
        # Use Claude client
        claude_client = ClaudeClient()
        
        # Extract company info
        company_info = await claude_client.extract_company_info(request.job_description)
        
        # Generate message using resume content, profile type, and extracted info
        system_prompt = """
        You are an expert job application assistant. Your task is to craft personalized, 
        professional outreach messages from job seekers to recruiters or hiring managers.
        The message should highlight relevant skills from the resume that match the job description,
        show interest in the company, and have an appropriate tone for the platform.
        """
        
        user_prompt = f"""
        Create a personalized {request.message_type} message from a job seeker to a recruiter based on:

        1. RESUME CONTENT:
        {resume_content}

        2. PROFILE TYPE: {resume.profile_type}
        Primary languages: {resume.primary_languages}
        Frameworks: {resume.frameworks}
        Experience level: {resume.seniority} with {resume.years_experience}

        3. JOB DESCRIPTION:
        {request.job_description}

        4. COMPANY INFO:
        {json.dumps(company_info, indent=2)}

        5. MESSAGE TYPE: {request.message_type}
        
        Requirements:
        - Include applicants name and contact information
        - Keep the message appropriate for the {request.message_type} format
        - Highlight the most relevant skills from the resume that match the job
        - Reference specific company information and emphasize experience relevant to this specific role
        - Use an appropriate professional tone for the platform
        - Include a clear call to action
        - DO NOT use generic phrases like "I am writing to express my interest"
        - Emphasize the candidate's experience specifically as a {resume.profile_type}

        Return ONLY the message text without any additional explanation or context.
        """
        
        message = await claude_client._send_request(system_prompt, user_prompt)
        
        # Save the generated message in the database
        db_message = models.Message(
            content=message,
            message_type=request.message_type,
            owner_id=user.id,
            resume_id=resume.id,
            # Add job_description_id if you have it
        )
        
        db.add(db_message)
        db.commit()
        
        # Build profile classification
        profile_classification = {
            "profile_type": resume.profile_type,
            "primary_languages": resume.primary_languages.split(",") if resume.primary_languages else [],
            "frameworks": resume.frameworks.split(",") if resume.frameworks else [],
            "years_experience": resume.years_experience,
            "seniority": resume.seniority,
            "industry_focus": resume.industry_focus
        }
        
        return MessageResponse(
            message=message, 
            company_info=company_info,
            resume_info=resume_info,
            profile_classification=profile_classification,
            resume_id=resume.id,
            resume_title=resume.title
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating message: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))