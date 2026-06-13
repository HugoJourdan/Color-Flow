"""Trial + Lemon Squeezy license gating for Dynamic Anchors.

Cocoa-free and unit-tested. The Glyphs-aware glue (urllib, NSAlert,
Glyphs.defaults storage) lives in plugin.py and calls into this module.

Two pieces of persisted state, each stored as a JSON string under its own
Glyphs.defaults key:
  - TrialState: when the user first ran the plugin on this machine.
  - LicenseState: cached Lemon Squeezy activation, refreshed periodically.

`resolve_entitlement(license_state, trial_state, now=...)` is the single
gate the plugin uses to decide whether to enable rule evaluation.

Lemon Squeezy reference: https://docs.lemonsqueezy.com/api/license-api
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, TypedDict, cast

LEMON_SQUEEZY_API = "https://api.lemonsqueezy.com/v1"
ACTIVATE_URL = f"{LEMON_SQUEEZY_API}/licenses/activate"
VALIDATE_URL = f"{LEMON_SQUEEZY_API}/licenses/validate"
DEACTIVATE_URL = f"{LEMON_SQUEEZY_API}/licenses/deactivate"

DEFAULT_TRIAL_DAYS = 30
DEFAULT_REVALIDATE_DAYS = 7
DEFAULT_GRACE_DAYS = 30

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_EXPIRED = "expired"
STATUS_DISABLED = "disabled"


class HttpResponse(TypedDict):
    status: int
    body: dict[str, Any]


HttpTransport = Callable[[str, str, dict[str, str]], HttpResponse]


# ---------- state objects ----------


@dataclass(frozen=True)
class TrialState:
    """When the user first launched the plugin on this machine."""

    started_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {"started_at": self.started_at.isoformat()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrialState | None":
        try:
            return cls(started_at=_parse_iso(data["started_at"]))
        except (KeyError, TypeError, ValueError):
            return None


@dataclass(frozen=True)
class LicenseState:
    """Cached Lemon Squeezy activation, refreshed on a schedule."""

    key: str
    instance_id: str
    instance_name: str
    status: str
    last_validated: datetime
    activation_limit: int | None = None
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "status": self.status,
            "last_validated": self.last_validated.isoformat(),
            "activation_limit": self.activation_limit,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LicenseState | None":
        try:
            expires_raw = data.get("expires_at")
            return cls(
                key=str(data["key"]),
                instance_id=str(data["instance_id"]),
                instance_name=str(data["instance_name"]),
                status=str(data["status"]),
                last_validated=_parse_iso(data["last_validated"]),
                activation_limit=data.get("activation_limit"),
                expires_at=_parse_iso(expires_raw) if expires_raw else None,
            )
        except (KeyError, TypeError, ValueError):
            return None


# ---------- entitlement (the gate the plugin calls) ----------


EntitlementKind = Literal["licensed", "trial", "trial_expired", "unlicensed"]


@dataclass(frozen=True)
class Entitlement:
    kind: EntitlementKind
    trial_days_remaining: int | None = None
    expires_on: datetime | None = None
    reason: str | None = None

    @property
    def allows_use(self) -> bool:
        return self.kind in ("licensed", "trial")


def resolve_entitlement(
    license_state: LicenseState | None,
    trial_state: TrialState | None,
    *,
    now: datetime | None = None,
    trial_duration_days: int = DEFAULT_TRIAL_DAYS,
    grace_days: int = DEFAULT_GRACE_DAYS,
) -> Entitlement:
    """Decide whether the user is allowed to use the plugin right now."""
    current = now or _utcnow()
    if is_license_active(license_state, now=current, grace_days=grace_days):
        assert license_state is not None
        return Entitlement(kind="licensed", expires_on=license_state.expires_at)
    if trial_state is not None:
        remaining = trial_remaining(trial_state, now=current, duration_days=trial_duration_days)
        trial_end = trial_state.started_at + timedelta(days=trial_duration_days)
        if remaining > timedelta(0):
            return Entitlement(
                kind="trial",
                trial_days_remaining=_ceil_days(remaining),
                expires_on=trial_end,
            )
        return Entitlement(
            kind="trial_expired",
            trial_days_remaining=0,
            expires_on=trial_end,
            reason="Trial expired",
        )
    return Entitlement(kind="unlicensed", reason="No trial started")


# ---------- trial helpers ----------


def start_trial(*, now: datetime | None = None) -> TrialState:
    """Stamp the start-of-trial timestamp. Caller persists the result."""
    return TrialState(started_at=now or _utcnow())


def trial_remaining(
    state: TrialState,
    *,
    now: datetime | None = None,
    duration_days: int = DEFAULT_TRIAL_DAYS,
) -> timedelta:
    """How much trial time is left. Returns timedelta(0) if expired."""
    elapsed = (now or _utcnow()) - state.started_at
    remaining = timedelta(days=duration_days) - elapsed
    return remaining if remaining > timedelta(0) else timedelta(0)


def trial_active(
    state: TrialState,
    *,
    now: datetime | None = None,
    duration_days: int = DEFAULT_TRIAL_DAYS,
) -> bool:
    return trial_remaining(state, now=now, duration_days=duration_days) > timedelta(0)


# ---------- license helpers ----------


def is_license_active(
    state: LicenseState | None,
    *,
    now: datetime | None = None,
    grace_days: int = DEFAULT_GRACE_DAYS,
) -> bool:
    """True when the cached license state still entitles the user."""
    if state is None:
        return False
    if state.status != STATUS_ACTIVE:
        return False
    current = now or _utcnow()
    if state.expires_at is not None and state.expires_at <= current:
        return False
    return (current - state.last_validated) < timedelta(days=grace_days)


def should_revalidate(
    state: LicenseState,
    *,
    now: datetime | None = None,
    interval_days: int = DEFAULT_REVALIDATE_DAYS,
) -> bool:
    elapsed = (now or _utcnow()) - state.last_validated
    return elapsed >= timedelta(days=interval_days)


# ---------- Lemon Squeezy API ----------


@dataclass(frozen=True)
class ActivationSuccess:
    state: LicenseState


@dataclass(frozen=True)
class ActivationFailure:
    reason: str
    http_status: int


ActivationOutcome = ActivationSuccess | ActivationFailure


@dataclass(frozen=True)
class ValidationSuccess:
    state: LicenseState


@dataclass(frozen=True)
class ValidationFailure:
    reason: str
    http_status: int
    network_error: bool = False


ValidationOutcome = ValidationSuccess | ValidationFailure


@dataclass(frozen=True)
class DeactivationSuccess:
    pass


@dataclass(frozen=True)
class DeactivationFailure:
    reason: str
    http_status: int


DeactivationOutcome = DeactivationSuccess | DeactivationFailure


def activate(
    key: str,
    instance_name: str,
    *,
    http: HttpTransport,
    now: datetime | None = None,
) -> ActivationOutcome:
    """POST /licenses/activate. Returns ActivationSuccess(state) on 200+activated=True."""
    try:
        response = http(
            "POST",
            ACTIVATE_URL,
            {"license_key": key, "instance_name": instance_name},
        )
    except Exception as exc:
        return ActivationFailure(reason=str(exc) or "network error", http_status=0)
    body = response["body"]
    if response["status"] >= 400 or not body.get("activated"):
        return ActivationFailure(reason=_extract_error(body), http_status=response["status"])
    state = _state_from_response(body, key=key, now=now or _utcnow())
    if state is None:
        return ActivationFailure(
            reason="Malformed response from license server",
            http_status=response["status"],
        )
    return ActivationSuccess(state=state)


def validate(
    state: LicenseState,
    *,
    http: HttpTransport,
    now: datetime | None = None,
) -> ValidationOutcome:
    """POST /licenses/validate. Refreshes state on success; flags network_error on transport raise."""
    try:
        response = http(
            "POST",
            VALIDATE_URL,
            {"license_key": state.key, "instance_id": state.instance_id},
        )
    except Exception as exc:
        return ValidationFailure(
            reason=str(exc) or "network error",
            http_status=0,
            network_error=True,
        )
    body = response["body"]
    if response["status"] >= 400 or not body.get("valid"):
        return ValidationFailure(reason=_extract_error(body), http_status=response["status"])
    refreshed = _state_from_response(body, key=state.key, now=now or _utcnow())
    if refreshed is None:
        return ValidationFailure(
            reason="Malformed response from license server",
            http_status=response["status"],
        )
    return ValidationSuccess(state=refreshed)


def deactivate(
    state: LicenseState,
    *,
    http: HttpTransport,
) -> DeactivationOutcome:
    """POST /licenses/deactivate. Frees the seat so the key can move to another machine."""
    try:
        response = http(
            "POST",
            DEACTIVATE_URL,
            {"license_key": state.key, "instance_id": state.instance_id},
        )
    except Exception as exc:
        return DeactivationFailure(reason=str(exc) or "network error", http_status=0)
    body = response["body"]
    if response["status"] >= 400 or not body.get("deactivated"):
        return DeactivationFailure(reason=_extract_error(body), http_status=response["status"])
    return DeactivationSuccess()


# ---------- (de)serialization for Glyphs.defaults ----------


def serialize_trial(state: TrialState | None) -> str | None:
    return json.dumps(state.to_dict()) if state else None


def deserialize_trial(payload: str | None) -> TrialState | None:
    data = _load_json_dict(payload)
    return TrialState.from_dict(data) if data is not None else None


def serialize_license(state: LicenseState | None) -> str | None:
    return json.dumps(state.to_dict()) if state else None


def deserialize_license(payload: str | None) -> LicenseState | None:
    data = _load_json_dict(payload)
    return LicenseState.from_dict(data) if data is not None else None


# ---------- internals ----------


def _state_from_response(body: dict[str, Any], *, key: str, now: datetime) -> LicenseState | None:
    license_key_raw = body.get("license_key")
    instance_raw = body.get("instance")
    if not isinstance(license_key_raw, dict) or not isinstance(instance_raw, dict):
        return None
    license_key_obj = cast(dict[str, Any], license_key_raw)
    instance_obj = cast(dict[str, Any], instance_raw)
    instance_id: Any = instance_obj.get("id")
    if not instance_id:
        return None
    expires_raw: Any = license_key_obj.get("expires_at")
    try:
        expires = _parse_iso(expires_raw) if expires_raw else None
    except (TypeError, ValueError):
        return None
    activation_limit_raw: Any = license_key_obj.get("activation_limit")
    activation_limit: int | None
    if activation_limit_raw is None:
        activation_limit = None
    elif isinstance(activation_limit_raw, int):
        activation_limit = activation_limit_raw
    else:
        try:
            activation_limit = int(activation_limit_raw)
        except (TypeError, ValueError):
            activation_limit = None
    return LicenseState(
        key=key,
        instance_id=str(instance_id),
        instance_name=str(instance_obj.get("name", "")),
        status=str(license_key_obj.get("status", STATUS_ACTIVE)),
        last_validated=now,
        activation_limit=activation_limit,
        expires_at=expires,
    )


def _extract_error(body: dict[str, Any]) -> str:
    err: Any = body.get("error")
    if isinstance(err, str) and err:
        return err
    if isinstance(err, dict):
        err_dict = cast(dict[str, Any], err)
        message: Any = err_dict.get("message") or err_dict.get("detail")
        if message:
            return str(message)
    return "Unknown error"


def _parse_iso(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse datetime from {type(value).__name__}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ceil_days(delta: timedelta) -> int:
    seconds = delta.total_seconds()
    if seconds <= 0:
        return 0
    return -(-int(seconds) // 86400)


def _load_json_dict(payload: str | None) -> dict[str, Any] | None:
    if not payload:
        return None
    try:
        loaded: Any = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return cast(dict[str, Any], loaded)
