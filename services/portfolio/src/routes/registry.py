"""
Service registry endpoint - tells frontend where all services are located.
This avoids CORS issues by having backend proxy handle service discovery.
"""

from fastapi import APIRouter, Request
import os

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/services")
async def get_services_registry(request: Request):
    """
    Get all service endpoints.
    Automatically detects backend host from incoming request.
    """
    # Get the host from the incoming request
    # This handles both localhost and external access
    client_host = request.headers.get("x-forwarded-host") or request.client.host
    if client_host.startswith("::1"):  # IPv6 localhost
        client_host = "localhost"
    
    # For development, use environment variable if set, otherwise use request host
    backend_host = os.getenv("BACKEND_HOST", "localhost")
    
    services = {
        "portfolio": f"http://{backend_host}:3001",
        "strategy": f"http://{backend_host}:3002",
        "risk": f"http://{backend_host}:3003",
        "execution": f"http://{backend_host}:3004",
        "orchestrator": f"http://{backend_host}:3005",
        "analytics": f"http://{backend_host}:3006",
        "config": f"http://{backend_host}:3007",
        "local_ai": f"http://{backend_host}:3008",
    }
    
    return {
        "services": services,
        "backend_host": backend_host,
    }
