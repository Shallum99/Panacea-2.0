# File: backend/app/llm/resume_extractor.py
import logging
from typing import Dict, Any

from app.llm.tiny_llama_client import TinyLlamaClient

logger = logging.getLogger(__name__)

class ResumeExtractor:
    """Extracts structured information from resumes using TinyLlama."""
    
    def __init__(self):
        self.llm_client = TinyLlamaClient()
    
    async def extract_resume_info(self, resume_content: str) -> Dict[str, Any]:
        """Extract key information from a resume."""
        try:
            # Create a simple prompt for TinyLlama to extract resume information
            prompt = f"""
Extract the following information from this resume:
1. Name
2. Email
3. Phone
4. Top skills (list format)
5. Years of experience
6. Education
7. Most recent job title
8. Most recent company

Resume:
{resume_content}

Format the response like:
Name: Name of the user
Email: Email of the user
Phone: Number of the user
Skills: Skills of the user
Experience: Experience of the user
Education: Education of the user
Recent Job: Recent job title
Recent Company: Recent company name
            """
            
            response = await self.llm_client._send_request(prompt)
            print(response, "<-----------this is the response")
            
            # Parse the response into a structured format
            result = {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown"
            }
            
            # Process line by line
            for line in response.split('\n'):
                line = line.strip()
                if not line or ':' not in line:
                    continue
                
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if key == 'name':
                    result["name"] = value
                elif key == 'email':
                    result["email"] = value
                elif key == 'phone':
                    result["phone"] = value
                elif key in ('skills', 'top skills'):
                    # Split skills by commas or similar separators
                    result["skills"] = [s.strip() for s in value.split(',')]
                elif key in ('experience', 'years of experience', 'years experience'):
                    result["years_experience"] = value
                elif key == 'education':
                    result["education"] = value
                elif key in ('recent job', 'most recent job', 'recent job title'):
                    result["recent_job"] = value
                elif key in ('recent company', 'most recent company'):
                    result["recent_company"] = value
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting resume info: {str(e)}")
            # Return default values if extraction fails
            return {
                "name": "Unknown",
                "email": "Unknown",
                "phone": "Unknown",
                "skills": [],
                "years_experience": "Unknown",
                "education": "Unknown",
                "recent_job": "Unknown",
                "recent_company": "Unknown"
            }