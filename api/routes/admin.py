import logging

from fastapi import APIRouter, HTTPException, Request

from api.auth_context import get_request_app_user
from api.schemas import WipeAllDataBody
from services import contact_storage as storage
from services.contact_service import delete_all_contacts
from services.zoho_service import ZohoError, soft_delete_all_leads_for_user

router = APIRouter(tags=["Admin"])
logger = logging.getLogger(__name__)


@router.post("/admin/wipe-all-data")
async def wipe_all_data(body: WipeAllDataBody, request: Request):
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true in the request body to wipe local database and related data.",
        )

    app_user = get_request_app_user(request)
    result = {
        "contacts": delete_all_contacts(),
        "storage": storage.storage_label(),
        "zoho": None,
        "scoped_to_user": bool(app_user),
    }
    if body.include_zoho:
        try:
            result["zoho"] = soft_delete_all_leads_for_user(app_user)
        except ZohoError as exc:
            logger.warning("Zoho soft-delete wipe skipped or partial: %s", exc)
            result["zoho"] = {"soft_deleted": 0, "error": str(exc)}

    return {"success": True, **result}
