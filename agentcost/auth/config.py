"""
Auth Configuration — All Keycloak/OIDC/SAML settings in one place.

Reads from environment variables with sensible defaults for local dev
(Keycloak at localhost:8080, realm 'agentcost').

Production deployments override via env vars or .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class AuthConfig:
    """Immutable auth configuration, loaded once at startup."""

    # ── Feature toggle ──────────────────────────────────────────
    enabled: bool = True  # Set False to disable auth entirely (dev mode)

    # ── Keycloak connection ─────────────────────────────────────
    keycloak_url: str = "http://localhost:8080"  # Internal (container-to-container)
    keycloak_public_url: str = ""  # Browser-facing (empty = same as keycloak_url)
    realm: str = "agentcost"

    # ── OIDC (API backend) ──────────────────────────────────────
    oidc_client_id: str = "agentcost-api"
    oidc_client_secret: str = "agentcost-api-dev-secret"

    # ── SAML ────────────────────────────────────────────────────
    saml_entity_id: str = "https://agentcost.local/saml/metadata"
    saml_acs_url: str = "http://localhost:8100/auth/saml/acs"
    saml_slo_url: str = "http://localhost:8100/auth/saml/slo"

    # ── JWT validation ──────────────────────────────────────────
    jwt_algorithms: list[str] = field(default_factory=lambda: ["RS256"])
    jwt_audience: str = "agentcost-api"
    jwt_leeway_seconds: int = 30

    # ── API key auth (for SDK / agent traffic) ──────────────────
    api_key_header: str = "X-AgentCost-Key"
    api_key_prefix: str = "ac_"

    # ── Session / Cookie ────────────────────────────────────────
    session_cookie_name: str = "agentcost_session"
    session_secret: str = "change-me-in-production-please"
    session_max_age: int = 86400  # 24 hours

    # ── Derived URLs (internal — container-to-container) ───────
    @property
    def issuer_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.realm}"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer_url}/protocol/openid-connect/certs"

    @property
    def token_url(self) -> str:
        return f"{self.issuer_url}/protocol/openid-connect/token"

    @property
    def userinfo_url(self) -> str:
        return f"{self.issuer_url}/protocol/openid-connect/userinfo"

    @property
    def saml_idp_metadata_url(self) -> str:
        return f"{self.issuer_url}/protocol/saml/descriptor"

    @property
    def admin_api_url(self) -> str:
        return f"{self.keycloak_url}/admin/realms/{self.realm}"

    # ── Derived URLs (public — browser-facing) ──────────────────
    @property
    def _public_base(self) -> str:
        """Keycloak URL the browser should use. Falls back to keycloak_url."""
        return (self.keycloak_public_url or self.keycloak_url).rstrip("/")

    @property
    def public_issuer_url(self) -> str:
        return f"{self._public_base}/realms/{self.realm}"

    @property
    def auth_url(self) -> str:
        """Authorization endpoint — browser redirect, must use public URL."""
        return f"{self.public_issuer_url}/protocol/openid-connect/auth"

    @property
    def logout_url(self) -> str:
        """Logout endpoint — browser redirect, must use public URL."""
        return f"{self.public_issuer_url}/protocol/openid-connect/logout"


@lru_cache(maxsize=1)
def get_auth_config() -> AuthConfig:
    """Load auth config from environment. Cached — call once at startup."""
    return AuthConfig(
        enabled=os.environ.get("AGENTCOST_AUTH_ENABLED", "true").lower() != "false",
        keycloak_url=os.environ.get("KEYCLOAK_URL", "http://localhost:8080"),
        keycloak_public_url=os.environ.get("KEYCLOAK_PUBLIC_URL", ""),
        realm=os.environ.get("KEYCLOAK_REALM", "agentcost"),
        oidc_client_id=os.environ.get("KEYCLOAK_CLIENT_ID", "agentcost-api"),
        oidc_client_secret=os.environ.get(
            "KEYCLOAK_CLIENT_SECRET", "agentcost-api-dev-secret"
        ),
        saml_entity_id=os.environ.get(
            "SAML_ENTITY_ID", "https://agentcost.local/saml/metadata"
        ),
        saml_acs_url=os.environ.get(
            "SAML_ACS_URL", "http://localhost:8100/auth/saml/acs"
        ),
        saml_slo_url=os.environ.get(
            "SAML_SLO_URL", "http://localhost:8100/auth/saml/slo"
        ),
        session_secret=os.environ.get(
            "SESSION_SECRET", "change-me-in-production-please"
        ),
        api_key_header=os.environ.get("API_KEY_HEADER", "X-AgentCost-Key"),
    )
