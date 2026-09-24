# Campus Lost & Found

**Report a lost or found item in a few seconds. The app matches descriptions and photos, explains each match, and checks ownership before anyone collects an item.**

---

## The problem

On most campuses, lost and found means a WhatsApp group, a cardboard box at the security desk and a lot of luck.

- **Owners and finders describe items differently.** "Navy Milton flask with a mountain sticker" and "blue metal bottle, sticker on it" are the same bottle, but a keyword search won't connect them.
- **Owners usually have no photo** of what they lost. Finders usually have only a photo.
- **Anyone can claim anything.** If you can see a photo of a phone, you can describe it well enough to take it home.

## What we built

A lost-and-found platform that does three things a notice board can't.

### 1. Matches by meaning and by photo
Each report is turned into vectors, both for its text (MiniLM) and its photo (CLIP), so similar items end up close together. Because CLIP puts photos and text in the same space, a **finder's photo can match an owner's written description**, even when the owner never had a photo.

### 2. Tells you how sure it is, and why
Each candidate gets a confidence score and plain-language reasons: *"same color (blue)"*, *"found in the same area (library)"*, *"the finder's photo fits your description"*. Confidence is spread across all the candidates, because only one of them can be yours and yours may not have been handed in yet. So two identical chargers show about 50% each, not 90% each.

### 3. Smart Claim: the right question, then proof
- **One question instead of a long list.** When several items look alike, the app works out which question would best tell them apart and asks only that. If three black chargers differ only by the name on the plug, it asks *"Is anything written on it?"* rather than *"What colour is it?"*
- **Ownership is checked with a secret.** The finder records a detail that is never shown, such as a scratch, something inside, or a name under the lid. The claimant gets an open-ended question about that kind of detail and has to describe it. A matching answer gets a pickup code; a vague one like *"it's black"* doesn't.

---

## How it works

```
 lost report ─┐                                          ┌─> ranked matches + reasons
              ├─> enrich ─> embed ─> filter ─> score ─> fuse ─> confidence ─┤
found report ─┘                                          └─> owner alert (found items)

 claim ─> open question built from the finder's private detail ─> judge answer ─> pickup code ─> desk hand-over
```

| Stage | What happens |
|---|---|
| **Enrich** | A photo fills in the category, colors and (with optional OCR) any visible writing on its own. The text is scanned for brand, color and location. |
| **Embed** | MiniLM turns descriptions into vectors; CLIP turns photos and short captions into vectors in the same space. |
| **Filter** | Pairs that can't match are dropped: a bottle is never a laptop, and an item can't be found before it was lost. |
| **Score** | Up to nine signals per pair, each from 0 to 1: text similarity, photo similarity, **photo against description**, category, color, brand, writing on the item, distance between campus zones, and time gap. A signal with no evidence is skipped, not counted as zero. |
| **Fuse** | A weighted average, turned into a probability and then compared across all candidates, since at most one can be yours. |
| **Ask** | If the top match isn't clear, Smart Claim picks the question whose answer best tells the candidates apart (confidence-weighted entropy). |
| **Alert** | When a new found item scores at least 75% against an open lost report, the owner is notified in the app and by email. |

## Results

Evaluated on a hand-written set of 10 lost reports against 22 found reports, 12 of which are look-alike distractors:

| Configuration | Recall@1 | Recall@3 | MRR |
|---|---|---|---|
| Text similarity only | 0.70 | 0.90 | 0.82 |
| Text + attributes | 0.80 | 1.00 | 0.90 |
| **Full fusion** | **0.90** | **1.00** | **0.95** |

Recall@1 is how often the right item is ranked first; Recall@3 is how often it's in the top 3. MRR (mean reciprocal rank) rewards putting the right item higher: 1.0 means always first.

Adding structured signals (color, brand, place, time) to text similarity cuts ranking mistakes. Full fusion puts the right item first 9 times out of 10. The set is small and text-only, so these numbers show the approach works rather than proving it at scale.

In the demo data:
- A lost navy bottle, described with no photo, matches the right found bottle at **98% confidence**.
- Two near-identical black chargers start at **52% vs 46%**. Smart Claim asks about writing on the item, and the owner's answer ("my name ARJUN is on the plug") moves the right charger to the top.

## Email notifications across the whole journey

Nobody has to keep checking the site. Everyone involved gets an email at each step:

| When | Who | What they get |
|---|---|---|
| A likely match is handed in | Owner | What was found, how confident the match is, where it's kept, and a link to claim it |
| The owner passes the ownership check | Owner | Their **pickup code** and where to collect the item |
| The owner passes the ownership check | Finder | Confirmation, plus a request to drop the item at the desk if they still have it |
| The desk hands the item over | Finder | A thank-you: the item is back with its owner |

Emails are sent in the background, so the app never waits on the mail server, and a mail outage can't break a report or a claim. Contact details are used only for these emails and are never shown.

## Privacy and safety

- **Public listings show only safe fields.** Contact details, the finder's secret detail and the exact writing on an item are never shown publicly. Roll numbers and phone numbers are masked in descriptions.
- **Matching alone never releases an item.** Collection needs a correct answer about the secret detail, and then a pickup code checked at the desk.
- **Guessing is limited.** Each report gets a limited number of Smart Claim questions, and repeated wrong ownership answers flag the claim for staff.
- **It works without an LLM.** Claude or any OpenAI-compatible model can improve text extraction and answer judging, but everything falls back to rules. A rate limit or a network outage doesn't break the app.

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | React 19, Vite, React Router. Plain CSS, no UI framework |
| Backend | FastAPI, SQLite (vectors stored alongside reports) |
| Matching | sentence-transformers: `all-MiniLM-L6-v2` for text, `clip-ViT-B-32` for photos and text-to-photo; rapidfuzz; scikit-learn for the optional learned calibrator |
| Optional AI | Claude (Haiku) or any OpenAI-compatible model for extraction and claim judging |
| Deployment | One Docker container serving the API, photos and frontend, deployed to Hugging Face Spaces |

Matching runs in memory, so ranking an item against every open report takes milliseconds. The only slow step is the one-off photo embedding when a report is submitted.

## What we'd build next

- **Campus login and a staff role.** There are no accounts yet, and the desk page is open.
- **More notification channels:** SMS and Telegram alongside email, and a daily digest for the desk.
- **A calibrator learned from real data.** The code already fits one from labelled pairs; it needs a larger, photographed dataset.
- **Real campus geography**, using walking distances between buildings instead of approximate zone coordinates.
- **Automatic blurring** of ID cards and faces in photos before listing.

## Honest note

The individual techniques (text embeddings, CLIP, weighted score fusion, entropy-based question selection) are well known. Our contribution is combining them for lost and found: **ask the one question that settles it instead of showing a long list, and verify ownership with a secret the claimant has never seen.**
