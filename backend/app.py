"""
Campus Lost & Found - FastAPI backend.

    uvicorn app:app --reload --port 8000     (the first start downloads the models)

Reports, claims and owner alerts live in SQLite (lostfound.db) and photos in
./uploads. Every report is also kept in memory with its vectors, so matching is
just arithmetic and returns in milliseconds.
"""
from __future__ import annotations

import io
import os
import pickle
import re
import secrets
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

import db
import enrich
import llm
import notify
import verify
from matcher import CAMPUS_ZONES, CATEGORY_GROUPS, Encoder, Match, Report, best_question, rank

HERE = Path(__file__).parent
UPLOADS = db.DATA_DIR / "uploads"
UPLOADS.mkdir(exist_ok=True)

NOTIFY_AT = 0.75            # alert an owner once a found item reaches this confidence
SIMILAR_AT = 0.40           # softer "something similar was handed in" alert from here
AMBIGUOUS_BELOW = 0.75      # below this, Smart Claim asks the owner one question
MAX_CLAIM_ATTEMPTS = 2      # wrong answers before a claim is flagged for staff
MAX_ANSWERS = 3             # Smart Claim answers per lost report (stops guessing games)
MAX_PHOTO_BYTES = 10 * 1024 * 1024
KEPT_AT = ["Security desk", "Library front desk", "Department office", "With the finder"]
CODE_ALPHABET = "ACDEFHJKMNPRTUVWXY34679"   # no look-alikes such as 0/O or 1/I

state: dict = {"encoder": None, "tagger": None, "calibrator": None}
REPORTS: dict[str, Report] = {}
ANSWERS: Counter = Counter()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    state["encoder"] = Encoder(remove_background=os.getenv("REMOVE_BG") == "1")
    state["tagger"] = enrich.AutoTagger(state["encoder"])
    calibrator = HERE / "calibrator.pkl"          # written by: python evaluate.py --save-calibrator
    if calibrator.exists():
        state["calibrator"] = pickle.loads(calibrator.read_bytes())
    for r in db.load_reports():
        REPORTS[r.id] = r
    print(f"Ready with {len(REPORTS)} reports. LLM: {'on' if llm.available() else 'off, using rules'}. "
          f"Email: {'on' if notify.enabled() else 'off, printing to console'}.")
    yield


app = FastAPI(title="Campus Lost & Found", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")


# ============================================================================= helpers
def now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def redact(text: str) -> str:
    """Hide roll numbers, phone numbers and similar codes in anything shown publicly."""
    return re.sub(r"\b(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{4,}\b", "••••", text)


def public(r: Report) -> dict:
    """What anyone may see. Never includes contact, private details or the writing itself."""
    return {
        "id": r.id, "kind": r.kind, "description": redact(r.description),
        "category": r.category, "colors": r.colors, "brand": r.brand, "location": r.location,
        "time": r.time.isoformat(timespec="minutes") if r.time else None, "status": r.status,
        "photo_url": f"/uploads/{Path(r.image_path).name}" if r.image_path else None,
        "kept_at": r.kept_at, "has_writing": bool(r.text_on_item),
        "created_at": r.created_at.isoformat(timespec="minutes") if r.created_at else None,
    }


def get_report(rid: str, kind: str | None = None) -> Report:
    r = REPORTS.get(rid)
    if r is None or (kind and r.kind != kind):
        raise HTTPException(404, f"No {kind + ' ' if kind else ''}report has the id {rid}.")
    return r


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "Time must look like 2026-09-24T15:30.")
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t   # store local, naive


def read_photo(upload: UploadFile) -> Image.Image:
    data = upload.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "That photo is over 10 MB. Try a smaller one.")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "That file isn't a photo we can read. Use a JPG, PNG or WebP.")
    img.thumbnail((1280, 1280))
    return img


