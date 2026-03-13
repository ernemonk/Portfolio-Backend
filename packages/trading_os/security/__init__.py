"""
trading_os.security
━━━━━━━━━━━━━━━━━━━
AES-256 encrypted credential vault for API keys and secrets.
"""

from trading_os.security.vault import APIKeyVault, EncryptionError

__all__ = ["APIKeyVault", "EncryptionError"]
