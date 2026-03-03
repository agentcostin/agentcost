"""
AgentCost License Key System

Validates license keys for enterprise feature activation.

Key types:
  - Community: No key needed (all core features available)
  - Trial:     Self-service 30-day trial via CLI
  - Enterprise: Paid license key (generated separately, contact open@agentcost.in)

Configuration:
  AGENTCOST_LICENSE_KEY=AC-xxxx-xxxx   (env var)
  or place in ~/.agentcost/license.key  (file)

The license key encodes:
  - Key type (trial / enterprise)
  - Max users (0 = unlimited)
  - Expiry date
  - HMAC signature (prevents tampering)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agentcost.license")

# ── Constants ────────────────────────────────────────────────────────────────

LICENSE_ENV_VAR = "AGENTCOST_LICENSE_KEY"
LICENSE_FILE_PATHS = [
    Path.home() / ".agentcost" / "license.key",
    Path("license.key"),  # project root
]

# HMAC key for signing — in production, use a proper secret management system.
# This key is used to sign trial keys locally. Enterprise keys are signed
# server-side and validated here.
_SIGNING_KEY = os.environ.get(
    "AGENTCOST_LICENSE_SECRET",
    "agentcost-v1-default-signing-key-change-in-production"
).encode()

# ── License Data ─────────────────────────────────────────────────────────────

@dataclass
class License:
    """Parsed and validated license."""
    valid: bool = False
    tier: str = "community"           # community | trial | enterprise
    max_users: int = 5                # 0 = unlimited
    expires_at: Optional[datetime] = None
    licensed_to: str = ""
    features: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def days_remaining(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def is_enterprise(self) -> bool:
        return self.valid and self.tier in ("enterprise", "trial") and not self.is_expired

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "tier": self.tier,
            "max_users": self.max_users,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "days_remaining": self.days_remaining,
            "licensed_to": self.licensed_to,
            "features": self.features,
            "is_expired": self.is_expired,
            "error": self.error,
        }


# ── Community License (always valid) ────────────────────────────────────────

COMMUNITY_LICENSE = License(
    valid=True,
    tier="community",
    max_users=5,
    expires_at=None,
    licensed_to="Community User",
    features=["tracing", "dashboard", "forecasting", "optimizer",
              "analytics", "estimator", "plugins", "cli", "otel_export"],
)

ENTERPRISE_FEATURES = [
    "auth", "org", "budget_enforcement", "policy_engine",
    "notifications", "anomaly_detection", "gateway", "event_bus",
]


# ── Key Validation ───────────────────────────────────────────────────────────

def _sign(payload: str) -> str:
    """HMAC-SHA256 signature for a payload."""
    return hmac.new(_SIGNING_KEY, payload.encode(), hashlib.sha256).hexdigest()[:16]


def generate_trial_key(days: int = 30, max_users: int = 10) -> str:
    """Generate a self-service trial license key (local signing)."""
    import base64
    expires = datetime.utcnow() + timedelta(days=days)
    payload = json.dumps({
        "t": "trial",
        "u": max_users,
        "e": expires.strftime("%Y%m%d"),
        "l": "Trial User",
    }, separators=(",", ":"))

    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = _sign(payload)
    return f"AC-{sig}-{encoded}"

def _parse_key(key: str) -> License:
    """Parse and validate a license key string."""
    key = key.strip()

    if not key.startswith("AC-"):
        return License(valid=False, error="Invalid key format: must start with AC-")

    parts = key[3:]  # remove "AC-"
    dash_pos = parts.find("-")
    if dash_pos == -1:
        return License(valid=False, error="Invalid key format: missing signature")

    sig = parts[:dash_pos]
    encoded = parts[dash_pos + 1:]

    # Decode payload
    import base64
    try:
        # Restore padding
        padded = encoded + "=" * (4 - len(encoded) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded)
        payload = payload_bytes.decode()
        data = json.loads(payload)
    except Exception as e:
        return License(valid=False, error=f"Invalid key: decode failed ({e})")

    # Verify signature
    expected_sig = _sign(payload)
    if not hmac.compare_digest(sig, expected_sig):
        return License(valid=False, error="Invalid key: signature mismatch")

    # Parse fields
    tier = data.get("t", "community")
    max_users = data.get("u", 5)
    licensed_to = data.get("l", "")
    features = data.get("f", ENTERPRISE_FEATURES if tier == "enterprise" else [])

    try:
        expires_at = datetime.strptime(data["e"], "%Y%m%d")
    except (KeyError, ValueError):
        return License(valid=False, error="Invalid key: bad expiry date")

    lic = License(
        valid=True,
        tier=tier,
        max_users=max_users,
        expires_at=expires_at,
        licensed_to=licensed_to,
        features=features,
    )

    if lic.is_expired:
        lic.error = f"License expired on {expires_at.strftime('%Y-%m-%d')}"
        lic.valid = False

    return lic


# ── Key Loading ──────────────────────────────────────────────────────────────

def _load_key_from_env() -> Optional[str]:
    """Load license key from environment variable."""
    return os.environ.get(LICENSE_ENV_VAR)


def _load_key_from_file() -> Optional[str]:
    """Load license key from file."""
    for path in LICENSE_FILE_PATHS:
        try:
            if path.exists():
                key = path.read_text().strip()
                if key:
                    logger.debug(f"License key loaded from {path}")
                    return key
        except Exception:
            continue
    return None


# ── Public API ───────────────────────────────────────────────────────────────

_cached_license: Optional[License] = None


def get_license() -> License:
    """Get the current license (cached after first call)."""
    global _cached_license
    if _cached_license is not None:
        return _cached_license

    # Try env var first, then file
    key = _load_key_from_env() or _load_key_from_file()

    if not key:
        logger.debug("No license key found — using community edition")
        _cached_license = COMMUNITY_LICENSE
        return _cached_license

    _cached_license = _parse_key(key)

    if _cached_license.valid:
        logger.info(
            f"License validated: {_cached_license.tier} "
            f"(users: {_cached_license.max_users or 'unlimited'}, "
            f"expires: {_cached_license.expires_at.strftime('%Y-%m-%d') if _cached_license.expires_at else 'never'})"
        )
    else:
        logger.warning(f"License invalid: {_cached_license.error} — falling back to community")
        _cached_license = License(
            valid=True, tier="community", max_users=5,
            licensed_to="Community User",
            features=COMMUNITY_LICENSE.features,
            error=_cached_license.error,
        )

    return _cached_license


def reset_license():
    """Clear cached license (for testing)."""
    global _cached_license
    _cached_license = None


def has_enterprise_feature(feature: str) -> bool:
    """Check if a specific enterprise feature is licensed."""
    lic = get_license()
    if not lic.is_enterprise:
        return False
    return feature in lic.features


def license_info() -> dict:
    """Return license details for /api/health and CLI."""
    return get_license().to_dict()
