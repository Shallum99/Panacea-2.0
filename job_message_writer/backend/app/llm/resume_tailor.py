# File: backend/app/llm/resume_tailor.py
import re
import logging
from typing import Dict, List, Any
import json

from app.llm.claude_client import ClaudeClient
from app.schemas.resume_tailor import ResumeSection

logger = logging.getLogger(__name__)

async def extract_resume_sections(resume_content):
    try:
        # Make the text search friendly
        resume_lines = resume_content.split('\n')
        resume_for_search = '\n'.join(line.strip() for line in resume_lines if line.strip())
        
        # First, identify where each section begins
        section_starts = {}
        section_names = {
            ResumeSection.SKILLS: ['SKILLS', 'TECHNICAL SKILLS', 'CORE COMPETENCIES'],
            ResumeSection.PROJECTS: ['PROJECTS', 'PROJECTS - (LIVE)', 'PROJECT EXPERIENCE', 'TECHNICAL PROJECTS'],
            ResumeSection.EXPERIENCE: ['EXPERIENCE', 'WORK EXPERIENCE', 'PROFESSIONAL EXPERIENCE', 'EMPLOYMENT HISTORY']
        }
        
        lines = resume_for_search.split('\n')
        for i, line in enumerate(lines):
            for section_type, headers in section_names.items():
                for header in headers:
                    if line.startswith(header):
                        section_starts[section_type] = i
                        break
        
        # Sort the sections by their position in the document
        sorted_sections = sorted(section_starts.items(), key=lambda x: x[1])
        
        # Extract content between sections
        sections = {}
        for i, (section_type, start_line) in enumerate(sorted_sections):
            start_idx = start_line + 1  # Start from the line after the heading
            
            # Find the end of this section (start of next section or end of document)
            if i < len(sorted_sections) - 1:
                end_idx = sorted_sections[i+1][1]
            else:
                end_idx = len(lines)
                
            # Extract and join the content
            content = '\n'.join(lines[start_idx:end_idx])
            sections[section_type] = content.strip()
        
        # Add empty values for any missing sections
        for section_type in [ResumeSection.SKILLS, ResumeSection.PROJECTS, ResumeSection.EXPERIENCE]:
            if section_type not in sections:
                sections[section_type] = ""
        
        # If we couldn't extract any sections, try the LLM approach
        if all(not content for content in sections.values()):
            sections = await extract_sections_with_llm(resume_content)
            
        return sections
    
    except Exception as e:
        logger.error(f"Error extracting resume sections: {str(e)}")
        return {
            ResumeSection.SKILLS: "",
            ResumeSection.PROJECTS: "",
            ResumeSection.EXPERIENCE: ""
        }


async def extract_sections_with_llm(resume_content: str) -> Dict[str, str]:
    """
    Use Claude to extract sections when regex fails.
    """
    try:
        client = ClaudeClient()
        
        system_prompt = """
        You are an expert at parsing resumes. Your task is to extract specific sections from a resume.
        """
        
        user_prompt = f"""
        Extract the following sections from this resume:
        1. Skills section (technical skills, core competencies, etc.)
        2. Projects section (project experience, technical projects, etc.)
        3. Experience section (work experience, professional experience, etc.)

        Format your response as a valid JSON object with these keys: "skills", "projects", "experience".
        Each value should be the complete text of that section.

        Resume:
        {resume_content}
        """
        
        response = await client._send_request(system_prompt, user_prompt)
        
        # Try to parse JSON response
        try:
            extracted = json.loads(response)
            sections = {
                ResumeSection.SKILLS: extracted.get("skills", ""),
                ResumeSection.PROJECTS: extracted.get("projects", ""),
                ResumeSection.EXPERIENCE: extracted.get("experience", "")
            }
            return sections
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract sections from the text response
            logger.warning("Failed to parse JSON response from Claude, falling back to regex extraction")
            skills_match = re.search(r'"skills":\s*"(.*?)"(?=,|\})', response, re.DOTALL)
            projects_match = re.search(r'"projects":\s*"(.*?)"(?=,|\})', response, re.DOTALL)
            experience_match = re.search(r'"experience":\s*"(.*?)"(?=,|\})', response, re.DOTALL)
            
            return {
                ResumeSection.SKILLS: skills_match.group(1).strip() if skills_match else "",
                ResumeSection.PROJECTS: projects_match.group(1).strip() if projects_match else "",
                ResumeSection.EXPERIENCE: experience_match.group(1).strip() if experience_match else ""
            }
    
    except Exception as e:
        logger.error(f"Error using LLM to extract resume sections: {str(e)}")
        return {
            ResumeSection.SKILLS: "",
            ResumeSection.PROJECTS: "",
            ResumeSection.EXPERIENCE: ""
        }


