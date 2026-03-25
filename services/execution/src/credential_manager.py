"""
Credential Manager for Alpaca Integration
Fetches encrypted credentials from Config service vault
"""

import httpx
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class CredentialManager:
    """
    Manages credential retrieval from Config service vault
    
    Credentials are stored encrypted in PostgreSQL and retrieved via:
    GET /credentials/{id}/decrypt -> returns decrypted value
    """
    
    CONFIG_SERVICE_URL = "http://config:3007"  # Docker internal network
    
    @staticmethod
    async def get_alpaca_credentials() -> Dict[str, str]:
        """
        Retrieve Alpaca credentials from vault
        
        Returns:
            {"api_key": "...", "api_secret": "..."}
        
        Credential format in vault:
        - Provider: "Alpaca"
        - Key: "api_key" -> contains API key
        - Key: "api_secret" -> contains API secret
        """
        try:
            # Step 1: List all credentials
            async with httpx.AsyncClient() as client:
                list_response = await client.get(
                    f"{CredentialManager.CONFIG_SERVICE_URL}/credentials",
                    timeout=10
                )
                list_response.raise_for_status()
                credentials = list_response.json()
            
            # Step 2: Find Alpaca credentials
            alpaca_creds = {}
            for cred in credentials:
                if cred.get("provider_name", "").lower() == "alpaca":
                    key = cred.get("credential_key")
                    cred_id = cred.get("id")
                    
                    if cred_id and key in ["api_key", "api_secret"]:
                        # Step 3: Decrypt each credential
                        async with httpx.AsyncClient() as client:
                            decrypt_response = await client.post(
                                f"{CredentialManager.CONFIG_SERVICE_URL}/credentials/{cred_id}/decrypt",
                                timeout=10
                            )
                            decrypt_response.raise_for_status()
                            decrypted = decrypt_response.json()
                            alpaca_creds[key] = decrypted.get("decrypted_value")
            
            if not alpaca_creds.get("api_key") or not alpaca_creds.get("api_secret"):
                raise ValueError("Alpaca credentials incomplete in vault")
            
            logger.info("✓ Retrieved Alpaca credentials from vault")
            return alpaca_creds
        
        except Exception as e:
            logger.error(f"Failed to get Alpaca credentials: {e}")
            raise
    
    @staticmethod
    async def get_credential(
        provider: str, 
        key: str
    ) -> Optional[str]:
        """
        Get a specific credential by provider and key
        
        Args:
            provider: Provider name (e.g., "Alpaca", "CoinGecko")
            key: Credential key (e.g., "api_key", "api_secret")
        
        Returns:
            Decrypted credential value or None
        """
        try:
            async with httpx.AsyncClient() as client:
                # List credentials
                list_response = await client.get(
                    f"{CredentialManager.CONFIG_SERVICE_URL}/credentials",
                    timeout=10
                )
                list_response.raise_for_status()
                credentials = list_response.json()
            
            # Find matching credential
            for cred in credentials:
                if (cred.get("provider_name", "").lower() == provider.lower() and
                    cred.get("credential_key") == key):
                    
                    cred_id = cred.get("id")
                    if cred_id:
                        # Decrypt
                        async with httpx.AsyncClient() as client:
                            decrypt_response = await client.post(
                                f"{CredentialManager.CONFIG_SERVICE_URL}/credentials/{cred_id}/decrypt",
                                timeout=10
                            )
                            decrypt_response.raise_for_status()
                            decrypted = decrypt_response.json()
                            value = decrypted.get("decrypted_value")
                            logger.info(f"✓ Retrieved {provider}/{key} from vault")
                            return value
            
            logger.warning(f"Credential not found: {provider}/{key}")
            return None
        
        except Exception as e:
            logger.error(f"Failed to get credential {provider}/{key}: {e}")
            return None
    
    @staticmethod
    async def list_providers() -> list:
        """List all providers that have stored credentials"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{CredentialManager.CONFIG_SERVICE_URL}/credentials",
                    timeout=10
                )
                response.raise_for_status()
                credentials = response.json()
            
            providers = list(set(c.get("provider_name") for c in credentials if c.get("provider_name")))
            logger.info(f"✓ Available providers: {providers}")
            return providers
        
        except Exception as e:
            logger.error(f"Failed to list providers: {e}")
            return []
