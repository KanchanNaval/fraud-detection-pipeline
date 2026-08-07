"""
Generates 3 consecutive daily claims files — simulates what the business
team would send each day. Demonstrates that duplicate/frequency patterns
spanning multiple days get caught, and that already-notified claims don't
trigger repeat alerts.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

random.seed(7)
np.random.seed(7)

claim_types = ["Auto", "Health", "Property", "Life", "Travel"]
regions = ["North", "South", "East", "West", "Central"]
policy_pool = [f"POL{1000+i}" for i in range(60)]
claimant_pool = [f"Claimant_{i}" for i in range(60)]

def random_claim(claim_id, policy_id=None, claimant=None, claim_date=None, amount=None):
    idx = policy_pool.index(policy_id) if policy_id else random.randrange(len(policy_pool))
    policy_id = policy_id or policy_pool[idx]
    claimant = claimant or claimant_pool[idx]
    claim_type = random.choice(claim_types)
    policy_start = datetime(2025, 1, 1) + timedelta(days=random.randint(0, 400))
    claim_date = claim_date or (policy_start + timedelta(days=random.randint(10, 500)))
    coverage_limit = random.choice([50000, 100000, 200000, 500000])
    base_amount = {"Auto": 8000, "Health": 15000, "Property": 25000,
                    "Life": 100000, "Travel": 3000}[claim_type]
    claim_amount = amount if amount else max(500, np.random.normal(base_amount, base_amount * 0.35))
    return {
        "ClaimID": claim_id, "PolicyID": policy_id, "ClaimantName": claimant,
        "ClaimType": claim_type, "Region": random.choice(regions),
        "PolicyStartDate": policy_start.date(), "ClaimDate": claim_date.date(),
        "ClaimAmount": round(claim_amount, 2), "CoverageLimit": coverage_limit,
    }

today = datetime(2026, 8, 8)
day_labels = [(today - timedelta(days=2)).strftime("%Y-%m-%d"),
              (today - timedelta(days=1)).strftime("%Y-%m-%d"),
              today.strftime("%Y-%m-%d")]

# --- Day 1: normal batch of claims ---
day1 = [random_claim(f"CLM{30000+i}") for i in range(40)]
# a claim near coverage limit
day1[5]["CoverageLimit"] = 60000
day1[5]["ClaimAmount"] = 58500.0
pd.DataFrame(day1).to_excel(f"/home/claude/fraud_pipeline/data/daily_claims_{day_labels[0]}.xlsx", index=False)

# --- Day 2: includes a claim frequency pattern starting ---
day2 = [random_claim(f"CLM{30100+i}") for i in range(35)]
# same claimant starts filing multiple claims
freq_policy, freq_claimant = policy_pool[8], claimant_pool[8]
day2.append(random_claim("CLM30900", freq_policy, freq_claimant, datetime(2026, 8, 5)))
day2.append(random_claim("CLM30901", freq_policy, freq_claimant, datetime(2026, 8, 6)))
pd.DataFrame(day2).to_excel(f"/home/claude/fraud_pipeline/data/daily_claims_{day_labels[1]}.xlsx", index=False)

# --- Day 3 (today): frequency pattern completes + a fresh duplicate + early claim ---
day3 = [random_claim(f"CLM{30200+i}") for i in range(30)]
day3.append(random_claim("CLM30902", freq_policy, freq_claimant, datetime(2026, 8, 7)))  # 3rd claim -> frequency flag trips today
# duplicate claim (same policy + amount as an existing one, filed today)
dup_source = day1[10]
day3.append(random_claim("CLM30950", dup_source["PolicyID"],
                          claimant_pool[policy_pool.index(dup_source["PolicyID"])],
                          today, dup_source["ClaimAmount"]))
# brand-new early claim
early_policy_idx = 45
day3.append({
    "ClaimID": "CLM30960", "PolicyID": policy_pool[early_policy_idx],
    "ClaimantName": claimant_pool[early_policy_idx], "ClaimType": "Property",
    "Region": "East", "PolicyStartDate": datetime(2026, 8, 1).date(),
    "ClaimDate": datetime(2026, 8, 4).date(), "ClaimAmount": 38000.0,
    "CoverageLimit": 45000,
})
pd.DataFrame(day3).to_excel(f"/home/claude/fraud_pipeline/data/daily_claims_{day_labels[2]}.xlsx", index=False)

print("Created 3 daily files:", day_labels)
