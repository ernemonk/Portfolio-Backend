"""
API Proxy Router
──────────────────────────────────
Routes all /api/{service}/* requests from the browser through the portfolio service,
eliminating CORS issues. The portfolio service proxies to the actual backend services.
"""

import os
from fastapi import APIRouter, Request, Response
import httpx

router = APIRouter(prefix="/api", tags=["proxy"])

# Service URLs - use Docker internal hostnames + their assigned ports
SERVICE_URLS = {
    "portfolio": "http://portfolio:3001",
    "strategy": "http://strategy:3002",
    "risk": "http://risk:3003",
    "execution": "http://execution:3004",
    "orchestrator": "http://orchestrator:3005",
    "analytics": "http://analytics:3006",
    "config": "http://config:3007",
    "local_ai": "http://local_ai:3008",
}


@router.api_route("/{service_name}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_request(service_name: str, path: str, request: Request):
    """
    Proxy all requests from browser to backend services.
    
    Example:
      GET /api/config/health
      → Proxies to http://config:3006/health
    """
    
    if service_name not in SERVICE_URLS:
        return Response(
            content=f"Unknown service: {service_name}",
            status_code=404,
        )
    
    service_url = SERVICE_URLS[service_name]
    target_url = f"{service_url}/{path}"
    
    # Copy query parameters
    if request.query_params:
        target_url += f"?{request.query_params}"
    
    # Longer timeout for AI model operations (loading can take 60+ seconds)
    timeout = 120.0 if service_name == "local_ai" else 30.0
    
    try:
        # Copy request body for POST/PUT requests
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
        
        # Copy important headers
        headers = {}
        content_type = request.headers.get("content-type")
        if content_type:
            headers["Content-Type"] = content_type
        
        # Proxy the request with extended timeout for AI
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
            )
            
            # Return response with same status and headers
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={
                    k: v for k, v in response.headers.items()
                    if k.lower() not in ["content-encoding", "content-length"]
                },
            )
    except httpx.TimeoutException:
        return Response(
            content=f"Service {service_name} timeout",
            status_code=504,
        )
    except Exception as e:
        return Response(
            content=f"Error proxying to {service_name}: {str(e)}",
            status_code=502,
        )
