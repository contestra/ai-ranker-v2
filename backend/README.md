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

## 🔧 Grounding Configuration

### Provider Comparison

| Provider | Method | Challenges | Solution |
|----------|--------|------------|----------|
| **OpenAI** | Responses API with `web_search` tools | Sometimes returns searches without synthesis | Three-stage fallback chain |
| **Vertex/Gemini** | GoogleSearch tool with Forced Function Calling | Requires explicit tool config | Auto-configured per model capabilities |

### OpenAI Grounding Details
OpenAI grounded mode uses the Responses API with `web_search` tools. Due to API limitations where the model sometimes returns web search results without synthesizing a final answer, the adapter implements a deterministic fallback chain.

### Fallback Chain
1. **Initial Request**: Grounded call with `web_search` tools
2. **Provoker Retry**: If empty response but tool calls present, adds synthesis prompt
3. **Two-Step Fallback**: If still empty, runs synthesis without tools using evidence list

### Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `OPENAI_PROVOKER_ENABLED` | `true` | Enable provoker retry for empty responses |
| `OPENAI_GROUNDED_TWO_STEP` | `false` | Enable two-step synthesis fallback (recommend `true` in production) |
| `OPENAI_GROUNDED_MAX_EVIDENCE` | `5` | Maximum citations to include in evidence list |
| `OPENAI_GROUNDED_MAX_TOKENS` | `6000` | Maximum output tokens for grounded requests |

### Telemetry Fields

The adapter records these fields in metadata for BigQuery analytics:

- `provoker_retry_used`: Whether provoker retry was attempted
- `synthesis_step_used`: Whether two-step synthesis was used
- `synthesis_tool_count`: Number of tool calls from Step-A
- `synthesis_evidence_count`: Number of citations in evidence list
- `anchored_citations_count`: Citations with URL annotations (currently 0)
- `unlinked_sources_count`: Citations without annotations
- `why_not_grounded`: Reason grounding wasn't applied (None or "not_requested")
- `provider_api_version`: API version identifier ("openai:responses-v1 (sdk)")
- `seed_key_id`: Seed key for reproducibility
- `provoker_value`: The actual provoker text used (if any)
- `response_output_sha256`: SHA256 hash of response content for provenance

### REQUIRED Mode Enforcement

When `grounding_mode="REQUIRED"`, the adapter enforces strict grounding:
1. Must have `tool_call_count > 0` (web searches performed)
2. Must have `len(citations) > 0` (evidence extracted)
3. Fails with `GroundingRequiredFailedError` if either condition not met

### Citation Schema

All citations are normalized to:
```json
{
  "url": "https://...",
  "title": "Article Title",
  "domain": "example.com",
  "source_type": "web_search_result | evidence_list | url_annotation"
}
```

### Production Recommendations

```bash
# Production settings
export OPENAI_GROUNDED_TWO_STEP=true  # Enable synthesis fallback
export OPENAI_GROUNDED_MAX_TOKENS=6000  # Sufficient budget
export OPENAI_GROUNDED_MAX_EVIDENCE=5  # Balanced evidence list
```

### Determinism Guarantees

The adapter ensures deterministic grounded responses:
- **OpenAI**: Even when the Responses API fails to synthesize, our fallback chain guarantees a final answer
- **Vertex/Gemini**: Forced Function Calling ensures GoogleSearch is always invoked when grounding is requested
- **REQUIRED Mode**: Strict fail-closed enforcement - both providers must show evidence of grounding or the request fails

---
**Version**: 2.7.1 | **Status**: Production Ready | **Updated**: 2025-09-05