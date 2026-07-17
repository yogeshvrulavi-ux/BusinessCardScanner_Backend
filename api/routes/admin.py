import logging

from fastapi import APIRouter, Depends, HTTPException

from api.schemas import WipeAllDataBody
from auth.constants import ROLE_ADMIN, ROLE_SUPER_ADMIN
from auth.dependencies import require_role
from services import contact_storage as storage
from services.contact_service import delete_all_contacts

router = APIRouter(tags=["Admin"])
logger = logging.getLogger(__name__)


@router.post(
    "/admin/wipe-all-data",
    summary="Wipe all data (Admin/SuperAdmin only)",
    description="Soft-deletes all local PostgreSQL contacts. Requires ADMIN or SUPER_ADMIN role.",
)
def wipe_all_data(
    body: WipeAllDataBody,
    _user: dict = Depends(require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)),
):
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true in the request body to wipe local database contacts.",
        )

    result = {
        "contacts": delete_all_contacts(),
        "storage": storage.storage_label(),
    }
    return {"success": True, **result}
