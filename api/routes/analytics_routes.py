"""Analytics / Insights endpoint — aggregate contact statistics from PostgreSQL."""
import logging
from typing import Any

from fastapi import APIRouter, Depends

from auth.constants import ROLE_SUPER_ADMIN
from auth.dependencies import require_role
from db.pool import db_cursor

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics"])


@router.get("/api/analytics/summary")
async def get_analytics_summary(
    user: dict = Depends(require_role(ROLE_SUPER_ADMIN)),
):
    """Return system-wide contact, user, company, and event analytics."""
    try:
        where_clause = "WHERE (c.is_deleted = FALSE OR c.is_deleted IS NULL)"
        params: list[Any] = []

        with db_cursor(commit=False) as cur:
            cur.execute(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE c."syncStatus" = 'synced') AS synced,
                    COUNT(*) FILTER (WHERE c."syncStatus" = 'failed') AS failed,
                    COUNT(*) FILTER (
                        WHERE COALESCE(c."syncStatus", 'synced') NOT IN ('synced', 'failed')
                    ) AS pending
                FROM contacts c
                LEFT JOIN users u ON c.created_by_user_id = u.id
                {where_clause}
            """, params)
            totals = dict(cur.fetchone())

            cur.execute(f"""
                SELECT
                    COALESCE(comp.company_name, 'Unassigned') AS company_name,
                    COUNT(*) AS count
                FROM contacts c
                LEFT JOIN users u ON c.created_by_user_id = u.id
                LEFT JOIN companies comp
                    ON comp.id = COALESCE(c.owner_company_id, u.company_id)
                {where_clause}
                GROUP BY comp.company_name
                ORDER BY count DESC
            """, params)
            by_company = [dict(row) for row in cur.fetchall()]

            cur.execute(f"""
                SELECT
                    u.id::text AS user_id,
                    COALESCE(
                        NULLIF(BTRIM(CONCAT_WS(' ', u.first_name, u.last_name)), ''),
                        u.username,
                        u.email,
                        'Unknown'
                    ) AS user_name,
                    COALESCE(u.username, '') AS username,
                    COALESCE(u.email, '') AS email,
                    COALESCE(r.name, c.created_by_role, 'Unknown') AS role,
                    COALESCE(comp.company_name, 'Unassigned') AS company_name,
                    COALESCE(
                        NULLIF(BTRIM(CONCAT_WS(' ', admin_u.first_name, admin_u.last_name)), ''),
                        admin_u.username,
                        admin_u.email,
                        ''
                    ) AS admin_name,
                    COUNT(*) AS count,
                    COUNT(DISTINCT NULLIF(LOWER(BTRIM(c."eventName")), '')) AS event_count
                FROM contacts c
                LEFT JOIN users u ON c.created_by_user_id = u.id
                LEFT JOIN roles r ON u.role_id = r.id
                LEFT JOIN companies comp
                    ON comp.id = COALESCE(c.owner_company_id, u.company_id)
                LEFT JOIN users admin_u
                    ON admin_u.id = COALESCE(u.admin_id, comp.admin_id)
                {where_clause}
                GROUP BY
                    u.id, u.first_name, u.last_name, u.username, u.email,
                    r.name, c.created_by_role, comp.company_name,
                    admin_u.first_name, admin_u.last_name,
                    admin_u.username, admin_u.email
                ORDER BY count DESC
            """, params)
            by_user = [dict(row) for row in cur.fetchall()]

            cur.execute(f"""
                SELECT
                    MIN(NULLIF(c."eventId", '')) AS event_id,
                    MIN(BTRIM(c."eventName")) AS event_name,
                    COALESCE(comp.company_name, 'Unassigned') AS company_name,
                    COALESCE(
                        NULLIF(BTRIM(CONCAT_WS(' ', admin_u.first_name, admin_u.last_name)), ''),
                        admin_u.username,
                        admin_u.email,
                        ''
                    ) AS admin_name,
                    COUNT(*) AS contact_count,
                    COUNT(DISTINCT c.created_by_user_id) AS user_count,
                    COUNT(*) FILTER (WHERE c."syncStatus" = 'synced') AS synced,
                    COUNT(*) FILTER (WHERE c."syncStatus" = 'failed') AS failed,
                    COUNT(*) FILTER (
                        WHERE COALESCE(c."syncStatus", 'synced') NOT IN ('synced', 'failed')
                    ) AS pending,
                    STRING_AGG(
                        DISTINCT COALESCE(
                            NULLIF(BTRIM(CONCAT_WS(' ', u.first_name, u.last_name)), ''),
                            u.username,
                            u.email,
                            'Unknown'
                        ),
                        ', '
                    ) AS contributors,
                    MIN(c."createdAt") AS first_capture,
                    MAX(c."createdAt") AS last_capture
                FROM contacts c
                LEFT JOIN users u ON c.created_by_user_id = u.id
                LEFT JOIN companies comp
                    ON comp.id = COALESCE(c.owner_company_id, u.company_id)
                LEFT JOIN users admin_u ON admin_u.id = comp.admin_id
                {where_clause}
                  AND NULLIF(BTRIM(c."eventName"), '') IS NOT NULL
                GROUP BY
                    LOWER(BTRIM(c."eventName")),
                    comp.id, comp.company_name,
                    admin_u.first_name, admin_u.last_name,
                    admin_u.username, admin_u.email
                ORDER BY last_capture DESC
            """, params)
            by_event = [dict(row) for row in cur.fetchall()]

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
            "by_event": by_event,
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
            "by_event": [],
            "recent_activity": [],
            "error": str(exc),
        }