async def optimize_skills(skills: str, job_description: str) -> str:
    """
    Optimize skills section based on job description.
    """
    try:
        client = ClaudeClient()
        
        system_prompt = """
        You are an expert ATS optimization consultant. Your task is to optimize a resume skills section 
        to better match a job description for ATS systems.
        """
        
        user_prompt = f"""
        I need to optimize my skills section to better match this job description for ATS systems.

        JOB DESCRIPTION:
        {job_description}

        MY CURRENT SKILLS SECTION:
        {skills}

        Please optimize my skills section for ATS by:
        1. Keeping all my legitimate skills (don't invent skills I don't have)
        2. Reorganizing skills to prioritize those mentioned in the job description
        3. Reformatting if necessary for better ATS readability
        4. Using exact terminology from the job description where applicable
        5. Ensuring the skills are presented clearly with appropriate categorization if needed

        Only return the optimized skills section, with NO explanations or additional text.
        """
        
        response = await client._send_request(system_prompt, user_prompt)
        return response.strip()
    
    except Exception as e:
        logger.error(f"Error optimizing skills section: {str(e)}")
        return skills


async def optimize_projects(projects: str, job_description: str) -> str:
    """
    Optimize projects section based on job description.
    """
    try:
        client = ClaudeClient()
        
        system_prompt = """
        You are an expert ATS optimization consultant. Your task is to optimize a resume projects section 
        to better match a job description for ATS systems.
        """
        
        user_prompt = f"""
        I need to optimize my projects section to better match this job description for ATS systems.

        JOB DESCRIPTION:
        {job_description}

        MY CURRENT PROJECTS SECTION:
        {projects}

        Please optimize my projects section for ATS by:
        1. Keeping all my legitimate projects (don't invent projects I haven't done)
        2. Emphasizing technologies and skills mentioned in the job description
        3. If I've used alternative technologies that serve the same purpose as those in the job description, you may update the technology stack while keeping the project description accurate
        4. Rephrasing achievements to use keywords from the job description
        5. Ensuring bullet points follow the accomplishment-oriented format (action verb + task + result)
        6. Using exact terminology from the job description where applicable

        Only return the optimized projects section, with NO explanations or additional text.
        """
        
        response = await client._send_request(system_prompt, user_prompt)
        return response.strip()
    
    except Exception as e:
        logger.error(f"Error optimizing projects section: {str(e)}")
        return projects


async def optimize_experience(experience: str, job_description: str) -> str:
    """
    Optimize experience section based on job description.
    """
    try:
        client = ClaudeClient()
        
        system_prompt = """
        You are an expert ATS optimization consultant. Your task is to optimize a resume experience section 
        to better match a job description for ATS systems.
        """
        
        user_prompt = f"""
        I need to optimize my professional experience section to better match this job description for ATS systems.

        JOB DESCRIPTION:
        {job_description}

        MY CURRENT EXPERIENCE SECTION:
        {experience}

        Please optimize my experience section for ATS by:
        1. Keeping all my legitimate work history (don't invent positions or companies)
        2. Highlighting responsibilities that align with the job description
        3. Rephrasing achievements to use keywords from the job description
        4. If I've used alternative technologies that serve the same purpose as those in the job description, you may update the technology mentions while keeping the experience accurate
        5. Ensuring bullet points follow the accomplishment-oriented format (action verb + task + result)
        6. Using exact terminology from the job description where applicable
        7. Maintaining chronological order and date format

        Only return the optimized experience section, with NO explanations or additional text.
        """
        
        response = await client._send_request(system_prompt, user_prompt)
        return response.strip()
    
    except Exception as e:
        logger.error(f"Error optimizing experience section: {str(e)}")
        return experience


async def optimize_section(section_type: ResumeSection, content: str, job_description: str) -> str:
    """
    Optimize a specific resume section based on job description.
    """
    if section_type == ResumeSection.SKILLS:
        return await optimize_skills(content, job_description)
    elif section_type == ResumeSection.PROJECTS:
        return await optimize_projects(content, job_description)
    elif section_type == ResumeSection.EXPERIENCE:
        return await optimize_experience(content, job_description)
    else:
        logger.warning(f"Unknown section type: {section_type}")
        return content