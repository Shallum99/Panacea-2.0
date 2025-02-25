# File: backend/app/utils/pdf_extractor.py
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def extract_text_from_pdf(pdf_content: bytes) -> Optional[str]:
    """Extract text content from a PDF file."""
    try:
        # Try using pdfplumber first
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                full_text = ""
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n\n"
                
                logger.info(f"Successfully extracted {len(full_text)} characters from PDF using pdfplumber")
                return full_text
        except ImportError:
            logger.warning("pdfplumber not installed, trying fallback methods")
        
            
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return None