"""User interaction usage ingestion.

The monitor stores IF-01 observations from the kiosk/UI. It does not send
commands or participate in mission control.
"""

from __future__ import annotations

import logging

import db


logger = logging.getLogger("monitor.usage")


def record_information(payload: dict) -> None:
    request_type = payload.get("request_type")
    if request_type not in {"INTERACTING", "ESCORT", "CANCEL"}:
        logger.warning("unknown IF-01 request_type: %s", payload)
        return
    if request_type == "CANCEL":
        return

    customer = payload.get("customer") or {}
    language = customer.get("language") or payload.get("customer_language")
    profile = customer.get("profile") or payload.get("customer_profile")
    at = payload.get("timestamp") or db.utc_now_iso()
    escort_used = 1 if request_type == "ESCORT" else 0

    db.execute(
        "INSERT INTO ui_usage_log(source, language, customer_profile, escort_used, at) "
        "VALUES (?, ?, ?, ?, ?)",
        (request_type, language, profile, escort_used, at),
    )
    logger.info("usage %s language=%s profile=%s", request_type, language, profile)
