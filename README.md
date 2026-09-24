---
title: Campus Lost & Found
emoji: 🎒
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 7860
---

# Campus Lost & Found

Matches lost-item reports with found-item reports using descriptions **and photos**, ranks the candidates with a confidence score, explains every match, and adds **Smart Claim**: one well-chosen question when several items look alike, then a private-detail check before anyone can collect an item.

- **Backend:** FastAPI, SQLite, sentence-transformers (MiniLM for text, CLIP for photos and text-to-photo)
- **Frontend:** React and Vite, no UI framework

```
lost report ─┐                                ┌─> ranked matches + reasons ─> Smart Claim question (if ambiguous)
             ├─> enrich ─> embed ─> filter ─> score (8 signals) ─> fuse ─> confidence
found report ┘   (rules/LLM,  (MiniLM,  (category,   text, photo, text-to-photo,        └─> owner alerts (found items)
                  CLIP tags,   CLIP)     time)       color, brand, writing, place, time)
                  OCR)
claim ─> open question from the finder's private detail ─> judge the answer ─> pickup code ─> desk hands it over
```

## Quick start

You need Python 3.10+ and Node.js 20.19+ (or 22.12+).

**1. Backend** (first start downloads about 700 MB of models, so do it before the venue Wi-Fi gets busy):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install torch --index-url https://download.pytorch.org/whl/cpu   # small CPU build; skip on macOS
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

**2. Demo data**, in a second terminal while the API runs:

```bash
cd backend && python seed.py
```

This prints links for the demo and the right answers to type.

**3. Frontend:**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (it proxies /api to port 8000)
```

To start over, stop the API and delete `backend/lostfound.db` and `backend/uploads/`.

## The 3-minute demo

1. **Finder.** Go to *I found something*, add a photo, and watch the category and colors fill in. Add a private detail and save. Anyone with a matching lost report is alerted.
2. **Owner, clear case.** Open the bottle link printed by `seed.py`. The top result is stamped *Likely yours* and lists its reasons. One of them, "the finder's photo fits the owner's description", is text-to-photo matching; the owner had no photo.
3. **Owner, ambiguous case.** Open the charger link. Two black chargers sit near 50% each, so Smart Claim asks what's written on the item. Answer `my name ARJUN is on the plug` and the right charger jumps to about 96%.
4. **Claim.** Press *This is mine*. A vague answer fails. `my name is written on the plug in silver marker` passes and shows a pickup code.
5. **Desk.** Enter the code on the *Desk* page to hand the item over.
6. **Proof.** Run `python evaluate.py eval_sample.csv` and show the ablation table on your last slide.

## How matching works

Each (lost, found) pair gets up to eight signals, each on a 0–1 scale. A signal is skipped when there's no evidence for it, rather than counted as a zero.

| Signal | How it's computed |
|---|---|
| Text | MiniLM cosine similarity between the two descriptions |
| Photo | CLIP cosine similarity when both sides have a photo |
| Text-to-photo | CLIP similarity between the owner's caption and the finder's photo, or the reverse |
| Color | Overlap of normalized colors (navy counts as blue). Needed because text embeddings are nearly color-blind |
| Brand | Fuzzy string match |
| Writing on the item | OCR or typed text compared with the owner's details |
| Location | Decays with the distance between campus zones |
| Time | Decays with hours since the item was last seen. Items found before that are filtered out |

- **Rescaling.** Raw cosine scores live on different scales, so each is rescaled before fusing. A correct CLIP text-to-photo pair scores only about 0.3.
- **Confidence.** Pair probabilities are converted to odds, and confidence = odds ÷ (1 + sum of all candidates' odds). At most one item can be the owner's, and maybe none has been handed in yet. So two identical chargers each get about 50% instead of both claiming 90%.
- **Smart Claim question.** It picks the attribute with the highest confidence-weighted entropy across the likely candidates. It asks open-ended questions, so it never leaks what the finder saw.

## Configuration

| Variable | What it does |
|---|---|
| `ANTHROPIC_API_KEY` | Uses Claude for attribute extraction, claim questions and answer judging. `ANTHROPIC_MODEL` defaults to `claude-haiku-4-5-20251001` |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | Uses any OpenAI-compatible endpoint instead, e.g. a local Ollama server at `http://localhost:11434/v1` |
| `REMOVE_BG=1` | Removes photo backgrounds before CLIP (needs `pip install rembg`) |
| `VITE_API_URL` | Frontend: points at an API deployed somewhere else |

