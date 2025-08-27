#!/usr/bin/env python3
"""
Test script for Webshare.io proxy connection
Tests all vantage policies and verifies proxy routing
"""

import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
import sys
sys.path.insert(0, '/home/leedr/ai-ranker-v2/backend')

from app.services.proxy_service import ProxyService, ProxyClass, ConnectionType
from app.llm.types import VantagePolicy


async def test_proxy_connection():
    """Test proxy connection with all vantage policies"""
    
    print("=" * 60)
    print("WEBSHARE.IO PROXY CONNECTION TEST")
    print("=" * 60)
    
    # Initialize proxy service
    proxy_service = ProxyService()
    
    # Check if credentials are configured
    if not proxy_service.base_username or proxy_service.base_username == 'your_webshare_username':
        print("\n❌ ERROR: Please update WEBSHARE_USERNAME and WEBSHARE_PASSWORD in .env file")
        print("   Current username:", proxy_service.base_username)
        return
    
    print(f"\n✅ Proxy service initialized")
    print(f"   Username: {proxy_service.base_username}")
    print(f"   Host: {proxy_service.host}:{proxy_service.port}")
    print(f"   Enabled: {proxy_service.enabled}")
    
    # Test countries
    test_countries = ["US", "DE", "GB", "FR"]
    
    # Test all vantage policies
    for policy in VantagePolicy:
        print(f"\n{'=' * 40}")
        print(f"Testing VantagePolicy.{policy.name}")
        print('=' * 40)
        
        if policy in [VantagePolicy.PROXY_ONLY, VantagePolicy.ALS_PLUS_PROXY]:
            # Test proxy for each country
            for country in test_countries:
                print(f"\n📍 Testing proxy for {country}...")
                
                # Get proxy config
                proxy_config = proxy_service.get_proxy_config(
                    country_code=country,
                    vantage_policy=policy,
                    proxy_class=ProxyClass.RESIDENTIAL,
                    connection=ConnectionType.BACKBONE
                )
                
                if proxy_config:
                    print(f"   Config: {proxy_config.username_suffix}")
                    print(f"   URL: {proxy_config.url[:30]}...")
                    
                    # Verify the connection
                    ip_info = await proxy_service.verify_proxy_connection(proxy_config)
                    if ip_info:
                        print(f"   ✅ SUCCESS: Connected via proxy")
                        print(f"      IP: {ip_info.get('ip')}")
                        print(f"      Location: {ip_info.get('city')}, {ip_info.get('country')}")
                        print(f"      ISP: {ip_info.get('org')}")
                    else:
                        print(f"   ❌ FAILED: Could not connect via proxy")
                else:
                    print(f"   ⚠️  No proxy config (expected for this policy)")
        else:
            print(f"   ℹ️  Policy {policy.name} does not use proxy (expected)")
    
    # Test rotating vs backbone
    print(f"\n{'=' * 40}")
    print("Testing Connection Types")
    print('=' * 40)
    
    for connection_type in [ConnectionType.ROTATING, ConnectionType.BACKBONE]:
        print(f"\n🔄 Testing {connection_type.value} connection...")
        
        proxy_config = proxy_service.get_proxy_config(
            country_code="US",
            vantage_policy=VantagePolicy.PROXY_ONLY,
            proxy_class=ProxyClass.DATACENTER,
            connection=connection_type
        )
        
        if proxy_config:
            print(f"   Username: {proxy_config.username_suffix}")
            expected_suffix = "rotate" if connection_type == ConnectionType.ROTATING else ""
            if expected_suffix in proxy_config.username_suffix or (not expected_suffix and "-rotate" not in proxy_config.username_suffix):
                print(f"   ✅ Correct username format")
            else:
                print(f"   ❌ Wrong username format")


async def test_direct_proxy():
    """Test direct proxy connection without the service"""
    import httpx
    
    print("\n" + "=" * 60)
    print("DIRECT PROXY CONNECTION TEST")
    print("=" * 60)
    
    username = os.getenv('WEBSHARE_USERNAME')
    password = os.getenv('WEBSHARE_PASSWORD')
    
    if not username or username == 'your_webshare_username':
        print("\n❌ Please set your actual Webshare credentials first")
        return
    
    # Test direct connection with US proxy
    proxy_url = f"http://{username}-US:{ password}@p.webshare.io:80"
    print(f"\n🔍 Testing direct connection to US proxy...")
    print(f"   Proxy URL: http://{username}-US:***@p.webshare.io:80")
    
    try:
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=10.0
        ) as client:
            response = await client.get("https://ipinfo.io/json")
            data = response.json()
            print(f"\n✅ Direct proxy connection successful!")
            print(f"   Your proxy IP: {data.get('ip')}")
            print(f"   Location: {data.get('city')}, {data.get('region')}, {data.get('country')}")
            print(f"   ISP: {data.get('org')}")
    except Exception as e:
        print(f"\n❌ Direct proxy connection failed: {e}")
        print("\nPossible issues:")
        print("1. Check your WEBSHARE_USERNAME and WEBSHARE_PASSWORD")
        print("2. Ensure your Webshare plan is active")
        print("3. Check if your plan includes US proxies")


async def main():
    """Run all tests"""
    
    # Test direct connection first
    await test_direct_proxy()
    
    # Then test through the service
    await test_proxy_connection()
    
    print("\n" + "=" * 60)
    print("✅ PROXY TESTS COMPLETE")
    print("=" * 60)
    
    print("\n📝 REMEMBER TO UPDATE YOUR .env FILE:")
    print("   WEBSHARE_USERNAME=your_actual_username")
    print("   WEBSHARE_PASSWORD=your_actual_password")


if __name__ == "__main__":
    asyncio.run(main())