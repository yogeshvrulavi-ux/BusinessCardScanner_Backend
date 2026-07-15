"""Analytics / Insights endpoint — aggregate contact statistics from PostgreSQL."""
import logging
from typing import Any

from fastapi import APIRouter, Depends
from psycopg2.extras import RealDictCursor

from auth.dependencies import get_current_user, require_role
from auth.constants import ROLE_ADMIN, ROLE_SUPER_ADMIN
from services.local_db_service import _connect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics"])


@router.get("/api/analytics/summary")
async def get_analytics_summary(
    user: dict = Depends(require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)),
):
    """Return aggregated contact stats: total, synced, pending, failed, by company."""
    try:
        with _connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total contacts (filtered by RBAC)
                where_clause = "WHERE (c.is_deleted = FALSE OR c.is_deleted IS NULL)"
                params: list[Any] = []

                role = user.get("role", "")
                company_id = user.get("company_id")
                user_id = user.get("id")

                if role == "USER" and user_id:
                    where_clause += " AND c.created_by_user_id = %s"
                    params.append(user_id)
                elif role == "ADMIN" and company_id:
                    where_clause += " AND u.company_id = %s"
                    params.append(company_id)

                # Overall counts
                cur.execute(f"""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE c."syncStatus" = 'synced_zoho' OR c."zohoLeadId" IS NOT NULL) AS synced,
                        COUNT(*) FILTER (WHERE c."syncStatus" = 'failed') AS failed,
                        COUNT(*) FILTER (WHERE c."syncStatus" != 'synced_zoho' AND c."zohoLeadId" IS NULL AND c."syncStatus" != 'failed') AS pending
                    FROM contacts c
                    LEFT JOIN users u ON c.created_by_user_id = u.id
                    {where_clause}
                """, params)
                totals = dict(cur.fetchone())

                # Contacts per company
                cur.execute(f"""
                    SELECT
                        COALESCE(comp.company_name, 'Unassigned') AS company_name,
                        COUNT(*) AS count
                    FROM contacts c
                    LEFT JOIN users u ON c.created_by_user_id = u.id
                    LEFT JOIN companies comp ON u.company_id = comp.id
                    {where_clause}
                    GROUP BY comp.company_name
                    ORDER BY count DESC
                    LIMIT 20
                """, params)
                by_company = [dict(row) for row in cur.fetchall()]

                # Contacts per user (top 20)
                cur.execute(f"""
                    SELECT
                        COALESCE(u.first_name || ' ' || u.last_name, 'Unknown') AS user_name,
                        COALESCE(comp.company_name, 'Unassigned') AS company_name,
                        COUNT(*) AS count
                    FROM contacts c
                    LEFT JOIN users u ON c.created_by_user_id = u.id
                    LEFT JOIN companies comp ON u.company_id = comp.id
                    {where_clause}
                    GROUP BY u.first_name, u.last_name, comp.company_name
                    ORDER BY count DESC
                    LIMIT 20
                """, params)
                by_user = [dict(row) for row in cur.fetchall()]

                # Recent activity (last 7 days)
                cur.execute(f"""
                    SELECT
                        DATE(c."createdAt") AS date,
                        COUNT(*) AS count
                    FROM contacts c
                    LEFT JOIN users u ON c.created_by_user_id = u.id
                    {where_clause}
                      AND c."createdAt" >= NOW() - INTERVAL '7 days'
                    GROUP BY DATE(c."createdAt")
                    ORDER BY date ASC
                """, params)
                recent_activity = [
                    {"date": str(row["date"]), "count": int(row["count"])}
                    for row in cur.fetchall()
                ]

        return {
            "total": int(totals.get("total") or 0),
            "synced": int(totals.get("synced") or 0),
            "pending": int(totals.get("pending") or 0),
            "failed": int(totals.get("failed") or 0),
            "by_company": by_company,
            "by_user": by_user,
            "recent_activity": recent_activity,
        }
    except Exception as exc:
        logger.error("Analytics summary failed: %s", exc, exc_info=True)
        return {
            "total": 0,
            "synced": 0,
            "pending": 0,
            "failed": 0,
            "by_company": [],
            "by_user": [],
            "recent_activity": [],
            "error": str(exc),
        }
