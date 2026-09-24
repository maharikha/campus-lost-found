"""
Measure matching quality - this table is your "it actually works" slide.

    python evaluate.py eval_sample.csv
    python evaluate.py my_items.csv --save-calibrator    # also writes calibrator.pkl

CSV columns: item_id, role, description, category, colors (a;b), brand, location,
             hours, photo, text_on_item
Each physical item appears once as role=lost and once as role=found with the same
item_id. Extra found rows with their own item_id are distractors: make them look
similar (more black chargers!), because hard negatives keep the numbers honest.
`hours` is the time offset (lost: last seen, found: when found); `photo` is a path
relative to the CSV. The API loads calibrator.pkl on start-up; measure it again on a
different, held-out CSV before you quote its numbers.
"""
from __future__ import annotations

import csv
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

from matcher import WEIGHTS, Calibrator, Encoder, Report, rank

CONFIGS = {
    "text only": {"text": 1.0},
    "text + attributes": {k: WEIGHTS[k] for k in ("text", "category", "color", "brand", "text_on_item")},
    "photo signals only": {"image": 1.0, "cross": 1.0},
    "full fusion": WEIGHTS,
}


def load(path: Path) -> tuple[list[Report], list[Report]]:
    start = datetime(2026, 1, 1, 9)
    lost, found = [], []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            get = lambda k: (row.get(k) or "").strip()          # noqa: E731
            r = Report(id=f"{get('role')}:{get('item_id')}", kind=get("role"),
                       description=get("description"), category=get("category") or "other",
                       colors=[c for c in get("colors").split(";") if c],
                       brand=get("brand") or None, location=get("location") or None,
                       time=start + timedelta(hours=float(get("hours") or 0)),
                       image_path=str(path.parent / get("photo")) if get("photo") else None,
                       text_on_item=get("text_on_item") or None)
            (lost if r.kind == "lost" else found).append(r)
    return lost, found


def score(lost: list[Report], found: list[Report], **kwargs) -> tuple[float, float, float]:
    """Recall@1, Recall@3 and mean reciprocal rank of the true found report."""
    hit1 = hit3 = rr = 0.0
    for q in lost:
        ranked = [m.report.id for m in rank(q, found, top_k=len(found), **kwargs)]
        target = "found:" + q.id.split(":", 1)[1]
        pos = ranked.index(target) + 1 if target in ranked else None
        hit1 += pos == 1
        hit3 += bool(pos and pos <= 3)
        rr += 1 / pos if pos else 0.0
    n = len(lost) or 1
    return hit1 / n, hit3 / n, rr / n


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    csv_path = Path(sys.argv[1])
    lost, found = load(csv_path)
    print(f"{len(lost)} lost reports vs {len(found)} found reports "
          f"({len(found) - len(lost)} distractors)\n")
    Encoder().encode(lost + found)
    has_photos = any(r.image_path for r in lost + found)

    print(f"{'configuration':22s} {'R@1':>6s} {'R@3':>6s} {'MRR':>6s}")
    for name, weights in CONFIGS.items():
        if "text" not in weights and not has_photos:
            print(f"{name:22s}   (needs photos in the CSV)")
            continue
        r1, r3, mrr = score(lost, found, weights=weights)
        print(f"{name:22s} {r1:6.2f} {r3:6.2f} {mrr:6.2f}")

    if "--save-calibrator" in sys.argv:
        pairs = [(q, f, q.id.split(":", 1)[1] == f.id.split(":", 1)[1]) for q in lost for f in found]
        calibrator = Calibrator().fit(pairs)
        (Path(__file__).parent / "calibrator.pkl").write_bytes(pickle.dumps(calibrator))
        r1, r3, mrr = score(lost, found, calibrator=calibrator)
        print(f"{'calibrated (in-sample)':22s} {r1:6.2f} {r3:6.2f} {mrr:6.2f}")
        print("\nSaved calibrator.pkl - restart the API to use it.")
