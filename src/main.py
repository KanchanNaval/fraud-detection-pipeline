"""
Daily Insurance Fraud Detection Pipeline
============================================
Run manually:      python src/main.py
Run on a schedule:  see ../SCHEDULING.md for daily cron / Task Scheduler setup

Flow:
  1. Load ALL claims files seen so far (today's + every prior day) — needed
     because duplicate/frequency rules only make sense with historical context,
     not a single day in isolation.
  2. Apply rule-based fraud checks + ML anomaly detection across that full history.
  3. Compare against state file of already-notified claim IDs.
  4. Only NEW flags (never notified before) go into today's alert.
  5. Save today's report, send notification, update the state file.
"""
import glob
import os
import sys
import yaml
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(__file__))
from rules import apply_all_rules
from ml_model import apply_ml_anomaly_detection
from notify import notify
from state import load_notified_ids, save_notified_ids

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    with open(os.path.join(BASE_DIR, "config", "config.yaml")) as f:
        return yaml.safe_load(f)


def load_all_claims(cfg) -> pd.DataFrame:
    """Loads and combines every daily file seen so far (cumulative history)."""
    folder = os.path.join(BASE_DIR, cfg["data"]["input_folder"])
    pattern = os.path.join(folder, cfg["data"]["file_pattern"])
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching {pattern} found.")

    frames = []
    for fp in files:
        df = pd.read_excel(fp)
        missing_cols = set(cfg["data"]["required_columns"]) - set(df.columns)
        if missing_cols:
            raise ValueError(f"{fp} is missing required columns: {missing_cols}")
        df["source_file"] = os.path.basename(fp)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined["PolicyStartDate"] = pd.to_datetime(combined["PolicyStartDate"])
    combined["ClaimDate"] = pd.to_datetime(combined["ClaimDate"])
    # if the same ClaimID appears in more than one file (re-sent/corrected row),
    # keep the most recently loaded version
    combined = combined.drop_duplicates(subset="ClaimID", keep="last").reset_index(drop=True)
    return combined, files[-1]


def score_and_flag(df, cfg):
    df = apply_all_rules(df, cfg)
    df = apply_ml_anomaly_detection(df, cfg)

    points_rule = cfg["scoring"]["points_per_rule"]
    points_ml = cfg["scoring"]["points_ml_anomaly"]

    df["total_score"] = (df["rule_score"] * points_rule) + \
                         (df["flag_ml_anomaly"].astype(int) * points_ml)
    df["is_flagged"] = df["total_score"] >= cfg["scoring"]["flag_threshold"]
    return df


def run():
    cfg = load_config()
    output_dir = os.path.join(BASE_DIR, "output")
    os.makedirs(output_dir, exist_ok=True)
    today_label = datetime.now().strftime("%Y-%m-%d")

    df, latest_file = load_all_claims(cfg)
    print(f"Loaded {len(df)} total claims across all files seen so far.")
    print(f"Most recent file: {os.path.basename(latest_file)}")

    df = score_and_flag(df, cfg)
    all_flagged = df[df["is_flagged"]].sort_values("total_score", ascending=False)

    # --- only alert on claims we haven't already notified on ---
    state_path = os.path.join(BASE_DIR, cfg["state"]["notified_claims_file"])
    already_notified = load_notified_ids(state_path)
    new_flags = all_flagged[~all_flagged["ClaimID"].isin(already_notified)]

    print(f"Total flagged (all-time): {len(all_flagged)} | "
          f"Already notified previously: {len(already_notified)} | "
          f"NEW today: {len(new_flags)}")

    # Save today's full report (everything flagged, for audit purposes)
    report_path = os.path.join(output_dir, f"fraud_report_{today_label}.xlsx")
    export_cols = ["ClaimID", "PolicyID", "ClaimantName", "ClaimType", "Region",
                   "ClaimAmount", "CoverageLimit", "rule_score", "flag_ml_anomaly",
                   "total_score", "is_flagged", "rule_reasons"]
    df_export = all_flagged[export_cols].copy()
    df_export["rule_reasons"] = df_export["rule_reasons"].apply(lambda x: "; ".join(x))
    df_export["previously_notified"] = all_flagged["ClaimID"].isin(already_notified)
    df_export.to_excel(report_path, index=False)
    print(f"Full flagged-claims report saved: {report_path}")

    if len(new_flags) > 0:
        notify(new_flags, cfg, today_label, output_dir)
        updated_ids = already_notified | set(new_flags["ClaimID"])
        save_notified_ids(state_path, updated_ids, today_label)
        print(f"State file updated — {len(updated_ids)} claim IDs now marked as notified.")
    else:
        print("No NEW claims flagged today — no notification sent.")

    return df_export, new_flags


if __name__ == "__main__":
    run()
