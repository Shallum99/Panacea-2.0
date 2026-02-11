# File: backend/app/db/models.py
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text, DateTime, Float, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.database import Base


class ApplicationStatus(str, enum.Enum):
    DRAFT = "draft"
    MESSAGE_GENERATED = "message_generated"
    APPROVED = "approved"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    REPLIED = "replied"
    FAILED = "failed"


class ApplicationMethod(str, enum.Enum):
    MANUAL = "manual"
    EMAIL = "email"
    AUTO_APPLY_URL = "auto_apply_url"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    supabase_id = Column(String, unique=True, index=True, nullable=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=True)  # No longer needed with Supabase auth
    is_active = Column(Boolean, default=True)
    gmail_refresh_token = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    resumes = relationship("Resume", back_populates="owner")
    job_descriptions = relationship("JobDescription", back_populates="owner")
    messages = relationship("Message", back_populates="owner")
    applications = relationship("Application", back_populates="owner")


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
    applications = relationship("Application", back_populates="resume")


class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)
    job_description_id = Column(Integer, ForeignKey("job_descriptions.id"), nullable=True)

    # Application details
    status = Column(String, default=ApplicationStatus.DRAFT.value, index=True)
    method = Column(String, default=ApplicationMethod.MANUAL.value)

    # Target info
    company_name = Column(String, nullable=True)
    position_title = Column(String, nullable=True)
    recipient_email = Column(String, nullable=True)
    recipient_name = Column(String, nullable=True)
    job_url = Column(String, nullable=True)

    # Generated content
    message_type = Column(String, nullable=True)
    generated_message = Column(Text, nullable=True)
    edited_message = Column(Text, nullable=True)
    final_message = Column(Text, nullable=True)

    # Email tracking
    email_message_id = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)

    # ATS scores
    ats_score_before = Column(Float, nullable=True)
    ats_score_after = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="applications")
    resume = relationship("Resume", back_populates="applications")
    job_description = relationship("JobDescription")