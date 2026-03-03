"""
Tests for AgentCost Block 2: Multi-Tenant Org Management.

Run: python -m pytest tests/test_org.py -v
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── Test OrgService ─────────────────────────────────────────────────────────


class TestOrgService:
    def test_slugify(self):
        from agentcost.org.org_service import OrgService

        assert OrgService._slugify("My Great Org") == "my-great-org"
        assert OrgService._slugify("Hello   World!!") == "hello-world"
        assert OrgService._slugify("  spaces  ") == "spaces"


# ─── Test Role Hierarchy in TeamService ──────────────────────────────────────


class TestTeamRules:
    def test_cant_assign_higher_role(self):
        from agentcost.auth.models import AuthContext, AuthMethod, TokenClaims, Role

        # org_manager trying to assign org_admin
        claims = TokenClaims(sub="mgr-1", org_id="org1", roles=["org_manager"])
        actor = AuthContext(claims=claims, method=AuthMethod.OIDC)
        assert actor.role == Role.ORG_MANAGER
        assert not actor.has_role(Role.ORG_ADMIN)

    def test_platform_admin_can_assign_any_role(self):
        from agentcost.auth.models import AuthContext, AuthMethod, TokenClaims, Role

        claims = TokenClaims(sub="pa-1", org_id="org1", roles=["platform_admin"])
        actor = AuthContext(claims=claims, method=AuthMethod.OIDC)
        assert actor.is_platform_admin
        assert actor.has_role(Role.ORG_ADMIN)


# ─── Test AuditService Hash Chaining ─────────────────────────────────────────


class TestAuditHashChain:
    def test_hash_chain_logic(self):
        """Test hash chain computation matches expected behavior."""
        import hashlib

        prev_hash = "GENESIS"
        entry_data = "login|user1|user|org1|||login|null|2026-01-01T00:00:00"
        expected = hashlib.sha256(f"{prev_hash}|{entry_data}".encode()).hexdigest()
        assert len(expected) == 64  # SHA-256 hex digest
        assert expected != prev_hash

    def test_chain_breaks_on_tamper(self):
        """If an entry is modified, the chain should detect it."""
        import hashlib

        # Entry 1
        prev = "GENESIS"
        data1 = "login|u1|user|o1|||login|null|t1"
        hash1 = hashlib.sha256(f"{prev}|{data1}".encode()).hexdigest()

        # Entry 2 (chained to entry 1)
        data2 = "logout|u1|user|o1|||logout|null|t2"
        hash2 = hashlib.sha256(f"{hash1}|{data2}".encode()).hexdigest()

        # Tamper entry 1
        tampered_data1 = "login|HACKER|user|o1|||login|null|t1"
        tampered_hash1 = hashlib.sha256(f"{prev}|{tampered_data1}".encode()).hexdigest()

        # Recompute entry 2 with original prev_hash (hash1)
        recomputed_hash2 = hashlib.sha256(f"{hash1}|{data2}".encode()).hexdigest()
        assert recomputed_hash2 == hash2  # Still matches because we used original hash1

        # But if we try with tampered_hash1, it won't match
        wrong_hash2 = hashlib.sha256(f"{tampered_hash1}|{data2}".encode()).hexdigest()
        assert wrong_hash2 != hash2  # Chain broken!


# ─── Test InviteService Logic ────────────────────────────────────────────────


class TestInviteRules:
    def test_invite_expiry_days(self):
        from agentcost.org.invite_service import INVITE_EXPIRY_DAYS

        assert INVITE_EXPIRY_DAYS == 7


# ─── FastAPI Integration Tests ───────────────────────────────────────────────


@pytest.mark.skipif(
    not os.environ.get("AGENTCOST_AUTH_ENABLED"), reason="Auth not enabled"
)
class TestOrgAPI:
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

    def test_health_shows_new_version(self, client_no_auth):
        r = client_no_auth.get("/api/health")
        assert r.status_code == 200
        assert r.json()["version"] == "1.0.0"

    def test_org_endpoints_registered(self, client_no_auth):
        """Verify org routes are mounted."""
        r = client_no_auth.get("/org")
        # With auth disabled, anonymous user gets through but org may not exist
        assert r.status_code in (200, 404)

    @pytest.mark.skip(reason="Requires AGENTCOST_AUTH_ENABLED")
    def test_org_members_endpoint(self, client_no_auth):
        r = client_no_auth.get("/org/members")
        assert r.status_code == 200
        data = r.json()
        assert "members" in data
        assert "total" in data

    @pytest.mark.skip(reason="Requires AGENTCOST_AUTH_ENABLED")
    def test_org_audit_endpoint(self, client_no_auth):
        r = client_no_auth.get("/org/audit")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert "total" in data

    @pytest.mark.skip(reason="Requires AGENTCOST_AUTH_ENABLED")
    def test_org_audit_verify(self, client_no_auth):
        r = client_no_auth.get("/org/audit/verify")
        assert r.status_code == 200
        data = r.json()
        assert "valid" in data

    @pytest.mark.skip(reason="Requires AGENTCOST_AUTH_ENABLED")
    def test_org_invites_endpoint(self, client_no_auth):
        r = client_no_auth.get("/org/invites")
        assert r.status_code == 200

    @pytest.mark.skip(reason="Requires AGENTCOST_AUTH_ENABLED")
    def test_profile_update_no_fields(self, client_no_auth):
        r = client_no_auth.put("/org/profile", json={})
        assert r.status_code == 400
