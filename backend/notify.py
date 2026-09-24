"""
Email notifications for the whole claim lifecycle, using only the standard library.

    owner   possible match handed in, claim approved (with the pickup code)
    finder  the owner was verified, the item was collected

Set SMTP_USER and SMTP_PASSWORD to send real email (for Gmail, an app password:
Google account > Security > 2-Step Verification > App passwords). Without them,
every email is printed to the console instead, so the app works the same.

    SMTP_HOST   default smtp.gmail.com         SMTP_PORT  default 587 (STARTTLS)
    MAIL_FROM   default SMTP_USER              APP_URL    link base, e.g. https://you.hf.space
"""
from __future__ import annotations

import os
import re
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

from matcher import Report

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USER
APP_URL = os.getenv("APP_URL", "").rstrip("/")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_pool = ThreadPoolExecutor(max_workers=1)     # SMTP takes a second or two; never block a request


def enabled() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD)


NOUNS = {"id_card": "ID card", "other": "item", "clothing": "clothing item",
         "earphones": "pair of earphones", "glasses": "pair of glasses", "keys": "set of keys"}


def _item(r: Report) -> str:
    """'pink Nike clothing item', 'pair of black Bose earphones', 'ID card'."""
    colors = "" if r.category == "id_card" else " and ".join(r.colors)
    brand = r.brand[0].upper() + r.brand[1:] if r.brand and r.brand.islower() else r.brand
    noun = NOUNS.get(r.category, r.category.replace("_", " "))
    counter, _, noun = noun.rpartition(" of ")          # "pair of earphones" -> "pair", "earphones"
    words = " ".join(x for x in (colors, brand, noun) if x)
    return f"{counter} of {words}" if counter else words


def a_item(r: Report) -> str:
    """With the right article: 'an orange bottle', 'a pink Nike clothing item'."""
    name = _item(r)
    return ("an " if name[0].lower() in "aeiou" else "a ") + name


def _link(path: str) -> str:
    return f"\n\nOpen it here: {APP_URL}{path}" if APP_URL else ""


def _deliver(to: str, subject: str, body: str) -> None:
    if not enabled():
        print(f"[email off] to {to}: {subject}")
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = f"Campus Lost & Found <{MAIL_FROM}>", to, subject
    msg.set_content(body + "\n\n- Campus Lost & Found\n")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        print(f"[email sent] to {to}: {subject}")
    except (smtplib.SMTPException, OSError) as e:      # a mail problem must never break the app
        print(f"[email failed] to {to}: {subject} ({e})")


def send(report: Report | None, subject: str, body: str) -> None:
    """Queue an email to the report's contact. Phone numbers and blanks are skipped."""
    contact = (report.contact or "").strip() if report else ""
    if EMAIL_RE.match(contact):
        _pool.submit(_deliver, contact, subject, body)


# ============================================================================= the four emails
def match_found(lost: Report, found: Report, confidence: float, place: str, likely: bool = True) -> None:
    item = a_item(found)
    claim = ("To collect it, open your report, press \"This is mine\" and answer one question "
             "about it. The question checks you're the owner." + _link(f"/reports/{lost.id}"))
    if likely:
        send(lost, f"{item[0].upper()}{item[1:]} that may be yours was handed in",
             f"Good news: someone handed in {item} that matches your report "
             f"({round(confidence * 100)}% confidence), and {place}.\n\n" + claim)
    else:
        send(lost, f"{item[0].upper()}{item[1:]} similar to yours was handed in",
             f"Someone handed in {item} that looks similar to the {_item(lost)} you reported, "
             f"and {place}. It may not be yours, "
             "but it's worth a quick look at the photo and details.\n\nIf it is yours: " + claim[0].lower() + claim[1:])


def claim_approved(lost: Report | None, found: Report, code: str) -> None:
    where = found.kept_at or "Security desk"
    pickup = ("The finder still has it. The desk will arrange the hand-over."
              if where == "With the finder" else f"Collect it from the {where.lower()}.")
    send(lost, f"Your pickup code: {code}",
         f"You've been verified as the owner of the {_item(found)}.\n\n"
         f"Pickup code: {code}\n\n{pickup} Show this code at the desk.")


def owner_verified(found: Report) -> None:
    ask = ("Please bring it to the security desk so the owner can collect it."
           if found.kept_at == "With the finder" else "There's nothing more you need to do.")
    send(found, f"The owner of the {_item(found)} you found has been verified",
         f"Thanks for handing in the {_item(found)}. Its owner has just proved it's theirs. {ask}")


def item_returned(found: Report) -> None:
    send(found, f"The {_item(found)} you found is back with its owner",
         f"The {_item(found)} you handed in has been collected by its owner. Thank you for helping!")
