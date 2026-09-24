"""
Fill the app with demo reports through the real API (start the server first):

    python seed.py                        # or: python seed.py http://localhost:8000

Lost reports go in first, so the found items that follow trigger owner alerts.
To attach photos, put them in seed_photos/ named after the keys below (F1.jpg...).
For the real demo, photograph items your team actually owns.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
PHOTOS = Path(__file__).parent / "seed_photos"
NOW = datetime.now().replace(second=0, microsecond=0)


def ago(hours: float) -> str:
    return (NOW - timedelta(hours=hours)).isoformat(timespec="minutes")


LOST = {  # owners write a lot and rarely have a photo
    "L1": dict(description="Lost my navy blue Milton steel bottle with a mountain sticker. "
                           "Last had it in the library around lunch.",
               category="bottle", colors="navy", brand="Milton", location="library",
               time=ago(4), contact="owner.one@example.edu"),
    "L2": dict(description="Lost my college ID card this morning. Name Priya Sharma, "
                           "roll number 21CS045.",
               category="id_card", time=ago(10), contact="priya@example.edu"),
    "L3": dict(description="Lost my black phone charger with a long cable around lunch time, "
                           "not sure where.",
               category="charger", colors="black", time=ago(7), contact="arjun@example.edu"),
}

FOUND = {  # finders write little; private details are never shown
    "F1": dict(description="Blue metal water bottle left on a reading table, has a sticker",
               category="bottle", colors="blue", location="library", time=ago(3.3),
               kept_at="Library front desk", secret_details="small dent near the base"),
    "F2": dict(description="Black plastic water bottle near the canteen counter",
               category="bottle", colors="black", location="canteen", time=ago(2.5),
               kept_at="Security desk", secret_details="half full of lemon juice"),
    "F3": dict(description="Black charger, found on a table in the canteen", category="charger",
               colors="black", location="canteen", time=ago(5), kept_at="Security desk",
               text_on_item="Arjun", secret_details="name written on the plug in silver marker"),
    "F4": dict(description="Black charger and cable left plugged in, classroom 204",
               category="charger", colors="black", location="main_block", time=ago(5.5),
               kept_at="Department office", text_on_item="CSE LAB 3",
               secret_details="lab asset sticker on the brick"),
    "F5": dict(description="Student ID card lying near the bike stand", category="id_card",
               location="parking", time=ago(9), kept_at="Security desk",
               text_on_item="Priya Sharma 21CS045", secret_details="green college fest lanyard"),
    "F6": dict(description="White Samsung charger with a frayed cable", category="charger",
               colors="white", brand="Samsung", location="canteen", time=ago(4.5),
               kept_at="Security desk", secret_details="tape wrapped around the frayed part"),
    "F7": dict(description="Grey hoodie left on a seat after the event", category="clothing",
               colors="gray", location="auditorium", time=ago(20), kept_at="Security desk",
               secret_details="bus pass in the front pocket"),
    "F8": dict(description="White wireless earbuds case", category="earphones", colors="white",
               location="library", time=ago(6), kept_at="Library front desk",
               secret_details="one earbud is missing from the case"),
}


def post(kind: str, key: str, fields: dict) -> dict:
    photo = next(iter(sorted(PHOTOS.glob(f"{key}.*"))), None) if PHOTOS.exists() else None
    files = {"photo": (photo.name, photo.read_bytes())} if photo else None
    r = httpx.post(f"{API}/api/reports", data={"kind": kind, **fields}, files=files, timeout=120)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    ids = {}
    for key, fields in LOST.items():
        ids[key] = post("lost", key, fields)["report"]["id"]
    for key, fields in FOUND.items():
        res = post("found", key, fields)
        ids[key] = res["report"]["id"]
        if res["alerted"]:
            print(f"{key} alerted {res['alerted']} owner(s)")
    print("\nSeeded:", ", ".join(f"{k}={v}" for k, v in ids.items()))
    print("\nTry these in the app (npm run dev):")
    print(f"  Bottle match:     http://localhost:5173/reports/{ids['L1']}")
    print(f"  Smart Claim demo: http://localhost:5173/reports/{ids['L3']}")
    print("  Right answer to the question: my name ARJUN is on the plug")
    print("  Right answer to the ownership check: my name is written on the plug in silver marker")
