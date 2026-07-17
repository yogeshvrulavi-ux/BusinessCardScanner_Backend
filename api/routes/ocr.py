"""POST /api/ocr — online OCR via AWS Textract.

Accepts a multipart image upload, calls Textract to extract text, then
parses with the existing parse_business_card parser. Returns the
structured contact data for the frontend Review/edit screen.
"""
import logging

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from auth.dependencies import get_current_user
from services.textract_service import extract_text, is_textract_configured
from utils.parser_utils import parse_business_card

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["OCR"])


@router.post(
    "/ocr",
    summary="Extract contact data from a business card image",
    description=(
        "Upload a card image. AWS Textract extracts raw text, then the "
        "parser structures it into name, company, email, phone, website, "
        "address, etc. Use this when the device is online; offline falls "
        "back to browser-based PaddleOCR."
    ),
)
async def ocr_card(
    request: Request,
    file: UploadFile = File(..., description="Business card image (PNG/JPEG)."),
):
    # Enforce authentication (raises 401 if not logged in)
    get_current_user(request)

    if not is_textract_configured():
        raise HTTPException(
            status_code=503,
            detail="AWS Textract is not configured on the backend.",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image upload.")

    # Validate content type loosely
    content_type = (file.content_type or "").lower()
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(
            status_code=415,
            detail=f"Expected an image file, got '{content_type}'.",
        )

    try:
        raw_text = extract_text(image_bytes)
    except RuntimeError as exc:
        logger.error("OCR failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    contact = parse_business_card(raw_text)

    return {
        "engine": "textract",
        "rawText": raw_text,
        "contact": contact,
    }
