# File: backend/app/api/endpoints/resumes.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Any, List, Dict, Optional
import json
import logging

from app.db.database import get_db
from app.db import models
from app.schemas.resume import ResumeResponse, ResumeContentResponse
from app.llm.claude_client import ClaudeClient
from app.utils.pdf_extractor import extract_text_from_pdf

router = APIRouter()
logger = logging.getLogger(__name__)

# Helper function to get or create a default user for development
def get_or_create_default_user(db: Session):
    """Get or create a default user for development purposes."""
    db_user = db.query(models.User).first()
    
    if not db_user:
        db_user = models.User(
            email="user@example.com",
            hashed_password="dummy_hashed_password",
            is_active=True
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
    return db_user

# Helper function to ensure correct types in extracted info
def ensure_correct_types(extracted_info: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all fields in extracted_info have the correct types."""
    if not extracted_info:
        return {
            "name": "Unknown",
            "email": "Unknown",
            "phone": "Unknown",
            "skills": [],
            "years_experience": "Unknown",
            "education": "Unknown",
            "recent_job": "Unknown",
            "recent_company": "Unknown",
            "profile_type": "Unknown",
            "primary_languages": [],
            "frameworks": [],
            "seniority": "Unknown",
            "industry_focus": "Unknown"
        }
    
    # Handle years_experience specifically
    if "years_experience" in extracted_info and not isinstance(extracted_info["years_experience"], str):
        extracted_info["years_experience"] = str(extracted_info["years_experience"])
        if extracted_info["years_experience"].isdigit():
            extracted_info["years_experience"] += " years"
    
    # Ensure string fields are strings
    for field in ["name", "email", "phone", "education", "recent_job", "recent_company", 
                  "profile_type", "seniority", "industry_focus"]:
        if field in extracted_info and not isinstance(extracted_info[field], str):
            extracted_info[field] = str(extracted_info[field])
    
    # Ensure list fields are lists
    for field in ["skills", "primary_languages", "frameworks"]:
        if field in extracted_info:
            if not isinstance(extracted_info[field], list):
                if isinstance(extracted_info[field], str):
                    extracted_info[field] = [s.strip() for s in extracted_info[field].split(",")]
                else:
                    extracted_info[field] = [str(extracted_info[field])]
        else:
            extracted_info[field] = []
    
    return extracted_info

async def extract_resume_data(content: str) -> Dict[str, Any]:
    """Extract resume data using Claude with handling for nested structures."""
    try:
        claude = ClaudeClient()
        
        # Clean up the content
        # Remove excessive whitespace and normalize line breaks
        cleaned_content = ' '.join(content.split())
        
        system_prompt = """
        You are an expert resume analyzer with experience in technical hiring. Your task is to carefully extract key information from a resume that might have formatting issues due to PDF extraction.
        """
        
        user_prompt = f"""
        Analyze this resume text carefully (which was extracted from a PDF and may have formatting issues) and extract the following information:
        
        Return a single flat JSON object with these fields (do not use nested objects):
        - name: The full name of the person
        - email: Email address
        - phone: Phone number
        - skills: All technical and soft skills (as an array)
        - years_experience: Total years of experience
        - education: Highest education qualification
        - recent_job: Most recent job title
        - recent_company: Most recent company name
        - profile_type: The primary role (Frontend, Backend, Full Stack, etc.)
        - primary_languages: Main programming languages (as an array)
        - frameworks: Frameworks and libraries (as an array)
        - seniority: Seniority level (Junior, Mid-level, Senior, etc.)
        - industry_focus: Industries they have experience in
        
        IMPORTANT: Return a flat JSON structure (not nested). All fields should be at the top level of the JSON object.
        
        Resume text:
        {cleaned_content}
        """
        
        response = await claude._send_request(system_prompt, user_prompt)
        
        # Parse the response
        try:
            result = json.loads(response)
            logger.info(f"Successfully extracted resume data with profile type: {result.get('profile_type', 'Unknown')}")
            
            # Handle either flat or nested structure
            if "basic_information" in result or "profile_classification" in result:
                # We have a nested structure, flatten it
                flattened = {}
                
                if "basic_information" in result:
                    for key, value in result["basic_information"].items():
                        flattened[key] = value
                
                if "profile_classification" in result:
                    for key, value in result["profile_classification"].items():
                        flattened[key] = value
                
                return flattened
            else:
                # Already flat, return as is
                return result
            
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Claude response, trying to extract JSON")
            # Try to extract JSON
            import re
            json_pattern = r'({[\s\S]*})'
            match = re.search(json_pattern, response)
            if match:
                try:
                    extracted_json = json.loads(match.group(1))
                    
                    # Check for nested structure
                    if "basic_information" in extracted_json or "profile_classification" in extracted_json:
                        # We have a nested structure, flatten it
                        flattened = {}
                        
                        if "basic_information" in extracted_json:
                            for key, value in extracted_json["basic_information"].items():
                                flattened[key] = value
                        
                        if "profile_classification" in extracted_json:
                            for key, value in extracted_json["profile_classification"].items():
                                flattened[key] = value
                        
                        return flattened
                    else:
                        # Already flat, return as is
                        return extracted_json
                except json.JSONDecodeError:
                    pass
            
            logger.warning("Falling back to default extracted info values")
            return {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown",
                "profile_type": "Unknown",
                "primary_languages": [],
                "frameworks": [],
                "seniority": "Unknown",
                "industry_focus": "Unknown"
            }
    except Exception as e:
        logger.error(f"Error extracting resume data: {str(e)}")
        return {
            "name": "Unknown",
            "email": "Unknown",
            "phone": "Unknown",
            "skills": [],
            "years_experience": "Unknown",
            "education": "Unknown",
            "recent_job": "Unknown",
            "recent_company": "Unknown",
            "profile_type": "Unknown",
            "primary_languages": [],
            "frameworks": [],
            "seniority": "Unknown",
            "industry_focus": "Unknown"
        }

@router.post("/", response_model=ResumeResponse)
async def create_resume(
    title: str = Form(...),  # Profile name (e.g., "My Backend Developer Resume")
    file: UploadFile = File(...),  # Now this is required
    make_active: bool = Form(True),  # Whether to make this the active profile
    db: Session = Depends(get_db)
) -> Any:
    """Create a new resume profile from a PDF file."""
    try:
        # Get or create default user
        user = get_or_create_default_user(db)
        
        # Check if file is a PDF
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Read the file content
        file_content = await file.read()
        logger.info(f"Read {len(file_content)} bytes from uploaded file {file.filename}")
        
        # Extract text from PDF
        content = await extract_text_from_pdf(file_content)
        
        # Debug log the extracted content length and sample
        if content:
            logger.info(f"Extracted {len(content)} characters from PDF")
            # Log first 500 chars for debugging
            logger.info(f"First 500 chars of extracted content: {content[:500]}")
        else:
            logger.error("No content was extracted from the PDF")
            raise HTTPException(status_code=400, detail="Could not extract text from PDF or PDF is empty")
            
        if not content or len(content.strip()) < 10:  # Sanity check for minimum content
            logger.error(f"Extracted content too short: {len(content) if content else 0} chars")
            raise HTTPException(status_code=400, detail="Could not extract text from PDF or PDF is empty")
        
        # Extract resume information and profile classification using Claude
        logger.info("Sending extracted content to Claude for analysis")
        extracted_data = await extract_resume_data(content)
        
        # Debug log the extracted data
        logger.info(f"Claude analysis results: {json.dumps(extracted_data)}")
        
        # Ensure correct types
        extracted_data = ensure_correct_types(extracted_data)
        
        # If making this profile active, deactivate all other profiles for this user
        if make_active:
            db.query(models.Resume).filter(
                models.Resume.owner_id == user.id,
                models.Resume.is_active == True
            ).update({"is_active": False})
        
        # Create new resume with extracted information
        db_resume = models.Resume(
            title=title,
            content=content,
            file_path=file.filename,
            owner_id=user.id,
            is_active=make_active,
            
            # Store extracted information
            extracted_info=json.dumps(extracted_data),
            name=extracted_data.get("name"),
            email=extracted_data.get("email"),
            phone=extracted_data.get("phone"),
            skills=",".join(extracted_data.get("skills", [])),
            years_experience=extracted_data.get("years_experience"),
            education=extracted_data.get("education"),
            recent_job=extracted_data.get("recent_job"),
            recent_company=extracted_data.get("recent_company"),
            
            # Store profile classification
            profile_type=extracted_data.get("profile_type"),
            primary_languages=",".join(extracted_data.get("primary_languages", [])),
            frameworks=",".join(extracted_data.get("frameworks", [])),
            seniority=extracted_data.get("seniority"),
            industry_focus=extracted_data.get("industry_focus")
        )
        
        db.add(db_resume)
        db.commit()
        db.refresh(db_resume)
        
        # Return response
        return {
            "id": db_resume.id,
            "title": db_resume.title,
            "filename": file.filename,
            "is_active": db_resume.is_active,
            "extracted_info": extracted_data,
            "profile_classification": {
                "profile_type": extracted_data.get("profile_type"),
                "primary_languages": extracted_data.get("primary_languages", []),
                "frameworks": extracted_data.get("frameworks", []),
                "years_experience": extracted_data.get("years_experience"),
                "seniority": extracted_data.get("seniority"),
                "industry_focus": extracted_data.get("industry_focus")
            }
        }
    except Exception as e:
        logger.error(f"Error creating resume: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[ResumeResponse])
def read_resumes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> Any:
    """Get all resume profiles for the current user."""
    try:
        # Get default user
        user = get_or_create_default_user(db)
        
        # Get resumes for this user
        resumes = db.query(models.Resume).filter(
            models.Resume.owner_id == user.id
        ).offset(skip).limit(limit).all()
        
        result = []
        for resume in resumes:
            # Parse extracted info
            try:
                extracted_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
                # Ensure correct types
                extracted_info = ensure_correct_types(extracted_info)
            except:
                extracted_info = {
                    "name": "Unknown",
                    "email": "Unknown",
                    "phone": "Unknown",
                    "skills": [],
                    "years_experience": "Unknown",
                    "education": "Unknown",
                    "recent_job": "Unknown",
                    "recent_company": "Unknown"
                }
            
            # Build profile classification
            profile_classification = {
                "profile_type": resume.profile_type,
                "primary_languages": resume.primary_languages.split(",") if resume.primary_languages else [],
                "frameworks": resume.frameworks.split(",") if resume.frameworks else [],
                "years_experience": resume.years_experience,
                "seniority": resume.seniority,
                "industry_focus": resume.industry_focus
            }
                
            result.append({
                "id": resume.id,
                "title": resume.title,
                "filename": resume.file_path,
                "is_active": resume.is_active,
                "extracted_info": extracted_info,
                "profile_classification": profile_classification
            })
            
        return result
    except Exception as e:
        logger.error(f"Error reading resumes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/active", response_model=ResumeResponse)
def get_active_resume(
    db: Session = Depends(get_db)
) -> Any:
    """Get the user's active resume profile."""
    try:
        # Get default user
        user = get_or_create_default_user(db)
        
        # Get active resume
        resume = db.query(models.Resume).filter(
            models.Resume.owner_id == user.id,
            models.Resume.is_active == True
        ).first()
        
        if not resume:
            # If no active resume, get the most recent one and make it active
            resume = db.query(models.Resume).filter(
                models.Resume.owner_id == user.id
            ).order_by(models.Resume.created_at.desc()).first()
            
            if resume:
                resume.is_active = True
                db.commit()
            else:
                raise HTTPException(status_code=404, detail="No resume profiles found")
        
        # Parse extracted info
        try:
            extracted_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
            # Ensure correct types
            extracted_info = ensure_correct_types(extracted_info)
        except:
            extracted_info = {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown"
            }
        
        # Build profile classification
        profile_classification = {
            "profile_type": resume.profile_type,
            "primary_languages": resume.primary_languages.split(",") if resume.primary_languages else [],
            "frameworks": resume.frameworks.split(",") if resume.frameworks else [],
            "years_experience": resume.years_experience,
            "seniority": resume.seniority,
            "industry_focus": resume.industry_focus
        }
            
        return {
            "id": resume.id,
            "title": resume.title,
            "filename": resume.file_path,
            "is_active": resume.is_active,
            "extracted_info": extracted_info,
            "profile_classification": profile_classification
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting active resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{resume_id}/set-active", response_model=ResumeResponse)
def set_active_resume(
    resume_id: int,
    db: Session = Depends(get_db)
) -> Any:
    """Set a specific resume profile as the active one."""
    try:
        # Get default user
        user = get_or_create_default_user(db)
        
        # Check if the resume exists and belongs to the user
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id,
            models.Resume.owner_id == user.id
        ).first()
        
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        # Deactivate all other resumes
        db.query(models.Resume).filter(
            models.Resume.owner_id == user.id,
            models.Resume.id != resume_id
        ).update({"is_active": False})
        
        # Set this resume as active
        resume.is_active = True
        db.commit()
        
        # Parse extracted info
        try:
            extracted_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
            # Ensure correct types
            extracted_info = ensure_correct_types(extracted_info)
        except:
            extracted_info = {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown"
            }
        
        # Build profile classification
        profile_classification = {
            "profile_type": resume.profile_type,
            "primary_languages": resume.primary_languages.split(",") if resume.primary_languages else [],
            "frameworks": resume.frameworks.split(",") if resume.frameworks else [],
            "years_experience": resume.years_experience,
            "seniority": resume.seniority,
            "industry_focus": resume.industry_focus
        }
            
        return {
            "id": resume.id,
            "title": resume.title,
            "filename": resume.file_path,
            "is_active": resume.is_active,
            "extracted_info": extracted_info,
            "profile_classification": profile_classification
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting active resume: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{resume_id}", response_model=ResumeResponse)
def read_resume(
    resume_id: int,
    db: Session = Depends(get_db)
) -> Any:
    """Get a specific resume by ID with extracted information."""
    try:
        # Get default user
        user = get_or_create_default_user(db)
        
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id,
            models.Resume.owner_id == user.id
        ).first()
        
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        # Parse extracted info
        try:
            extracted_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
            # Ensure correct types
            extracted_info = ensure_correct_types(extracted_info)
        except:
            extracted_info = {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown"
            }
        
        # Build profile classification
        profile_classification = {
            "profile_type": resume.profile_type,
            "primary_languages": resume.primary_languages.split(",") if resume.primary_languages else [],
            "frameworks": resume.frameworks.split(",") if resume.frameworks else [],
            "years_experience": resume.years_experience,
            "seniority": resume.seniority,
            "industry_focus": resume.industry_focus
        }
            
        return {
            "id": resume.id,
            "title": resume.title,
            "filename": resume.file_path,
            "is_active": resume.is_active,
            "extracted_info": extracted_info,
            "profile_classification": profile_classification
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading resume: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{resume_id}/content", response_model=ResumeContentResponse)
def read_resume_content(
    resume_id: int,
    db: Session = Depends(get_db)
) -> Any:
    """Get the content of a specific resume with extracted information."""
    try:
        # Get default user
        user = get_or_create_default_user(db)
        
        resume = db.query(models.Resume).filter(
            models.Resume.id == resume_id,
            models.Resume.owner_id == user.id
        ).first()
        
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        
        # Parse extracted info
        try:
            extracted_info = json.loads(resume.extracted_info) if resume.extracted_info else {}
            # Ensure correct types
            extracted_info = ensure_correct_types(extracted_info)
        except:
            extracted_info = {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown"
            }
        
        # Build profile classification
        profile_classification = {
            "profile_type": resume.profile_type,
            "primary_languages": resume.primary_languages.split(",") if resume.primary_languages else [],
            "frameworks": resume.frameworks.split(",") if resume.frameworks else [],
            "years_experience": resume.years_experience,
            "seniority": resume.seniority,
            "industry_focus": resume.industry_focus
        }
            
        return {
            "id": resume.id,
            "title": resume.title,
            "filename": resume.file_path,
            "content": resume.content,
            "is_active": resume.is_active,
            "extracted_info": extracted_info,
            "profile_classification": profile_classification
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading resume content: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))