"""Tests for user-scoped Zoho soft delete."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from services.zoho_service import (
    apply_soft_delete_meta_to_zoho_payload,
    lead_is_soft_deleted,
    soft_delete_lead,
)


class TestSoftDeleteMetadata(unittest.TestCase):
    def test_lead_is_soft_deleted(self) -> None:
        lead = {"Description": "Event: Expo\nDeleted: true\nDeletedAt: 2026-01-01T00:00:00Z"}
        self.assertTrue(lead_is_soft_deleted(lead))

    def test_active_lead_not_soft_deleted(self) -> None:
        lead = {"Description": "Event: Expo\nCapturedBy: user@example.com"}
        self.assertFalse(lead_is_soft_deleted(lead))

    def test_apply_soft_delete_meta(self) -> None:
        payload = {"Description": "Event: Expo\nCapturedBy: user@example.com"}
        apply_soft_delete_meta_to_zoho_payload(
            payload,
            {"email": "user@example.com", "id": "user-1"},
        )
        self.assertIn("Deleted: true", payload["Description"])
        self.assertIn("DeletedBy: user@example.com", payload["Description"])


class TestSoftDeleteOwnership(unittest.TestCase):
    @patch("services.auth_service.is_auth_enabled", return_value=True)
    @patch("services.zoho_service.update_lead")
    @patch("services.zoho_service._fetch_lead_description")
    def test_denies_cross_user_delete(
        self,
        fetch_desc: unittest.mock.MagicMock,
        _update: unittest.mock.MagicMock,
        _auth: unittest.mock.MagicMock,
    ) -> None:
        fetch_desc.return_value = "Event: Expo\nCapturedBy: user-a@example.com"
        with self.assertRaises(Exception) as ctx:
            soft_delete_lead(
                "lead-1",
                {"email": "user-b@example.com", "id": "b"},
            )
        self.assertIn("403", str(ctx.exception.status_code))

    @patch("services.auth_service.is_auth_enabled", return_value=True)
    @patch("services.zoho_service.update_lead")
    @patch("services.zoho_service._fetch_lead_description")
    def test_allows_owner_delete(
        self,
        fetch_desc: unittest.mock.MagicMock,
        update: unittest.mock.MagicMock,
        _auth: unittest.mock.MagicMock,
    ) -> None:
        fetch_desc.return_value = "Event: Expo\nCapturedBy: user-a@example.com"
        result = soft_delete_lead(
            "lead-1",
            {"email": "user-a@example.com", "id": "a"},
        )
        self.assertTrue(result["soft_deleted"])
        update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
