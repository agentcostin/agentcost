"""
JWT Provider — Validates Keycloak-issued JWTs using JWKS (RS256).

Features:
  - Fetches and caches Keycloak's JWKS public keys
  - Auto-refreshes keys on signature failure (key rotation)
  - Validates issuer, audience, expiry, and custom claims
  - Returns TokenClaims dataclass on success

This module has NO FastAPI dependency — can be used from CLI, workers, etc.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from .config import AuthConfig, get_auth_config
from .models import TokenClaims

logger = logging.getLogger("agentcost.auth.jwt")

# ── Lazy imports (only needed when auth is enabled) ──────────────────────────

_jwt = None
_jwk_client = None


def _ensure_imports():
    """Import PyJWT lazily so the package is optional for dev/free tier."""
    global _jwt
    if _jwt is None:
        try:
            import jwt as pyjwt

            _jwt = pyjwt
        except ImportError:
            raise ImportError(
                "JWT authentication requires PyJWT.\n"
                "Install with: pip install PyJWT[crypto]"
            )


class JWKSKeyCache:
    """Fetches and caches JWKS signing keys from Keycloak.

    Keys are refreshed:
      - On first request
      - After cache_ttl_seconds (default 300s / 5 min)
      - On verification failure (key rotation)
    """

    def __init__(self, jwks_url: str, cache_ttl_seconds: int = 300):
        self._jwks_url = jwks_url
        self._cache_ttl = cache_ttl_seconds
        self._keys: dict = {}
        self._last_fetch: float = 0

    def _fetch(self) -> None:
        """Download JWKS from Keycloak."""
        _ensure_imports()
        import urllib.request
        import ssl

        # In dev, Keycloak runs on HTTP — skip SSL verification
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            req = urllib.request.Request(
                self._jwks_url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read())
                self._keys = {k["kid"]: k for k in data.get("keys", [])}
                self._last_fetch = time.time()
                logger.info(
                    "JWKS refreshed from %s — %d keys", self._jwks_url, len(self._keys)
                )
        except Exception as e:
            logger.error("Failed to fetch JWKS from %s: %s", self._jwks_url, e)
            if not self._keys:
                raise

    def _is_stale(self) -> bool:
        return (time.time() - self._last_fetch) > self._cache_ttl

    def get_key(self, kid: str, force_refresh: bool = False):
        """Get the RSA public key for a given kid.

        Returns a PyJWT-compatible RSA key object.
        """
        _ensure_imports()
        from jwt.algorithms import RSAAlgorithm

        if force_refresh or self._is_stale() or kid not in self._keys:
            self._fetch()

        key_data = self._keys.get(kid)
        if not key_data:
            raise ValueError(
                f"Key ID '{kid}' not found in JWKS (available: {list(self._keys.keys())})"
            )

        return RSAAlgorithm.from_jwk(json.dumps(key_data))


# ── Module-level singleton ───────────────────────────────────────────────────

_key_cache: Optional[JWKSKeyCache] = None


def _get_key_cache(config: Optional[AuthConfig] = None) -> JWKSKeyCache:
    global _key_cache
    if _key_cache is None:
        cfg = config or get_auth_config()
        _key_cache = JWKSKeyCache(cfg.jwks_url)
    return _key_cache


def reset_key_cache() -> None:
    """Reset the JWKS cache. Used in tests."""
    global _key_cache
    _key_cache = None


# ── Token validation ─────────────────────────────────────────────────────────


def validate_jwt(token: str, config: Optional[AuthConfig] = None) -> TokenClaims:
    """Validate a Keycloak-issued JWT and return structured claims.

    Steps:
      1. Decode header to get `kid` (key ID)
      2. Fetch RSA public key from JWKS cache
      3. Verify signature, expiry, issuer
      4. Extract custom claims (org_id, org_slug, roles)
      5. Return TokenClaims

    Raises:
      jwt.ExpiredSignatureError — token has expired
      jwt.InvalidTokenError — any other validation failure
      ValueError — missing key in JWKS
    """
    _ensure_imports()

    cfg = config or get_auth_config()
    cache = _get_key_cache(cfg)

    # Step 1: read kid from unverified header
    header = _jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise _jwt.InvalidTokenError("JWT header missing 'kid'")

    # Step 2: get public key
    try:
        key = cache.get_key(kid)
    except ValueError:
        # Key not found — maybe rotation happened, force refresh once
        key = cache.get_key(kid, force_refresh=True)

    # Step 3: verify and decode
    # Accept both internal (http://keycloak:8080) and public (http://localhost:8180)
    # issuer URLs, since Keycloak signs tokens with the URL the user logged in through.
    valid_issuers = {cfg.issuer_url, cfg.public_issuer_url}

    # Decode — Keycloak access tokens may not include 'aud' claim,
    # so we validate audience only if present.
    payload = _jwt.decode(
        token,
        key=key,
        algorithms=cfg.jwt_algorithms,
        leeway=cfg.jwt_leeway_seconds,
        options={
            "verify_exp": True,
            "verify_iss": False,  # We check manually below
            "verify_aud": False,  # Keycloak doesn't always include aud
            "require": ["exp", "iss", "sub"],
        },
    )

    # Manual issuer validation against both internal and public URLs
    token_issuer = payload.get("iss", "")
    if token_issuer not in valid_issuers:
        raise _jwt.InvalidTokenError(
            f"Invalid issuer '{token_issuer}'. Expected one of: {valid_issuers}"
        )

    # Optional audience check — only if aud is present in the token
    token_aud = payload.get("aud")
    if token_aud:
        valid_audiences = {cfg.oidc_client_id, "account"}
        aud_list = token_aud if isinstance(token_aud, list) else [token_aud]
        if not any(a in valid_audiences for a in aud_list):
            raise _jwt.InvalidTokenError(
                f"Invalid audience '{token_aud}'. Expected one of: {valid_audiences}"
            )

    # Step 4-5: build claims object
    claims = TokenClaims.from_jwt(payload)
    logger.debug(
        "JWT validated: sub=%s org=%s roles=%s", claims.sub, claims.org_id, claims.roles
    )
    return claims


def decode_jwt_unverified(token: str) -> dict:
    """Decode a JWT WITHOUT verification. For debugging/logging only."""
    _ensure_imports()
    return _jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
