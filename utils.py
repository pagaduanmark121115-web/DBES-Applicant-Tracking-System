"""
utils.py
Small shared helper functions used across pages.
"""

from datetime import date, datetime
import pandas as pd


def parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def days_since(date_applied, as_of=None) -> int:
    applied = parse_date(date_applied)
    if applied is None:
        return 0
    as_of = as_of or date.today()
    return (as_of - applied).days


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")
