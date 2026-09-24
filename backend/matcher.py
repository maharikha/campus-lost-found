"""
matcher.py - core matching engine for a Campus Lost-and-Found Matcher.

Lost-and-found data is lopsided: owners write detailed descriptions but rarely
have a photo, while finders snap a photo and type very little. So this engine
combines several signals for every (lost, found) pair:

  text      owner's words vs finder's words      (sentence embeddings)
  image     owner's photo vs finder's photo      (CLIP image embeddings)
  cross     owner's words vs finder's photo      (CLIP puts text and images in one space)
  category, color, brand, text_on_item           (structured checks)
  location, time                                 (campus plausibility)

and turns them into a similarity score, an ambiguity-aware confidence and a
plain-English explanation. best_question() powers the "Smart Claim" feature:
when several found items look alike, it picks the one question to ask the owner.

Install:   pip install sentence-transformers pillow rapidfuzz scikit-learn numpy
Optional:  pip install rembg          # background removal, helps photo matching
Demo:      python matcher.py
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from PIL import Image, ImageOps
from rapidfuzz import fuzz

# =============================================================================
# Campus config - edit for your campus
# =============================================================================
CATEGORY_GROUPS = {  # category -> group. Items in different groups never match.
    "phone": "electronics", "laptop": "electronics", "tablet": "electronics",
    "charger": "electronics", "earphones": "electronics", "calculator": "electronics",
    "bottle": "bottle", "bag": "bag", "wallet": "wallet", "id_card": "cards",
    "keys": "keys", "clothing": "clothing", "umbrella": "umbrella",
    "book": "stationery", "notebook": "stationery", "watch": "accessories",
    "glasses": "accessories", "jewelry": "accessories", "other": "other",
}

COLOR_ALIASES = {
    "navy": "blue", "sky blue": "blue", "light blue": "blue", "dark blue": "blue",
    "teal": "blue", "turquoise": "blue", "maroon": "red", "burgundy": "red",
    "crimson": "red", "grey": "gray", "silver": "gray", "charcoal": "gray",
    "gold": "yellow", "golden": "yellow", "beige": "brown", "tan": "brown",
    "cream": "white", "off-white": "white", "violet": "purple",
    "lavender": "purple", "olive": "green", "mint": "green",
}

# Approximate zone positions in metres (x, y). Replace with real coordinates
# from your campus map - or better, walking distances between buildings.
CAMPUS_ZONES = {
    "library": (0, 0), "main_block": (150, 40), "canteen": (220, 180),
    "auditorium": (100, 260), "parking": (-200, 120),
    "sports_complex": (450, -250), "hostel": (600, 300),
}

# Relative importance of each signal. Used until you fit a Calibrator.
WEIGHTS = {
    "text": 0.20, "image": 0.25, "cross": 0.20, "category": 0.10, "color": 0.15,
    "brand": 0.05, "text_on_item": 0.20, "location": 0.05, "time": 0.05,
}

# Raw cosine similarities live on very different scales per model: a CORRECT
# text-vs-photo pair in CLIP typically scores only ~0.30, while two photos of
# unrelated things often score 0.5-0.7. Map each onto 0..1 before combining.
# (Measured on sample data; a Calibrator learns better scaling from your data.)
RANGES = {"text": (0.20, 0.75), "image": (0.60, 0.95), "cross": (0.16, 0.32)}

STOPWORDS = {"the", "and", "on", "in", "of", "an", "is", "it", "my", "with",
             "to", "at", "for", "has", "was", "its", "this", "that"}


# =============================================================================
# Data model
# =============================================================================
@dataclass
class Report:
    id: str
    kind: str                            # "lost" or "found"
    description: str                     # free text from the reporter
    category: str = "other"              # a key of CATEGORY_GROUPS
    colors: list[str] = field(default_factory=list)
    brand: str | None = None
    marks: list[str] = field(default_factory=list)   # "mountain sticker", "cracked corner"
    location: str | None = None          # a key of CAMPUS_ZONES
    time: datetime | None = None         # lost: when last SEEN; found: when FOUND
    image_path: str | None = None
    text_on_item: str | None = None      # name / roll no. / sticker text (typed or OCR)
    secret_details: str | None = None    # finder only - never shown publicly
    status: str = "open"                 # open -> claimed -> returned
    contact: str | None = None           # app-level fields below: not used for matching
    kept_at: str | None = None
    created_at: datetime | None = None
    text_vec: np.ndarray | None = field(default=None, repr=False)
    caption_vec: np.ndarray | None = field(default=None, repr=False)
    image_vec: np.ndarray | None = field(default=None, repr=False)

    def clip_caption(self) -> str:
        """Short caption for CLIP: it was trained on short alt-text and truncates at 77 tokens."""
        if self.category == "other":            # no category noun: let CLIP read the text
            return " ".join(self.description.split()[:25]) or "a photo of an object"
        words = [" ".join(self.colors), self.brand or "", self.category.replace("_", " ")]
        caption = "a photo of a " + " ".join(w for w in words if w)
        if self.marks:
            caption += " with " + ", ".join(self.marks[:3])
        return caption


# =============================================================================
# Embeddings
# =============================================================================
class Encoder:
    """Loads the models once (do this at server start-up) and embeds reports.
    Reports in several languages? Use text_model="paraphrase-multilingual-MiniLM-L12-v2"
    and encode captions with "clip-ViT-B-32-multilingual-v1" (same space as CLIP images)."""

    def __init__(self, text_model: str = "all-MiniLM-L6-v2",
                 clip_model: str = "clip-ViT-B-32", remove_background: bool = False):
        from sentence_transformers import SentenceTransformer
        self.text_model = SentenceTransformer(text_model)
        self.clip_model = SentenceTransformer(clip_model)
        self.remove_background = remove_background

    def prepare(self, img: Image.Image) -> Image.Image:
        """Optionally cut the item out of its background, which otherwise dominates CLIP."""
        if self.remove_background:
            try:
                from rembg import remove
                cut = remove(img)
                canvas = Image.new("RGB", cut.size, (255, 255, 255))
                canvas.paste(cut, mask=cut.getchannel("A"))
                return canvas
            except ImportError:
                pass
        return img

    def load_image(self, path: str) -> Image.Image:
        return ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # fix phone rotation

    def embed_image(self, img: Image.Image) -> np.ndarray:
        return self.clip_model.encode(self.prepare(img), normalize_embeddings=True)

    def encode_photo(self, report: Report, img: Image.Image | None = None) -> None:
        report.image_vec = self.embed_image(img if img is not None else self.load_image(report.image_path))

    def encode(self, reports: list[Report]) -> None:
        """Fill text_vec, caption_vec and image_vec in place (unit-length vectors).
        Photos that already have a vector are not re-encoded."""
        if not reports:
            return
        texts = self.text_model.encode([r.description for r in reports], normalize_embeddings=True)
        caps = self.clip_model.encode([r.clip_caption() for r in reports], normalize_embeddings=True)
        for r, t, c in zip(reports, texts, caps):
            r.text_vec, r.caption_vec = t, c
        for r in reports:
            if r.image_path and r.image_vec is None:
                self.encode_photo(r)

    def text_similarity(self, a: str, b: str) -> float:
        va, vb = self.text_model.encode([a, b], normalize_embeddings=True)
        return float(va @ vb)


# =============================================================================
# Pair signals
# =============================================================================
def _rescale(x: float, key: str) -> float:
    lo, hi = RANGES[key]
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


def _colors(colors: list[str]) -> set[str]:
    return {COLOR_ALIASES.get(c.lower().strip(), c.lower().strip()) for c in colors if c.strip()}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if len(t) >= 2 and t not in STOPWORDS]


def _token_overlap(needle: str, haystack: str) -> float | None:
    """Share of the needle's words that fuzzily appear in the haystack."""
    need, hay = _tokens(needle), set(_tokens(haystack))
    if not need or not hay:
        return None
    return sum(any(fuzz.ratio(t, h) >= 85 for h in hay) for t in need) / len(need)


