# File: backend/app/llm/tiny_llama_client.py
import os
import json
import httpx
from typing import Dict, Any, Optional, List
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TinyLlamaClient:
    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "tinyllama")
        logger.info(f"Initialized TinyLlamaClient with model: {self.model}")
        
    async def _send_request(self, prompt: str) -> str:
        """Send a request to the Ollama API with a single prompt."""
        logger.info(f"Sending request to Ollama API with model: {self.model}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=120.0
                )
                

                print(response, "this is the respinseeeeee")
                if response.status_code != 200:
                    logger.error(f"API request failed with status code {response.status_code}: {response.text}")
                    raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
                
                result = response.json().get("response", "")
                logger.info(f"Received response from Ollama API (first 100 chars): {result[:100]}...")
                return result
        except Exception as e:
            logger.error(f"Error in Ollama API request: {str(e)}")
            raise

    async def extract_company_info(self, job_description: str) -> Dict[str, Any]:
        """Extract company information from a job description - simplified for TinyLlama."""
        # Simplify the prompt for TinyLlama
        prompt = f"""
Job Description: {job_description}

From the job description above, extract the following information:
1. Company name
2. Industry
3. Company size (startup, mid-size, enterprise, etc.)
4. Main technologies mentioned
5. Location
6. Company mission or goals

Format your response like this example:
Company name: Google
Industry: Technology
Company size: Large enterprise
Technologies: Python, JavaScript, Cloud
Location: Mountain View, CA (Remote available)
Mission: Organize the world's information
        """
        
        try:
            response_text = await self._send_request(prompt)

            logger.info("Processing TinyLlama response")
            
            # Initialize result dictionary
            result = {
                "company_name": "Unknown",
                "industry": "Unknown",
                "company_size": "Unknown",
                "company_culture": [],
                "technologies": [],
                "location": "Unknown",
                "mission": "Unknown"
            }
            
            # Extract information using simple patterns
            company_match = re.search(r"[Cc]ompany(?:\s+)[Nn]ame:?\s*(.+)", response_text)
            if company_match:
                result["company_name"] = company_match.group(1).strip()
                
            industry_match = re.search(r"[Ii]ndustry:?\s*(.+)", response_text)
            if industry_match:
                result["industry"] = industry_match.group(1).strip()
                
            size_match = re.search(r"[Cc]ompany(?:\s+)[Ss]ize:?\s*(.+)", response_text)
            if size_match:
                result["company_size"] = size_match.group(1).strip()
                
            tech_match = re.search(r"[Tt]echnologies?:?\s*(.+)", response_text)
            if tech_match:
                techs = tech_match.group(1).strip()
                # Split by commas, or other common separators
                result["technologies"] = [t.strip() for t in re.split(r'[,;/]', techs)]
                
            location_match = re.search(r"[Ll]ocation:?\s*(.+)", response_text)
            if location_match:
                result["location"] = location_match.group(1).strip()
                
            mission_match = re.search(r"[Mm]ission:?\s*(.+)", response_text)
            if mission_match:
                result["mission"] = mission_match.group(1).strip()
            
            # Ensure we're returning a dictionary, not a list
            logger.info(f"Extracted company info: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting company info: {str(e)}")
            return {
                "company_name": "Unknown",
                "industry": "Unknown",
                "company_size": "Unknown",
                "company_culture": [],
                "technologies": [],
                "location": "Unknown",
                "mission": "Unknown"
            }

    async def generate_message(
        self, 
        resume: str, 
        job_description: str,
        company_info: Dict[str, Any],
        message_type: str
    ) -> str:
        """Generate a personalized message - simplified for TinyLlama."""
        # Define character limits based on message type
        char_limits = {
            "linkedin": 300,
            "inmail": 2000,
            "email": 3000,
            "ycombinator": 500
        }
        
        limit = char_limits.get(message_type.lower(), 1000)
        
        # Extract key resume points to avoid context length issues
        resume_summary = self._extract_resume_highlights(resume)
        
        # Simplify the prompt
        prompt = f"""
Write a short {message_type} message from a job applicant to a recruiter.

KEY INFO:
- Job is at {company_info['company_name']} in {company_info['industry']}
- Company works with: {', '.join(company_info['technologies']) if company_info['technologies'] else 'technology'}
- Applicant skills: {resume_summary}
- Message type: {message_type}
- Keep under {limit} characters
- Be professional but friendly
- Include a clear call to action

Write ONLY the message:
        """
        
        try:
            response_text = await self._send_request(prompt)
            # Clean up any formatting or extra text
            message = response_text.strip()
            
            # Enforce character limit
            if len(message) > limit:
                message = message[:limit]
                
            return message
        except Exception as e:
            logger.error(f"Error generating message: {str(e)}")
            return "I apologize, but I encountered an issue generating your message. Please try again or adjust your inputs."
    
    def _extract_resume_highlights(self, resume: str) -> str:
        """Extract key highlights from resume to reduce context length."""
        # Simple approach: take first 200 chars, focus on skills/experience
        highlights = resume[:200]
        
        # Try to extract skills
        skills_match = re.search(r"[Ss]kills:?\s*(.+)", resume)
        if skills_match:
            skills = skills_match.group(1)[:100]
            highlights += f" Skills: {skills}"
            
        # Try to extract experience
        exp_match = re.search(r"[Ee]xperience:?\s*(.+)", resume)
        if exp_match:
            experience = exp_match.group(1)[:100]
            highlights += f" Experience: {experience}"
            
        return highlights[:300]  # Limit to 300 chars total