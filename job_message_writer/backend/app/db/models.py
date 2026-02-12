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
    tier = Column(String, default="free", server_default="free", nullable=False)
    custom_message_limit = Column(Integer, nullable=True)
    custom_tailor_limit = Column(Integer, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Profile: Personal Details
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    portfolio_url = Column(String, nullable=True)

    # Profile: Professional Summary
    professional_summary = Column(Text, nullable=True)

    # Profile: Master Skills (comma-separated)
    master_skills = Column(Text, nullable=True)

    # Profile: Job Preferences
    target_roles = Column(Text, nullable=True)
    target_industries = Column(Text, nullable=True)
    target_locations = Column(Text, nullable=True)
    work_arrangement = Column(String, nullable=True)
    salary_range_min = Column(Integer, nullable=True)
    salary_range_max = Column(Integer, nullable=True)

    # Profile: Tone Settings
    tone_formality = Column(String, default="balanced", server_default="balanced")
    tone_confidence = Column(String, default="confident", server_default="confident")
    tone_verbosity = Column(String, default="concise", server_default="concise")

    resumes = relationship("Resume", back_populates="owner")
    job_descriptions = relationship("JobDescription", back_populates="owner")
    messages = relationship("Message", back_populates="owner")
    applications = relationship("Application", back_populates="owner")
    writing_samples = relationship("WritingSample", back_populates="user")


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    content = Column(Text)
    company_info = Column(Text, nullable=True)  # JSON string of extracted company info
    url = Column(String, nullable=True)
    source = Column(String, nullable=True)  # "manual", "url", "greenhouse", "lever"
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
    subject = Column(String, nullable=True)
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


class UsageLog(Base):
    __tablename__ = "usage_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action_type = Column(String, nullable=False)  # "message_generation" or "resume_tailor"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


class WritingSample(Base):
    __tablename__ = "writing_samples"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    sample_type = Column(String, nullable=True)  # email/linkedin/cover_letter/other
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="writing_samples")


class ChatConversation(Base):
    __tablename__ = "chat_conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user", "assistant", "tool_use", "tool_result"
    content = Column(Text, nullable=False)  # plain text or JSON string for tool messages
    tool_name = Column(String, nullable=True)
    tool_call_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("ChatConversation", back_populates="messages")