#!/bin/bash
# Final acceptance check - quick static validation

echo "======================================================================"
echo "GROUNDING IMPLEMENTATION - FINAL ACCEPTANCE CHECK"
echo "======================================================================"
echo ""

FAILED=0

echo "=== 1. STATIC GUARDS ==="
echo ""

# Check 1: No web_search_preview
echo -n "1. No web_search_preview references: "
COUNT=$(grep -RIn "web_search_preview" backend/ 2>/dev/null | wc -l)
if [ $COUNT -eq 0 ]; then
    echo "✅ PASS (0 references)"
else
    echo "❌ FAIL ($COUNT references found)"
    FAILED=1
fi

# Check 2: No google.genai/HttpOptions/GenerateContentConfig
echo -n "2. No google.genai/HttpOptions/GenerateContentConfig: "
COUNT=$(grep -RIn "google\.genai\|HttpOptions\|GenerateContentConfig" backend/ 2>/dev/null | wc -l)
if [ $COUNT -eq 0 ]; then
    echo "✅ PASS (0 references)"
else
    echo "❌ FAIL ($COUNT references found)"
    FAILED=1
fi

# Check 3: No disallowed models in LLM adapters
echo -n "3. No gemini-2.0/flash/exp/chatty in LLM adapters: "
COUNT=$(grep -RIn -E "gemini-2\.0|flash|exp|chatty" backend/app/llm/adapters/ 2>/dev/null | wc -l)
if [ $COUNT -eq 0 ]; then
    echo "✅ PASS (0 references)"
else
    echo "❌ FAIL ($COUNT references found)"
    FAILED=1
fi

echo ""
echo "=== 2. TOOL CONFIGURATION ==="
echo ""

# Check OpenAI web_search tool
echo -n "4. OpenAI uses web_search tool: "
if grep -q '"web_search"' app/llm/adapters/openai_adapter.py; then
    echo "✅ PASS"
else
    echo "❌ FAIL"
    FAILED=1
fi

# Check OpenAI tool_choice
echo -n "5. OpenAI sets tool_choice (auto/required): "
if grep -q 'tool_choice.*=.*"required"\|tool_choice.*=.*"auto"' app/llm/adapters/openai_adapter.py; then
    echo "✅ PASS"
else
    echo "❌ FAIL"
    FAILED=1
fi

# Check Vertex GoogleSearchRetrieval
echo -n "6. Vertex uses Tool.from_google_search_retrieval: "
if grep -q "from_google_search_retrieval" app/llm/adapters/vertex_adapter.py; then
    echo "✅ PASS"
else
    echo "❌ FAIL"
    FAILED=1
fi

# Check Vertex two-step attestation
echo -n "7. Vertex has two-step attestation fields: "
if grep -q "step2_tools_invoked\|step2_source_ref" app/llm/adapters/vertex_adapter.py; then
    echo "✅ PASS"
else
    echo "❌ FAIL"
    FAILED=1
fi

echo ""
echo "=== 3. MODEL PINS ==="
echo ""

# Check model allowlists exist
echo -n "8. Model allowlists configured: "
if [ -f app/llm/models.py ]; then
    if grep -q "OPENAI_ALLOWED_MODELS\|VERTEX_ALLOWED_MODELS" app/llm/models.py; then
        echo "✅ PASS"
    else
        echo "❌ FAIL (allowlists not found)"
        FAILED=1
    fi
else
    echo "❌ FAIL (models.py not found)"
    FAILED=1
fi

# Check REQUIRED enforcement
echo -n "9. REQUIRED mode enforcement: "
OPENAI_CHECK=$(grep -c "GROUNDING_REQUIRED_ERROR\|REQUIRED.*grounded_effective" app/llm/adapters/openai_adapter.py)
VERTEX_CHECK=$(grep -c "GroundingRequiredError\|REQUIRED.*grounded_effective" app/llm/adapters/vertex_adapter.py)
if [ $OPENAI_CHECK -gt 0 ] && [ $VERTEX_CHECK -gt 0 ]; then
    echo "✅ PASS"
else
    echo "❌ FAIL"
    FAILED=1
fi

echo ""
echo "======================================================================"
if [ $FAILED -eq 0 ]; then
    echo "✅ ALL STATIC CHECKS PASSED"
    echo ""
    echo "The implementation is ready for:"
    echo "  - OpenAI GPT-5 with web_search tool (Preferred/Required modes)"
    echo "  - Vertex Gemini 2.5-pro with GoogleSearch (Preferred/Required modes)"
    echo "  - Two-step grounded JSON for Vertex"
    echo "  - Fail-closed REQUIRED mode enforcement"
    echo ""
    echo "Next: Run 'python final_acceptance_test.py' for runtime validation"
else
    echo "❌ SOME CHECKS FAILED - Review issues above"
fi
echo "======================================================================"

exit $FAILED