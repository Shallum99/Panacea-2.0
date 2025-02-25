# File: backend/app/llm/claude_resume_extractor.py
import logging
import json
from typing import Dict, Any

from app.llm.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

class ClaudeResumeExtractor:
    """Extracts structured information from resumes using Claude."""
    
    def __init__(self):
        self.claude_client = ClaudeClient()
    
    async def extract_resume_info(self, resume_content: str) -> Dict[str, Any]:
        """Extract key information from a resume."""
        try:
            system_prompt = """
            You are an expert resume analyzer. Your task is to extract structured information from a resume.
            Return the results as a valid JSON object with no additional text.
            """
            
            user_prompt = f"""
            Extract the following information from this resume:
            1. name: Full name of the person (string)
            2. email: Email address (string)
            3. phone: Phone number (string)
            4. skills: List of skills mentioned (array of strings)
            5. years_experience: Total years of experience (string, not number)
            6. education: Highest education qualification (string)
            7. recent_job: Most recent job title (string)
            8. recent_company: Most recent company name (string)

            Make sure all fields are returned as the correct type. Specifically, "years_experience" must be a string (e.g., "7 years"), not a number.

            If any information is not available in the resume, use "Unknown" for strings or empty arrays.

            Resume:
            {resume_content}

            Return ONLY a valid JSON object with the fields above. No explanation, just the JSON.
            """
            
            response = await self.claude_client._send_request(system_prompt, user_prompt)
            
            # Parse the response into a structured format
            try:
                result = json.loads(response)
                logger.info("Successfully parsed resume information from Claude response")
                
                # Ensure years_experience is a string
                if "years_experience" in result and not isinstance(result["years_experience"], str):
                    result["years_experience"] = str(result["years_experience"]) + " years"
                
                # Ensure other fields have correct types
                for field in ["name", "email", "phone", "education", "recent_job", "recent_company"]:
                    if field in result and not isinstance(result[field], str):
                        result[field] = str(result[field])
                
                if "skills" in result and not isinstance(result["skills"], list):
                    if isinstance(result["skills"], str):
                        result["skills"] = [skill.strip() for skill in result["skills"].split(",")]
                    else:
                        result["skills"] = [str(result["skills"])]
                
                return result
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON from Claude response, trying to extract JSON")
                # Try to extract JSON from the text
                import re
                json_pattern = r'({[\s\S]*})'
                match = re.search(json_pattern, response)
                if match:
                    try:
                        result = json.loads(match.group(1))
                        # Apply the same type conversions
                        if "years_experience" in result and not isinstance(result["years_experience"], str):
                            result["years_experience"] = str(result["years_experience"]) + " years"
                        
                        for field in ["name", "email", "phone", "education", "recent_job", "recent_company"]:
                            if field in result and not isinstance(result[field], str):
                                result[field] = str(result[field])
                        
                        if "skills" in result and not isinstance(result["skills"], list):
                            if isinstance(result["skills"], str):
                                result["skills"] = [skill.strip() for skill in result["skills"].split(",")]
                            else:
                                result["skills"] = [str(result["skills"])]
                                
                        return result
                    except json.JSONDecodeError:
                        pass
                
                # If all extraction attempts fail, create a default response
                logger.warning("Falling back to default resume info values")
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