Without any LLM settings, everything falls back to keyword rules. The app always runs, and a rate limit can't break your live demo.

**Make it your campus:**
- `CAMPUS_ZONES` in `backend/matcher.py`: real building positions, or better, walking distances
- `CATEGORY_GROUPS` and `COLOR_ALIASES` in `backend/matcher.py`
- `BRANDS` in `backend/enrich.py`: brands students actually carry
- `KEPT_AT` in `backend/app.py`: drop-off points

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | Categories, colors, zones and drop-off points for the forms |
| POST | `/api/autotag` | Photo in; suggested category, colors and writing out |
| POST | `/api/reports` | Create a lost or found report (multipart form, optional `photo`) |
| GET | `/api/reports` | Found items still waiting. Lost reports are never listed |
| GET | `/api/reports/{id}` | One report, plus owner alerts for lost reports |
| GET | `/api/reports/{id}/matches` | Ranked matches and, if ambiguous, the Smart Claim question |
| POST | `/api/reports/{id}/answer` | Answer the question; returns re-ranked matches |
| POST | `/api/claims` | Start a claim: `{found_id, lost_id}` |
| POST | `/api/claims/{id}/verify` | Check the ownership answer: `{answer}` |
| POST | `/api/pickups/{code}` | Desk confirms the hand-over |
| GET | `/api/admin/stats` | Numbers for the desk page |

Interactive docs are at http://localhost:8000/docs.

## Measuring it

`evaluate.py` reports Recall@1, Recall@3 and mean reciprocal rank for text only, text + attributes, photo signals only, and full fusion.

**Build a dataset:**
- Photograph 30–50 items your team owns twice: an "owner photo" and a "finder photo" in a different place and light.
- Have different teammates write the owner and finder descriptions, so the styles differ naturally.
- Add look-alike distractors.
- Follow the format in `eval_sample.csv`.

**Train a calibrator:** `--save-calibrator` fits a logistic regression on your pairs, so the weights are learned and confidence is a real probability. It writes `calibrator.pkl`, which the API loads on start-up. Quote numbers only from a held-out CSV.

## Project layout

```
backend/
  app.py         API: reports, matching, alerts, Smart Claim, pickups, desk stats
  matcher.py     matching engine: signals, fusion, confidence, explanations, question picker
  enrich.py      text extraction (LLM or rules), CLIP photo tags, OCR, answer parsing
  verify.py      ownership question and answer judge
  llm.py         optional LLM client with graceful fallback
  db.py          SQLite storage (vectors stored as blobs)
  seed.py        demo data through the real API
  evaluate.py    Recall@K / MRR / ablation, calibrator training
frontend/src/
  pages/         Home, ReportForm (lost + found), ReportPage (matches), ClaimPage, Desk
  components/    TagCard, Stamp, ColorPicker, PhotoPicker
  styles.css     the whole design system
```

## Suggested team split (4 people)

| Role | Owns |
|---|---|
| Matching | `matcher.py` and `enrich.py`: tune ranges and weights, add DINOv2 for photo-to-photo |
| Backend | `app.py` and `db.py`: real email or Telegram alerts in `alert_owners()`, deployment |
| Frontend | Pages and components: polish, empty states, demo flow |
| Data and pitch | Photograph items, build the eval CSV, run `evaluate.py`, make the deck |

## Before real use

This is a hackathon build. Before real students rely on it:

- **Add login.** There are no accounts. "Your reports" is stored in the browser, and the Desk page is open to anyone. Add campus login (SSO) and a staff role.
- **Use an LLM for claims.** Without an LLM, the ownership check is a strict word overlap, which is fine for a demo. Staff should still look at the item at pickup.
- **Scale the index.** Matching runs in memory with SQLite, which is plenty for a campus. For more, move vectors to Postgres with pgvector and run background workers.
- **Protect privacy.** Public text hides roll-number-style codes, but finders should still keep names out of descriptions. Photos of ID cards should be blurred before listing.