def zone_distance(a: str | None, b: str | None) -> float | None:
    if a not in CAMPUS_ZONES or b not in CAMPUS_ZONES:
        return None
    (x1, y1), (x2, y2) = CAMPUS_ZONES[a], CAMPUS_ZONES[b]
    return math.hypot(x1 - x2, y1 - y2)


def is_plausible(lost: Report, found: Report, slack_hours: float = 2) -> bool:
    """Hard filters for impossible pairs."""
    if lost.time and found.time and found.time < lost.time - timedelta(hours=slack_hours):
        return False                             # found before the owner last saw it
    g1 = CATEGORY_GROUPS.get(lost.category, "other")
    g2 = CATEGORY_GROUPS.get(found.category, "other")
    return g1 == g2 or "other" in (g1, g2)       # a bottle is never a laptop


def pair_features(lost: Report, found: Report) -> dict[str, float | None]:
    """Every signal on a 0..1 scale, or None when there is no evidence either way."""
    f: dict[str, float | None] = dict.fromkeys(WEIGHTS)
    f["text"] = _rescale(float(lost.text_vec @ found.text_vec), "text")
    if lost.image_vec is not None and found.image_vec is not None:
        f["image"] = _rescale(float(lost.image_vec @ found.image_vec), "image")
    cross = [float(a.caption_vec @ b.image_vec)
             for a, b in ((lost, found), (found, lost)) if b.image_vec is not None]
    if cross:
        f["cross"] = _rescale(max(cross), "cross")
    if "other" not in (lost.category, found.category):
        f["category"] = 1.0 if lost.category == found.category else 0.5
    c1, c2 = _colors(lost.colors), _colors(found.colors)
    if c1 and c2:
        f["color"] = len(c1 & c2) / len(c1 | c2)
    if lost.brand and found.brand:
        f["brand"] = fuzz.token_set_ratio(lost.brand.lower(), found.brand.lower()) / 100
    if lost.text_on_item and found.text_on_item:     # both sides know: can confirm OR contradict
        f["text_on_item"] = max(_token_overlap(found.text_on_item, lost.text_on_item) or 0.0,
                                _token_overlap(lost.text_on_item, found.text_on_item) or 0.0)
    elif found.text_on_item or lost.text_on_item:    # one side only: a mention counts, silence doesn't
        needle = found.text_on_item or lost.text_on_item
        other = lost.description if found.text_on_item else found.description
        f["text_on_item"] = _token_overlap(needle, other) or None
    d = zone_distance(lost.location, found.location)
    if d is not None:
        f["location"] = math.exp(-d / 300)             # ~300 m decay; tune for your campus
    if lost.time and found.time:
        hours = max((found.time - lost.time).total_seconds() / 3600, 0)
        f["time"] = math.exp(-hours / 72)              # most items turn up within days
    return f


