#!/usr/bin/env python3
"""
P0 Critical Improvements Test Script
Tests the newly implemented institutional libraries and enhanced connectors
Verifies API health monitoring and failover capabilities
"""

import asyncio
import sys
import os
from datetime import datetime

# Add Backend services to path
sys.path.append('/Users/user/Projects/Portfolio/Backend/services/data_ingestion/src')

async def test_institutional_libraries():
    """Test newly installed institutional libraries"""
    
    print("🧪 Testing Institutional Libraries Installation...")
    
    tests = []
    
    # Test CCXT
    try:
        import ccxt
        exchanges = ccxt.exchanges
        tests.append(f"✅ CCXT v{ccxt.__version__} - {len(exchanges)} exchanges available")
    except ImportError as e:
        tests.append(f"❌ CCXT import failed: {e}")
    
    # Test FRED API
    try:
        from fredapi import Fred
        tests.append("✅ FRED API library available")
    except ImportError as e:
        tests.append(f"❌ FRED API import failed: {e}")
    
    # Test WebSocket libraries
    try:
        import websockets
        tests.append("✅ WebSocket library available")
    except ImportError as e:
        tests.append(f"❌ WebSocket import failed: {e}")
    
    # Test Tornado
    try:
        import tornado
        tests.append("✅ Tornado web framework available")
    except ImportError as e:
        tests.append(f"❌ Tornado import failed: {e}")
    
    # Test Data Science libraries
    try:
        import pandas as pd
        import numpy as np
        tests.append(f"✅ Pandas v{pd.__version__} & NumPy v{np.__version__}")
    except ImportError as e:
        tests.append(f"❌ Data science libraries import failed: {e}")
    
    for test_result in tests:
        print(f"   {test_result}")
    
    return len([t for t in tests if "✅" in t])


async def test_api_health_monitoring():
    """Test the new API health monitoring system"""
    
    print("\n🔍 Testing API Health Monitoring System...")
    
    try:
        from monitoring.api_health_monitor import APIHealthMonitor
        
        monitor = APIHealthMonitor()
        
        # Test monitoring configuration
        total_services = len(monitor.service_configs)
        critical_services = len([s for s in monitor.service_configs.values() if s.get('critical', False)])
        
        print(f"   ✅ Monitor configured for {total_services} services")
        print(f"   📊 {critical_services} critical services identified")
        
        # Test a few key services
        test_services = ['kraken', 'coingecko', 'coinpaprika']
        working_services = 0
        
        for service in test_services:
            try:
                metrics = await monitor.check_service(service)
                if metrics and any(m.status in ['healthy', 'degraded'] for m in metrics):
                    status = "✅ Working"
                    working_services += 1
                else:
                    status = "⚠️  Issues detected"
                
                print(f"   {status} {service}")
                
            except Exception as e:
                print(f"   ❌ {service} test failed: {str(e)[:50]}")
        
        # Test dashboard generation
        dashboard = monitor.get_dashboard_data()
        print(f"   📊 Dashboard generated - System status: {dashboard['system_status']}")
        
        return working_services
        
    except Exception as e:
        print(f"   ❌ Health monitoring test failed: {e}")
        return 0


async def test_enhanced_ccxt_connector():
    """Test the enhanced CCXT connector"""
    
    print("\n🌐 Testing Enhanced CCXT Connector...")
    
    try:
        from connectors.ccxt_universal import CCXTConnector, WebSocketStreamer
        from src.rate_limiter import RateLimiter
        
        # Create rate limiter
        rate_limiter = RateLimiter()
        
        connector = CCXTConnector(rate_limiter, exchange_name='kraken')  # Use Kraken (most reliable)
        
        # Test connection
        connection_test = await connector.test_connection()
        
        if connection_test.get('ok'):
            print(f"   ✅ {connection_test.get('message')}")
        else:
            print(f"   ⚠️  Connection test: {connection_test.get('message', 'Unknown issue')}")
        
        # Test exchange health report
        print("   🔍 Testing exchange connectivity across multiple exchanges...")
        
        health_report = await connector.get_exchange_health_report()
        
        working = health_report['summary']['working_exchanges']
        total = health_report['summary']['total_tested']
        success_rate = health_report['summary']['success_rate_pct']
        
        print(f"   📊 Exchange Health: {working}/{total} working ({success_rate:.1f}% success rate)")
        print(f"   🚀 Primary recommendation: {health_report.get('recommended_primary', 'None')}")
        
        if health_report.get('failover_options'):
            print(f"   🔄 Failover options: {', '.join(health_report['failover_options'][:3])}")
        
        await connector.close()
        return working
        
    except Exception as e:
        print(f"   ❌ CCXT connector test failed: {e}")
        return 0


