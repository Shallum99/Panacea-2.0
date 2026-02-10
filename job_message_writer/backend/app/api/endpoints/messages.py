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
from app.core.supabase_auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/generate", response_model=MessageResponse)
async def generate_message(
    request: MessageRequest,
    current_user: models.User = Depends(get_current_user), 
    db: Session = Depends(get_db)
) -> Any:
    """Generate a personalized message based on resume ID (or active profile), job description, and message type."""
    try:
        # Get or create default user
        user = current_user
        
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
        # Define message type characteristics
        message_type_info = {
            "linkedin_message": {
                "format": "LinkedIn Message",
                "length": "around 300 characters",
                "purpose": "a direct message to a LinkedIn connection",
                "tone": "professional yet conversational",
                "structure": "brief introduction, interest in position, 1-2 key qualifications, call to action"
            },
            "linkedin_connection": {
                "format": "LinkedIn Connection Request",
                "length": "around 200 characters",
                "purpose": "a request to connect on LinkedIn",
                "tone": "brief and professional",
                "structure": "very brief introduction, reason for connecting, 1 key qualification, polite closing"
            },
            "linkedin_inmail": {
                "format": "LinkedIn InMail",
                "length": "around 2000 characters",
                "purpose": "a more detailed message to a recruiter not in your network",
                "tone": "professional and confident",
                "structure": "formal greeting, introduction, background summary, key qualifications that match the job, specific company interest, call to action"
            },
            "email_short": {
                "format": "Short Email",
                "length": "around 1000 characters",
                "purpose": "a concise job application email",
                "tone": "professional and direct",
                "structure": "greeting, brief introduction, 2-3 key qualifications, interest in company, call to action"
            },
            "email_detailed": {
                "format": "Detailed Email",
                "length": "around 3000 characters",
                "purpose": "a comprehensive job application",
                "tone": "formal and detailed",
                "structure": "formal greeting, full introduction, detailed background, achievements, multiple qualifications aligned with job requirements, company-specific interest, detailed closing with call to action"
            },
            "ycombinator": {
                "format": "Y Combinator Application",
                "length": "around 500 characters",
                "purpose": "a startup-focused application",
                "tone": "direct, innovative, and impactful",
                "structure": "concise intro, highlight of innovative abilities, entrepreneurial mindset, growth metrics if applicable, direct closing"
            }
        }
        
        # Get the message type info
        msg_type = request.message_type
        if msg_type not in message_type_info:
            msg_type = "linkedin_message"  # Default fallback
        
        type_details = message_type_info[msg_type]
        
        # Generate message using resume content, profile type, and extracted info
        system_prompt = """
        You are an expert job application assistant. Your task is to craft personalized, 
        professional outreach messages from job seekers to recruiters or hiring managers.
        The message should highlight relevant skills from the resume that match the job description,
        show interest in the company, and have an appropriate tone for the platform.
        """
        
        recruiter_greeting = ""
        if request.recruiter_name:
            recruiter_greeting = f"Hi {request.recruiter_name},"
        
        user_prompt = f"""
        Create a personalized {type_details['format']} from a job seeker to a recruiter based on:

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

        5. MESSAGE TYPE DETAILS:
        Format: {type_details['format']}
        Length: {type_details['length']}
        Purpose: {type_details['purpose']}
        Tone: {type_details['tone']}
        Structure: {type_details['structure']}
        
        {f"6. RECRUITER NAME: {request.recruiter_name}" if request.recruiter_name else "Hiring Team"}
        
        Requirements:
        - If recruiter name is provided, address them directly or use a general greeting
        - Include applicant's name and contact information
        - Keep the message appropriate for {type_details['format']} with {type_details['length']}
        - Follow the structure: {type_details['structure']}
        - Use the tone: {type_details['tone']}
        - Highlight the most relevant skills from the resume that match the job
        - Reference specific company information and emphasize experience relevant to this specific role
        - Include a clear call to action
        - DO NOT use generic phrases like "I am writing to express my interest"
        - Emphasize the candidate's experience specifically as a {resume.profile_type}
        {f"- Start the message with '{recruiter_greeting}'" if request.recruiter_name else ""}

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