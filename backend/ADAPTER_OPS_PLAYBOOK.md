# AI Ranker Adapter Operations Playbook

## 🎯 Quick Reference

### Operational Defaults
- **Vertex grounded:** Direct (no proxy), use ALS for geo
- **Vertex ungrounded:** Direct by default, proxy via `VERTEX_PROXY_VIA_SDK=true` when needed
- **OpenAI:** Auto-proxy (backbone >2k tokens, rotating ≤2k), stream enabled, 240s read timeout

### Configuration
```bash
# Environment Variables
GOOGLE_GENAI_USE_VERTEXAI=true     # Grounded Vertex uses GenAI (no proxy)
VERTEX_PROXY_VIA_SDK=false         # Set true to enable Vertex SDK proxy
NO_PROXY=metadata.google.internal,169.254.169.254,localhost,127.0.0.1
WEBSHARE_SOCKS_PORT=1080           # For SOCKS5 fallback

# Token Settings (ALWAYS)
max_tokens=6000                    # Per user requirement
```

## 🚨 Important: Concurrency Warning

**Per-run env proxy on SDK path is process-global!** To avoid crosstalk:
- Use **singleflight lock** (one proxied SDK call at a time), OR
- Route to **dedicated worker process** with proxy env pre-set

## 📊 Telemetry Requirements

Every run MUST log:
- `vendor`, `vantage_policy`, `proxy_mode` (backbone|rotating|direct)
- `proxy_country`, `sdk_env_proxy` (bool), `proxy_effective` (bool)
- `timeouts_s` (connect/read/total), `streaming` (bool)
- `[LLM_ROUTE]`, `[LLM_RESULT]`, `[LLM_TIMEOUT]` log lines

## ✅ Acceptance Tests (Run for US + DE)

| Test | Config | Success Criteria |
|------|--------|-----------------|
| Vertex grounded, no proxy | Default | 0 timeouts, ALS geo visible |
| Vertex ungrounded, no proxy | Default | 0 timeouts, baseline latency |
| Vertex ungrounded + proxy | `VERTEX_PROXY_VIA_SDK=true` | 3/3 success, `sdk_env_proxy:true` |
| OpenAI proxied long | ALS+proxy, backbone | 3/3 success <90s, masked URI |

**Pass criteria:** ≥95% success per bucket, no proxy env leakage

## 🔧 Troubleshooting

### "Server disconnected" on Vertex?
- Keep grounded requests direct (no proxy needed)
- For ungrounded: Set `VERTEX_PROXY_VIA_SDK=true`
- Or switch to OpenAI adapter

### Need stronger geo signal?
- Use ALS (Ambient Location Signals)
- Client proxy won't change GoogleSearch server-side vantage

### Proxy not working?
1. Check `WEBSHARE_USERNAME` and `WEBSHARE_PASSWORD` are set
2. Verify `PROXY_ENABLED=true`
3. For Vertex: Ensure `VERTEX_PROXY_VIA_SDK=true`
4. Check logs for `[LLM_ROUTE]` proxy_mode field

## 🚀 Production Checklist

- [ ] Concurrency protection for SDK env proxy
- [ ] Fail-fast enabled for unsupported proxy requests
- [ ] Proxy credentials masked in all logs
- [ ] Backbone mode for >2000 tokens
- [ ] Streaming enabled for long proxied requests
- [ ] Telemetry capturing all required fields

## 📈 Future Optimizations

1. **Auto vendor switch:** If Vertex+proxy fails, auto-switch to OpenAI
2. **Token optimization:** Track usage deltas to optimize from "always 6000"
3. **Dedicated proxy worker:** Isolate proxied calls in separate process
4. **Geographic routing:** Smart vendor selection based on country

## 📝 Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| OpenAI Proxy | ✅ Working | Full support, backbone/rotating |
| Vertex GenAI Proxy | ⚠️ Unstable | SDK limitation, use env proxy |
| Vertex SDK Env Proxy | ✅ Working | Set `VERTEX_PROXY_VIA_SDK=true` |
| Grounding Support | ✅ Working | Both vendors |
| Telemetry | ✅ Complete | Full logging |
| Fail-fast | ✅ Implemented | Clear errors |

---
Last updated: 2025-08-26
Tested with: gpt-5, gemini-2.5-pro, 6000 tokens