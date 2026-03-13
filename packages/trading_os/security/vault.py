"""
trading_os.security.vault
━━━━━━━━━━━━━━━━━━━━━━━━━
AES-256 Fernet encryption vault for API credentials.

The master key is read from the VAULT_MASTER_KEY environment variable.
If no key exists on first boot, one is auto-generated and printed to stdout
so the operator can persist it in docker-compose / .env.

Usage:
    from trading_os.security.vault import APIKeyVault

    vault = APIKeyVault()                       # reads VAULT_MASTER_KEY from env
    encrypted = vault.encrypt("sk-live-abc123") # → base64 ciphertext
    plaintext = vault.decrypt(encrypted)        # → "sk-live-abc123"
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when encrypt/decrypt operations fail."""


class APIKeyVault:
    """
    Symmetric encryption vault using Fernet (AES-128-CBC + HMAC-SHA256).

    Fernet requires a 32-byte URL-safe base64-encoded key.
    We derive it from VAULT_MASTER_KEY via SHA-256 so operators can use
    any passphrase string rather than needing a specific format.
    """

    def __init__(self, master_key: Optional[str] = None) -> None:
        raw_key = master_key or os.environ.get("VAULT_MASTER_KEY")

        if not raw_key:
            # Auto-generate a key for first-time setup
            raw_key = secrets.token_urlsafe(32)
            print(
                "\n"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  ⚠️  VAULT_MASTER_KEY not set — auto-generated:        ║\n"
                f"║  {raw_key:<55}║\n"
                "║                                                        ║\n"
                "║  Add this to docker-compose.yml environment or .env    ║\n"
                "║  VAULT_MASTER_KEY={key}                                ║\n"
                "╚══════════════════════════════════════════════════════════╝\n"
            )
            os.environ["VAULT_MASTER_KEY"] = raw_key

        # Derive a Fernet-compatible 32-byte key from the passphrase
        derived = hashlib.sha256(raw_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(derived)
        self._fernet = Fernet(fernet_key)

    # ── Public API ────────────────────────────────────────────────────────

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string → base64 ciphertext string."""
        if not plaintext:
            return ""
        try:
            token = self._fernet.encrypt(plaintext.encode("utf-8"))
            return token.decode("utf-8")
        except Exception as exc:
            raise EncryptionError(f"Encryption failed: {exc}") from exc

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64 ciphertext string → plaintext string."""
        if not ciphertext:
            return ""
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return plaintext.decode("utf-8")
        except InvalidToken:
            raise EncryptionError(
                "Decryption failed — wrong master key or corrupted data"
            )
        except Exception as exc:
            raise EncryptionError(f"Decryption failed: {exc}") from exc

    def rotate_key(self, new_master_key: str, encrypted_values: list[str]) -> list[str]:
        """
        Re-encrypt a list of ciphertext values with a new master key.
        Returns the list of newly-encrypted values in the same order.
        """
        # Decrypt everything with the current key
        plaintexts = [self.decrypt(ct) for ct in encrypted_values]

        # Build a new vault with the new key
        new_vault = APIKeyVault(master_key=new_master_key)

        # Re-encrypt with the new key
        return [new_vault.encrypt(pt) for pt in plaintexts]

    @staticmethod
    def generate_master_key() -> str:
        """Generate a cryptographically secure master key string."""
        return secrets.token_urlsafe(32)

    def is_encrypted(self, value: str) -> bool:
        """Best-effort check if a string looks like Fernet ciphertext."""
        if not value:
            return False
        try:
            # Fernet tokens are base64-encoded and start with 'gAAAAA'
            return value.startswith("gAAAAA") and len(value) > 100
        except Exception:
            return False
