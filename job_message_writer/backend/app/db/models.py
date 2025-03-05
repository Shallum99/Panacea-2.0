# File: backend/app/db/models.py
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    resumes = relationship("Resume", back_populates="owner")
    job_descriptions = relationship("JobDescription", back_populates="owner")
    messages = relationship("Message", back_populates="owner")

class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    file_path = Column(String, nullable=True)  # Path to resume file in S3
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="resumes")

class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    company_info = Column(Text, nullable=True)  # JSON string of extracted company info
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="job_descriptions")
    messages = relationship("Message", back_populates="job_description")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text)
    message_type = Column(String)  # "linkedin", "inmail", "email", "ycombinator"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    job_description_id = Column(Integer, ForeignKey("job_descriptions.id"))
    resume_id = Column(Integer, ForeignKey("resumes.id"))
    
    owner = relationship("User", back_populates="messages")
    job_description = relationship("JobDescription", back_populates="messages")
    resume = relationship("Resume")


# Modify this part in backend/app/db/models.py

class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True)
    title = Column(String)  # This will be the profile name (e.g., "My Backend Resume", "My Frontend Resume")
    content = Column(Text)
    file_path = Column(String, nullable=True)  # Path to resume file in S3
    
    # Profile type information
    profile_type = Column(String, nullable=True)  # "Frontend", "Backend", "Full Stack", etc.
    
    # Basic extracted information
    extracted_info = Column(Text, nullable=True)  # JSON string of extracted resume info
    name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    skills = Column(Text, nullable=True)  # Comma-separated list of skills
    years_experience = Column(String, nullable=True)
    education = Column(String, nullable=True)
    recent_job = Column(String, nullable=True)
    recent_company = Column(String, nullable=True)
    
    # Additional profile details
    primary_languages = Column(Text, nullable=True)  # Comma-separated list
    frameworks = Column(Text, nullable=True)  # Comma-separated list
    seniority = Column(String, nullable=True)
    industry_focus = Column(String, nullable=True)
    
    # Is this the user's active profile?
    is_active = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    owner_id = Column(Integer, ForeignKey("users.id"))
    
    owner = relationship("User", back_populates="resumes")
