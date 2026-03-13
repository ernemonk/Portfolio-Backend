#!/usr/bin/env python3
"""
Comprehensive backend service testing
"""
import httpx
import json
from datetime import datetime

print('🧪 COMPREHENSIVE SERVICE TESTING')
print('=' * 50)

services = {
    'strategy': 'http://strategy:3002',
    'risk': 'http://risk:3003', 
    'execution': 'http://execution:3004',
    'orchestrator': 'http://orchestrator:3005',
    'data_ingestion': 'http://data_ingestion:3009',
    'config': 'http://config:3007'
}

# Test data
test_candles = [
    {'timestamp': 1700000000000, 'open': 29000, 'high': 30000, 'low': 28500, 'close': 29800, 'volume': 100},
    {'timestamp': 1700086400000, 'open': 29800, 'high': 31000, 'low': 29000, 'close': 30500, 'volume': 120},
    {'timestamp': 1700172800000, 'open': 30500, 'high': 32000, 'low': 30000, 'close': 31500, 'volume': 110}
]

client = httpx.Client(timeout=10.0)
test_results = {}

for service_name, base_url in services.items():
    print(f'\n📊 Testing {service_name.upper()} ({base_url})')
    print('-' * 40)
    
    service_results = {'health': False, 'functionality': False, 'details': []}
    
    try:
        # Test health endpoint
        resp = client.get(f'{base_url}/health')
        if resp.status_code == 200:
            health_data = resp.json()
            service_results['health'] = True
            print(f'✅ Health: {health_data.get("status", "ok")}')
            service_results['details'].append(f'Health: {health_data.get("status", "ok")}')
            
            if 'uptime' in health_data:
                print(f'   Uptime: {health_data["uptime"]:.1f}s')
                service_results['details'].append(f'Uptime: {health_data["uptime"]:.1f}s')
            if 'checks' in health_data:
                for check, status in health_data['checks'].items():
                    print(f'   {check}: {status}')
                    service_results['details'].append(f'{check}: {status}')
        else:
            print(f'❌ Health check failed: {resp.status_code}')
            service_results['details'].append(f'Health failed: {resp.status_code}')
            test_results[service_name] = service_results
            continue
            
    except Exception as e:
        print(f'❌ Service unreachable: {str(e)[:50]}')
        service_results['details'].append(f'Unreachable: {str(e)[:50]}')
        test_results[service_name] = service_results
        continue
        
    # Service-specific functionality tests
    try:
        if service_name == 'strategy':
            resp = client.get(f'{base_url}/strategies')
            if resp.status_code == 200:
                strategies = resp.json()
                service_results['functionality'] = True
                print(f'✅ Strategy list: {len(strategies)} strategies loaded')
                service_results['details'].append(f'{len(strategies)} strategies loaded')
                for strat in strategies:
                    status_text = "enabled" if strat["enabled"] else "disabled"
                    print(f'   - {strat["name"]}: {status_text}')
                    service_results['details'].append(f'{strat["name"]}: {status_text}')
            else:
                print(f'❌ Strategy list failed: {resp.status_code}')
                service_results['details'].append(f'Strategy list failed: {resp.status_code}')
                
        elif service_name == 'risk':
            resp = client.get(f'{base_url}/limits')
            if resp.status_code == 200:
                limits = resp.json()
                service_results['functionality'] = True
                print(f'✅ Risk limits retrieved: {len(limits)} limits')
                service_results['details'].append(f'{len(limits)} risk limits')
            else:
                print(f'❌ Risk limits failed: {resp.status_code}')
                service_results['details'].append(f'Risk limits failed: {resp.status_code}')
                
        elif service_name == 'execution':
            resp = client.get(f'{base_url}/queue/status')  
            if resp.status_code == 200:
                queue_status = resp.json()
                service_results['functionality'] = True
                size = queue_status.get("size", "unknown")
                print(f'✅ Execution queue: {size} orders')
                service_results['details'].append(f'Queue: {size} orders')
            else:
                print(f'❌ Execution queue check failed: {resp.status_code}')
                service_results['details'].append(f'Queue check failed: {resp.status_code}')
                
        elif service_name == 'orchestrator':
            resp = client.get(f'{base_url}/status')
            if resp.status_code == 200:
                orch_status = resp.json() 
                service_results['functionality'] = True
                status = orch_status.get("status", "unknown")
                print(f'✅ Orchestrator status: {status}')
                service_results['details'].append(f'Status: {status}')
            else:
                print(f'❌ Orchestrator status failed: {resp.status_code}')
                service_results['details'].append(f'Status check failed: {resp.status_code}')
                
        elif service_name == 'data_ingestion':
            resp = client.get(f'{base_url}/connectors')
            if resp.status_code == 200:
                connectors = resp.json()
                service_results['functionality'] = True
                print(f'✅ Data connectors: {len(connectors)} configured')
                service_results['details'].append(f'{len(connectors)} data connectors')
            else:
                print(f'❌ Data connectors failed: {resp.status_code}')
                service_results['details'].append(f'Connectors failed: {resp.status_code}')
                
        elif service_name == 'config':
            resp = client.get(f'{base_url}/config')
            if resp.status_code == 200:
                config_data = resp.json()
                service_results['functionality'] = True
                print(f'✅ Config data retrieved: {len(config_data)} settings')
                service_results['details'].append(f'{len(config_data)} config settings')
            else:
                print(f'❌ Config retrieval failed: {resp.status_code}')
                service_results['details'].append(f'Config failed: {resp.status_code}')
                
    except Exception as e:
        print(f'⚠️  Functionality test error: {str(e)[:50]}')
        service_results['details'].append(f'Func error: {str(e)[:50]}')
        
    test_results[service_name] = service_results

client.close()

# Summary
print(f'\n🏁 TESTING COMPLETE at {datetime.now().strftime("%H:%M:%S")}')
print('=' * 50)

healthy_services = sum(1 for result in test_results.values() if result['health'])
functional_services = sum(1 for result in test_results.values() if result['functionality'])

print(f'📊 Health Status: {healthy_services}/{len(services)} services healthy')
print(f'🔧 Functionality: {functional_services}/{len(services)} services functional')

if healthy_services == len(services) and functional_services == len(services):
    print('\n🎉 ALL SERVICES PASSING - READY FOR INTEGRATION TESTING!')
else:
    print('\n❌ Some services need attention:')
    for service_name, results in test_results.items():
        if not (results['health'] and results['functionality']):
            status = '❌ FAIL'
            if results['health'] and not results['functionality']:
                status = '⚠️  PARTIAL'
            print(f'   {service_name}: {status}')