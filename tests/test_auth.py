"""
Tests for AgentCost Auth Module (Block 1).

Run: python -m pytest tests/test_auth.py -v
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── Test Auth Models ────────────────────────────────────────────────────────


class TestRole:
    def test_role_ordering(self):
        from agentcost.auth.models import Role

        assert Role.PLATFORM_ADMIN > Role.ORG_ADMIN
        assert Role.ORG_ADMIN > Role.ORG_MANAGER
        assert Role.ORG_MANAGER > Role.ORG_MEMBER
        assert Role.ORG_MEMBER > Role.ORG_VIEWER

    def test_role_from_str(self):
        from agentcost.auth.models import Role

        assert Role.from_str("org_admin") == Role.ORG_ADMIN
        assert Role.from_str("unknown_role") == Role.ORG_VIEWER


class TestTokenClaims:
    def test_from_jwt_payload(self):
        from agentcost.auth.models import TokenClaims, Role

        payload = {
            "sub": "user-123",
            "email": "test@example.com",
            "name": "Test User",
            "org_id": "org-456",
            "org_slug": "test-org",
            "roles": ["org_admin", "org_member"],
            "iss": "http://localhost:8080/realms/agentcost",
            "aud": "agentcost-api",
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
        }
        claims = TokenClaims.from_jwt(payload)
        assert claims.sub == "user-123"
        assert claims.email == "test@example.com"
        assert claims.org_id == "org-456"
        assert claims.highest_role == Role.ORG_ADMIN
        assert claims.has_role(Role.ORG_MEMBER)
        assert not claims.has_role(Role.PLATFORM_ADMIN)

    def test_from_saml_attributes(self):
        from agentcost.auth.models import TokenClaims

        attrs = {
            "email": ["saml@example.com"],
            "firstName": ["SAML"],
            "lastName": ["User"],
            "org_id": ["org-789"],
            "org_slug": ["saml-org"],
            "role": ["org_member"],
        }
        claims = TokenClaims.from_saml(attrs, name_id="saml@example.com")
        assert claims.sub == "saml@example.com"
        assert claims.name == "SAML User"
        assert claims.org_id == "org-789"

    def test_empty_roles_defaults_to_viewer(self):
        from agentcost.auth.models import TokenClaims, Role

        claims = TokenClaims(sub="x", roles=[])
        assert claims.highest_role == Role.ORG_VIEWER


class TestAuthContext:
    def test_anonymous_context(self):
        from agentcost.auth.models import AuthContext, AuthMethod

        ctx = AuthContext.anonymous()
        assert ctx.method == AuthMethod.ANONYMOUS
        assert not ctx.is_authenticated

    def test_authenticated_context(self):
        from agentcost.auth.models import AuthContext, AuthMethod, TokenClaims, Role

        claims = TokenClaims(
            sub="u1", email="a@b.com", org_id="org1", roles=["org_admin"]
        )
        ctx = AuthContext(claims=claims, method=AuthMethod.OIDC)
        assert ctx.is_authenticated
        assert ctx.is_org_admin
        assert ctx.has_role(Role.ORG_MEMBER)

    def test_to_dict(self):
        from agentcost.auth.models import AuthContext, AuthMethod, TokenClaims

        claims = TokenClaims(
            sub="u1", email="a@b.com", org_id="org1", roles=["org_member"]
        )
        ctx = AuthContext(claims=claims, method=AuthMethod.API_KEY, api_key_id="k1")
        d = ctx.to_dict()
        assert d["user_id"] == "u1"
        assert d["method"] == "api_key"
        assert d["api_key_id"] == "k1"


# ─── Test Auth Config ────────────────────────────────────────────────────────


class TestAuthConfig:
    def test_default_config(self):
        from agentcost.auth.config import AuthConfig

        cfg = AuthConfig()
        assert cfg.enabled is True
        assert "realms/agentcost" in cfg.issuer_url
        assert cfg.jwks_url.endswith("/certs")

    def test_derived_urls(self):
        from agentcost.auth.config import AuthConfig

        cfg = AuthConfig(keycloak_url="https://kc.example.com", realm="test")
        assert cfg.issuer_url == "https://kc.example.com/realms/test"

    def test_config_from_env(self, monkeypatch):
        from agentcost.auth.config import get_auth_config

        get_auth_config.cache_clear()
        monkeypatch.setenv("AGENTCOST_AUTH_ENABLED", "false")
        monkeypatch.setenv("KEYCLOAK_URL", "https://sso.prod.com")
        cfg = get_auth_config()
        assert cfg.enabled is False
        assert cfg.keycloak_url == "https://sso.prod.com"
        get_auth_config.cache_clear()


# ─── Test API Key ────────────────────────────────────────────────────────────


class TestAPIKey:
    def test_generate_key_format(self):
        from agentcost.auth.api_key import generate_api_key

        full_key, prefix, key_hash = generate_api_key()
        assert full_key.startswith("ac_live_")
        assert len(prefix) == 12
        assert len(key_hash) == 64

    def test_hash_consistency(self):
        from agentcost.auth.api_key import generate_api_key, _hash_key

        full_key, _, key_hash = generate_api_key()
        assert _hash_key(full_key) == key_hash


# ─── Test Org Filter SQL ─────────────────────────────────────────────────────


class TestOrgFilter:
    def test_platform_admin_sees_all(self):
        from agentcost.auth.dependencies import org_filter_sql
        from agentcost.auth.models import AuthContext, AuthMethod, TokenClaims

        claims = TokenClaims(sub="a", org_id="org1", roles=["platform_admin"])
        ctx = AuthContext(claims=claims, method=AuthMethod.OIDC)
        where, params = org_filter_sql(ctx)
        assert where == ""
        assert params == []

    def test_regular_user_scoped(self):
        from agentcost.auth.dependencies import org_filter_sql
        from agentcost.auth.models import AuthContext, AuthMethod, TokenClaims

        claims = TokenClaims(sub="a", org_id="org-42", roles=["org_member"])
        ctx = AuthContext(claims=claims, method=AuthMethod.OIDC)
        where, params = org_filter_sql(ctx)
        assert "org_id = ?" in where
        assert params == ["org-42"]


# ─── Test Session Tokens ─────────────────────────────────────────────────────


class TestSessionTokens:
    def test_create_and_validate(self):
        from agentcost.auth.dependencies import create_session_token, _validate_session
        from agentcost.auth.models import TokenClaims, AuthMethod
        from agentcost.auth.config import AuthConfig

        cfg = AuthConfig(session_secret="test-secret-key-123")
        claims = TokenClaims(
            sub="user-1", email="t@x.com", org_id="org-1", roles=["org_member"]
        )
        token = create_session_token(claims, cfg)
        ctx = _validate_session(token, cfg)
        assert ctx is not None
        assert ctx.method == AuthMethod.SESSION
        assert ctx.claims.sub == "user-1"

    def test_invalid_session(self):
        from agentcost.auth.dependencies import _validate_session
        from agentcost.auth.config import AuthConfig

        assert _validate_session("garbage", AuthConfig(session_secret="s")) is None

    def test_wrong_secret(self):
        from agentcost.auth.dependencies import create_session_token, _validate_session
        from agentcost.auth.models import TokenClaims
        from agentcost.auth.config import AuthConfig

        claims = TokenClaims(sub="u1", roles=["org_member"])
        token = create_session_token(claims, AuthConfig(session_secret="s1"))
        assert _validate_session(token, AuthConfig(session_secret="s2")) is None


# ─── Test SAML Metadata ─────────────────────────────────────────────────────


class TestSAMLMetadata:
    def test_minimal_metadata(self):
        from agentcost.auth.saml_provider import _minimal_sp_metadata
        from agentcost.auth.config import AuthConfig

        cfg = AuthConfig(
            saml_entity_id="https://test.local/saml",
            saml_acs_url="http://localhost:8100/auth/saml/acs",
            saml_slo_url="http://localhost:8100/auth/saml/slo",
        )
        xml = _minimal_sp_metadata(cfg)
        assert "EntityDescriptor" in xml
        assert "https://test.local/saml" in xml
        assert "AssertionConsumerService" in xml


# ─── FastAPI Integration Tests ───────────────────────────────────────────────


class TestFastAPIIntegration:
    @pytest.fixture
    def client_no_auth(self, monkeypatch):
        monkeypatch.setenv("AGENTCOST_AUTH_ENABLED", "false")
        from agentcost.auth.config import get_auth_config

        get_auth_config.cache_clear()
        from fastapi.testclient import TestClient
        from agentcost.api.server import app

        with TestClient(app) as c:
            yield c
        get_auth_config.cache_clear()

    def test_health(self, client_no_auth):
        r = client_no_auth.get("/api/health")
        assert r.status_code == 200
        assert r.json()["version"] == "0.3.0"
        assert r.json()["auth_enabled"] is False

    def test_auth_health_disabled(self, client_no_auth):
        r = client_no_auth.get("/auth/health")
        assert r.status_code == 200
        assert r.json()["status"] == "disabled"

    def test_me_anonymous(self, client_no_auth):
        r = client_no_auth.get("/auth/me")
        assert r.status_code == 200
        assert r.json()["auth_method"] == "anonymous"

    def test_saml_metadata(self, client_no_auth):
        r = client_no_auth.get("/auth/saml/metadata")
        assert r.status_code == 200
        assert "EntityDescriptor" in r.text

    def test_summary_no_auth(self, client_no_auth):
        r = client_no_auth.get("/api/summary")
        assert r.status_code == 200
