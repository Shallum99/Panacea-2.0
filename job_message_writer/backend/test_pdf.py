# File: backend/test_pdf.py
import asyncio
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the extract_text_from_pdf function
sys.path.append('.')  # Add current directory to path
from app.utils.pdf_extractor import extract_text_from_pdf

async def test_pdf_extraction(file_path):
    """Test PDF extraction on a file."""
    try:
        logger.info(f"Reading file: {file_path}")
        with open(file_path, 'rb') as f:
            pdf_content = f.read()
        
        logger.info("Extracting text...")
        text = await extract_text_from_pdf(pdf_content)
        
        if text and len(text) > 0:
            logger.info(f"Successfully extracted {len(text)} characters")
            # Print first 500 characters
            logger.info(f"First 500 characters:\n{text[:500]}...")
            return True
        else:
            logger.error("No text extracted or text is empty")
            return False
    except Exception as e:
        logger.error(f"Error testing PDF extraction: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_pdf.py <pdf_file_path>")
        sys.exit(1)
    
    pdf_file = sys.argv[1]
    result = asyncio.run(test_pdf_extraction(pdf_file))
    
    if result:
        print("\nPDF extraction test successful!")
        sys.exit(0)
    else:
        print("\nPDF extraction test failed!")
        sys.exit(1)