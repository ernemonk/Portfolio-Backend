"""
Vault Client - Helper for services to fetch credentials from the data_ingestion vault API.

Usage:
    from trading_os.security.vault_client import VaultClient
    
    vault = VaultClient(vault_url="http://localhost:3009")
    api_key = await vault.get_credential("binance", "api_key")
    api_secret = await vault.get_credential("binance", "api_secret")
"""

import asyncio
from typing import Dict, Optional, List
import aiohttp
import os


class VaultClient:
    """Client for fetching decrypted credentials from the data_ingestion vault API."""
    
    def __init__(self, vault_url: Optional[str] = None):
        """
        Initialize vault client.
        
        Args:
            vault_url: Base URL of the data_ingestion service (e.g., "http://localhost:3009")
                      Defaults to http://localhost:3009 or DATA_INGESTION_URL env var
        """
        self.vault_url = vault_url or os.getenv("DATA_INGESTION_URL", "http://localhost:3009")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Context manager entry."""
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._session:
            await self._session.close()
    
    async def get_credential(
        self, 
        provider_name: str, 
        credential_key: str = "api_key"
    ) -> Optional[str]:
        """
        Fetch and decrypt a credential from the vault.
        
        Args:
            provider_name: Provider name (e.g., "binance", "anthropic")
            credential_key: Credential key (e.g., "api_key", "api_secret")
        
        Returns:
            Decrypted credential value or None if not found
        
        Raises:
            aiohttp.ClientError: If vault API is unreachable
            ValueError: If credential not found or inactive
        """
        session = self._session or aiohttp.ClientSession()
        try:
            # Fetch credential metadata
            async with session.get(
                f"{self.vault_url}/credentials",
                params={
                    "provider_name": provider_name,
                    "credential_key": credential_key,
                }
            ) as resp:
                if resp.status != 200:
                    raise ValueError(
                        f"Failed to fetch credential {provider_name}.{credential_key}: HTTP {resp.status}"
                    )
                
                credentials = await resp.json()
                
                if not credentials:
                    raise ValueError(
                        f"Credential not found: {provider_name}.{credential_key}"
                    )
                
                # Get the first matching credential
                cred = credentials[0]
                
                if not cred.get("is_active", True):
                    raise ValueError(
                        f"Credential is inactive: {provider_name}.{credential_key}"
                    )
                
                # Fetch decrypted value
                cred_id = cred["id"]
                async with session.get(
                    f"{self.vault_url}/credentials/{cred_id}/decrypt"
                ) as decrypt_resp:
                    if decrypt_resp.status != 200:
                        raise ValueError(
                            f"Failed to decrypt credential {cred_id}: HTTP {decrypt_resp.status}"
                        )
                    
                    data = await decrypt_resp.json()
                    return data.get("value")
        
        finally:
            if not self._session:
                await session.close()
    
    async def list_credentials(
        self, 
        provider_name: Optional[str] = None
    ) -> List[Dict]:
        """
        List all credentials (without encrypted values).
        
        Args:
            provider_name: Optional filter by provider name
        
        Returns:
            List of credential metadata dictionaries
        """
        session = self._session or aiohttp.ClientSession()
        try:
            params = {}
            if provider_name:
                params["provider_name"] = provider_name
            
            async with session.get(
                f"{self.vault_url}/credentials",
                params=params
            ) as resp:
                if resp.status != 200:
                    raise ValueError(f"Failed to list credentials: HTTP {resp.status}")
                
                return await resp.json()
        
        finally:
            if not self._session:
                await session.close()
    
    async def get_vault_status(self) -> Dict:
        """
        Get vault status and statistics.
        
        Returns:
            Vault status dictionary with total_credentials, active_credentials, providers, etc.
        """
        session = self._session or aiohttp.ClientSession()
        try:
            async with session.get(f"{self.vault_url}/vault/status") as resp:
                if resp.status != 200:
                    raise ValueError(f"Failed to get vault status: HTTP {resp.status}")
                
                return await resp.json()
        
        finally:
            if not self._session:
                await session.close()


# Convenience function for one-off credential fetches
async def get_credential(
    provider_name: str,
    credential_key: str = "api_key",
    vault_url: Optional[str] = None
) -> Optional[str]:
    """
    Fetch a single credential from the vault (convenience function).
    
    Example:
        api_key = await get_credential("binance", "api_key")
        api_secret = await get_credential("binance", "api_secret")
    
    Args:
        provider_name: Provider name
        credential_key: Credential key
        vault_url: Optional vault URL override
    
    Returns:
        Decrypted credential value
    """
    async with VaultClient(vault_url) as vault:
        return await vault.get_credential(provider_name, credential_key)


if __name__ == "__main__":
    # Example usage
    async def main():
        # Using context manager (recommended for multiple calls)
        async with VaultClient() as vault:
            try:
                api_key = await vault.get_credential("binance", "api_key")
                print(f"Binance API Key: {api_key[:10]}..." if api_key else "Not found")
                
                status = await vault.get_vault_status()
                print(f"Vault Status: {status}")
            except Exception as e:
                print(f"Error: {e}")
        
        # One-off fetch
        try:
            secret = await get_credential("anthropic", "api_key")
            print(f"Anthropic Key: {secret[:10]}..." if secret else "Not found")
        except Exception as e:
            print(f"Error: {e}")
    
    asyncio.run(main())
