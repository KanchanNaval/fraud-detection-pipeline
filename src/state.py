"""
Tracks which claim IDs have already triggered a notification, so a daily
run only alerts on genuinely NEW flags — not the same claim resurfacing
every day until someone closes it out.
"""
import json
import os
from datetime import datetime


def load_notified_ids(path: str) -> set:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        data = json.load(f)
    return set(data.get("notified_claim_ids", []))


def save_notified_ids(path: str, all_notified_ids: set, run_date: str = None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "last_updated": run_date or datetime.now().strftime("%Y-%m-%d"),
        "notified_claim_ids": sorted(all_notified_ids),
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
