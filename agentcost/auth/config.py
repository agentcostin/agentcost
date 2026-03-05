"""
Auth Configuration — Generic OIDC / SAML settings.

Phase 5: Replaced Keycloak-specific configuration with provider-agnostic
OIDC and SAML configuration. Works with any standards-compliant provider:
  - Okta, Auth0, Azure AD, Google, AWS Cognito, OneLogin, etc.
  - Self-hosted: Keycloak, Authentik, Dex, Authelia

Configuration via environment variables:
  OIDC_ISSUER_URL    — e.g., https://auth.example.com/realms/myapp
  OIDC_CLIENT_ID     — e.g., agentcost-api
  OIDC_CLIENT_SECRET — (from your IdP)
  SAML_IDP_METADATA_URL — e.g., https://auth.example.com/saml/metadata

Auto-discovery: If OIDC_ISSUER_URL is set, endpoints (auth, token, JWKS,
userinfo) are auto-discovered from {issuer}/.well-known/openid-configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class AuthConfig:
    """Immutable auth configuration, loaded once at startup."""

    # -- Feature toggle --
    enabled: bool = True

    # -- OIDC (generic — any compliant provider) --
    oidc_issuer_url: str = "http://localhost:8080/realms/agentcost"
    oidc_client_id: str = "agentcost-api"
    oidc_client_secret: str = "agentcost-api-dev-secret"

    # Override discovery URLs (auto-derived from issuer if empty)
    oidc_auth_url: str = ""
    oidc_token_url: str = ""
    oidc_jwks_url: str = ""
    oidc_userinfo_url: str = ""
    oidc_logout_url: str = ""

    # -- SAML (generic — any IdP) --
    saml_entity_id: str = "https://agentcost.local/saml/metadata"
    saml_acs_url: str = "http://localhost:8100/auth/saml/acs"
    saml_slo_url: str = "http://localhost:8100/auth/saml/slo"
    saml_idp_entity_id: str = ""
    saml_idp_sso_url: str = ""
    saml_idp_slo_url: str = ""
    saml_idp_cert: str = ""
    saml_idp_metadata_url: str = ""

    # -- JWT validation --
    jwt_algorithms: list[str] = field(default_factory=lambda: ["RS256"])
    jwt_audience: str = "agentcost-api"
    jwt_leeway_seconds: int = 30

    # -- API key auth --
    api_key_header: str = "X-AgentCost-Key"
    api_key_prefix: str = "ac_"

    # -- Session / Cookie --
    session_cookie_name: str = "agentcost_session"
    session_secret: str = "change-me-in-production-please"
    session_max_age: int = 86400

    # -- Derived OIDC URLs --

    @property
    def issuer_url(self) -> str:
        return self.oidc_issuer_url

    @property
    def jwks_url(self) -> str:
        return self.oidc_jwks_url or f"{self.oidc_issuer_url}/protocol/openid-connect/certs"

    @property
    def token_url(self) -> str:
        return self.oidc_token_url or f"{self.oidc_issuer_url}/protocol/openid-connect/token"

    @property
    def userinfo_url(self) -> str:
        return self.oidc_userinfo_url or f"{self.oidc_issuer_url}/protocol/openid-connect/userinfo"

    @property
    def auth_url(self) -> str:
        return self.oidc_auth_url or f"{self.oidc_issuer_url}/protocol/openid-connect/auth"

    @property
    def logout_url(self) -> str:
        return self.oidc_logout_url or f"{self.oidc_issuer_url}/protocol/openid-connect/logout"

    @property
    def discovery_url(self) -> str:
        return f"{self.oidc_issuer_url}/.well-known/openid-configuration"

    # -- Backward compat --

    @property
    def public_issuer_url(self) -> str:
        return self.issuer_url

    @property
    def saml_idp_metadata_url_derived(self) -> str:
        """SAML IdP metadata: use explicit URL or derive from issuer."""
        if self.saml_idp_metadata_url:
            return self.saml_idp_metadata_url
        return f"{self.oidc_issuer_url}/protocol/saml/descriptor"


@lru_cache(maxsize=1)
def get_auth_config() -> AuthConfig:
    """Load auth config from environment. Cached."""
    # Support both new OIDC_* and legacy KEYCLOAK_* env vars
    legacy_issuer = ""
    kc_url = os.environ.get("KEYCLOAK_URL", "")
    kc_realm = os.environ.get("KEYCLOAK_REALM", "")
    if kc_url and kc_realm:
        legacy_issuer = f"{kc_url}/realms/{kc_realm}"
    elif kc_url:
        legacy_issuer = f"{kc_url}/realms/agentcost"

    return AuthConfig(
        enabled=os.environ.get("AGENTCOST_AUTH_ENABLED", "true").lower() != "false",
        oidc_issuer_url=os.environ.get(
            "OIDC_ISSUER_URL",
            legacy_issuer or "http://localhost:8080/realms/agentcost",
        ),
        oidc_client_id=os.environ.get(
            "OIDC_CLIENT_ID",
            os.environ.get("KEYCLOAK_CLIENT_ID", "agentcost-api"),
        ),
        oidc_client_secret=os.environ.get(
            "OIDC_CLIENT_SECRET",
            os.environ.get("KEYCLOAK_CLIENT_SECRET", "agentcost-api-dev-secret"),
        ),
        oidc_auth_url=os.environ.get("OIDC_AUTH_URL", ""),
        oidc_token_url=os.environ.get("OIDC_TOKEN_URL", ""),
        oidc_jwks_url=os.environ.get("OIDC_JWKS_URL", ""),
        oidc_userinfo_url=os.environ.get("OIDC_USERINFO_URL", ""),
        oidc_logout_url=os.environ.get("OIDC_LOGOUT_URL", ""),
        saml_entity_id=os.environ.get("SAML_ENTITY_ID", "https://agentcost.local/saml/metadata"),
        saml_acs_url=os.environ.get("SAML_ACS_URL", "http://localhost:8100/auth/saml/acs"),
        saml_slo_url=os.environ.get("SAML_SLO_URL", "http://localhost:8100/auth/saml/slo"),
        saml_idp_entity_id=os.environ.get("SAML_IDP_ENTITY_ID", ""),
        saml_idp_sso_url=os.environ.get("SAML_IDP_SSO_URL", ""),
        saml_idp_slo_url=os.environ.get("SAML_IDP_SLO_URL", ""),
        saml_idp_cert=os.environ.get("SAML_IDP_CERT", ""),
        saml_idp_metadata_url=os.environ.get("SAML_IDP_METADATA_URL", ""),
        session_secret=os.environ.get("SESSION_SECRET", "change-me-in-production-please"),
        api_key_header=os.environ.get("API_KEY_HEADER", "X-AgentCost-Key"),
    )


def discover_oidc_endpoints(issuer_url: str) -> dict:
    """Fetch OIDC discovery document and return endpoint URLs.

    Works with any OIDC-compliant provider (Okta, Auth0, Azure AD, Keycloak, etc.).
    """
    import json
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read())
