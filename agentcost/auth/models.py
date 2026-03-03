"""
Auth Models — Data structures for authentication context.

These are plain dataclasses (no ORM dependency) so they can be used
across the API layer, middleware, and tests without importing FastAPI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AuthMethod(str, Enum):
    """How the user/agent authenticated."""
    OIDC = "oidc"           # JWT from Keycloak OIDC flow
    SAML = "saml"           # SAML assertion → session
    API_KEY = "api_key"     # SDK / agent API key
    SESSION = "session"     # Cookie-based session (post SAML/OIDC)
    ANONYMOUS = "anonymous" # Auth disabled or public endpoint


class Role(str, Enum):
    """Platform roles — maps to Keycloak realm roles."""
    PLATFORM_ADMIN = "platform_admin"
    ORG_ADMIN = "org_admin"
    ORG_MANAGER = "org_manager"
    ORG_MEMBER = "org_member"
    ORG_VIEWER = "org_viewer"

    @classmethod
    def from_str(cls, s: str) -> "Role":
        try:
            return cls(s)
        except ValueError:
            return cls.ORG_VIEWER  # safe default

    @property
    def level(self) -> int:
        """Numeric level for comparison: higher = more privileged."""
        return {
            Role.ORG_VIEWER: 10,
            Role.ORG_MEMBER: 20,
            Role.ORG_MANAGER: 30,
            Role.ORG_ADMIN: 40,
            Role.PLATFORM_ADMIN: 100,
        }[self]

    def __ge__(self, other: "Role") -> bool:
        return self.level >= other.level

    def __gt__(self, other: "Role") -> bool:
        return self.level > other.level

    def __le__(self, other: "Role") -> bool:
        return self.level <= other.level

    def __lt__(self, other: "Role") -> bool:
        return self.level < other.level


@dataclass(frozen=True)
class TokenClaims:
    """Decoded claims from a Keycloak JWT or SAML assertion.

    Fields align with the custom protocol mappers in the realm config:
      - org_id, org_slug: multi-tenant isolation
      - roles: realm-level role list
      - Standard OIDC: sub, email, name, preferred_username
    """
    sub: str                              # Keycloak user UUID
    email: str = ""
    name: str = ""
    preferred_username: str = ""
    org_id: str = "default"
    org_slug: str = "default"
    roles: list[str] = field(default_factory=list)
    iss: str = ""                         # Token issuer URL
    aud: str | list[str] = ""             # Audience
    exp: int = 0                          # Expiry (epoch)
    iat: int = 0                          # Issued at (epoch)

    @property
    def highest_role(self) -> Role:
        """Return the most privileged role from the claims."""
        if not self.roles:
            return Role.ORG_VIEWER
        parsed = [Role.from_str(r) for r in self.roles]
        return max(parsed, key=lambda r: r.level)

    def has_role(self, required: Role) -> bool:
        """Check if any claimed role meets or exceeds the required level."""
        return self.highest_role >= required

    @classmethod
    def from_jwt(cls, payload: dict) -> "TokenClaims":
        """Construct from a decoded JWT payload dict."""
        return cls(
            sub=payload.get("sub", ""),
            email=payload.get("email", ""),
            name=payload.get("name", ""),
            preferred_username=payload.get("preferred_username", ""),
            org_id=payload.get("org_id", "default"),
            org_slug=payload.get("org_slug", "default"),
            roles=payload.get("roles", []),
            iss=payload.get("iss", ""),
            aud=payload.get("aud", ""),
            exp=payload.get("exp", 0),
            iat=payload.get("iat", 0),
        )

    @classmethod
    def from_saml(cls, attributes: dict, name_id: str = "") -> "TokenClaims":
        """Construct from SAML assertion attributes.

        SAML attributes come as lists; we take the first value.
        """
        def _first(key: str, default: str = "") -> str:
            val = attributes.get(key, [default])
            return val[0] if isinstance(val, list) else val

        return cls(
            sub=name_id or _first("email"),
            email=_first("email"),
            name=f"{_first('firstName')} {_first('lastName')}".strip(),
            preferred_username=_first("email"),
            org_id=_first("org_id", "default"),
            org_slug=_first("org_slug", "default"),
            roles=attributes.get("role", ["org_member"]),
        )


@dataclass
class AuthContext:
    """The resolved authentication context attached to every request.

    Combines token claims with runtime metadata (auth method, API key ID).
    This is what route handlers receive via Depends(get_current_user).
    """
    claims: TokenClaims
    method: AuthMethod = AuthMethod.ANONYMOUS
    api_key_id: Optional[str] = None      # Set when auth method is API_KEY
    session_id: Optional[str] = None      # Set when using cookie session

    # ── Convenience accessors ────────────────────────────────────

    @property
    def user_id(self) -> str:
        return self.claims.sub

    @property
    def email(self) -> str:
        return self.claims.email

    @property
    def org_id(self) -> str:
        return self.claims.org_id

    @property
    def org_slug(self) -> str:
        return self.claims.org_slug

    @property
    def role(self) -> Role:
        return self.claims.highest_role

    def has_role(self, required: Role) -> bool:
        return self.claims.has_role(required)

    @property
    def is_platform_admin(self) -> bool:
        return self.has_role(Role.PLATFORM_ADMIN)

    @property
    def is_org_admin(self) -> bool:
        return self.has_role(Role.ORG_ADMIN)

    @property
    def is_authenticated(self) -> bool:
        return self.method != AuthMethod.ANONYMOUS

    def to_dict(self) -> dict:
        """Serialize for audit log / JSON responses."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "org_id": self.org_id,
            "org_slug": self.org_slug,
            "role": self.role.value,
            "method": self.method.value,
            "api_key_id": self.api_key_id,
        }

    @classmethod
    def anonymous(cls) -> "AuthContext":
        """Return an unauthenticated context (for auth-disabled mode)."""
        return cls(
            claims=TokenClaims(sub="anonymous", org_id="default", org_slug="default"),
            method=AuthMethod.ANONYMOUS,
        )