def explain(lost: Report, found: Report, f: dict) -> tuple[list[str], list[str]]:
    """Plain-English reasons for (pros) and against (cons) a match."""
    pros: list[str] = []
    cons: list[str] = []

    def judge(key: str, pro: str, con: str, hi: float = 0.7, lo: float = 0.3) -> None:
        v = f.get(key)
        if v is not None and v >= hi:
            pros.append(pro)
        elif v is not None and v <= lo:
            cons.append(con)

    c1, c2 = _colors(lost.colors), _colors(found.colors)
    judge("text_on_item", "writing on the item matches the owner's details",
          "writing on the item doesn't match", hi=0.5, lo=0.0)
    judge("cross", "the finder's photo fits the owner's description",
          "the finder's photo doesn't fit the description")
    judge("image", "the two photos look alike", "the two photos look different")
    judge("text", "the descriptions are very similar", "the descriptions differ a lot")
    judge("color", f"same color ({', '.join(sorted(c1 & c2))})",
          f"color differs ({'/'.join(sorted(c1))} vs {'/'.join(sorted(c2))})", hi=0.5, lo=0.0)
    judge("brand", f"same brand ({found.brand})",
          f"brand differs ({lost.brand} vs {found.brand})", hi=0.8, lo=0.5)
    d = zone_distance(lost.location, found.location)
    if d is not None:
        where = "in the same area" if d < 50 else f"about {d:.0f} m away"
        (pros if d <= 300 else cons).append(f"found {where} ({found.location.replace('_', ' ')})")
    if lost.time and found.time:
        hours = (found.time - lost.time).total_seconds() / 3600
        when = ("around when it was last seen" if hours < 0.25 else
                f"{hours * 60:.0f} min after it was last seen" if hours < 1 else
                f"{hours:.0f} h after it was last seen")
        (pros if hours <= 48 else cons).append(f"found {when}")
    return pros, cons


