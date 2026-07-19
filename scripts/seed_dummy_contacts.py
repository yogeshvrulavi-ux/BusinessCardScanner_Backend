"""One-off helper: seed dummy contacts through the running API to verify the UI.

Usage:  python scripts/seed_dummy_contacts.py [BASE_URL]
Defaults to http://localhost:5000 and the seeded SuperAdmin credentials.
"""

import json
import os
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
IDENTIFIER = os.getenv("SUPERADMIN_EMAIL", "superadmin@ulavi.com")
PASSWORD = os.getenv("SUPERADMIN_PASSWORD", "SuperAdmin@123")

DUMMY_CONTACTS = [
    {
        "fullName": "Varun Gupta",
        "firstName": "Varun",
        "lastName": "Gupta",
        "designation": "Director",
        "company": "Affinity Travels",
        "phone": "9818753062",
        "secondaryPhone": "8920070133",
        "email": "contact@affinitytravels.in",
        "secondaryEmail": "affinitytravels07@gmail.com",
        "website": "www.affinitytravels.in",
        "address": "16, Palika Palace, R.K. Ashram Metro Station, New Delhi-110001",
        "eventName": "Travel Expo 2026",
        "notes": "Dummy data seeded for UI testing.",
    },
    {
        "fullName": "Priya Sharma",
        "firstName": "Priya",
        "lastName": "Sharma",
        "designation": "Marketing Head",
        "company": "Bluewave Media",
        "phone": "9876543210",
        "email": "priya@bluewavemedia.in",
        "website": "www.bluewavemedia.in",
        "address": "Plot 42, Sector 18, Gurugram, Haryana-122015",
        "eventName": "Ad Summit Delhi",
        "notes": "Dummy data seeded for UI testing.",
    },
    {
        "fullName": "Rahul Verma",
        "firstName": "Rahul",
        "lastName": "Verma",
        "designation": "Founder & CEO",
        "company": "Verma Textiles Pvt Ltd",
        "phone": "9812345678",
        "email": "rahul@vermatextiles.com",
        "website": "www.vermatextiles.com",
        "address": "88, MG Road, Jaipur, Rajasthan-302001",
        "gstNumber": "08AABCV1234F1Z5",
        "eventName": "Textile Fair Jaipur",
        "notes": "Dummy data seeded for UI testing.",
    },
    {
        "fullName": "Anita Desai",
        "firstName": "Anita",
        "lastName": "Desai",
        "designation": "Senior Consultant",
        "company": "Pinnacle Advisors LLP",
        "phone": "9900112233",
        "email": "anita.desai@pinnacleadvisors.com",
        "website": "www.pinnacleadvisors.com",
        "address": "4th Floor, Trade Tower, Bandra Kurla Complex, Mumbai-400051",
        "eventName": "Finance Conclave",
        "notes": "Dummy data seeded for UI testing.",
    },
    {
        "fullName": "Mohammed Irfan",
        "firstName": "Mohammed",
        "lastName": "Irfan",
        "designation": "Sales Manager",
        "company": "TechnoSoft Solutions",
        "phone": "9765432109",
        "email": "irfan@technosoft.io",
        "website": "www.technosoft.io",
        "address": "Hitech City, Hyderabad, Telangana-500081",
        "eventName": "SaaS Meetup Hyderabad",
        "notes": "Dummy data seeded for UI testing.",
    },
]


def post_json(path: str, body: dict, token: str | None = None) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get_json(path: str, token: str) -> object:
    req = urllib.request.Request(
        f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    auth = post_json("/api/auth/login", {"identifier": IDENTIFIER, "password": PASSWORD})
    token = auth["access_token"]
    print(f"Logged in as {IDENTIFIER}")

    for contact in DUMMY_CONTACTS:
        body = {
            **contact,
            "connectionMode": "online",
            # Never fire real outreach for dummy rows.
            "skipWhatsApp": True,
            "skipEmail": True,
        }
        result = post_json("/api/contacts", body, token)
        print(f"  created: {contact['fullName']:<20} id={result.get('id')}")

    contacts = get_json("/api/contacts", token)
    total = len(contacts) if isinstance(contacts, list) else contacts
    print(f"Done. API now returns {total} contact(s).")


if __name__ == "__main__":
    main()
