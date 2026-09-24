"""
Turn raw form input into structured fields the matcher can use.

Text:   an LLM when one is configured (see llm.py), keyword rules otherwise.
Photos: CLIP zero-shot suggestions for category and color, plus OCR for any
        writing on the item when `easyocr` is installed.
Edit the lists below for your campus (brands students actually carry, etc.).
"""
from __future__ import annotations

import re

import numpy as np
from rapidfuzz import fuzz

import llm
from matcher import CAMPUS_ZONES, CATEGORY_GROUPS, COLOR_ALIASES, Report

BASIC_COLORS = ["black", "white", "gray", "blue", "red", "green", "yellow",
                "orange", "pink", "purple", "brown"]

CATEGORY_PROMPTS = {  # how CLIP should picture each category
    "phone": "a smartphone", "laptop": "a laptop computer", "tablet": "a tablet computer",
    "charger": "a phone charger with a cable", "earphones": "earphones or earbuds",
    "calculator": "a calculator", "bottle": "a water bottle", "bag": "a backpack or bag",
    "wallet": "a wallet", "id_card": "an identity card", "keys": "a set of keys",
    "clothing": "a jacket, hoodie or other clothing", "umbrella": "an umbrella",
    "book": "a book", "notebook": "a notebook", "watch": "a wristwatch",
    "glasses": "a pair of glasses", "jewelry": "a piece of jewelry",
    "other": "some other object",         # catch-all, so odd items aren't forced into a category
}

CATEGORY_KEYWORDS = {
    "phone": ["phone", "iphone", "mobile", "smartphone", "android"],
    "laptop": ["laptop", "macbook", "chromebook"],
    "tablet": ["tablet", "ipad"],
    "charger": ["charger", "adapter", "charging cable", "cable", "power bank", "powerbank"],
    "earphones": ["earphones", "earphone", "earbuds", "earbud", "airpods", "headphones", "headset"],
    "calculator": ["calculator"],
    "bottle": ["bottle", "flask", "tumbler", "sipper"],
    "bag": ["bag", "backpack", "pouch", "tote", "purse"],
    "wallet": ["wallet", "card holder", "cardholder"],
    "id_card": ["id card", "identity card", "student id", "college id", "id-card"],
    "keys": ["key", "keys", "keychain", "key chain", "keyring"],
    "clothing": ["hoodie", "jacket", "sweater", "sweatshirt", "shirt", "t-shirt", "scarf",
                 "cap", "hat", "coat", "shoes"],
    "umbrella": ["umbrella"],
    "book": ["book", "textbook", "novel"],
    "notebook": ["notebook", "diary", "register", "journal"],
    "watch": ["watch", "smartwatch"],
    "glasses": ["glasses", "spectacles", "specs", "sunglasses"],
    "jewelry": ["ring", "necklace", "bracelet", "earring", "earrings", "pendant", "chain"],
}

BRANDS = ["apple", "samsung", "oneplus", "xiaomi", "redmi", "realme", "oppo", "vivo", "motorola",
          "nokia", "dell", "hp", "lenovo", "asus", "acer", "boat", "jbl", "sony", "bose",
          "skullcandy", "casio", "titan", "fastrack", "fossil", "milton", "cello", "hydro flask",
          "borosil", "nike", "adidas", "puma", "wildcraft", "skybags", "american tourister",
          "ray-ban", "parker", "anker", "logitech"]

MARK_WORDS = ["sticker", "stickers", "scratch", "scratches", "scratched", "dent", "dented",
              "crack", "cracked", "keychain", "engraved", "logo", "torn", "stain", "patch",
              "cover", "case", "strap", "tape"]

FILLER = {"a", "an", "the", "with", "has", "have", "had", "and", "my", "its", "it", "of", "on",
          "in", "is", "some", "small", "big"}


