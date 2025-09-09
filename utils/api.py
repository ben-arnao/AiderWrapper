"""External API helpers.

Network calls to services like OpenAI live in this module so they can be
mocked cleanly during testing and kept separate from other utilities.
"""
from datetime import date, timedelta  # Compute date ranges for API calls
from typing import Callable

import requests


def verify_api_key(api_key: str, request_fn: Callable = requests.get) -> bool:
    """Call OpenAI API to ensure the provided key is valid."""
    if not api_key:
        raise ValueError("API key not provided")

    resp = request_fn(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if resp.status_code == 200:
        return True
    # Surface details so the caller can display them to the user
    raise ValueError(
        f"API key validation failed: {resp.status_code} {getattr(resp, 'text', '')}"
    )


def fetch_usage_data(api_key: str, days: int = 30, request_fn: Callable = requests.get) -> dict:
    """Return spending and credit data from the OpenAI billing API."""
    headers = {"Authorization": f"Bearer {api_key}"}

    end = date.today()
    start = end - timedelta(days=days)
    usage_resp = request_fn(
        "https://api.openai.com/v1/dashboard/billing/usage",
        headers=headers,
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    if usage_resp.status_code != 200:
        raise ValueError(getattr(usage_resp, "text", "usage request failed"))
    total_spent = usage_resp.json().get("total_usage", 0) / 100.0  # convert cents to dollars

    credits_resp = request_fn(
        "https://api.openai.com/v1/dashboard/billing/credit_grants",
        headers=headers,
    )
    if credits_resp.status_code != 200:
        raise ValueError(getattr(credits_resp, "text", "credits request failed"))
    credits = credits_resp.json()
    total_granted = credits.get("total_granted", 0)
    total_used = credits.get("total_used", 0)
    total_available = credits.get("total_available", 0)

    pct_used = (total_used / total_granted * 100) if total_granted else 0

    return {
        "total_spent": total_spent,
        "credits_total": total_granted,
        "credits_remaining": total_available,
        "pct_credits_used": pct_used,
    }
