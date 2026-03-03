"""
API Key Authentication — For SDK and agent traffic.

API keys bypass OIDC and are validated directly against the database.
Format: ac_live_<32 random chars>  (stored as bcrypt hash)

Flow:
  1. Client sends X-AgentCost-Key header
  2. Extract prefix (first 12 chars) to find candidate rows
  3. Verify bcrypt hash against full key
  4. Return AuthContext with org_id and scopes from the key row
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Optional

from .config import get_auth_config
from .models import AuthContext, AuthMethod, TokenClaims

logger = logging.getLogger("agentcost.auth.api_key")


def generate_api_key(prefix: str = "ac_live_") -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (full_key, key_prefix, key_hash)
        - full_key: shown once to the user (ac_live_xxxx...xxxx)
        - key_prefix: first 12 chars, stored for lookup display
        - key_hash: SHA-256 hash, stored in DB for verification
    """
    random_part = secrets.token_urlsafe(32)
    full_key = f"{prefix}{random_part}"
    key_prefix = full_key[:12]
    key_hash = _hash_key(full_key)
    return full_key, key_prefix, key_hash


def _hash_key(key: str) -> str:
    """SHA-256 hash of the API key. Fast lookups, constant-time comparison."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def validate_api_key(key: str, db=None) -> Optional[AuthContext]:
    """Validate an API key against the database.

    Args:
        key: The full API key from the request header
        db: Database adapter (from get_db()). If None, imported lazily.

    Returns:
        AuthContext if valid, None if invalid or expired.
    """
    config = get_auth_config()

    # Basic format check
    if not key or not key.startswith(config.api_key_prefix):
        return None

    # Get database
    if db is None:
        from ..data.connection import get_db

        db = get_db()

    key_hash = _hash_key(key)

    # Look up by hash — constant time since we compare hashes, not the raw key
    row = db.fetch_one(
        "SELECT id, org_id, key_prefix, scopes, expires_at FROM api_keys WHERE key_hash = ?",
        (key_hash,),
    )

    if not row:
        logger.warning("API key not found (prefix: %s...)", key[:12])
        return None

    # Check expiry
    if row.get("expires_at"):
        try:
            expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(expires.tzinfo):
                logger.warning(
                    "Expired API key: %s (expired %s)",
                    row["key_prefix"],
                    row["expires_at"],
                )
                return None
        except (ValueError, TypeError):
            pass

    # Update last_used timestamp (fire-and-forget, don't block auth)
    try:
        db.execute(
            "UPDATE api_keys SET last_used = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), row["id"]),
        )
    except Exception as e:
        logger.debug("Failed to update last_used for key %s: %s", row["id"], e)

    # Build auth context — API keys get org_member role by default,
    # scoped by the scopes column
    (row.get("scopes") or "*").split(",")
    claims = TokenClaims(
        sub=f"apikey:{row['id']}",
        email="",
        name=f"API Key ({row['key_prefix']}...)",
        org_id=row.get("org_id", "default"),
        org_slug="",  # Could join to orgs table if needed
        roles=["org_member"],
    )

    ctx = AuthContext(
        claims=claims,
        method=AuthMethod.API_KEY,
        api_key_id=row["id"],
    )

    logger.debug("API key validated: %s org=%s", row["key_prefix"], claims.org_id)
    return ctx