# =============================================================================
# Fusion, confidence, ranking
# =============================================================================
def fuse(f: dict, weights: dict = WEIGHTS) -> float:
    """Weighted average over the signals that exist; missing ones are skipped, not zeroed."""
    have = {k: v for k, v in f.items() if v is not None and weights.get(k, 0) > 0}
    total = sum(weights[k] for k in have)
    return sum(weights[k] * v for k, v in have.items()) / total if total else 0.0


def pseudo_probability(similarity: float, center: float = 0.6, slope: float = 0.07) -> float:
    """Hand-tuned stand-in for a calibrated probability. Replace with a Calibrator."""
    return 1 / (1 + math.exp(-(similarity - center) / slope))


class Calibrator:
    """Learns signal weights AND a calibrated match probability from labelled
    pairs with logistic regression. Missing signals become 0 plus a 'missing' flag."""

    def __init__(self) -> None:
        from sklearn.linear_model import LogisticRegression
        self.model = LogisticRegression(max_iter=1000)

    @staticmethod
    def vectorize(f: dict) -> list[float]:
        return [x for k in WEIGHTS for x in ((f[k] or 0.0), float(f[k] is None))]

    def fit(self, pairs: list[tuple[Report, Report, bool]]) -> "Calibrator":
        """pairs: (lost, found, is_same_item). Use every true pair plus several
        HARD negatives per lost report (same category, different item)."""
        X = [self.vectorize(pair_features(lo, fo)) for lo, fo, _ in pairs]
        self.model.fit(X, [int(y) for _, _, y in pairs])
        return self

    def probability(self, f: dict) -> float:
        return float(self.model.predict_proba([self.vectorize(f)])[0, 1])


@dataclass
class Match:
    report: Report       # the candidate from the other side
    similarity: float    # 0..1: how alike this pair is on its own
    confidence: float    # 0..1: chance THIS is the item, given all other candidates
    pros: list[str]
    cons: list[str]
    features: dict

    @property
    def band(self) -> str:
        return "high" if self.confidence >= 0.75 else "medium" if self.confidence >= 0.4 else "low"


def rank(query: Report, pool: list[Report], top_k: int = 5,
         calibrator: Calibrator | None = None, weights: dict = WEIGHTS) -> list[Match]:
    """Rank open reports of the opposite kind for `query`. Works both ways: a new
    lost report vs found items, or a new found item vs open lost reports."""
    scored: list[tuple[Match, float]] = []
    for cand in pool:
        if cand.kind == query.kind or cand.status != "open":
            continue
        lost, found = (query, cand) if query.kind == "lost" else (cand, query)
        if not is_plausible(lost, found):
            continue
        f = pair_features(lost, found)
        sim = fuse(f, weights)
        p = calibrator.probability(f) if calibrator else pseudo_probability(sim)
        scored.append((Match(cand, sim, 0.0, *explain(lost, found, f), f), p))
    # At most one candidate can be the real item, and maybe none is (not handed
    # in yet). With independent match probabilities p_i that gives
    # P(candidate i is the one) = odds_i / (1 + sum of all odds).
    odds = [min(p, 1 - 1e-6) / (1 - min(p, 1 - 1e-6)) for _, p in scored]
    total = 1 + sum(odds)
    for (m, _), o in zip(scored, odds):
        m.confidence = o / total
    return sorted((m for m, _ in scored), key=lambda m: m.confidence, reverse=True)[:top_k]


# =============================================================================
# Novel feature seed - Smart Claim: ask the one question that splits the candidates
# =============================================================================
QUESTIONS = {  # attribute -> (open-ended question, how reliably owners can answer it)
    "text_on_item": ("Is anything written, printed or stuck on it, like a name, a sticker or a logo?", 1.0),
    "brand": ("What brand or model is it?", 0.9),
    "color": ("What color is it? Mention any secondary colors too.", 0.8),
    "location": ("Where were you when you last had it?", 0.6),
}


def _attr_value(r: Report, attr: str):
    if attr == "color":
        return frozenset(_colors(r.colors)) or None
    if attr == "brand":
        return r.brand.lower() if r.brand else None
    if attr == "text_on_item":
        return r.text_on_item.lower() if r.text_on_item else None
    return r.location if attr == "location" else None