# ----------------------------------------------------------------------------- text rules
def guess_category(text: str) -> str | None:
    """Keyword match. In 'laptop charger' the last noun wins: that's a charger."""
    low = f" {text.lower()} "
    hits = []
    for cat, words in CATEGORY_KEYWORDS.items():
        for w in words:
            for m in re.finditer(rf"\b{re.escape(w)}s?\b", low):
                hits.append((m.start(), m.end(), cat))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept = []
    for h in hits:                       # drop matches inside a longer one ("key" in "key chain")
        if not kept or h[0] >= kept[-1][1]:
            kept.append(h)
    for i, (_, end, cat) in enumerate(kept):
        nxt = kept[i + 1] if i + 1 < len(kept) else None
        if nxt and nxt[2] != cat and not low[end:nxt[0]].strip(" -"):
            continue                     # a modifier directly followed by the real noun
        return cat
    return None


def extract_colors(text: str) -> list[str]:
    low, found = text.lower(), []
    for c in sorted(set(BASIC_COLORS) | set(COLOR_ALIASES) | {"grey"}, key=len, reverse=True):
        if re.search(rf"\b{re.escape(c)}\b", low):
            found.append(c)
            low = re.sub(rf"\b{re.escape(c)}\b", " ", low)
    return found[:3]


def extract_brand(text: str) -> str | None:
    low = text.lower()
    for b in BRANDS:
        if re.search(rf"\b{re.escape(b)}\b", low):
            return b.title() if b not in ("hp", "jbl") else b.upper()
    return None


def extract_marks(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9-]+", text.lower())
    marks = []
    for i, w in enumerate(words):
        if w in MARK_WORDS:
            before = [x for x in words[max(0, i - 2):i] if x not in FILLER]
            marks.append(" ".join(before + [w]))
    return list(dict.fromkeys(marks))[:3]


def extract_writing(text: str, answer_mode: bool = False) -> str | None:
    """Names, roll numbers or quoted text that appear to be written on the item.
    answer_mode: the text answers 'what's written on it?', so ALL-CAPS words count too."""
    parts = re.findall(r"[\"“]([^\"”]{2,40})[\"”]", text)
    m = re.search(r"\b(?i:name|named|written|says|reads|printed|engraved|labell?ed|initials)\b"
                  r"(?:\s+(?i:is|was|as|of|on it))*\s*[:\-]?\s*"
                  r"([A-Za-z0-9][\w.\-]*(?:\s+[A-Z0-9][\w.\-]*){0,3})", text)
    if m:
        parts.append(m.group(1))
    parts += re.findall(r"\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{5,}\b", text)  # roll no. etc.
    if answer_mode:
        parts += re.findall(r"\b[A-Z]{2,}\b", text)
    seen = list(dict.fromkeys(p.strip() for p in parts if p.strip()))
    return " ".join(seen)[:80] or None


def extract_zone(text: str) -> str | None:
    low = text.lower()
    best, score = None, 0
    for zone in CAMPUS_ZONES:
        s = fuzz.partial_ratio(zone.replace("_", " "), low)
        if s > score:
            best, score = zone, s
    return best if score >= 80 else None


EXTRACT_PROMPT = (
    "You extract structured fields from lost-and-found reports on a university campus. "
    "Allowed categories: {cats}. Return JSON with keys: category (one allowed value or null), "
    "colors (list of basic color words), brand (string or null), marks (list of short "
    "distinguishing features such as 'mountain sticker' or 'cracked corner'), text_on_item "
    "(names, numbers or words written on the item, or null). Use only what the text states.")


def extract_fields(description: str) -> dict:
    """LLM extraction when available, filled in by rules wherever it comes back empty."""
    rules = {"category": guess_category(description), "colors": extract_colors(description),
             "brand": extract_brand(description), "marks": extract_marks(description),
             "text_on_item": extract_writing(description)}
    data = {}
    if llm.available() and description.strip():
        data = llm.complete_json(EXTRACT_PROMPT.format(cats=", ".join(CATEGORY_GROUPS)),
                                 description) or {}
    out = {k: data.get(k) or v for k, v in rules.items()}
    if out["category"] not in CATEGORY_GROUPS:
        out["category"] = rules["category"]
    out["colors"] = [str(c) for c in (out["colors"] or [])][:3]
    out["marks"] = [str(m) for m in (out["marks"] or [])][:3]
    return out


