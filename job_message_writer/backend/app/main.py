# File: backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.api.api import api_router
from app.db.database import engine
from app.db import models

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database more safely
def init_db():
    try:
        # Create tables without indexes
        logger.info("Creating database tables if they don't exist...")
        # Create tables one by one with error handling
        for table in models.Base.metadata.sorted_tables:
            try:
                if not engine.dialect.has_table(engine.connect(), table.name):
                    logger.info(f"Creating table: {table.name}")
                    table.create(engine, checkfirst=True)
                else:
                    logger.info(f"Table {table.name} already exists.")
            except Exception as e:
                logger.error(f"Error creating table {table.name}: {e}")
                
        logger.info("Database initialization completed.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

# Initialize database
init_db()

# Add missing columns to existing tables (safe to re-run)
def migrate_db():
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS gmail_refresh_token VARCHAR"
            ))
            conn.execute(text(
                "ALTER TABLE applications ADD COLUMN IF NOT EXISTS subject VARCHAR"
            ))
            # Rate limiting: tier + custom limits on users
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS tier VARCHAR NOT NULL DEFAULT 'free'"
            ))
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_message_limit INTEGER"
            ))
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS custom_tailor_limit INTEGER"
            ))
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR"
            ))
            # Usage log table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usage_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    action_type VARCHAR NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_usage_log_user_id ON usage_log (user_id)"
            ))
            # Profile: Personal Details
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS linkedin_url VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS portfolio_url VARCHAR"))
            # Profile: Professional Summary
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS professional_summary TEXT"))
            # Profile: Master Skills
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS master_skills TEXT"))
            # Profile: Job Preferences
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS target_roles TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS target_industries TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS target_locations TEXT"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS work_arrangement VARCHAR"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS salary_range_min INTEGER"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS salary_range_max INTEGER"))
            # Profile: Tone Settings
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tone_formality VARCHAR DEFAULT 'balanced'"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tone_confidence VARCHAR DEFAULT 'confident'"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS tone_verbosity VARCHAR DEFAULT 'concise'"))
            # Writing Samples table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS writing_samples (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    title VARCHAR,
                    content TEXT NOT NULL,
                    sample_type VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_writing_samples_user_id ON writing_samples (user_id)"
            ))
            # Job descriptions: url + source
            conn.execute(text("ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS url VARCHAR"))
            conn.execute(text("ALTER TABLE job_descriptions ADD COLUMN IF NOT EXISTS source VARCHAR"))
            # Chat tables
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    title VARCHAR DEFAULT 'New Chat',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_chat_conversations_user_id ON chat_conversations (user_id)"
            ))
            conn.execute(text(
                "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS application_id INTEGER REFERENCES applications(id)"
            ))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                    role VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    tool_name VARCHAR,
                    tool_call_id VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_chat_messages_conversation_id ON chat_messages (conversation_id)"
            ))
            # Resume editor: form_map column
            conn.execute(text("ALTER TABLE resumes ADD COLUMN IF NOT EXISTS form_map TEXT"))
            # Resume versions table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS resume_versions (
                    id SERIAL PRIMARY KEY,
                    resume_id INTEGER NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL DEFAULT 1,
                    file_path VARCHAR,
                    storage_path VARCHAR,
                    content TEXT,
                    change_summary VARCHAR,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_resume_versions_resume_id ON resume_versions (resume_id)"
            ))
            conn.commit()
            logger.info("DB migration: all columns + tables ensured")
    except Exception as e:
        logger.warning(f"DB migration skipped: {e}")

migrate_db()

# Ensure Supabase Storage buckets exist
try:
    from app.services.storage import ensure_buckets_exist
    ensure_buckets_exist()
except Exception as e:
    logger.warning(f"Supabase Storage init skipped: {e}")

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

# Configure CORS with settings
logger.info(f"CORS_ORIGINS = {settings.CORS_ORIGINS}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router)

@app.get("/")
def read_root():
    return {"status": "Job Message Writer API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)