def match_json(m: Match) -> dict:
    return {"report": public(m.report), "similarity": round(m.similarity, 3),
            "confidence": round(m.confidence, 3), "band": m.band, "pros": m.pros, "cons": m.cons}


def matches_for(r: Report, top_k: int = 5) -> dict:
    if r.kind == "found":   # finders never see owners' reports; owners get alerted instead
        return {"matches": [], "question": None, "alerted": db.count_notifications(found_id=r.id)}
    pool = [x for x in REPORTS.values() if x.kind == "found"]
    ms = [m for m in rank(r, pool, top_k=top_k, calibrator=state["calibrator"])
          if m.confidence >= 0.01 or m.similarity >= 0.5]       # drop obvious non-matches
    question = None
    if (r.status == "open" and len(ms) >= 2 and ms[0].confidence < AMBIGUOUS_BELOW
            and ANSWERS[r.id] < MAX_ANSWERS):
        best = best_question(r, ms)
        if best:
            question = {"attribute": best[0], "text": best[1]}
    return {"matches": [match_json(m) for m in ms], "question": question}


def contradicts(f: dict) -> bool:
    """Both sides know it and it disagrees: no shared color, another brand, other writing."""
    return f.get("color") == 0 or (f.get("brand") is not None and f["brand"] <= 0.5) \
        or f.get("text_on_item") == 0


def alert_owners(found: Report) -> int:
    """Check a newly found item against every open lost report. Owners hear about likely
    matches, and about similar items (lower score, or a clear difference such as color)."""
    open_lost = [x for x in REPORTS.values() if x.kind == "lost" and x.status == "open"]
    alerted = 0
    for m in rank(found, open_lost, top_k=5, calibrator=state["calibrator"]):
        if m.confidence >= SIMILAR_AT:
            likely = m.confidence >= NOTIFY_AT and not contradicts(m.features)
            where = found.kept_at or "Security desk"
            place = ("the finder still has it" if where == "With the finder"
                     else f"it's at the {where.lower()}")
            item = notify.a_item(found)
            item = item[0].upper() + item[1:]
            db.add_notification(m.report.id, found.id, m.confidence,
                                f"{item} that may be yours was handed in, and {place}." if likely else
                                f"{item} similar to yours was handed in, and {place}. Take a look in case it's yours.")
            notify.match_found(m.report, found, m.confidence, place, likely)
            alerted += 1
    return alerted


def claim_json(c: dict) -> dict:
    found = REPORTS.get(c["found_id"])
    out = {"id": c["id"], "status": c["status"], "question": c["question"],
           "attempts": c["attempts"], "attempts_left": max(0, MAX_CLAIM_ATTEMPTS - c["attempts"]),
           "item": public(found) if found else None, "kept_at": found.kept_at if found else None,
           "lost_id": c["lost_id"]}
    if c["status"] == "approved":
        out["pickup_code"] = c["pickup_code"]
    return out


# ============================================================================= endpoints
@app.get("/api/meta")
def meta():
    """Everything the forms need: categories, colors, campus zones, drop-off points."""
    return {"categories": list(CATEGORY_GROUPS), "colors": enrich.BASIC_COLORS,
            "zones": list(CAMPUS_ZONES), "kept_at": KEPT_AT, "llm": llm.available()}


@app.post("/api/autotag")
def autotag(photo: UploadFile = File(...)):
    """Suggest category, colors and visible writing from a photo (fills the form in)."""
    img = read_photo(photo)
    tags = state["tagger"].tag(state["encoder"].embed_image(img))
    return {**tags, "writing": enrich.read_text(img)}


