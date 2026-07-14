import logging

from fastapi import APIRouter, HTTPException, Request

from api.auth_context import (
    app_user_filter_kwargs,
    get_request_app_user,
    get_request_app_user_for_sync,
    get_scanner_email_from_request,
)

from api.outreach import (
    email_response,
    payload_to_outreach_contact,
    run_post_zoho_outreach,
    whatsapp_response,
)
from api.schemas import CreateLeadRequest, SyncFromLocalRequest, ZohoLeadSummary
from services import local_db_service as local_db
from services.contact_service import _contact_to_zoho_payload, sync_payload_to_zoho
from services.local_db_service import LocalDbError
from services.zoho_service import (
    ZohoError,
    create_lead,
    format_zoho_error_message,
    get_leads,
    soft_delete_lead,
)

router = APIRouter(prefix="/api/leads", tags=["Leads"])
logger = logging.getLogger(__name__)


@router.post(
    "/sync-from-local",
    summary="Sync extracted contact to Zoho CRM",
    description=(
        "Primary save path from the Review page. Accepts browser-OCR fields plus "
        "`eventName` and user-written `notes` (stored together in Zoho Features / Description)."
    ),
)
async def sync_from_local_route(body: SyncFromLocalRequest, request: Request):
    try:
        payload = body.model_dump(exclude_none=True)
        result = sync_payload_to_zoho(
            payload,
            app_user=get_request_app_user_for_sync(request),
        )
        if result.get("success"):
            outreach_contact = payload_to_outreach_contact(body.model_dump())
            whatsapp_result, email_result = await run_post_zoho_outreach(
                contact=outreach_contact,
                skip_whatsapp=body.skipWhatsApp,
                skip_email=body.skipEmail,
                log_context="sync-from-local",
                scanner_email=get_scanner_email_from_request(request),
            )
            result.update(whatsapp_response(whatsapp_result))
            result.update(
                email_response(
                    email_result,
                    fallback_extracted=str(outreach_contact.get("email") or ""),
                )
            )
            if body.skipEmail:
                result["email_skipped"] = True
        return result
    except ZohoError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=format_zoho_error_message(exc),
        ) from exc
    except Exception as exc:
        logger.error("Local contact Zoho sync failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/create",
    summary="Create Zoho lead (direct)",
    description="Creates a lead in Zoho CRM. Prefer `/sync-from-local` from the frontend Review page.",
)
async def create_lead_route(body: CreateLeadRequest, request: Request):
    zoho_lead = _contact_to_zoho_payload(
        body.model_dump(),
        app_user=get_request_app_user_for_sync(request),
    )
    try:
        zoho_response = create_lead(zoho_lead)
        first = (zoho_response.get("data") or [{}])[0]
        return {
            "success": True,
            "message": "Lead created successfully in Zoho CRM.",
            "lead": {
                "id": (first.get("details") or {}).get("id"),
                "status": first.get("status", "unknown"),
                "code": first.get("code"),
            },
            "zoho": zoho_response,
        }
    except ZohoError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get(
    "",
    response_model=list[ZohoLeadSummary],
    summary="List Zoho CRM leads",
    description="Returns leads with `eventName` and `notes` parsed from the Zoho Features (Description) field.",
)
async def list_leads_route(request: Request):
    try:
        return get_leads(**app_user_filter_kwargs(request))
    except ZohoError as exc:
        logger.warning("Zoho leads fetch failed (%s): %s", exc.status_code, exc)
        raise HTTPException(
            status_code=exc.status_code if exc.status_code >= 400 else 502,
            detail=format_zoho_error_message(exc),
        ) from exc


@router.delete("/{lead_id}")
async def delete_lead_route(lead_id: str, request: Request):
    if not lead_id.strip():
        raise HTTPException(status_code=400, detail="Lead id is required.")
    try:
        app_user = get_request_app_user(request)
        result = soft_delete_lead(lead_id.strip(), app_user)
        try:
            local_db.delete_contact_by_zoho_lead_id(lead_id.strip())
        except LocalDbError as exc:
            logger.warning(
                "Zoho lead %s soft-deleted but local DB cleanup failed: %s",
                lead_id.strip(),
                exc,
            )
        return {
            "success": True,
            "message": "Lead marked as deleted in Zoho CRM.",
            **result,
        }
    except ZohoError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
