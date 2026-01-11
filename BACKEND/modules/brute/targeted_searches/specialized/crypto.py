#!/usr/bin/env python3
"""
Cryptocurrency and IP Address Search Module
Supports blockchain exploration for multiple cryptocurrencies and IP address intelligence
"""

import re
import json
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime
from urllib.parse import quote
import ipaddress

logger = logging.getLogger(__name__)

class CryptoSearch:
    """
    Cryptocurrency wallet and IP address search with entity extraction
    Supports Bitcoin, Ethereum, Litecoin, Dogecoin, Dash, Bitcoin Cash, and more
    """
    
    def __init__(self):
        """Initialize cryptocurrency search with wallet patterns and service URLs"""
        
        # Wallet address patterns for validation
        self.wallet_patterns = {
            'bitcoin': re.compile(r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,62}$'),
            'ethereum': re.compile(r'^0x[a-fA-F0-9]{40}$'),
            'litecoin': re.compile(r'^(L|M|ltc1)[a-zA-Z0-9]{26,}$'),
            'dogecoin': re.compile(r'^D[a-zA-Z0-9]{33}$'),
            'dash': re.compile(r'^X[a-zA-Z0-9]{33}$'),
            'bitcoin_cash': re.compile(r'^(q|p|bitcoincash:)[a-z0-9]{41,}$'),
            'bitcoin_sv': re.compile(r'^(1|3|bc1)[a-zA-HJ-NP-Z0-9]{25,62}$'),  # Same as BTC
        }
        
        # Comprehensive service URLs with all the new endpoints
        self.crypto_apis = {
            'bitcoin': [
                {
                    'name': 'BTC Validation',
                    'url': 'https://blockexplorer.com/api/addr/{0}',
                    'type': 'api',
                    'description': 'Validate a Bitcoin address via BlockExplorer API'
                },
                {
                    'name': 'BTC Received',
                    'url': 'https://blockchain.info/q/getreceivedbyaddress/{0}',
                    'type': 'api',
                    'description': 'Total satoshis received by address'
                },
                {
                    'name': 'BTC Sent',
                    'url': 'https://blockchain.info/q/getsentbyaddress/{0}',
                    'type': 'api',
                    'description': 'Total satoshis sent from address'
                },
                {
                    'name': 'BTC Balance',
                    'url': 'https://blockchain.info/q/addressbalance/{0}',
                    'type': 'api',
                    'description': 'Current satoshi balance'
                },
                {
                    'name': 'BTC First Seen',
                    'url': 'https://blockchain.info/q/addressfirstseen/{0}',
                    'type': 'api',
                    'description': 'First seen date of address'
                },
                {
                    'name': 'Blockchain Explorer',
                    'url': 'https://www.blockchain.com/btc/address/{0}',
                    'type': 'explorer',
                    'description': 'Blockchain.com explorer'
                },
                {
                    'name': 'Cloverpool Explorer',
                    'url': 'https://explorer.cloverpool.com/btc/address/{0}',
                    'type': 'explorer',
                    'description': 'Cloverpool BTC explorer'
                },
                {
                    'name': 'ChainAbuse',
                    'url': 'https://www.chainabuse.com/address/{0}',
                    'type': 'reputation',
                    'description': 'Search ChainAbuse reports'
                },
                {
                    'name': 'Bitcoin WhosWho',
                    'url': 'https://bitcoinwhoswho.com/address/{0}',
                    'type': 'reputation',
                    'description': 'Bitcoin identity directory'
                },
                {
                    'name': 'OXT',
                    'url': 'https://oxt.me/address/{0}',
                    'type': 'analysis',
                    'description': 'Graph analysis of BTC address'
                },
                {
                    'name': 'WalletExplorer',
                    'url': 'https://www.walletexplorer.com/address/{0}',
                    'type': 'analysis',
                    'description': 'BTC cluster analysis'
                },
                {
                    'name': 'Blockchair',
                    'url': 'https://blockchair.com/bitcoin/address/{0}',
                    'type': 'explorer',
                    'description': 'Blockchair BTC explorer'
                }
            ],
            'ethereum': [
                {
                    'name': 'Blockchair ETH',
                    'url': 'https://blockchair.com/ethereum/address/{0}',
                    'type': 'explorer',
                    'description': 'ETH explorer on Blockchair'
                },
                {
                    'name': 'Etherscan',
                    'url': 'https://etherscan.io/address/{0}',
                    'type': 'explorer',
                    'description': 'Primary Ethereum explorer'
                }
            ],
            'bitcoin_cash': [
                {
                    'name': 'Blockchair BCH',
                    'url': 'https://blockchair.com/bitcoin-cash/address/{0}',
                    'type': 'explorer',
                    'description': 'BCH explorer on Blockchair'
                }
            ],
            'litecoin': [
                {
                    'name': 'Blockchair LTC',
                    'url': 'https://blockchair.com/litecoin/address/{0}',
                    'type': 'explorer',
                    'description': 'LTC explorer on Blockchair'
                }
            ],
            'dogecoin': [
                {
                    'name': 'Blockchair DOGE',
                    'url': 'https://blockchair.com/dogecoin/address/{0}',
                    'type': 'explorer',
                    'description': 'DOGE explorer on Blockchair'
                }
            ],
            'dash': [
                {
                    'name': 'Blockchair DASH',
                    'url': 'https://blockchair.com/dash/address/{0}',
                    'type': 'explorer',
                    'description': 'Dash explorer on Blockchair'
                }
            ],
            'generic': [
                {
                    'name': 'ScamSearch',
                    'url': 'https://scamsearch.io/search_report?searchoption=all&search={0}',
                    'type': 'reputation',
                    'description': 'Search for cryptocurrency scam reports'
                }
            ]
        }
        
        # Price conversion APIs
        self.conversion_apis = {
            'btc_price': {
                'name': 'BTC Price USD',
                'url': 'https://blockchain.info/q/24hrprice',
                'description': 'Current 1 BTC price in USD'
            },
            'btc_to_usd': {
                'name': 'BTC to USD',
                'url': 'https://api.coinconvert.net/convert/btc/usd?amount={0}',
                'description': 'Convert BTC amount to USD'
            },
            'usd_to_btc': {
                'name': 'USD to BTC',
                'url': 'https://blockchain.info/tobtc?currency=USD&value={0}',
                'description': 'Convert USD amount to BTC'
            },
            'sat_to_usd': {
                'name': 'Satoshis to USD',
                'url': 'https://api.exchangerate.host/convert?from=SAT&to=USD&amount={0}',
                'description': 'Convert satoshis to USD'
            },
            'usd_to_sat': {
                'name': 'USD to Satoshis',
                'url': 'https://api.exchangerate.host/convert?from=USD&to=SAT&amount={0}',
                'description': 'Convert USD to satoshis'
            }
        }
        
        # IP address services
        self.ip_services = {
            'shodan': 'https://api.shodan.io/shodan/host/{ip}',
            'ipinfo': 'https://ipinfo.io/{ip}/json',
            'abuseipdb': 'https://www.abuseipdb.com/check/{ip}',
            'virustotal': 'https://www.virustotal.com/gui/ip-address/{ip}',
            'whois': 'https://who.is/whois-ip/ip-address/{ip}',
            'ipgeolocation': 'https://ipgeolocation.io/ip-location/{ip}',
            'ipqualityscore': 'https://www.ipqualityscore.com/free-ip-lookup-proxy-vpn-test/lookup/{ip}',
            'projecthoneypot': 'https://www.projecthoneypot.org/ip_{ip}',
            'spamhaus': 'https://check.spamhaus.org/listed/?searchterm={ip}',
            'blacklistalert': 'https://www.blacklistalert.org/?q={ip}'
        }
        
        self.session = None
    
    def detect_wallet_type(self, address: str) -> Optional[str]:
        """
        Detect the cryptocurrency type from wallet address format
        Returns: cryptocurrency type or None if not recognized
        """
        for crypto_type, pattern in self.wallet_patterns.items():
            if pattern.match(address):
                return crypto_type
        return None
    
    def is_ip_address(self, query: str) -> bool:
        """Check if the query is a valid IP address (IPv4 or IPv6)"""
        try:
            ipaddress.ip_address(query)
            return True
        except ValueError:
            return False
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def fetch_api_data(self, url: str) -> Optional[Dict]:
        """Fetch data from API endpoint"""
        try:
            session = await self.get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    # Try to parse as JSON
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        # Return raw text if not JSON
                        return {'raw_response': text}
                else:
                    logger.warning(f"API request failed: {url} - Status: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    async def search_crypto_address(self, address: str) -> Dict[str, Any]:
        """
        Search for cryptocurrency wallet information
        """
        results = {
            'query': address,
            'query_type': 'cryptocurrency',
            'timestamp': datetime.now().isoformat(),
            'wallet_type': None,
            'api_results': {},
            'explorer_links': [],
            'reputation_links': [],
            'analysis_links': [],
            'errors': []
        }
        
        # Detect wallet type
        wallet_type = self.detect_wallet_type(address)
        if not wallet_type:
            # Try generic search for unknown wallet types
            wallet_type = 'generic'
            results['wallet_type'] = 'unknown'
        else:
            results['wallet_type'] = wallet_type
        
        # Get relevant APIs for this wallet type
        apis = self.crypto_apis.get(wallet_type, [])
        if wallet_type != 'generic':
            # Also add generic APIs that work for any crypto
            apis.extend(self.crypto_apis.get('generic', []))
        
        # Process each API
        for api_info in apis:
            url = api_info['url'].format(address)
            
            if api_info['type'] == 'api':
                # Fetch API data
                data = await self.fetch_api_data(url)
                if data:
                    results['api_results'][api_info['name']] = data
            elif api_info['type'] == 'explorer':
                results['explorer_links'].append({
                    'name': api_info['name'],
                    'url': url,
                    'description': api_info['description']
                })
            elif api_info['type'] == 'reputation':
                results['reputation_links'].append({
                    'name': api_info['name'],
                    'url': url,
                    'description': api_info['description']
                })
            elif api_info['type'] == 'analysis':
                results['analysis_links'].append({
                    'name': api_info['name'],
                    'url': url,
                    'description': api_info['description']
                })
        
        # Extract entities from API results
        results['entities'] = self.extract_crypto_entities(results)
        
        return results
    
    async def search_ip_address(self, ip: str) -> Dict[str, Any]:
        """
        Search for IP address information
        """
        results = {
            'query': ip,
            'query_type': 'ip_address',
            'timestamp': datetime.now().isoformat(),
            'api_results': {},
            'service_links': [],
            'errors': []
        }
        
        # Validate IP
        try:
            ip_obj = ipaddress.ip_address(ip)
            results['ip_version'] = 'IPv4' if ip_obj.version == 4 else 'IPv6'
            results['is_private'] = ip_obj.is_private
            results['is_global'] = ip_obj.is_global
        except ValueError:
            results['errors'].append(f"Invalid IP address: {ip}")
            return results
        
        # Try to fetch basic IP info
        ipinfo_url = f"https://ipinfo.io/{ip}/json"
        ipinfo_data = await self.fetch_api_data(ipinfo_url)
        if ipinfo_data:
            results['api_results']['ipinfo'] = ipinfo_data
        
        # Add service links for manual checking
        for service_name, url_template in self.ip_services.items():
            results['service_links'].append({
                'name': service_name,
                'url': url_template.format(ip=ip)
            })
        
        # Extract entities from results
        results['entities'] = self.extract_ip_entities(results)
        
        return results
    
    def extract_crypto_entities(self, results: Dict) -> List[Dict]:
        """Extract entities from cryptocurrency search results"""
        entities = []
        
        # Add the wallet address itself as an entity
        entities.append({
            'type': 'CRYPTO_ADDRESS',
            'value': results['query'],
            'wallet_type': results.get('wallet_type', 'unknown'),
            'confidence': 1.0
        })
        
        # Extract from API results
        for api_name, data in results.get('api_results', {}).items():
            if isinstance(data, dict):
                # Look for transaction hashes
                if 'txs' in data:
                    for tx in data.get('txs', [])[:5]:  # Limit to first 5
                        if 'hash' in tx:
                            entities.append({
                                'type': 'TRANSACTION_HASH',
                                'value': tx['hash'],
                                'source': api_name,
                                'confidence': 0.9
                            })
                
                # Look for related addresses
                if 'inputs' in data:
                    for inp in data.get('inputs', [])[:5]:
                        if 'addr' in inp:
                            entities.append({
                                'type': 'CRYPTO_ADDRESS',
                                'value': inp['addr'],
                                'relation': 'input_address',
                                'source': api_name,
                                'confidence': 0.8
                            })
                
                if 'outputs' in data:
                    for out in data.get('outputs', [])[:5]:
                        if 'addr' in out:
                            entities.append({
                                'type': 'CRYPTO_ADDRESS',
                                'value': out['addr'],
                                'relation': 'output_address',
                                'source': api_name,
                                'confidence': 0.8
                            })
        
        return entities
    
    def extract_ip_entities(self, results: Dict) -> List[Dict]:
        """Extract entities from IP address search results"""
        entities = []
        
        # Add the IP address itself as an entity
        entities.append({
            'type': 'IP_ADDRESS',
            'value': results['query'],
            'version': results.get('ip_version', 'unknown'),
            'is_private': results.get('is_private', False),
            'confidence': 1.0
        })
        
        # Extract from IPInfo results
        ipinfo = results.get('api_results', {}).get('ipinfo', {})
        if ipinfo:
            if 'hostname' in ipinfo:
                entities.append({
                    'type': 'DOMAIN',
                    'value': ipinfo['hostname'],
                    'relation': 'reverse_dns',
                    'confidence': 0.9
                })
            
            if 'org' in ipinfo:
                entities.append({
                    'type': 'ORGANIZATION',
                    'value': ipinfo['org'],
                    'relation': 'ip_owner',
                    'confidence': 0.8
                })
            
            if 'city' in ipinfo:
                entities.append({
                    'type': 'LOCATION',
                    'value': f"{ipinfo.get('city', '')}, {ipinfo.get('region', '')}, {ipinfo.get('country', '')}".strip(', '),
                    'confidence': 0.7
                })
        
        return entities
    
    async def search(self, query: str) -> Dict[str, Any]:
        """
        Main search method - routes to crypto or IP search based on query
        """
        # Remove 'crypto:' prefix if present
        if query.startswith('crypto:'):
            query = query[7:].strip()
        
        # Check if it's an IP address
        if self.is_ip_address(query):
            return await self.search_ip_address(query)
        else:
            return await self.search_crypto_address(query)
    
    async def get_price_conversions(self, amount: float = 1.0, from_currency: str = 'btc') -> Dict[str, Any]:
        """
        Get price conversions for cryptocurrency amounts
        """
        results = {
            'amount': amount,
            'from_currency': from_currency,
            'conversions': {},
            'timestamp': datetime.now().isoformat()
        }
        
        if from_currency.lower() == 'btc':
            # Get current BTC price
            price_data = await self.fetch_api_data(self.conversion_apis['btc_price']['url'])
            if price_data:
                results['conversions']['btc_price_usd'] = price_data
            
            # Convert BTC to USD
            btc_usd_url = self.conversion_apis['btc_to_usd']['url'].format(amount)
            btc_usd_data = await self.fetch_api_data(btc_usd_url)
            if btc_usd_data:
                results['conversions']['btc_to_usd'] = btc_usd_data
        
        elif from_currency.lower() == 'usd':
            # Convert USD to BTC
            usd_btc_url = self.conversion_apis['usd_to_btc']['url'].format(amount)
            usd_btc_data = await self.fetch_api_data(usd_btc_url)
            if usd_btc_data:
                results['conversions']['usd_to_btc'] = usd_btc_data
            
            # Convert USD to Satoshis
            usd_sat_url = self.conversion_apis['usd_to_sat']['url'].format(amount)
            usd_sat_data = await self.fetch_api_data(usd_sat_url)
            if usd_sat_data:
                results['conversions']['usd_to_satoshis'] = usd_sat_data
        
        return results
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()


# Example usage
async def main():
    crypto_search = CryptoSearch()
    
    # Test Bitcoin address
    btc_results = await crypto_search.search("crypto:1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    print(json.dumps(btc_results, indent=2))
    
    # Test IP address
    ip_results = await crypto_search.search("8.8.8.8")
    print(json.dumps(ip_results, indent=2))
    
    # Test price conversion
    price_results = await crypto_search.get_price_conversions(1.5, 'btc')
    print(json.dumps(price_results, indent=2))
    
    await crypto_search.cleanup()


if __name__ == "__main__":
    asyncio.run(main())