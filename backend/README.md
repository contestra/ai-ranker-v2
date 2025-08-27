# AI Ranker V2 Backend

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Run backend
./start_backend.sh
```

## 📊 System Status

| Component | Status | Notes |
|-----------|--------|-------|
| Geographic A/B Testing | ✅ Working | 4 vantage policies |
| Proxy Routing | ✅ Working | Backbone/rotating modes |
| Grounding | ✅ Working | OpenAI & Vertex |
| Rate Limiting | ✅ Working | 3 OpenAI, 4 Vertex concurrent |
| Health Monitoring | ✅ Working | Auth & proxy endpoints |
| Authentication | ⚠️ ADC Required | Run `gcloud auth application-default login` |

## 🔍 Health Checks

```bash
# Check auth status
curl -s http://localhost:8000/health/auth | jq '.status'

# Check proxy mode  
curl -s http://localhost:8000/health/proxy | jq '.mode_guess'
```

## 📚 Documentation

- **[SYSTEM_DOCUMENTATION.md](SYSTEM_DOCUMENTATION.md)** - Complete system guide
- **[ADAPTER_OPS_PLAYBOOK.md](ADAPTER_OPS_PLAYBOOK.md)** - Operational playbook
- **[HEALTH_MONITORING_SETUP.md](HEALTH_MONITORING_SETUP.md)** - Monitoring configuration
- **[VERTEX_AUTH_SETUP.md](VERTEX_AUTH_SETUP.md)** - Authentication setup

## ⚡ Key Features

### Geographic Testing
- **US**: Life Extension, Thorne, Pure Encapsulations
- **DE**: Sunday Natural, Moleqlar, Avea

### Smart Proxy
- **≤2000 tokens**: Rotating mode
- **>2000 tokens**: Backbone mode (stable IP)
- **6000 tokens**: Always backbone

### Models (ONLY)
- **OpenAI**: `gpt-5` 
- **Vertex**: `gemini-2.5-pro`
- **Tokens**: Always 6000

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| Auth error | Run ADC login (see VERTEX_AUTH_SETUP.md) |
| Rate limit 429 | Automatic retry with 3 concurrent max |
| Empty grounded response | Automatic synthesis fallback |
| Proxy timeout | Uses 240s for backbone mode |

## 📈 Performance

- **OpenAI Direct**: 84-162s
- **OpenAI Proxy**: 51-123s  
- **Vertex Direct**: 40-48s (US), 118-877s (DE)
- **No SLA violations**: All <480s timeout

## 🔒 Security

- Proxy credentials masked in logs
- WIF for production, ADC for development
- All secrets in `.env` (gitignored)

---
**Version**: 2.7.0 | **Status**: Production Ready | **Updated**: 2025-08-27