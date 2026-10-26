from typing import Literal

# Labels verified in the imported Yahoo player payload's status_full field.
YAHOO_STATUS_LABELS = {
    "O": "Out (short-term injury)",
    "NA": "Not Active",
    "P": "Probable",
    "Q": "Questionable",
}
UNAVAILABLE_YAHOO_STATUSES = frozenset({"O", "NA"})
SUPPORTED_YAHOO_STATUSES = frozenset({"O", "NA", "P", "Q"})


def recommendation_eligibility(status: str | None) -> Literal["excluded", "uncertain", "unknown"]:
    if status in UNAVAILABLE_YAHOO_STATUSES:
        return "excluded"
    if status in {"P", "Q"}:
        return "uncertain"
    return "unknown"


def status_is_supported(status: str | None) -> bool:
    return status in SUPPORTED_YAHOO_STATUSES


def yahoo_status_reason(status: str | None) -> str:
    label = YAHOO_STATUS_LABELS.get(status, status or "Unknown")
    if recommendation_eligibility(status) == "excluded":
        return f"Current Yahoo status: {label}. Not eligible for normal recommendation. Historical value is shown for reference."
    if status in {"P", "Q"}:
        return f"Current Yahoo status: {label}. Recommendation permitted with status uncertainty; no injury forecast is implemented."
    return f"Current Yahoo status: {label}. Availability is unknown, not confirmed healthy."
