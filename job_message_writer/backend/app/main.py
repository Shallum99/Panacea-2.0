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

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

# Configure CORS with settings
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