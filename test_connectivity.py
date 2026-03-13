#!/usr/bin/env python3
"""
Quick connectivity test for all backend services
"""
import httpx
import sys

# Test service connectivity
services = {
    'config': 'http://config:3007',  # Using docker network names
    'strategy': 'http://strategy:3002', 
    'risk': 'http://risk:3003',
    'execution': 'http://execution:3004',
    'portfolio': 'http://portfolio:3005',  # Note: portfolio service runs on 3005
    'orchestrator': 'http://orchestrator:3005',  # Note: orchestrator also on 3005
    'data_ingestion': 'http://data_ingestion:3009'
}

print('🔍 Testing service connectivity...')
failed = []

for service, url in services.items():
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f'{url}/health')
            if resp.status_code == 200:
                data = resp.json()
                print(f'✅ {service:15} ({url}) - {data.get("status", "OK")}')
            else:
                print(f'❌ {service:15} ({url}) - HTTP {resp.status_code}')
                failed.append(service)
    except Exception as e:
        print(f'❌ {service:15} ({url}) - {str(e)[:50]}')
        failed.append(service)

print(f'\n📊 Results: {len(services) - len(failed)}/{len(services)} services healthy')

if failed:
    print(f'❌ Failed services: {failed}')
    sys.exit(1)
else:
    print('✅ All services are healthy!')