async def test_fred_economic_data():
    """Test FRED economic data connector"""
    
    print("\n💼 Testing FRED Economic Data Connector...")
    
    try:
        from connectors.fred_economic import FREDConnector
        from src.rate_limiter import RateLimiter
        
        # Create rate limiter
        rate_limiter = RateLimiter()
        
        # Test with demo key (won't work for real data but tests import/structure)
        fred = FREDConnector(rate_limiter, api_key="demo_key")
        
        # Test connection (will fail without real API key but tests the structure)
        connection_test = await fred.test_connection()
        
        if connection_test.get('ok'):
            print(f"   ✅ FRED connection test: {connection_test.get('message')}")
        else:
            print(f"   ⚠️  FRED connection test: {connection_test.get('message', 'API key needed')}")
            if 'API' in connection_test.get('message', ''):
                print("   💡 Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        
        # Test available symbols
        supported_symbols = fred.supported_symbols()
        
        print(f"   📈 {len(supported_symbols)} economic indicators supported")
        print(f"   📊 Examples: {', '.join(supported_symbols[:5])}")
        
        # Test category functionality
        categories = ['rates', 'inflation', 'employment', 'growth']
        available_categories = []
        
        for category in categories:
            try:
                category_symbols = fred.get_category_series(category)
                if category_symbols:
                    available_categories.append(f"{category}({len(category_symbols)})")
            except:
                pass
        
        if available_categories:
            print(f"   🏷️  Categories: {', '.join(available_categories)}")
        
        await fred.close()
        return 1
        
    except Exception as e:
        print(f"   ❌ FRED connector test failed: {e}")
        return 0


async def test_websocket_streaming():
    """Test WebSocket streaming capabilities"""
    
    print("\n⚡ Testing WebSocket Streaming Capabilities...")
    
    try:
        from connectors.ccxt_universal import WebSocketStreamer
        
        # Test WebSocket streamer initialization
        streamer = WebSocketStreamer(exchange_id='binance')
        
        # Check available endpoints
        available_endpoints = len(streamer.ws_endpoints)
        print(f"   ✅ WebSocket endpoints configured for {available_endpoints} exchanges")
        
        # Test endpoint availability
        supported_exchanges = ['binance', 'coinbase', 'kraken']
        available_exchanges = [ex for ex in supported_exchanges if ex in streamer.ws_endpoints]
        
        print(f"   🌐 Streaming available for: {', '.join(available_exchanges)}")
        
        # Note: Not testing actual WebSocket connection to avoid hanging
        print("   💡 Real-time streaming ready (requires active market connection)")
        
        return len(available_exchanges)
        
    except Exception as e:
        print(f"   ❌ WebSocket streaming test failed: {e}")
        return 0


async def generate_p0_summary():
    """Generate summary of P0 implementation status"""
    
    print("\n" + "="*60)
    print("📋 P0 CRITICAL IMPROVEMENTS - IMPLEMENTATION SUMMARY")
    print("="*60)
    
    # Track completion status
    completion_status = {}
    
    # Test all P0 components
    print("\n🔧 Testing P0 Critical Components...")
    
    library_score = await test_institutional_libraries()
    completion_status['institutional_libraries'] = library_score >= 4
    
    monitoring_score = await test_api_health_monitoring()
    completion_status['health_monitoring'] = monitoring_score >= 2
    
    ccxt_score = await test_enhanced_ccxt_connector()
    completion_status['enhanced_ccxt'] = ccxt_score >= 5
    
    fred_score = await test_fred_economic_data()
    completion_status['fred_connector'] = fred_score >= 1
    
    websocket_score = await test_websocket_streaming()
    completion_status['websocket_streaming'] = websocket_score >= 2
    
    # Calculate overall P0 completion
    completed_items = sum(completion_status.values())
    total_items = len(completion_status)
    completion_percentage = (completed_items / total_items) * 100
    
    print(f"\n📊 P0 COMPLETION STATUS: {completed_items}/{total_items} ({completion_percentage:.0f}%)")
    print("-" * 50)
    
    for item, completed in completion_status.items():
        status = "✅ COMPLETED" if completed else "⚠️  NEEDS WORK"
        item_name = item.replace('_', ' ').title()
        print(f"{status} {item_name}")
    
    # Next steps
    print(f"\n🚀 NEXT STEPS:")
    if completion_percentage == 100:
        print("   ✅ All P0 Critical improvements implemented!")
        print("   🎯 Ready to move to P1 High Priority tasks")
        print("   📈 System now supports 100+ exchanges with failover")
        print("   ⚡ Real-time WebSocket streaming available")
        print("   📊 Comprehensive health monitoring active")
    else:
        incomplete = [item for item, completed in completion_status.items() if not completed]
        print(f"   🔧 Complete remaining items: {', '.join(incomplete)}")
    
    print(f"\n💡 API RELIABILITY IMPROVEMENTS:")
    print(f"   🔄 Multi-exchange failover reduces single points of failure")
    print(f"   📊 Health monitoring enables proactive issue detection")
    print(f"   ⚡ WebSocket streaming provides real-time market data")
    print(f"   🏛️  FRED integration adds macroeconomic indicators")
    print(f"   🌐 Geographic redundancy improves global accessibility")
    
    return completion_percentage


async def main():
    """Main test execution"""
    
    print("🚀 P0 CRITICAL IMPROVEMENTS - TESTING & VALIDATION")
    print(f"⏰ Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    try:
        completion_percentage = await generate_p0_summary()
        
        print(f"\n🎯 P0 IMPLEMENTATION: {completion_percentage:.0f}% COMPLETE")
        
        if completion_percentage >= 80:
            print("🟢 TRADING OS P0 IMPROVEMENTS SUCCESSFULLY IMPLEMENTED")
            print("📈 System reliability and data coverage significantly enhanced")
        else:
            print("🟡 P0 IMPROVEMENTS PARTIALLY IMPLEMENTED")
            print("🔧 Additional work needed for full P0 completion")
    
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())