@app.post("/api/reports")
def create_report(
    kind: str = Form(...), description: str = Form(""), category: str = Form("other"),
    colors: str = Form(""), brand: str = Form(""), location: str = Form(""),
    time: str = Form(""), text_on_item: str = Form(""), secret_details: str = Form(""),
    kept_at: str = Form(""), contact: str = Form(""), photo: UploadFile | None = File(None),
):
    if kind not in ("lost", "found"):
        raise HTTPException(422, "kind must be 'lost' or 'found'.")
    has_photo = photo is not None and bool(photo.filename)
    if not description.strip() and not has_photo:
        raise HTTPException(422, "Add a description or a photo.")
    rid = new_id("L" if kind == "lost" else "F")
    r = Report(
        id=rid, kind=kind, description=description.strip(),
        category=category if category in CATEGORY_GROUPS else "other",
        colors=[c.strip().lower() for c in colors.split(",") if c.strip()],
        brand=brand.strip() or None, location=location if location in CAMPUS_ZONES else None,
        time=parse_time(time) or now(), text_on_item=text_on_item.strip() or None,
        secret_details=secret_details.strip() or None, kept_at=kept_at.strip() or None,
        contact=contact.strip() or None, created_at=now())
    image = None
    if has_photo:
        image = read_photo(photo)
        path = UPLOADS / f"{rid}.jpg"
        image.save(path, "JPEG", quality=85)
        r.image_path = str(path)
        state["encoder"].encode_photo(r, image)
    auto = enrich.enrich_report(r, state["tagger"], image)
    state["encoder"].encode([r])                  # text + caption vectors (photo is done)
    db.save_report(r)
    REPORTS[rid] = r
    alerted = alert_owners(r) if kind == "found" else 0
    return {"report": public(r), "auto_filled": auto, "alerted": alerted}


@app.get("/api/reports")
def list_reports(kind: str = "found", limit: int = 24):
    """Open reports of one kind. Only public() fields: no contact, secret or writing."""
    if kind not in ("lost", "found"):
        raise HTTPException(422, "kind must be 'lost' or 'found'.")
    items = [r for r in REPORTS.values() if r.kind == kind and r.status == "open"]
    items.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
    return [public(r) for r in items[:limit]]


@app.get("/api/reports/{rid}")
def read_report(rid: str):
    r = get_report(rid)
    return {"report": public(r), "alerts": db.notifications_for(rid) if r.kind == "lost" else []}


@app.get("/api/reports/{rid}/matches")
def read_matches(rid: str, top_k: int = 5):
    return matches_for(get_report(rid), top_k)


class AnswerIn(BaseModel):
    attribute: str
    answer: str


@app.post("/api/reports/{rid}/answer")
def answer_question(rid: str, body: AnswerIn):
    """Smart Claim part 1: the owner answers one question and the matches re-rank."""
    r = get_report(rid, "lost")
    if body.attribute not in ("color", "brand", "text_on_item", "location"):
        raise HTTPException(422, "That isn't one of the questions we ask.")
    if ANSWERS[rid] >= MAX_ANSWERS:
        raise HTTPException(429, "That's the most questions we can ask for one report. "
                                 "Pick the item that looks most like yours.")
    value = enrich.parse_answer(body.attribute, body.answer)
    if value is None:
        raise HTTPException(422, "We couldn't find an answer in that. Try again in a few words.")
    ANSWERS[rid] += 1
    if body.attribute == "color":
        r.colors = value
    else:
        setattr(r, body.attribute, value)
    state["encoder"].encode([r])                  # refresh the caption with the new detail
    db.save_report(r)
    return matches_for(r)


class ClaimIn(BaseModel):
    found_id: str
    lost_id: str | None = None


@app.post("/api/claims")
def start_claim(body: ClaimIn):
    """Smart Claim part 2: start an ownership check for a found item."""
    found = get_report(body.found_id, "found")
    if found.status != "open":
        raise HTTPException(409, "Someone has already claimed this item.")
    if body.lost_id:
        get_report(body.lost_id, "lost")
    stamp = now().isoformat(timespec="minutes")
    c = {"id": new_id("C"), "lost_id": body.lost_id, "found_id": found.id,
         "question": verify.make_question(found.secret_details, found.category)
         if found.secret_details else None,
         "attempts": 0, "status": "pending" if found.secret_details else "needs_staff",
         "pickup_code": None, "created_at": stamp, "updated_at": stamp}
    db.save_claim(c)
    return claim_json(c)


