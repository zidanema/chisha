"""Shared feedback submission helpers for non-Web channels."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from chisha import feedback_store


_QUICK_PRESETS: dict[str, dict[str, Any]] = {
    "good": {
        "rating": 1,
        "reason_match": 0,
        "fullness": 1,
        "oil_calibration": 1,
        "repurchase_intent": 2,
    },
    "ok": {
        "rating": 0,
        "reason_match": 1,
        "fullness": 1,
        "oil_calibration": 1,
        "repurchase_intent": 1,
    },
    "bad": {
        "rating": -1,
        "reason_match": 2,
        "fullness": 1,
        "oil_calibration": 2,
        "repurchase_intent": 0,
    },
}


def submit_quick_feedback(root: Path, session_id: str, preset: str, note: str = "") -> dict:
    """Submit a Feishu quick feedback preset into the canonical feedback store."""
    data = feedback_store.load_store(root)
    accepted = feedback_store.get_accepted(data, session_id)
    if accepted is None:
        raise ValueError(f"session 未选择，不能反馈: {session_id}")

    if preset == "not-eaten":
        payload = {
            "session_id": session_id,
            "accepted_rank": None,
            "rating": None,
            "reason_match": None,
            "fullness": None,
            "oil_calibration": None,
            "repurchase_intent": None,
            "note": note,
            "variant": "not-eaten",
            "quick": True,
        }
        return feedback_store.record_feedback(root, payload)

    defaults = _QUICK_PRESETS.get(preset)
    if defaults is None:
        raise ValueError(f"unknown feedback preset: {preset}")

    payload = {
        "session_id": session_id,
        "accepted_rank": accepted.get("accepted_rank"),
        **defaults,
        "note": note,
        "variant": "progressive",
        "quick": True,
    }
    _validate_progressive_payload(payload)
    return feedback_store.record_feedback(root, payload)


def _validate_progressive_payload(payload: dict[str, Any]) -> None:
    if payload.get("accepted_rank") is None:
        raise ValueError("progressive feedback requires accepted_rank")
    if payload.get("rating") not in (-1, 0, 1):
        raise ValueError("rating must be -1, 0 or 1")
    for key in ("reason_match", "fullness", "oil_calibration", "repurchase_intent"):
        if payload.get(key) not in (0, 1, 2):
            raise ValueError(f"{key} must be 0, 1 or 2")
