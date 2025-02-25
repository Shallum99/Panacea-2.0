# File: backend/app/llm/claude_client.py
import os
import json
import httpx
from typing import Dict, Any, Optional
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClaudeClient:
    def __init__(self):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        self.base_url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
        logger.info(f"Initialized ClaudeClient with model: {self.model}")
        
    async def _send_request(self, system_prompt: str, user_prompt: str) -> str:
        """Send a request to the Claude API."""
        logger.info(f"Sending request to Claude API with model: {self.model}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.base_url,
                    headers=self.headers,
                    json={
                        "model": self.model,
                        "system": system_prompt,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_prompt
                            }
                        ],
                        "max_tokens": 1024
                    },
                    timeout=60.0
                )
                
                if response.status_code != 200:
                    logger.error(f"API request failed with status code {response.status_code}: {response.text}")
                    raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
                
                result = response.json()
                content = result.get("content", [{}])[0].get("text", "")
                logger.info(f"Received response from Claude API (first 100 chars): {content[:100]}...")
                return content
        except Exception as e:
            logger.error(f"Error in Claude API request: {str(e)}")
            raise

    async def extract_company_info(self, job_description: str) -> Dict[str, Any]:
        """Extract company information from a job description."""
        system_prompt = """
        You are an AI specialized in analyzing job descriptions. Your task is to extract 
        key information about the company from the provided job description. You must return ONLY 
        a valid JSON object.
        """
        
        user_prompt = f"""
        Please analyze this job description and extract the following information:

        1. company_name: The name of the company
        2. industry: The industry or sector of the company
        3. company_size: Any indication of company size (startup, mid-size, enterprise, etc.)
        4. company_culture: Keywords related to company culture or values (as a list)
        5. technologies: Technologies or methodologies mentioned in the job description (as a list)
        6. location: Company location or whether remote work is available
        7. mission: Any mission statement or company goals mentioned

        If any information is not available, use an appropriate placeholder like "Unknown" for strings or empty lists.

        Job Description:
        {job_description}

        Return your answer as a valid JSON object with the fields above. No explanation, just the JSON object.
        """
        
        try:
            response_text = await self._send_request(system_prompt, user_prompt)
            
            # Try to parse the JSON response
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                # If direct parsing fails, try to extract JSON from the text
                import re
                json_pattern = r'({[\s\S]*})'
                match = re.search(json_pattern, response_text)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass
                
                # If still failing, return a default response
                logger.warning("Failed to parse JSON from Claude response")
                return {
                    "company_name": "Unknown",
                    "industry": "Unknown",
                    "company_size": "Unknown",
                    "company_culture": [],
                    "technologies": [],
                    "location": "Unknown",
                    "mission": "Unknown"
                }
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
        """Generate a personalized message based on resume, job description, and message type."""
        # Define character limits based on message type
        char_limits = {
            "linkedin": 300,
            "inmail": 2000,
            "email": 3000,
            "ycombinator": 500
        }
        
        limit = char_limits.get(message_type.lower(), 1000)
        
        system_prompt = """
        You are an expert job application assistant. Your task is to craft personalized, 
        professional outreach messages from job seekers to recruiters or hiring managers. 
        The message should highlight relevant skills from the resume that match the job description, 
        show interest in the company, and have an appropriate tone for the platform.
        """
        
        user_prompt = f"""
        Create a personalized {message_type} message from a job seeker to a recruiter based on:

        1. RESUME:
        {resume}

        2. JOB DESCRIPTION:
        {job_description}

        3. COMPANY INFO:
        {json.dumps(company_info, indent=2)}

        4. MESSAGE TYPE: {message_type}
        
        Requirements:
        - Keep the message under {limit} characters
        - Highlight 2-3 most relevant skills/experiences from the resume that match the job
        - Reference specific company information (culture, mission, or technologies)
        - Use an appropriate professional tone for the platform
        - Include a clear call to action
        - DO NOT use generic phrases like "I am writing to express my interest"

        Return ONLY the message text without any additional explanation or context.
        """
        
        try:
            response_text = await self._send_request(system_prompt, user_prompt)
            return response_text.strip()
        except Exception as e:
            logger.error(f"Error generating message: {str(e)}")
            return "I apologize, but I encountered an issue generating your message. Please try again or adjust your inputs."