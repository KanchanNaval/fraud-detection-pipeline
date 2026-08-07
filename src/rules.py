"""
Rule-based fraud checks. Each function returns a boolean Series aligned to
the dataframe index, plus a reason string used in the notification.
Add new rules here as the business team identifies new patterns.
"""
import pandas as pd


def flag_early_claims(df: pd.DataFrame, days_threshold: int) -> pd.Series:
    days_since_start = (df["ClaimDate"] - df["PolicyStartDate"]).dt.days
    return days_since_start <= days_threshold


def flag_high_amount(df: pd.DataFrame, ratio_threshold: float) -> pd.Series:
    return df["ClaimAmount"] >= (df["CoverageLimit"] * ratio_threshold)


def flag_duplicates(df: pd.DataFrame, window_days: int) -> pd.Series:
    """Same policy + same claim amount, filed within `window_days` of each other."""
    flags = pd.Series(False, index=df.index)
    grouped = df.groupby(["PolicyID", "ClaimAmount"])
    for _, group in grouped:
        if len(group) < 2:
            continue
        dates = group.sort_values("ClaimDate")["ClaimDate"]
        gaps = dates.diff().dt.days
        close_pairs = gaps <= window_days
        if close_pairs.any():
            flags.loc[group.index] = True
    return flags


def flag_frequency(df: pd.DataFrame, window_days: int, count_threshold: int) -> pd.Series:
    """Same claimant filing >= count_threshold claims within a trailing window."""
    flags = pd.Series(False, index=df.index)
    for claimant, group in df.groupby("ClaimantName"):
        dates = group.sort_values("ClaimDate")
        for idx, row in dates.iterrows():
            window_start = row["ClaimDate"] - pd.Timedelta(days=window_days)
            in_window = dates[(dates["ClaimDate"] >= window_start) &
                               (dates["ClaimDate"] <= row["ClaimDate"])]
            if len(in_window) >= count_threshold:
                flags.loc[in_window.index] = True
    return flags


def flag_data_integrity(df: pd.DataFrame) -> pd.Series:
    """Impossible data: claim filed before policy even started, or missing key fields."""
    missing = df[["ClaimantName", "PolicyID", "ClaimAmount"]].isna().any(axis=1)
    impossible_date = df["ClaimDate"] < df["PolicyStartDate"]
    return missing | impossible_date


def apply_all_rules(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Runs every rule and attaches boolean columns + a combined reasons column."""
    df = df.copy()
    df["flag_early_claim"] = flag_early_claims(df, cfg["rules"]["early_claim_days"])
    df["flag_high_amount"] = flag_high_amount(df, cfg["rules"]["high_amount_ratio"])
    df["flag_duplicate"] = flag_duplicates(df, cfg["rules"]["duplicate_window_days"])
    df["flag_frequency"] = flag_frequency(
        df, cfg["rules"]["frequency_window_days"], cfg["rules"]["frequency_threshold"]
    )
    df["flag_data_integrity"] = flag_data_integrity(df)

    reason_map = {
        "flag_early_claim": "Claim filed shortly after policy start",
        "flag_high_amount": "Claim amount close to/over coverage limit",
        "flag_duplicate": "Possible duplicate claim (same policy & amount)",
        "flag_frequency": "Unusually high claim frequency for this claimant",
        "flag_data_integrity": "Data integrity issue (missing fields / impossible dates)",
    }

    def build_reasons(row):
        return [reason for col, reason in reason_map.items() if row[col]]

    df["rule_reasons"] = df.apply(build_reasons, axis=1)
    df["rule_score"] = df[list(reason_map.keys())].sum(axis=1)
    return df
