"""Fetch historical body position from Owlet sleep-data API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from pyowletapi.const import REGION_INFO

from .const import decode_body_position

_LOGGER = logging.getLogger(__name__)

FIRESTORE_PROJECT = "owletcare-prod"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{FIRESTORE_PROJECT}"
    "/databases/(default)/documents"
)


@dataclass(frozen=True)
class ProfileContext:
    """Owlet baby profile linked to a sock."""

    account_key: str
    profile_id: str
    device_version: str


def _sleep_data_host(region: str) -> str:
    endpoint = "" if region == "world" else ".eu"
    return f"https://sleep-data{endpoint}.owletdata.com"


async def get_firebase_id_token(
    session: aiohttp.ClientSession, region: str, refresh_token: str
) -> tuple[str, str]:
    """Refresh Firebase credentials and return (id_token, user_id)."""
    api_key = REGION_INFO[region]["apiKey"]
    async with session.post(
        f"https://securetoken.googleapis.com/v1/token?key={api_key}",
        data={"grantType": "refresh_token", "refreshToken": refresh_token},
        headers={
            "X-Android-Package": "com.owletcare.owletcare",
            "X-Android-Cert": "2A3BC26DB0B8B0792DBE28E6FFDC2598F9B12B74",
        },
    ) as response:
        response.raise_for_status()
        payload = await response.json()

    id_token = payload["id_token"]
    user_id = payload["user_id"]
    return id_token, user_id


def _string_field(document: dict[str, Any], field: str) -> str | None:
    fields = document.get("fields", {})
    value = fields.get(field, {})
    if "stringValue" in value:
        return value["stringValue"]
    return None


async def _run_firestore_query(
    session: aiohttp.ClientSession,
    id_token: str,
    structured_query: dict[str, Any],
) -> list[dict[str, Any]]:
    async with session.post(
        f"{FIRESTORE_BASE}:runQuery",
        headers={"Authorization": f"Bearer {id_token}"},
        json={"structuredQuery": structured_query},
    ) as response:
        if response.status != 200:
            text = await response.text()
            raise aiohttp.ClientResponseError(
                response.request_info,
                response.history,
                status=response.status,
                message=text,
            )
        rows = await response.json()

    documents: list[dict[str, Any]] = []
    for row in rows:
        document = row.get("document")
        if document:
            documents.append(document)
    return documents


async def resolve_profile_for_dsn(
    session: aiohttp.ClientSession,
    region: str,
    refresh_token: str,
    dsn: str,
    device_version: str,
) -> ProfileContext | None:
    """Look up the baby profile associated with a sock DSN."""
    try:
        id_token, user_id = await get_firebase_id_token(session, region, refresh_token)
    except aiohttp.ClientError as err:
        _LOGGER.debug("Firebase token refresh failed for body position: %s", err)
        return None

    try:
        devices = await _run_firestore_query(
            session,
            id_token,
            {
                "from": [{"collectionId": "devices"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "dsn"},
                        "op": "EQUAL",
                        "value": {"stringValue": dsn},
                    }
                },
                "limit": 1,
            },
        )
    except aiohttp.ClientError as err:
        _LOGGER.debug("Firestore device lookup failed for %s: %s", dsn, err)
        return None

    if not devices:
        _LOGGER.debug("No Firestore device document found for DSN %s", dsn)
        return None

    device_doc = devices[0]
    device_id = device_doc["name"].rsplit("/", 1)[-1]
    account_key = _string_field(device_doc, "accountKey") or user_id

    try:
        services = await _run_firestore_query(
            session,
            id_token,
            {
                "from": [{"collectionId": "services"}],
                "where": {
                    "fieldFilter": {
                        "field": {"fieldPath": "deviceKey"},
                        "op": "EQUAL",
                        "value": {"stringValue": device_id},
                    }
                },
                "limit": 1,
            },
        )
    except aiohttp.ClientError as err:
        _LOGGER.debug("Firestore service lookup failed for device %s: %s", device_id, err)
        return None

    profile_id: str | None = None
    if services:
        service_user_keys = (
            services[0].get("fields", {}).get("serviceUserKeys", {}).get("mapValue", {})
        )
        for key, value in service_user_keys.get("fields", {}).items():
            if value.get("booleanValue"):
                profile_id = key
                break

    if profile_id is None:
        try:
            profiles = await _run_firestore_query(
                session,
                id_token,
                {
                    "from": [{"collectionId": "serviceUsers"}],
                    "where": {
                        "fieldFilter": {
                            "field": {"fieldPath": "accountKey"},
                            "op": "EQUAL",
                            "value": {"stringValue": account_key},
                        }
                    },
                    "limit": 1,
                },
            )
        except aiohttp.ClientError as err:
            _LOGGER.debug(
                "Firestore profile lookup failed for account %s: %s", account_key, err
            )
            return None

        if not profiles:
            _LOGGER.debug("No serviceUsers profile found for account %s", account_key)
            return None

        profile_id = profiles[0]["name"].rsplit("/", 1)[-1]

    return ProfileContext(
        account_key=account_key,
        profile_id=profile_id,
        device_version=device_version or "SS3",
    )


async def fetch_latest_body_position(
    session: aiohttp.ClientSession,
    region: str,
    refresh_token: str,
    dsn: str,
    device_version: str,
    profile: ProfileContext | None = None,
    lookback_hours: int = 4,
) -> str | None:
    """Return the latest decoded body position for a sock, if available."""
    if profile is None:
        profile = await resolve_profile_for_dsn(
            session, region, refresh_token, dsn, device_version
        )
    if profile is None:
        return None

    try:
        id_token, _user_id = await get_firebase_id_token(session, region, refresh_token)
    except aiohttp.ClientError as err:
        _LOGGER.debug("Firebase token refresh failed for sleep-data: %s", err)
        return None

    end = datetime.now(tz=UTC)
    start = end - timedelta(hours=lookback_hours)
    timezone = datetime.now(tz=ZoneInfo("localtime")).tzinfo
    timezone_name = getattr(timezone, "key", "UTC")

    params = {
        "startTime": str(int(start.timestamp())),
        "endTime": str(int(end.timestamp())),
        "timeZone": timezone_name,
        "version": profile.device_version,
        "returnBodyPositions": "true",
    }
    url = (
        f"{_sleep_data_host(region)}/v1/accounts/{profile.account_key}"
        f"/profiles/{profile.profile_id}/sleep"
    )

    try:
        async with session.get(
            url,
            params=params,
            headers={"Authorization": id_token},
        ) as response:
            if response.status != 200:
                text = await response.text()
                _LOGGER.debug(
                    "sleep-data request failed (%s): %s", response.status, text
                )
                return None
            payload = await response.json()
    except aiohttp.ClientError as err:
        _LOGGER.debug("sleep-data request error: %s", err)
        return None

    data = payload.get("data") or {}
    position_times = data.get("positionTimes") or []
    body_positions = data.get("bodyPositions") or []

    if not position_times or not body_positions:
        return None

    latest_code = body_positions[-1]
    return decode_body_position(int(latest_code))
