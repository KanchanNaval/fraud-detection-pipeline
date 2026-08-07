"""
Statistical anomaly layer on top of the rules. Isolation Forest is a good
starting point: it needs no labeled fraud history (which most teams don't
have yet), and it flags claims that are numerically unusual even if they
don't trip a named rule. As real confirmed-fraud labels accumulate over
future months, swap this for a supervised model (e.g. XGBoost) trained on
them for higher precision.
"""
import pandas as pd
from sklearn.ensemble import IsolationForest


def add_ml_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["days_since_policy_start"] = (df["ClaimDate"] - df["PolicyStartDate"]).dt.days
    df["amount_to_limit_ratio"] = df["ClaimAmount"] / df["CoverageLimit"]
    claim_counts = df.groupby("ClaimantName")["ClaimID"].transform("count")
    df["claimant_claim_count"] = claim_counts
    return df


def apply_ml_anomaly_detection(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = add_ml_features(df)

    if not cfg["ml"]["enabled"] or len(df) < cfg["ml"]["min_rows_required"]:
        df["flag_ml_anomaly"] = False
        df["ml_anomaly_score"] = 0.0
        return df

    features = df[["ClaimAmount", "days_since_policy_start",
                    "amount_to_limit_ratio", "claimant_claim_count"]].fillna(0)

    model = IsolationForest(
        contamination=cfg["ml"]["contamination"],
        random_state=42,
        n_estimators=200,
    )
    predictions = model.fit_predict(features)   # -1 = anomaly, 1 = normal
    scores = model.decision_function(features)  # lower = more anomalous

    df["flag_ml_anomaly"] = predictions == -1
    df["ml_anomaly_score"] = -scores  # flip so higher = more suspicious
    return df
