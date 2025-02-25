# File: backend/app/llm/ollama_client.py
import os
import json
import httpx
from typing import Dict, Any, Optional

class OllamaClient:
    def __init__(self):
        self.base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.environ.get("OLLAMA_MODEL", "llama3:8b")
        
    async def _send_request(self, system_prompt: str, user_prompt: str) -> str:
        """Send a request to the Ollama API."""
        prompt = f"{system_prompt}\n\n{user_prompt}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                raise Exception(f"API request failed with status code {response.status_code}: {response.text}")
            
            return response.json().get("response", "")

    async def extract_company_info(self, job_description: str) -> Dict[str, Any]:
        """Extract company information from a job description."""
        system_prompt = """
        You are an AI specialized in analyzing job descriptions. Your task is to extract 
        key information about the company from the provided job description. Return the 
        information in a structured JSON format.
        """
        
        user_prompt = f"""
        Please analyze this job description and extract the following information in JSON format:
        - company_name: The name of the company
        - industry: The industry or sector of the company
        - company_size: Any indication of company size (startup, mid-size, enterprise, etc.)
        - company_culture: Keywords related to company culture or values (as a list)
        - technologies: Technologies or methodologies mentioned in the job description (as a list)
        - location: Company location or whether remote work is available
        - mission: Any mission statement or company goals mentioned

        Job Description:
        {job_description}

        Return ONLY valid JSON without any additional text or explanation.
        """
        
        response_text = await self._send_request(system_prompt, user_prompt)
        
        # Try to extract just the JSON part
        try:
            # First, check if the entire response is a valid JSON
            return json.loads(response_text)
        except json.JSONDecodeError:
            # If not, try to extract JSON from the text
            import re
            # Look for content between triple backticks or just find json-like structures
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Try to find anything that looks like JSON with curly braces
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
            
            # If all else fails, return a dummy response
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
        
        response_text = await self._send_request(system_prompt, user_prompt)
        return response_text.strip()