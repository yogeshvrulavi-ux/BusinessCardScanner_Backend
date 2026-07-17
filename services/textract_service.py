"""AWS Textract service for business card OCR (online mode).

Uses boto3 with credentials from environment variables (no hardcoded secrets).
Calls DetectDocumentText (LINES) and optionally enriches via AnalyzeDocument (FORMS).
"""
import logging
import os

logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")

_textract_client = None


def _get_textract_client():
    """Lazy-init the boto3 Textract client from env credentials."""
    global _textract_client
    if _textract_client is None:
        if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
            raise RuntimeError(
                "AWS credentials not configured. Set AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY in .env."
            )
        import boto3
        _textract_client = boto3.client(
            "textract",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        )
    return _textract_client


def is_textract_configured() -> bool:
    """Return True when AWS env vars are present."""
    return bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_REGION)


def extract_text(image_bytes: bytes) -> str:
    """Extract raw text from a card image via Textract DetectDocumentText.

    Returns newline-joined LINE blocks. Raises RuntimeError on auth,
    rate-limit, or network failures with typed error messages.
    """
    client = _get_textract_client()

    try:
        response = client.detect_document_text(
            Document={"Bytes": image_bytes}
        )
    except Exception as exc:
        _handle_textract_error(exc)
        # _handle_textract_error always raises, but keep linter happy
        raise

    blocks = response.get("Blocks", [])
    lines = [
        block.get("Text", "")
        for block in blocks
        if block.get("BlockType") == "LINE"
    ]
    raw_text = "\n".join(lines)
    logger.info("Textract extracted %d lines, %d chars.", len(lines), len(raw_text))

    # Optional enrichment: key-value pairs from FORMS analysis
    try:
        analyze_response = client.analyze_document(
            Document={"Bytes": image_bytes},
            FeatureTypes=["FORMS"],
        )
        kv_lines = []
        for block in analyze_response.get("Blocks", []):
            if block.get("BlockType") == "KEY_VALUE_SET":
                text = block.get("Text", "")
                if text:
                    kv_lines.append(text)
        if kv_lines:
            logger.info("Textract FORMS enrichment: %d key-value blocks.", len(kv_lines))
    except Exception as exc:
        logger.warning("Textract FORMS enrichment failed (non-fatal): %s", exc)

    return raw_text


def _handle_textract_error(exc: Exception) -> None:
    """Map boto3 ClientError codes to typed RuntimeErrors."""
    error_code = ""
    if hasattr(exc, "response"):
        error_code = exc.response.get("Error", {}).get("Code", "")

    if error_code in ("UnauthorizedOperation", "AccessDenied", "InvalidSignatureException"):
        logger.error("Textract auth error: %s", exc)
        raise RuntimeError(
            "AWS Textract authorization failed. Check IAM permissions for "
            "textract:DetectDocumentText."
        ) from exc

    if error_code in ("ProvisionedThroughputExceededException", "ThrottlingException") or "RateLimit" in error_code:
        logger.warning("Textract rate limited: %s", exc)
        raise RuntimeError(
            "AWS Textract rate limit exceeded. Please retry in a moment."
        ) from exc

    if error_code in ("InvalidParameterException", "InvalidS3ObjectException"):
        logger.error("Textract invalid input: %s", exc)
        raise RuntimeError(f"AWS Textract invalid input: {exc}") from exc

    # Network / unknown
    logger.error("Textract unexpected error: %s", exc)
    raise RuntimeError(f"Unexpected Textract error: {exc}") from exc
