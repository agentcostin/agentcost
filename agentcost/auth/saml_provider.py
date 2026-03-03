"""
SAML 2.0 Service Provider — Enterprise SSO integration.

Handles the SAML SP side of authentication:
  - Generate SP metadata XML
  - Create AuthnRequest redirects to IdP (Keycloak)
  - Parse and validate ACS (Assertion Consumer Service) POST responses
  - Single Logout (SLO)

For local dev, Keycloak acts as both IdP and the bridge to external SAML IdPs.
In production, each enterprise customer configures their corporate IdP
(Okta, Azure AD, Ping, etc.) in Keycloak as an identity provider broker.

Dependencies: python3-saml (OneLogin's SAML toolkit)
  pip install python3-saml
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from .config import AuthConfig, get_auth_config
from .models import TokenClaims

logger = logging.getLogger("agentcost.auth.saml")


def _get_saml_settings(config: Optional[AuthConfig] = None, request_data: Optional[dict] = None) -> dict:
    """Build the python3-saml settings dict from our config.

    This maps AgentCost config to the structure OneLogin's toolkit expects.
    """
    cfg = config or get_auth_config()
    urlparse(cfg.saml_acs_url)

    settings = {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": cfg.saml_entity_id,
            "assertionConsumerService": {
                "url": cfg.saml_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": cfg.saml_slo_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": f"{cfg.keycloak_url}/realms/{cfg.realm}",
            "singleSignOnService": {
                "url": f"{cfg.keycloak_url}/realms/{cfg.realm}/protocol/saml",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": f"{cfg.keycloak_url}/realms/{cfg.realm}/protocol/saml",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            # Keycloak's signing cert — fetched dynamically or configured
            "x509cert": "",
        },
        "security": {
            "nameIdEncrypted": False,
            "authnRequestsSigned": False,
            "logoutRequestSigned": False,
            "logoutResponseSigned": False,
            "signMetadata": False,
            "wantMessagesSigned": True,
            "wantAssertionsSigned": True,
            "wantAssertionsEncrypted": False,
            "wantNameIdEncrypted": False,
            "requestedAuthnContext": False,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
            "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
        },
    }

    return settings


def _fetch_idp_metadata(config: Optional[AuthConfig] = None) -> str:
    """Fetch SAML IdP metadata XML from Keycloak."""
    import urllib.request
    import ssl

    cfg = config or get_auth_config()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = cfg.saml_idp_metadata_url
    req = urllib.request.Request(url, headers={"Accept": "application/xml"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return resp.read().decode("utf-8")


def get_sp_metadata(config: Optional[AuthConfig] = None) -> str:
    """Generate SAML SP metadata XML for AgentCost.

    This XML is provided to enterprise customers or uploaded to their IdP
    so they can configure their side of the SAML trust.
    """
    try:
        from onelogin.saml2.metadata import OneLogin_Saml2_Metadata  # noqa: F401
        from onelogin.saml2.settings import OneLogin_Saml2_Settings

        settings = OneLogin_Saml2_Settings(_get_saml_settings(config), sp_validation_only=True)
        metadata = settings.get_sp_metadata()
        errors = settings.validate_metadata(metadata)

        if errors:
            logger.error("SP metadata validation errors: %s", errors)

        return metadata.decode("utf-8") if isinstance(metadata, bytes) else metadata
    except ImportError:
        # Fallback: generate minimal metadata XML without python3-saml
        cfg = config or get_auth_config()
        return _minimal_sp_metadata(cfg)


def _minimal_sp_metadata(cfg: AuthConfig) -> str:
    """Minimal SAML SP metadata XML — no external dependency."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="{cfg.saml_entity_id}">
  <md:SPSSODescriptor
      AuthnRequestsSigned="false"
      WantAssertionsSigned="true"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>
    <md:AssertionConsumerService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="{cfg.saml_acs_url}"
        index="1" isDefault="true"/>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="{cfg.saml_slo_url}"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>"""


def create_authn_request(
    request_data: dict,
    relay_state: str = "/",
    config: Optional[AuthConfig] = None,
) -> tuple[str, dict]:
    """Create a SAML AuthnRequest and return the redirect URL.

    Args:
        request_data: Dict with 'http_host', 'server_port', 'script_name', etc.
        relay_state: URL to redirect to after successful auth.
        config: Auth config override.

    Returns:
        (redirect_url, request_info) — redirect_url to send the browser to.
    """
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        saml_auth = OneLogin_Saml2_Auth(request_data, _get_saml_settings(config))
        redirect_url = saml_auth.login(return_to=relay_state)
        return redirect_url, {"request_id": saml_auth.get_last_request_id()}
    except ImportError:
        # Fallback: construct redirect URL manually
        cfg = config or get_auth_config()
        idp_sso_url = f"{cfg.keycloak_url}/realms/{cfg.realm}/protocol/saml"
        logger.warning("python3-saml not installed — using basic SAML redirect")
        return idp_sso_url, {}


def process_saml_response(
    request_data: dict,
    config: Optional[AuthConfig] = None,
) -> tuple[Optional[TokenClaims], list[str]]:
    """Process a SAML Response POST at the ACS endpoint.

    Args:
        request_data: Dict with POST body containing SAMLResponse.

    Returns:
        (claims, errors) — TokenClaims if valid, errors list if not.
    """
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        saml_auth = OneLogin_Saml2_Auth(request_data, _get_saml_settings(config))
        saml_auth.process_response()
        errors = saml_auth.get_errors()

        if errors:
            logger.error("SAML response errors: %s (reason: %s)",
                         errors, saml_auth.get_last_error_reason())
            return None, errors

        if not saml_auth.is_authenticated():
            return None, ["User not authenticated"]

        # Extract attributes and NameID
        attributes = saml_auth.get_attributes()
        name_id = saml_auth.get_nameid()

        logger.info("SAML auth success: name_id=%s attrs=%s", name_id, list(attributes.keys()))

        claims = TokenClaims.from_saml(attributes, name_id=name_id)
        return claims, []

    except ImportError:
        logger.error("python3-saml not installed — cannot process SAML response")
        return None, ["python3-saml package not installed"]
    except Exception as e:
        logger.error("SAML processing error: %s", e, exc_info=True)
        return None, [str(e)]


def process_slo(
    request_data: dict,
    config: Optional[AuthConfig] = None,
) -> tuple[Optional[str], list[str]]:
    """Process SAML Single Logout request/response.

    Returns:
        (redirect_url, errors)
    """
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth

        saml_auth = OneLogin_Saml2_Auth(request_data, _get_saml_settings(config))
        redirect_url = saml_auth.process_slo()
        errors = saml_auth.get_errors()
        return redirect_url, errors
    except ImportError:
        return None, ["python3-saml not installed"]
