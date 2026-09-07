"""
Shared Auth Authenticator — LDAP/AD binding + local user sync.

Handles:
- LDAP bind authentication against Active Directory
- Local user lookup in iam.users (sync on first login)
- Role resolution from iam.user_roles
- Building UserContext after successful auth
"""

from __future__ import annotations

import logging
from uuid import UUID

import ldap3
from ldap3 import Connection, Server, ALL, NTLM

from shared.auth.models import UserContext

logger = logging.getLogger("auth.authenticator")


# ===========================================================================
# Exception classes
# ===========================================================================

class AuthenticationError(Exception):
    """Base class for auth failures."""


class InvalidCredentialsError(AuthenticationError):
    """Username or password is incorrect."""


class AccountDisabledError(AuthenticationError):
    """User account is deactivated."""


class AccountLockedError(AuthenticationError):
    """User account is locked after too many failed attempts."""


class LDAPConnectionError(AuthenticationError):
    """Cannot reach the LDAP/AD server."""


# ===========================================================================
# Authenticator
# ===========================================================================

class Authenticator:
    """Authenticates users against LDAP/Active Directory and syncs local state."""

    def __init__(
        self,
        server_url: str,
        base_dn: str,
        bind_dn: str | None = None,
        bind_password: str | None = None,
        user_dn_template: str | None = None,
        search_filter: str = "(sAMAccountName={username})",
        timeout: int = 10,
        use_tls: bool = False,
    ) -> None:
        self._server_url = server_url
        self._base_dn = base_dn
        self._bind_dn = bind_dn
        self._bind_password = bind_password
        self._user_dn_template = user_dn_template
        self._search_filter = search_filter
        self._timeout = timeout
        self._use_tls = use_tls

    def authenticate(self, username: str, password: str) -> dict:
        """Authenticate against LDAP and return AD attributes.

        Returns dict with: dn, username, email, display_name, department.
        Raises InvalidCredentialsError, AccountLockedError, LDAPConnectionError.
        """
        if self._user_dn_template:
            user_dn = self._user_dn_template.format(username=username)
            return self._direct_bind(user_dn, username, password)
        return self._search_and_bind(username, password)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _direct_bind(self, user_dn: str, username: str, password: str) -> dict:
        """Bind directly using a DN template."""
        server = Server(
            self._server_url, get_info=ALL, connect_timeout=self._timeout,
            use_ssl=self._use_tls,
        )
        try:
            conn = Connection(
                server, user=user_dn, password=password,
                authentication=NTLM, auto_bind=True,
                receive_timeout=self._timeout,
            )
            conn.search(
                search_base=user_dn, search_filter="(objectClass=*)",
                search_scope=ldap3.BASE, attributes=["*"],
            )
            if not conn.entries:
                raise InvalidCredentialsError(f"User '{username}' not found in AD")
            entry = conn.entries[0]
            conn.unbind()
            return self._extract_attributes(entry, user_dn, username)

        except ldap3.core.exceptions.LDAPInvalidCredentialsResult:
            raise InvalidCredentialsError(f"Invalid credentials for '{username}'")
        except ldap3.core.exceptions.LDAPAccountLockedResult:
            raise AccountLockedError(f"Account '{username}' is locked")
        except ldap3.core.exceptions.LDAPSocketOpenError as e:
            raise LDAPConnectionError(f"Cannot reach LDAP server: {e}") from e

    def _search_and_bind(self, username: str, password: str) -> dict:
        """Search for user with service account, then bind as user."""
        server = Server(
            self._server_url, get_info=ALL, connect_timeout=self._timeout,
            use_ssl=self._use_tls,
        )
        try:
            conn = Connection(
                server, user=self._bind_dn, password=self._bind_password,
                authentication=NTLM, auto_bind=True,
                receive_timeout=self._timeout,
            )
            search_filter = self._search_filter.format(username=username)
            conn.search(
                search_base=self._base_dn, search_filter=search_filter,
                search_scope=ldap3.SUBTREE, attributes=["*"],
            )
            if not conn.entries:
                raise InvalidCredentialsError(f"User '{username}' not found in AD")
            user_dn = conn.entries[0].entry_dn
            conn.unbind()
            return self._direct_bind(user_dn, username, password)

        except ldap3.core.exceptions.LDAPInvalidCredentialsResult:
            raise InvalidCredentialsError(f"Invalid credentials for '{username}'")
        except ldap3.core.exceptions.LDAPSocketOpenError as e:
            raise LDAPConnectionError(f"Cannot reach LDAP server: {e}") from e

    @staticmethod
    def _extract_attributes(entry, user_dn: str, username: str) -> dict:
        """Extract key attributes from an LDAP entry."""
        return {
            "dn": user_dn,
            "username": username,
            "email": str(entry.mail) if hasattr(entry, "mail") else "",
            "display_name": str(entry.displayName) if hasattr(entry, "displayName") else username,
            "department": str(entry.department) if hasattr(entry, "department") else None,
        }
