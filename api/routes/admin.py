import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth_context import get_request_app_user
from api.schemas import WipeAllDataBody
from auth.constants import ROLE_ADMIN, ROLE_SUPER_ADMIN
from auth.dependencies import require_role
from services import contact_storage as storage
from services.contact_service import delete_all_contacts
from services.zoho_service import ZohoError, soft_delete_all_leads_for_user

router = APIRouter(tags=["Admin"])
logger = logging.getLogger(__name__)


@router.post(
    "/admin/wipe-all-data",
    summary="Wipe all data (Admin/SuperAdmin only)",
    description="Soft-deletes all local contacts and optionally all Zoho leads. Requires ADMIN or SUPER_ADMIN role.",
)
def wipe_all_data(
    body: WipeAllDataBody,
    request: Request,
    _user: dict = Depends(require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)),
):
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
