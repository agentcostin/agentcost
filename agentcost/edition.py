"""
AgentCost Edition Detection

Determines whether enterprise features are available based on:
  1. License key (AGENTCOST_LICENSE_KEY env var or ~/.agentcost/license.key)
  2. Edition override (AGENTCOST_EDITION env var)
  3. Module presence (auto-detection)

Priority order:
  - AGENTCOST_EDITION=community → always community (ignores license)
  - Valid license key → enterprise (if modules present)
  - AGENTCOST_EDITION=enterprise → enterprise (if modules present)
  - AGENTCOST_EDITION=auto → checks license, then module presence
  - No key, no modules → community

Enterprise features require BOTH:
  - A valid license key (trial or paid)
  - Enterprise modules installed
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger("agentcost.edition")

# ── Edition constants ────────────────────────────────────────────────────────
COMMUNITY = "community"
ENTERPRISE = "enterprise"

# Enterprise module names (relative to agentcost package)
ENTERPRISE_MODULES = [
    "agentcost.auth",
    "agentcost.org",
    "agentcost.cost",
    "agentcost.policy",
    "agentcost.notify",
    "agentcost.anomaly",
    "agentcost.gateway",
    "agentcost.events",
]


def _detect_enterprise() -> bool:
    """Check if enterprise modules are importable."""
    try:
        import importlib

        importlib.import_module("agentcost.auth.config")
        return True
    except ImportError:
        return False


def _check_license() -> bool:
    """Check if a valid enterprise license key exists."""
    try:
        from .license import get_license

        lic = get_license()
        return lic.is_enterprise
    except Exception:
        return False


def get_edition() -> str:
    """Return the current edition: 'community' or 'enterprise'.

    Enterprise requires both a valid license AND enterprise modules installed.
    """
    setting = os.environ.get("AGENTCOST_EDITION", "auto").lower().strip()

    # Forced community — always community
    if setting == COMMUNITY:
        return COMMUNITY

    has_modules = _detect_enterprise()
    has_license = _check_license()

    # Forced enterprise — check modules + license
    if setting == ENTERPRISE:
        if not has_modules:
            logger.warning(
                "AGENTCOST_EDITION=enterprise but enterprise modules not found. "
                "Falling back to community edition."
            )
            return COMMUNITY
        if not has_license:
            logger.warning(
                "AGENTCOST_EDITION=enterprise but no valid license key found. "
                "Set AGENTCOST_LICENSE_KEY or place key in ~/.agentcost/license.key. "
                "Falling back to community edition."
            )
            return COMMUNITY
        return ENTERPRISE

    # Auto: need both modules AND license
    if has_modules and has_license:
        return ENTERPRISE

    return COMMUNITY


def is_enterprise() -> bool:
    """True if running in enterprise edition."""
    return get_edition() == ENTERPRISE


def is_community() -> bool:
    """True if running in community edition."""
    return get_edition() == COMMUNITY


# ── Feature availability checks ─────────────────────────────────────────────


def has_auth() -> bool:
    """SSO/SAML authentication available."""
    return is_enterprise()


def has_org() -> bool:
    """Multi-tenant organization management available."""
    return is_enterprise()


def has_budget_enforcement() -> bool:
    """Cost centers, allocations, budget enforcement available."""
    return is_enterprise()


def has_policy_engine() -> bool:
    """Policy engine and approval workflows available."""
    return is_enterprise()


def has_notifications() -> bool:
    """Notification channels and scorecards available."""
    return is_enterprise()


def has_anomaly_detection() -> bool:
    """ML-based anomaly detection available."""
    return is_enterprise()


def has_gateway() -> bool:
    """AI Gateway proxy available."""
    return is_enterprise()


def has_event_bus() -> bool:
    """Event bus with webhooks/SSE available."""
    return is_enterprise()


# ── Summary ──────────────────────────────────────────────────────────────────


def edition_info() -> dict:
    """Return edition details for /api/health and CLI."""
    edition = get_edition()

    # Include license info if available
    license_data = {}
    try:
        from .license import license_info

        license_data = license_info()
    except Exception:
        pass

    return {
        "edition": edition,
        "license": license_data,
        "features": {
            "auth": has_auth(),
            "org": has_org(),
            "budget_enforcement": has_budget_enforcement(),
            "policy_engine": has_policy_engine(),
            "notifications": has_notifications(),
            "anomaly_detection": has_anomaly_detection(),
            "gateway": has_gateway(),
            "event_bus": has_event_bus(),
        },
        # Always available in both editions
        "core": {
            "tracing": True,
            "dashboard": True,
            "forecasting": True,
            "optimizer": True,
            "analytics": True,
            "estimator": True,
            "plugins": True,
            "cli": True,
            "otel_export": True,
        },
    }
