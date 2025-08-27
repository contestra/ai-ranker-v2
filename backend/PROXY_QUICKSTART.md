# Webshare.io Proxy Quick Start Guide
## AI Ranker V2 - Residential Proxy System

### Status: ✅ FULLY OPERATIONAL

---

## 🚀 Quick Usage

### Making a Proxied Request

```python
from app.llm.types import LLMRequest, VantagePolicy

# Route through Germany proxy
request = LLMRequest(
    vendor="openai",
    model="gpt-5",
    vantage_policy=VantagePolicy.PROXY_ONLY,  # Activates proxy
    country_code="DE",  # Routes through Germany
    messages=[
        {"role": "user", "content": "What's the weather in Berlin?"}
    ]
)

# Or with ALS + Proxy
request = LLMRequest(
    vendor="vertex",
    model="gemini-2.5-pro",
    vantage_policy=VantagePolicy.ALS_PLUS_PROXY,  # Both ALS and proxy
    country_code="FR",  # Routes through France
    messages=[...]
)
```

## 📊 Vantage Policies

| Policy | Proxy | ALS | Use Case |
|--------|-------|-----|----------|
| `NONE` | ❌ | ❌ | Control group, direct connection |
| `ALS_ONLY` | ❌ | ✅ | Test prompt-based location |
| `PROXY_ONLY` | ✅ | ❌ | Test network-based location |
| `ALS_PLUS_PROXY` | ✅ | ✅ | Maximum geographic signal |

## 🌍 Supported Countries

- **US** - United States (multiple IPs)
- **DE** - Germany
- **FR** - France  
- **IT** - Italy
- **CH** - Switzerland
- **AE** - United Arab Emirates
- **GB** - United Kingdom (use "GB" not "UK")
- **SG** - Singapore

## ✅ Verified Working Proxies

| Country | Example IP | Location | ISP |
|---------|------------|----------|-----|
| US | 35.145.8.114 | Apopka, FL | Charter Communications |
| DE | 194.55.97.58 | Rostock | Various |

## 🔧 Configuration

### Environment Variables (.env)
```bash
WEBSHARE_USERNAME=iuneqpvp
WEBSHARE_PASSWORD=[your_password]
WEBSHARE_HOST=p.webshare.io
WEBSHARE_PORT=80
PROXY_ENABLED=true
```

### Connection Types

- **Backbone** (Stable): Best for streaming/long connections
  - Format: `username-CC-1` (e.g., `iuneqpvp-US-1`)
  
- **Rotating** (Dynamic): New IP per request
  - Format: `username-CC-rotate` (e.g., `iuneqpvp-US-rotate`)

## 🧪 Testing

### Test Proxy Connection
```bash
cd /home/leedr/ai-ranker-v2/backend
source venv/bin/activate
python test_proxy.py
```

### Quick Test Script
```python
import asyncio
from app.services.proxy_service import get_proxy_service
from app.llm.types import VantagePolicy

async def test():
    service = get_proxy_service()
    config = service.get_proxy_config(
        country_code="US",
        vantage_policy=VantagePolicy.PROXY_ONLY
    )
    
    if config:
        print(f"Proxy URL: {config.url}")
        ip_info = await service.verify_proxy_connection(config)
        if ip_info:
            print(f"Connected via: {ip_info.get('ip')} in {ip_info.get('city')}")

asyncio.run(test())
```

## 🏗️ Architecture

### Request Flow
```
1. LLMRequest with vantage_policy=PROXY_ONLY
   ↓
2. Adapter checks _should_use_proxy()
   ↓
3. ProxyService creates config with correct username
   ↓
4. Adapter creates proxied httpx client
   ↓
5. Request routes through proxy country
   ↓
6. Response returns with proxy IP
```

### Key Components

1. **ProxyService** (`app/services/proxy_service.py`)
   - Manages proxy configurations
   - Handles country normalization (UK→GB)
   - Verifies connections

2. **Adapters** (OpenAI & Vertex)
   - Check vantage_policy
   - Create per-run proxy clients
   - Clean up after completion

3. **Types** (`app/llm/types.py`)
   - VantagePolicy enum
   - LLMRequest with proxy fields

## ⚠️ Important Notes

1. **Country Codes**: Always use ISO codes (GB not UK)
2. **Numbered Suffixes**: Backbone requires `-1`, `-2`, etc.
3. **NO_PROXY**: Set for Vertex to protect metadata service
4. **Per-Run**: Each request can use different proxy/country
5. **Immutability**: Proxy is runtime decision, not in template hash

## 🐛 Troubleshooting

### 407 Proxy Authentication Required
- Check username format includes number: `iuneqpvp-US-1`
- Verify credentials in .env file
- Ensure Webshare plan is active

### Proxy Not Connecting
- Verify `PROXY_ENABLED=true` in .env
- Check `vantage_policy` is PROXY_ONLY or ALS_PLUS_PROXY
- Test with `python test_proxy.py`

### Country Not Working
- Check country is in your Webshare plan
- Use correct ISO code (GB not UK)
- Try different number suffix (-1, -2, -3)

## 📈 Performance

- **Latency**: Add ~100-500ms depending on country
- **Reliability**: 99%+ uptime with Webshare
- **Concurrency**: Multiple requests can use different proxies
- **Rotation**: Each request gets different IP with rotating mode

## 🔒 Security

- Credentials stored in .env (not in code)
- Per-run proxy prevents cross-contamination
- NO_PROXY protects cloud metadata services
- Proxy details logged for audit trail

---

## Need Help?

1. Check proxy status: `python test_proxy.py`
2. View logs in backend terminal
3. Check Webshare dashboard for quota/status
4. Review PROXY_IMPLEMENTATION_PLAN.md for details