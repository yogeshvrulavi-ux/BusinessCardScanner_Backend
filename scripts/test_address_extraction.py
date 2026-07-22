"""Verify address extraction against the sample business cards."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from utils.parser_utils import parse_business_card  # noqa: E402

SAMPLES = {
    "Olivia Alleppey": (
        """
OLIVIA
ALLEPPEY
Saravana Kumar
Vice President
+91 7736696888
vp@oliviaalleppey.com
Olivia Alleppey
Nehru Trophy Boat Race View
Finishing Point
Punnamada Alappuzha
www.oliviaalleppey.com
""",
        ["Punnamada Alappuzha", "Finishing Point", "Nehru Trophy"],
    ),
    "DMD Holidays": (
        """
DMD HOLIDAYS
A Dream For Your Magical Destination
Shaiju Rajendran
+91 8089216592
0484 2998239
+91 9072445253
info@dmdholidays.com
19/ 526 B, Pynadathu, Millupady, Poickattussery,
Chengamanad PO, Ernakulam - 683578
www.dmdholidays.com
""",
        ["Poickattussery", "Ernakulam", "683578"],
    ),
    "Adventure Tour (no address)": (
        """
Sanjay Kumar
ADVENTURE TOUR
Exploring Destination, Creating Memories
Spiti Tour
Leh Ladakh Jeep Tour
Mountain Trekking Tour
Student Tour
Female Tour
spitlehadventuretour@gmail.com
8544778313, 9816594513
9816678813, 8988428813
www.spitlehadventuretour.com
Your Journey, Our Passion
""",
        [],
    ),
    "Skyline India Travels": (
        """
Skyline India Travels
Since 1994
Madhavi
Manager-Domestic Tour
+91 6307576816
Skyline India Travels Pvt. Ltd.
+91 542 2508554/55/56/57
cmd@skylines.co.in
pradeep.rai@skylines.co.in
www.skylines.co.in
B-2/12, 1st Floor, Mint House Colony,
Nadesar, Varanasi, Pin-221002, (U.P.) India
Varanasi | Prayagraj | Ayodhya
""",
        ["Mint House Colony", "Varanasi", "221002"],
    ),
    "HRT Vacations": (
        """
ODISHA DMC
HRT VACATIONS PVT. LTD.
A Wholesale Tour Operator of Odisha
Rudra Narayan Senapati
Sales Manager
Mob. : 9827841117
8093012304
Plot - 1215/1400, Khandagiri Bari, Khandagiri, Bhubaneswar-751030
E-mail : hrtvacationspvtltd@gmail.com
www.hrtvacations.com
""",
        ["Plot", "Khandagiri", "751030"],
    ),
    "Seven Hills Hotels": (
        """
SEVEN HILLS HOTELS
Arun Kumar Sahoo
Sales - Manager
www.sevenhillshotels.in
Plot no.: 351
Sipasurubli Mouza, Baliapanda
Puri-752001, Odisha, India
+91 9124624248
smbbsr@sevenhillshotels.in
""",
        ["Plot no", "Baliapanda", "752001"],
    ),
    "Patra Travels": (
        """
PATRA TRAVELS PVT LTD
Recognized by Ministry of Tourism, Govt. of India & Odisha Tourism, Govt. of Odisha
DMC OF ODISHA
BALARAM PATRA | DIRECTOR
Mobile: (+91) 83379-11110
24X7 Support No. : 83379-11111
Email ID: b2b@patratravels.com
Address: Plot No. 1151, Tankapani Road,
Bhubaneswar, Odisha -751018
""",
        ["1151", "Tankapani", "751018"],
    ),
}


def main() -> int:
    failed = 0
    for name, (text, must_contain) in SAMPLES.items():
        result = parse_business_card(text)
        address = (result.get("address") or "").strip()
        print("=" * 60)
        print(name)
        print(address or "(empty)")
        if not must_contain:
            if address:
                print("FAIL: expected empty address")
                failed += 1
            else:
                print("OK")
            continue
        missing = [token for token in must_contain if token.lower() not in address.lower()]
        if missing:
            print(f"FAIL: missing {missing}")
            failed += 1
        else:
            print("OK")
    print("=" * 60)
    print(f"Failures: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