# ----------------------------------------------------------------------------- photos
class AutoTagger:
    """Zero-shot category and color suggestions for a photo, using CLIP."""

    def __init__(self, encoder) -> None:
        clip = encoder.clip_model
        self.categories = list(CATEGORY_PROMPTS)
        self.category_vecs = clip.encode([f"a photo of {p}" for p in CATEGORY_PROMPTS.values()],
                                         normalize_embeddings=True)
        self.color_vecs = clip.encode([f"a photo of a {c} object" for c in BASIC_COLORS],
                                      normalize_embeddings=True)

    @staticmethod
    def _softmax(scores: np.ndarray) -> np.ndarray:
        e = np.exp(100 * (scores - scores.max()))      # CLIP's logit scale is 100
        return e / e.sum()

    def tag(self, image_vec: np.ndarray) -> dict:
        cat_p = self._softmax(self.category_vecs @ image_vec)
        col_p = self._softmax(self.color_vecs @ image_vec)
        best = int(cat_p.argmax())
        order = np.argsort(-col_p)
        colors = [BASIC_COLORS[j] for j in order[:2] if col_p[j] >= 0.2] or [BASIC_COLORS[order[0]]]
        return {"category": self.categories[best],
                "category_confidence": round(float(cat_p[best]), 2), "colors": colors}


_ocr = None


def read_text(image) -> str | None:
    """Writing on the item (names, roll numbers, labels). Needs `pip install easyocr`."""
    global _ocr
    try:
        import easyocr
    except ImportError:
        return None
    if _ocr is None:
        _ocr = easyocr.Reader(["en"], gpu=False, verbose=False)
    words = [t.strip() for _, t, conf in _ocr.readtext(np.array(image)) if conf >= 0.4]
    return " ".join(w for w in words if len(w) >= 2)[:80] or None


# ----------------------------------------------------------------------------- orchestration
def enrich_report(r: Report, tagger: AutoTagger | None, image=None) -> dict:
    """Fill fields the reporter left empty: form values win, then text, then photo.
    Returns which fields were auto-filled and from where (the UI can say so)."""
    auto = {}
    fields = extract_fields(r.description) if r.description else {}
    if r.category == "other" and fields.get("category"):
        r.category, auto["category"] = fields["category"], "description"
    if not r.colors and fields.get("colors"):
        r.colors, auto["colors"] = fields["colors"], "description"
    r.brand = r.brand or fields.get("brand")
    r.marks = r.marks or fields.get("marks") or []
    if not r.text_on_item and fields.get("text_on_item"):
        r.text_on_item, auto["text_on_item"] = fields["text_on_item"], "description"
    if r.image_vec is not None and tagger is not None:
        tags = tagger.tag(r.image_vec)
        if r.category == "other" and tags["category"] != "other" and tags["category_confidence"] >= 0.35:
            r.category, auto["category"] = tags["category"], "photo"
        if not r.colors:
            r.colors, auto["colors"] = tags["colors"], "photo"
    if image is not None and r.kind == "found" and not r.text_on_item:
        text = read_text(image)
        if text:
            r.text_on_item, auto["text_on_item"] = text, "photo"
    if not r.description.strip():        # photo-only report: give the text model something
        r.description = " ".join(r.colors + [r.category.replace("_", " ")])
    return auto


def parse_answer(attribute: str, answer: str):
    """Turn an owner's free-text Smart Claim answer into a field value (None if unusable)."""
    answer = answer.strip()
    if not answer:
        return None
    if attribute == "color":
        return extract_colors(answer) or None
    if attribute == "brand":
        return extract_brand(answer) or answer[:40]
    if attribute == "location":
        return extract_zone(answer)
    if attribute == "text_on_item":
        if llm.available():
            data = llm.complete_json(
                "Extract exactly the text that the person says is written, printed or stuck on "
                "their item. JSON: {\"text\": string or null}", answer)
            if data and data.get("text"):
                return str(data["text"])[:80]
        return extract_writing(answer, answer_mode=True) or answer[:80]
    return None