def best_question(query: Report, matches: list[Match]) -> tuple[str, str] | None:
    """Pick the attribute whose answer best separates the likely candidates:
    entropy of its values across candidates, weighted by their confidence.
    Questions are open-ended so they never leak what the finder saw."""
    total = sum(m.confidence for m in matches) or 1.0
    best, best_gain = None, 0.0
    for attr, (question, reliability) in QUESTIONS.items():
        if _attr_value(query, attr) is not None:
            continue                                  # the owner already told us
        mass: dict = {}
        for m in matches:
            v = _attr_value(m.report, attr)
            if v is not None:
                mass[v] = mass.get(v, 0.0) + m.confidence
        known = sum(mass.values())
        if len(mass) < 2 or known <= 0:
            continue
        entropy = -sum(w / known * math.log2(w / known) for w in mass.values() if w > 0)
        gain = entropy * (known / total) * reliability   # discount attrs few candidates have
        if gain > best_gain:
            best, best_gain = (attr, question), gain
    return best


# =============================================================================
# Demo: python matcher.py   (add image_path="photos/x.jpg" to any report to use photos)
# =============================================================================
if __name__ == "__main__":
    day = datetime(2026, 9, 24, 9, 0)

    def at(hours: float) -> datetime:          # time = hours after 9 am
        return day + timedelta(hours=hours)

    found = [
        Report("F1", "found", "Blue metal water bottle left on a reading table, has a sticker",
               "bottle", ["blue"], location="library", time=at(6.7)),
        Report("F2", "found", "Black plastic water bottle near the canteen counter",
               "bottle", ["black"], location="canteen", time=at(7.5)),
        Report("F3", "found", "Black charger, found on a table in the canteen",
               "charger", ["black"], location="canteen", time=at(5), text_on_item="Arjun"),
        Report("F4", "found", "Black charger and cable left plugged in, classroom 204",
               "charger", ["black"], location="main_block", time=at(4.5), text_on_item="CSE LAB 3"),
        Report("F5", "found", "Student ID card lying near the bike stand",
               "id_card", location="parking", time=at(1), text_on_item="Priya Sharma 21CS045"),
        Report("F6", "found", "White Samsung charger with a frayed cable",
               "charger", ["white"], brand="Samsung", location="canteen", time=at(5.5)),
    ]
    lost = [
        Report("L1", "lost", "Lost my navy blue Milton steel bottle with a mountain sticker. "
               "Last had it in the library around 3pm.", "bottle", ["navy"], brand="Milton",
               marks=["mountain sticker"], location="library", time=at(6)),
        Report("L2", "lost", "Lost my college ID card this morning. Name Priya Sharma, "
               "roll number 21CS045.", "id_card", time=at(0)),
        Report("L3", "lost", "Lost my black phone charger with a long cable around lunch time, "
               "not sure where.", "charger", ["black"], time=at(3)),
    ]

    def show(q: Report, matches: list[Match]) -> None:
        print(f"\n{q.id} ({q.kind}): {q.description}")
        for i, m in enumerate(matches, 1):
            print(f"  {i}. {m.report.id} | similarity {m.similarity:.2f} | "
                  f"confidence {m.confidence:.0%} ({m.band}) | {m.report.description}")
            for sign, reasons in (("+", m.pros), ("-", m.cons)):
                if reasons:
                    print(f"       {sign} " + "; ".join(reasons))

    encoder = Encoder()                  # load once at server start-up
    encoder.encode(found + lost)         # in the app: encode each report when it's submitted

    for q in lost:
        show(q, rank(q, found, top_k=3))

    # Smart Claim: the charger is ambiguous, so ask the single most useful question.
    q = lost[2]
    matches = rank(q, found, top_k=3)
    ask = best_question(q, matches) if matches and matches[0].confidence < 0.75 else None
    if ask:
        attr, question = ask
        print(f'\n>> {q.id} is ambiguous. Smart Claim asks the owner: "{question}"')
        simulated = {"text_on_item": "Arjun", "location": "canteen", "brand": "unknown"}
        print(f'   Owner answers -> {attr} = "{simulated[attr]}"   (an LLM extracts this from free text)')
        setattr(q, attr, simulated[attr])
        show(q, rank(q, found, top_k=3))

    # A newly FOUND item is matched against open LOST reports the same way (-> notify owner):
    show(found[4], rank(found[4], lost, top_k=2))
