"""
Unit tests for grounding detection helpers.
Tests detection logic without hitting actual APIs.
"""
import types
import pytest
from app.llm.adapters.grounding_detection_helpers import (
    detect_openai_grounding, detect_vertex_grounding
)

# ---------- OpenAI Tests ----------

def test_openai_detects_web_search_call():
    """Test detection of web_search_call type in output"""
    resp = {"output": [{"type": "web_search_call"}]}
    grounded, calls = detect_openai_grounding(resp)
    assert grounded is True
    assert calls == 1

def test_openai_detects_multiple_search_calls():
    """Test counting multiple tool calls"""
    resp = {"output": [
        {"type": "web_search_call"},
        {"type": "web_search_result"},
        {"type": "tool_use"}
    ]}
    grounded, calls = detect_openai_grounding(resp)
    assert grounded is True
    assert calls == 3

def test_openai_detects_url_citation_annotation():
    """Test detection of URL citations in message content"""
    resp = {
        "output": [{
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": "hello",
                "annotations": [{"type": "url_citation", "url": "https://x.y"}],
            }]
        }]
    }
    grounded, calls = detect_openai_grounding(resp)
    assert grounded is True
    assert calls == 0  # citation w/o explicit call still counts as grounded

def test_openai_no_grounding_signals():
    """Test when no grounding signals are present"""
    resp = {"output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}]}
    grounded, calls = detect_openai_grounding(resp)
    assert grounded is False
    assert calls == 0

def test_openai_detects_tool_use():
    """Test legacy tool_use detection"""
    resp = {"output": [{"type": "tool_use"}, {"type": "tool_result"}]}
    grounded, calls = detect_openai_grounding(resp)
    assert grounded is True
    assert calls == 2

def test_openai_case_insensitive_search():
    """Test case-insensitive search detection"""
    resp = {"output": [{"type": "WEB_SEARCH"}]}
    grounded, calls = detect_openai_grounding(resp)
    assert grounded is True
    assert calls == 1

# ---------- Vertex / Gemini Tests ----------

def _obj(**kw):
    """Helper to create namespace objects"""
    return types.SimpleNamespace(**kw)

def test_vertex_snake_case_grounding_metadata():
    """Test snake_case field detection"""
    gm = _obj(web_search_queries=["site:example.com"], grounding_chunks=[], search_entry_point=None)
    cand = _obj(grounding_metadata=gm)
    resp = _obj(candidates=[cand])
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is True
    assert calls == 1

def test_vertex_camelCase_grounding_metadata():
    """Test camelCase field detection"""
    gm = {"webSearchQueries": ["q1","q2"], "groundingChunks": [], "searchEntryPoint": {}}
    resp = {"candidates": [{"groundingMetadata": gm}]}
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is True
    assert calls == 2

def test_vertex_no_grounding():
    """Test when no grounding metadata present"""
    resp = {"candidates": [{"grounding_metadata": {}}]}
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is False
    assert calls == 0

def test_vertex_grounding_chunks_only():
    """Test detection with only grounding chunks"""
    gm = {"groundingChunks": [{"content": "chunk1"}]}
    resp = {"candidates": [{"grounding_metadata": gm}]}
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is True
    assert calls == 1  # default count when no queries

def test_vertex_search_entry_point_only():
    """Test detection with only search entry point"""
    gm = _obj(web_search_queries=None, grounding_chunks=None, search_entry_point={"url": "http://x"})
    cand = _obj(grounding_metadata=gm)
    resp = _obj(candidates=[cand])
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is True
    assert calls == 1

def test_vertex_mixed_case_fields():
    """Test when both snake_case and camelCase exist"""
    # Should not double-count
    gm = _obj(web_search_queries=["q1"], webSearchQueries=["q2"])
    cand = _obj(grounding_metadata=gm)
    resp = _obj(candidates=[cand])
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is True
    assert calls == 1  # Takes first match, doesn't double count

def test_vertex_empty_candidates():
    """Test with empty candidates list"""
    resp = {"candidates": []}
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is False
    assert calls == 0

def test_vertex_no_candidates():
    """Test with missing candidates"""
    resp = {}
    grounded, calls = detect_vertex_grounding(resp)
    assert grounded is False
    assert calls == 0