# GPT-5 Testing Summary

## Key Findings

### ✅ GPT-5 IS Available via OpenAI API

The model `gpt-5` is accessible through the OpenAI Responses API and actively performs web searches when requested.

### Model Mapping Issue Fixed

**Problem:** The adapter was incorrectly remapping `gpt-5` → `gpt-5-chat-latest` (non-reasoning variant)

**Solution:** 
- Removed the automatic remapping in `app/llm/models.py`
- Now uses `gpt-5` directly as requested
- Added support for `gpt-5-mini` and `gpt-5-nano` variants

### API Requirements

**Correct API:** Responses API (`client.responses.create`)
- **NOT** Chat Completions API

**Correct Parameters:**
```python
response = await client.responses.create(
    model="gpt-5",
    input=user_prompt,  # NOT 'messages'
    instructions=system_instruction,  # NOT in messages array
    tools=[{"type": "web_search"}],  # Built-in web search tool
    temperature=1.0,  # REQUIRED for GPT-5
    max_output_tokens=3000  # NOT 'max_tokens'
)
```

### Web Search Functionality

✅ **GPT-5 DOES support web search** through the built-in `web_search` tool

In our test, GPT-5 made multiple web searches including:
- "August 2025 health news August 2025 site:reuters.com"
- "site:fda.gov August 2025 approval FDA August 2025 press release"
- "site:nih.gov August 2025 press release August 2025 NIH study"
- "August 2025 CDC health alert August 2025 HAN"
- "August 18, 2025 Texas Department of State Health Services measles outbreak"
- "August 2025 H5N1 human case United States August 2025 CDC"
- "August 2025 GLP-1 coverage insurance news August 2025"
- "site:fda.gov August 15 2025 Wegovy MASH approval FDA press release"

### Response Format

The Responses API returns a different structure than Chat Completions:
- Output is a list of response items (reasoning items, web search calls)
- Each web search call includes the query and status
- Final text output needs to be extracted from the response items

### Performance

- Response time: ~35-75 seconds for grounded requests with multiple web searches
- The model performs extensive searches to gather current information
- **CRITICAL: Requires 6000+ tokens** for grounded requests (not 2000)
- Rate limit: 30,000 tokens/minute

### Citations

✅ **GPT-5 DOES provide citations** when given enough tokens:
- Citations appear as `url_citation` annotations in the final `message` item
- Follow OpenAI Cookbook pattern: searches → reasoning → message with citations
- With only 2000 tokens, the model exhausts budget before generating the final message
- With 6000 tokens, citations are properly included

## Files Updated

1. **app/llm/models.py**
   - Removed `gpt-5` → `gpt-5-chat-latest` remapping
   - Added `gpt-5-mini` and `gpt-5-nano` to allowed models
   - Changed default to `gpt-5` (reasoning model)

2. **app/llm/adapters/openai_adapter.py**
   - Already correctly using Responses API
   - Already has web_search tool support
   - Temperature override for GPT-5 (always 1.0)

## Recommendations

1. **Use GPT-5 directly** - Don't remap to chat variants
2. **Expect longer response times** - Web search adds significant latency
3. **Handle the response format** - Output is a list of items, not simple text
4. **Monitor costs** - GPT-5 with extensive web searching may be expensive

## Test Status

✅ GPT-5 is available and working with web search
✅ Model mapping issue fixed
✅ Responses API parameters corrected
✅ Web search functionality confirmed