@app.get("/api/claims/{cid}")
def read_claim(cid: str):
    c = db.get_claim(cid)
    if not c:
        raise HTTPException(404, f"No claim has the id {cid}.")
    return claim_json(c)


class VerifyIn(BaseModel):
    answer: str


@app.post("/api/claims/{cid}/verify")
def verify_claim(cid: str, body: VerifyIn):
    c = db.get_claim(cid)
    if not c:
        raise HTTPException(404, f"No claim has the id {cid}.")
    if c["status"] != "pending":
        return claim_json(c)
    found = get_report(c["found_id"], "found")
    if found.status != "open":
        raise HTTPException(409, "Someone has already claimed this item.")
    passed, _method = verify.check_answer(body.answer, found.secret_details or "",
                                          state["encoder"].text_similarity)
    c["attempts"] += 1
    if passed:
        c["status"] = "approved"
        c["pickup_code"] = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        for rid in (found.id, c["lost_id"]):
            if rid in REPORTS:
                REPORTS[rid].status = "claimed"
                db.save_report(REPORTS[rid])
        notify.claim_approved(REPORTS.get(c["lost_id"]), found, c["pickup_code"])
        notify.owner_verified(found)
    elif c["attempts"] >= MAX_CLAIM_ATTEMPTS:
        c["status"] = "flagged"                   # a person at the desk takes over
    c["updated_at"] = now().isoformat(timespec="minutes")
    db.save_claim(c)
    return claim_json(c)


@app.post("/api/pickups/{code}")
def confirm_pickup(code: str):
    """The desk enters the owner's pickup code when handing the item over."""
    c = db.claim_by_code(code.strip().upper())
    if not c:
        raise HTTPException(404, "No approved claim has that pickup code.")
    found = REPORTS.get(c["found_id"])
    if c["status"] != "returned":
        c["status"], c["updated_at"] = "returned", now().isoformat(timespec="minutes")
        db.save_claim(c)
        for rid in (c["found_id"], c["lost_id"]):
            if rid in REPORTS:
                REPORTS[rid].status = "returned"
                db.save_report(REPORTS[rid])
        if found:
            notify.item_returned(found)
    return {"status": "returned", "item": public(found) if found else None}


@app.get("/api/admin/stats")
def stats():
    """Numbers for the desk dashboard. Add a login before real use."""
    rs = list(REPORTS.values())
    claims = db.list_claims(50)
    return {
        "counts": {
            "lost_open": sum(r.kind == "lost" and r.status == "open" for r in rs),
            "found_open": sum(r.kind == "found" and r.status == "open" for r in rs),
            "claimed": sum(r.kind == "found" and r.status == "claimed" for r in rs),
            "returned": sum(r.kind == "found" and r.status == "returned" for r in rs),
            "flagged": sum(c["status"] == "flagged" for c in claims),
            "alerts": db.count_notifications(),
        },
        "hotspots": Counter(r.location for r in rs if r.kind == "lost" and r.location).most_common(8),
        "categories": Counter(r.category for r in rs).most_common(8),
        "claims": [{"id": c["id"], "status": c["status"], "attempts": c["attempts"],
                    "created_at": c["created_at"],
                    "item": public(REPORTS[c["found_id"]]) if c["found_id"] in REPORTS else None}
                   for c in claims[:15]],
    }


# Production: serve the built frontend (npm run build) from this server, so the
# whole app is one URL. Must stay last: it answers every path the API doesn't.
DIST = HERE.parent / "frontend" / "dist"
if (DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found.")
        file = (DIST / path).resolve()
        if path and file.is_file() and file.is_relative_to(DIST.resolve()):
            return FileResponse(file)
        return FileResponse(DIST / "index.html")   # React Router handles /lost, /reports/... etc.
