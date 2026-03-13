"""
API Health Monitor - Comprehensive Service Health Monitoring
Tracks health, performance, and availability of all data sources
Used by Trading OS for failover decisions and service level monitoring
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import json
from dataclasses import dataclass, asdict
from collections import defaultdict
import statistics

import aiohttp


@dataclass
class HealthMetrics:
    """Health metrics for a single API endpoint"""
    service_name: str
    endpoint: str
    status: str  # 'healthy', 'degraded', 'failed', 'unknown'
    response_time_ms: Optional[int]
    success_rate: float  # 0.0 to 1.0
    error_count: int
    last_success: Optional[str]
    last_error: Optional[str]
    uptime_pct: float
    test_count: int
    consecutive_failures: int
    last_check: str


@dataclass
class ServiceSummary:
    """Summary health metrics for entire service"""
    service_name: str
    overall_status: str
    healthy_endpoints: int
    total_endpoints: int
    avg_response_time_ms: float
    success_rate: float
    uptime_pct: float
    last_updated: str


class APIHealthMonitor:
    """Comprehensive API health monitoring system"""
    
    def __init__(self):
        self.metrics_history = defaultdict(list)  # service_name -> List[HealthMetrics]
        self.service_configs = {}
        self.alert_thresholds = {
            'response_time_ms': 5000,
            'success_rate_min': 0.95,
            'consecutive_failures_max': 3,
            'uptime_min': 0.99
        }
        self._setup_monitoring_configs()
    
    def _setup_monitoring_configs(self):
        """Configure monitoring for all data ingestion services"""
        
        self.service_configs = {
            # Cryptocurrency APIs
            'kraken': {
                'endpoints': [
                    {'url': 'https://api.kraken.com/0/public/SystemStatus', 'timeout': 10},
                    {'url': 'https://api.kraken.com/0/public/Ticker?pair=XBTUSD', 'timeout': 10}
                ],
                'critical': True,
                'backup_services': ['coinbase', 'binance_us']
            },
            
            'coinbase': {
                'endpoints': [
                    {'url': 'https://api.exchange.coinbase.com/time', 'timeout': 10},
                    {'url': 'https://api.exchange.coinbase.com/products/BTC-USD/ticker', 'timeout': 10}
                ],
                'critical': True,
                'backup_services': ['kraken', 'binance_us']
            },
            
            'binance': {
                'endpoints': [
                    {'url': 'https://api.binance.com/api/v3/ping', 'timeout': 10},
                    {'url': 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', 'timeout': 10}
                ],
                'critical': True,
                'backup_services': ['kraken', 'coinbase'],
                'geo_restrictions': True  # Known to be blocked in some regions
            },
            
            'binance_us': {
                'endpoints': [
                    {'url': 'https://api.binance.us/api/v3/ping', 'timeout': 10},
                    {'url': 'https://api.binance.us/api/v3/ticker/price?symbol=BTCUSDT', 'timeout': 10}
                ],
                'critical': True,
                'backup_services': ['kraken', 'coinbase']
            },
            
            'coingecko': {
                'endpoints': [
                    {'url': 'https://api.coingecko.com/api/v3/ping', 'timeout': 15},
                    {'url': 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', 'timeout': 15}
                ],
                'critical': True,
                'rate_limited': True
            },
            
            'coinpaprika': {
                'endpoints': [
                    {'url': 'https://api.coinpaprika.com/v1/global', 'timeout': 15},
                    {'url': 'https://api.coinpaprika.com/v1/tickers/btc-bitcoin', 'timeout': 15}
                ],
                'critical': True
            },
            
            # Stock/Traditional Markets
            'yahoo_finance': {
                'endpoints': [
                    {'url': 'https://query1.finance.yahoo.com/v8/finance/chart/SPY', 'timeout': 15},
                    {'url': 'https://query1.finance.yahoo.com/v8/finance/chart/AAPL', 'timeout': 15}
                ],
                'critical': False,
                'known_issues': ['JSON parsing errors', 'Rate limiting']
            },
            
            'alpha_vantage': {
                'endpoints': [
                    {'url': 'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=1min&apikey=demo', 'timeout': 20}
                ],
                'critical': False,
                'rate_limited': True,
                'requires_api_key': True
            },
            
            # Economic Data
            'fred': {
                'endpoints': [
                    {'url': 'https://api.stlouisfed.org/fred/series?series_id=GDP&api_key=abcdefghijklmnopqrstuvwxyz123456&file_type=json', 'timeout': 15}
                ],
                'critical': True,
                'data_latency': 'monthly'
            },
            
            # News & Sentiment
            'news_api': {
                'endpoints': [
                    {'url': 'https://newsapi.org/v2/everything?q=bitcoin&apiKey=test', 'timeout': 20}
                ],
                'critical': False,
                'requires_api_key': True
            }
        }
    
    async def check_endpoint(self, service_name: str, endpoint_config: Dict[str, Any]) -> HealthMetrics:
        """Check health of a single endpoint"""
        
        url = endpoint_config['url']
        timeout = endpoint_config.get('timeout', 10)
        
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                    response_time_ms = int((time.time() - start_time) * 1000)
                    
                    # Try to read response to ensure it's valid
                    content = await response.text()
                    
                    if response.status == 200:
                        status = 'healthy'
                        if response_time_ms > self.alert_thresholds['response_time_ms']:
                            status = 'degraded'
                    elif response.status == 429:
                        status = 'degraded'  # Rate limited
                    else:
                        status = 'failed'
                    
                    return HealthMetrics(
                        service_name=service_name,
                        endpoint=url,
                        status=status,
                        response_time_ms=response_time_ms,
                        success_rate=1.0 if status in ['healthy', 'degraded'] else 0.0,
                        error_count=0 if status in ['healthy', 'degraded'] else 1,
                        last_success=datetime.utcnow().isoformat() if status in ['healthy', 'degraded'] else None,
                        last_error=f"HTTP {response.status}" if status == 'failed' else None,
                        uptime_pct=1.0 if status in ['healthy', 'degraded'] else 0.0,
                        test_count=1,
                        consecutive_failures=0 if status in ['healthy', 'degraded'] else 1,
                        last_check=datetime.utcnow().isoformat()
                    )
                    
        except asyncio.TimeoutError:
            return HealthMetrics(
                service_name=service_name,
                endpoint=url,
                status='failed',
                response_time_ms=None,
                success_rate=0.0,
                error_count=1,
                last_success=None,
                last_error='Timeout',
                uptime_pct=0.0,
                test_count=1,
                consecutive_failures=1,
                last_check=datetime.utcnow().isoformat()
            )
        except Exception as e:
            return HealthMetrics(
                service_name=service_name,
                endpoint=url,
                status='failed',
                response_time_ms=None,
                success_rate=0.0,
                error_count=1,
                last_success=None,
                last_error=str(e)[:100],
                uptime_pct=0.0,
                test_count=1,
                consecutive_failures=1,
                last_check=datetime.utcnow().isoformat()
            )
    
    async def check_service(self, service_name: str) -> List[HealthMetrics]:
        """Check health of all endpoints for a service"""
        
        if service_name not in self.service_configs:
            return []
        
        config = self.service_configs[service_name]
        endpoints = config.get('endpoints', [])
        
        # Check all endpoints concurrently
        tasks = [self.check_endpoint(service_name, endpoint) for endpoint in endpoints]
        metrics = await asyncio.gather(*tasks)
        
        return metrics
    
    async def check_all_services(self) -> Dict[str, List[HealthMetrics]]:
        """Check health of all configured services"""
        
        all_metrics = {}
        
        # Check all services concurrently  
        tasks = {service: self.check_service(service) for service in self.service_configs.keys()}
        results = await asyncio.gather(*tasks.values())
        
        for service, metrics in zip(tasks.keys(), results):
            all_metrics[service] = metrics
            
            # Store in history for trend analysis
            self.metrics_history[service].extend(metrics)
            
            # Keep only last 100 checks per service
            if len(self.metrics_history[service]) > 100:
                self.metrics_history[service] = self.metrics_history[service][-100:]
        
        return all_metrics
    
    def get_service_summary(self, service_name: str) -> Optional[ServiceSummary]:
        """Get summarized health metrics for a service"""
        
        if service_name not in self.metrics_history or not self.metrics_history[service_name]:
            return None
        
        recent_metrics = self.metrics_history[service_name][-10:]  # Last 10 checks
        
        # Calculate aggregated metrics
        healthy_count = sum(1 for m in recent_metrics if m.status == 'healthy')
        total_count = len(recent_metrics)
        
        response_times = [m.response_time_ms for m in recent_metrics if m.response_time_ms]
        avg_response_time = statistics.mean(response_times) if response_times else 0
        
        success_rates = [m.success_rate for m in recent_metrics]
        avg_success_rate = statistics.mean(success_rates) if success_rates else 0
        
        uptime_pcts = [m.uptime_pct for m in recent_metrics]
        avg_uptime = statistics.mean(uptime_pcts) if uptime_pcts else 0
        
        # Determine overall status
        if healthy_count == total_count:
            overall_status = 'healthy'
        elif healthy_count > total_count * 0.5:
            overall_status = 'degraded'
        else:
            overall_status = 'failed'
        
        return ServiceSummary(
            service_name=service_name,
            overall_status=overall_status,
            healthy_endpoints=healthy_count,
            total_endpoints=total_count,
            avg_response_time_ms=avg_response_time,
            success_rate=avg_success_rate,
            uptime_pct=avg_uptime,
            last_updated=datetime.utcnow().isoformat()
        )
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data for all services"""
        
        dashboard = {
            'overview': {
                'total_services': len(self.service_configs),
                'healthy_services': 0,
                'degraded_services': 0,
                'failed_services': 0,
                'last_updated': datetime.utcnow().isoformat()
            },
            'services': {},
            'alerts': [],
            'system_status': 'unknown'
        }
        
        for service_name in self.service_configs.keys():
            summary = self.get_service_summary(service_name)
            if summary:
                dashboard['services'][service_name] = asdict(summary)
                
                # Count service statuses
                if summary.overall_status == 'healthy':
                    dashboard['overview']['healthy_services'] += 1
                elif summary.overall_status == 'degraded':
                    dashboard['overview']['degraded_services'] += 1
                else:
                    dashboard['overview']['failed_services'] += 1
                
                # Generate alerts
                alerts = self._generate_alerts(service_name, summary)
                dashboard['alerts'].extend(alerts)
        
        # Determine overall system status
        total = dashboard['overview']['total_services']
        healthy = dashboard['overview']['healthy_services']
        failed = dashboard['overview']['failed_services']
        
        if healthy == total:
            dashboard['system_status'] = 'all_systems_operational'
        elif failed == 0:
            dashboard['system_status'] = 'partial_degradation'
        elif healthy > failed:
            dashboard['system_status'] = 'service_disruption'
        else:
            dashboard['system_status'] = 'major_outage'
        
        return dashboard
    
    def _generate_alerts(self, service_name: str, summary: ServiceSummary) -> List[Dict[str, Any]]:
        """Generate alerts based on service metrics"""
        
        alerts = []
        config = self.service_configs.get(service_name, {})
        
        # Critical service alerts
        if config.get('critical', False) and summary.overall_status == 'failed':
            alerts.append({
                'severity': 'critical',
                'service': service_name,
                'message': f'Critical service {service_name} is completely failed',
                'timestamp': datetime.utcnow().isoformat(),
                'backup_services': config.get('backup_services', [])
            })
        
        # Performance alerts
        if summary.avg_response_time_ms > self.alert_thresholds['response_time_ms']:
            alerts.append({
                'severity': 'warning',
                'service': service_name,
                'message': f'High response time: {summary.avg_response_time_ms:.0f}ms',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # Reliability alerts
        if summary.success_rate < self.alert_thresholds['success_rate_min']:
            alerts.append({
                'severity': 'error',
                'service': service_name,
                'message': f'Low success rate: {summary.success_rate:.1%}',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return alerts
    
    async def test_failover_scenario(self, primary_service: str) -> Dict[str, Any]:
        """Test failover capabilities when primary service fails"""
        
        config = self.service_configs.get(primary_service, {})
        backup_services = config.get('backup_services', [])
        
        # Check primary service
        primary_metrics = await self.check_service(primary_service)
        primary_healthy = any(m.status == 'healthy' for m in primary_metrics)
        
        # Check backup services
        backup_results = {}
        for backup in backup_services:
            backup_metrics = await self.check_service(backup)
            backup_healthy = any(m.status == 'healthy' for m in backup_metrics)
            backup_results[backup] = backup_healthy
        
        return {
            'primary_service': primary_service,
            'primary_available': primary_healthy,
            'backup_services': backup_results,
            'failover_ready': any(backup_results.values()) if not primary_healthy else True,
            'recommended_failover': next((k for k, v in backup_results.items() if v), None),
            'test_timestamp': datetime.utcnow().isoformat()
        }
    
    def get_service_recommendations(self) -> List[Dict[str, Any]]:
        """Get recommendations for improving service reliability"""
        
        recommendations = []
        
        for service_name in self.service_configs.keys():
            summary = self.get_service_summary(service_name)
            config = self.service_configs[service_name]
            
            if not summary:
                continue
                
            # Recommend backup services for failed critical services
            if (config.get('critical') and summary.overall_status == 'failed' and 
                not config.get('backup_services')):
                recommendations.append({
                    'type': 'backup_service',
                    'service': service_name,
                    'message': f'Critical service {service_name} needs backup alternatives',
                    'priority': 'high'
                })
            
            # Recommend geographic alternatives for geo-blocked services
            if config.get('geo_restrictions') and summary.overall_status == 'failed':
                recommendations.append({
                    'type': 'geographic_alternative',
                    'service': service_name,
                    'message': f'{service_name} may be geo-blocked, consider regional alternatives',
                    'priority': 'medium'
                })
            
            # Recommend caching for rate-limited services
            if (config.get('rate_limited') and summary.avg_response_time_ms > 2000):
                recommendations.append({
                    'type': 'caching',
                    'service': service_name,
                    'message': f'{service_name} would benefit from response caching',
                    'priority': 'medium'
                })
        
        return recommendations
    
    async def run_continuous_monitoring(self, check_interval_minutes: int = 5):
        """Run continuous monitoring loop"""
        
        print(f"🔄 Starting continuous API health monitoring (every {check_interval_minutes} minutes)")
        
        while True:
            try:
                print(f"\n🔍 Running health checks at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
                
                # Check all services
                all_metrics = await self.check_all_services()
                
                # Generate dashboard
                dashboard = self.get_dashboard_data()
                
                # Print summary
                print(f"📊 System Status: {dashboard['system_status'].replace('_', ' ').title()}")
                print(f"✅ Healthy: {dashboard['overview']['healthy_services']}")
                print(f"⚠️  Degraded: {dashboard['overview']['degraded_services']}")
                print(f"❌ Failed: {dashboard['overview']['failed_services']}")
                
                # Print alerts
                critical_alerts = [a for a in dashboard['alerts'] if a['severity'] == 'critical']
                if critical_alerts:
                    print("\n🚨 CRITICAL ALERTS:")
                    for alert in critical_alerts:
                        print(f"   • {alert['service']}: {alert['message']}")
                
                # Wait before next check
                await asyncio.sleep(check_interval_minutes * 60)
                
            except KeyboardInterrupt:
                print("\n⏹️  Monitoring stopped by user")
                break
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error


# Usage example and testing
async def main():
    """Example usage of the API health monitor"""
    
    monitor = APIHealthMonitor()
    
    # Run a single health check
    print("🔍 Running single health check across all services...")
    all_metrics = await monitor.check_all_services()
    
    # Get dashboard data
    dashboard = monitor.get_dashboard_data()
    print(f"\n📊 Dashboard Data:")
    print(json.dumps(dashboard, indent=2))
    
    # Get recommendations
    recommendations = monitor.get_service_recommendations()
    if recommendations:
        print(f"\n💡 Service Recommendations:")
        for rec in recommendations:
            print(f"   • {rec['service']}: {rec['message']} (Priority: {rec['priority']})")
    
    # Test failover for critical service
    print(f"\n🔄 Testing failover scenario for Binance...")
    failover_test = await monitor.test_failover_scenario('binance')
    print(json.dumps(failover_test, indent=2))


if __name__ == "__main__":
    # Run the health check
    asyncio.run(main())