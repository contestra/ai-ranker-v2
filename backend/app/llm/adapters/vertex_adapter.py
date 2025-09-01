"""
Vertex AI adapter for Gemini models via Vertex AI.
Default allowed models: gemini-2.5-pro, gemini-2.0-flash
Configurable via ALLOWED_VERTEX_MODELS env var.
Supports both vertexai SDK and google-genai for API compatibility.
Implements two-step grounded JSON policy as required.
"""
import json
import os
import re
import time
import logging
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import vertexai
from vertexai import generative_models as gm
from vertexai.generative_models import grounding
from vertexai.generative_models import Tool
from starlette.concurrency import run_in_threadpool

# Import settings for feature flags
from app.core.config import settings

# Import google-genai for new API support
try:
    import google.genai as genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from app.llm.types import LLMRequest, LLMResponse
from app.llm.models import VERTEX_ALLOWED_MODELS, VERTEX_DEFAULT_MODEL, validate_model
from .grounding_detection_helpers import detect_vertex_grounding
from urllib.parse import urlparse, urlunparse, parse_qs
from app.llm.citations.resolver import resolve_citation_url, resolve_citations_with_budget
from app.llm.citations.domains import registrable_domain_from_url

logger = logging.getLogger(__name__)

# Debug flag for citation extraction
DEBUG_GROUNDING = os.getenv("DEBUG_GROUNDING", "false").lower() == "true"
# Optional: emit unlinked (non-anchored) sources when no anchored citations were found.
# Default false to keep telemetry clean; can be enabled per-run via env.
EMIT_UNLINKED_SOURCES = os.getenv("CITATION_EXTRACTOR_EMIT_UNLINKED", "false").lower() == "true"

def _get_registrable_domain(url: str) -> str:
    """
    Extract registrable domain from URL.
    Simple implementation without public suffix list.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return ""
        
        # Remove port if present
        domain = domain.split(':')[0]
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # For Vertex redirects, keep the full domain
        if 'vertexaisearch.cloud.google.com' in domain:
            return domain
        
        # For most domains, return as-is (keeps subdomains)
        # Only strip for known second-level TLDs
        parts = domain.split('.')
        if len(parts) >= 3:
            # Check if it's a known second-level TLD pattern
            if parts[-2] in ['co', 'ac', 'gov', 'edu', 'org', 'net', 'com'] and parts[-1] in ['uk', 'jp', 'au', 'nz', 'za']:
                # e.g., example.co.uk -> return last 3 parts
                return '.'.join(parts[-3:])
        
        # For everything else, return full domain
        return domain
    except:
        return ""


def _normalize_url(url: str) -> str:
    """
    Normalize URL for deduplication:
    - Remove UTM params
    - Remove anchors
    - Lowercase host
    """
    try:
        parsed = urlparse(url)
        # Remove fragment
        parsed = parsed._replace(fragment='')
        
        # Remove tracking params
        if parsed.query:
            params = parse_qs(parsed.query)
            # Remove common tracking params
            tracking_params = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 
                              'utm_content', 'fbclid', 'gclid', 'ref', 'source'}
            cleaned_params = {k: v for k, v in params.items() 
                            if k.lower() not in tracking_params}
            
            # Rebuild query string
            if cleaned_params:
                query_parts = []
                for k, v_list in cleaned_params.items():
                    for v in v_list:
                        query_parts.append(f"{k}={v}")
                parsed = parsed._replace(query='&'.join(query_parts))
            else:
                parsed = parsed._replace(query='')
        
        # Lowercase netloc
        parsed = parsed._replace(netloc=parsed.netloc.lower())
        
        return urlunparse(parsed)
    except:
        return url


def _compute_ab_bucket(tenant_id: Optional[str] = None, account_id: Optional[str] = None, 
                      template_id: Optional[str] = None) -> float:
    """
    Compute stable A/B bucket for consistent rollout.
    Uses stable tenant/account identifiers for sticky bucketing.
    
    Args:
        tenant_id: Stable tenant identifier (preferred)
        account_id: Stable account identifier (fallback)
        template_id: Optional template ID for per-template bucketing
    
    Returns: float in [0, 1) for comparison with citation_extractor_v2 threshold
    """
    # Build stable key from tenant/account (never use request_id which changes)
    stable_key_parts = []
    if tenant_id:
        stable_key_parts.append(f"tenant:{tenant_id}")
    elif account_id:
        stable_key_parts.append(f"account:{account_id}")
    else:
        # Fallback for anonymous/testing - will get consistent assignment
        stable_key_parts.append("anonymous")
    
    # Optionally include template for per-template canaries
    if template_id:
        stable_key_parts.append(f"template:{template_id}")
    
    hash_key = "|".join(stable_key_parts)
    
    # Generate stable hash (MD5 is fine for distribution, not security)
    hash_obj = hashlib.md5(hash_key.encode())
    hash_bytes = hash_obj.digest()
    
    # Convert first 4 bytes to float in [0, 1)
    bucket_int = int.from_bytes(hash_bytes[:4], byteorder='big')
    max_int = 2**32 - 1
    
    return bucket_int / max_int


def _select_and_extract_citations(resp, tenant_id: str = None, account_id: str = None,
                                 template_id: str = None) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    A/B selection wrapper for citation extraction with proper flag precedence.
    
    Flag precedence:
    1. CITATIONS_EXTRACTOR_ENABLE=false → disable all extraction
    2. Otherwise, use percentage rollout via CITATION_EXTRACTOR_V2
    3. CITATION_EXTRACTOR_ENABLE_LEGACY controls fallback availability
    
    Returns: (citations, telemetry_dict)
    """
    telemetry = {}
    
    # Flag precedence 1: Master kill switch
    if not settings.citations_extractor_enable:
        telemetry["extractor_variant"] = "disabled"
        telemetry["ab_bucket"] = 0.0
        telemetry["anchored_citations_count"] = 0
        telemetry["unlinked_sources_count"] = 0
        return [], telemetry
    
    # Compute A/B bucket using stable identifiers
    bucket = _compute_ab_bucket(tenant_id=tenant_id, account_id=account_id, 
                               template_id=template_id)
    telemetry["ab_bucket"] = round(bucket, 4)
    
    # Clamp citation_extractor_v2 to [0, 1] for safety
    v2_threshold = max(0.0, min(1.0, settings.citation_extractor_v2))
    print(f"[DEBUG] citation_extractor_v2={settings.citation_extractor_v2}, v2_threshold={v2_threshold}, bucket={bucket}")
    
    # Boundary rule: bucket strictly less than threshold goes to V2
    # e.g., 0.05 threshold means buckets [0, 0.05) get V2 (exactly 5%)
    use_v2 = bucket < v2_threshold
    
    # Track current flag values
    telemetry["flag_snapshot"] = {
        "citation_extractor_v2": settings.citation_extractor_v2,
        "citations_extractor_enable": settings.citations_extractor_enable,
        "citation_extractor_enable_legacy": settings.citation_extractor_enable_legacy,
        "emit_unlinked_enabled": EMIT_UNLINKED_SOURCES,
    }
    
    # Try selected variant with fallback
    citations = []
    variant_used = None
    
    try:
        if use_v2:
            # Use V2 extractor
            variant_used = "v2"
            telemetry["extractor_variant"] = "v2"
            citations = _extract_vertex_citations(resp)
        else:
            # Use legacy extractor
            if settings.citation_extractor_enable_legacy:
                variant_used = "legacy"
                telemetry["extractor_variant"] = "legacy"
                citations = _extract_vertex_citations_legacy(resp)
            else:
                # Legacy disabled, use V2 anyway
                variant_used = "v2"
                telemetry["extractor_variant"] = "v2_forced"
                citations = _extract_vertex_citations(resp)
                
    except Exception as e:
        # On error, try fallback
        logger.warning(f"Citation extractor {variant_used} failed: {e}")
        telemetry["variant_error"] = str(e)[:200]  # Truncate for safety, no stack/PII
        
        if variant_used == "v2" and settings.citation_extractor_enable_legacy:
            try:
                logger.info("Falling back to legacy extractor")
                citations = _extract_vertex_citations_legacy(resp)
                telemetry["variant_fallback"] = True
                telemetry["extractor_variant"] = "legacy_fallback"
            except Exception as e2:
                logger.error(f"Legacy fallback also failed: {e2}")
                telemetry["fallback_error"] = str(e2)[:200]
    
    # Add citation metrics by variant
    anchored_count = 0
    unlinked_count = 0
    shape_set = set()
    
    for cit in citations:
        # Count anchored vs unlinked
        if cit.get("source_type") in ["direct_uri", "v1_join", "groundingChunks"]:
            anchored_count += 1
        elif cit.get("source_type") in ["unlinked", "legacy", "text_harvest"]:
            unlinked_count += 1
        
        # Track shape
        shape = cit.get("source_type", "unknown")
        shape_set.add(shape)
    
    telemetry["anchored_citations_count"] = anchored_count
    telemetry["unlinked_sources_count"] = unlinked_count
    telemetry["citations_shape_set"] = list(shape_set)
    telemetry["emit_unlinked_enabled"] = EMIT_UNLINKED_SOURCES
    
    return citations, telemetry


def _extract_vertex_citations_legacy(resp) -> List[Dict]:
    """
    Legacy citation extractor - simplified version before the comprehensive fixes.
    Kept for A/B testing and safe rollback.
    """
    citations = []
    seen_urls = {}
    
    # Simple extraction from candidates
    candidates = getattr(resp, 'candidates', [])
    if not candidates and hasattr(resp, 'model_dump'):
        dict_resp = resp.model_dump()
        candidates = dict_resp.get('candidates', [])
    
    for candidate in candidates:
        # Check groundingMetadata at candidate level
        gm = getattr(candidate, 'groundingMetadata', None) or getattr(candidate, 'grounding_metadata', None)
        if not gm and isinstance(candidate, dict):
            gm = candidate.get('groundingMetadata') or candidate.get('grounding_metadata')
        
        if gm:
            # Extract from various fields (simplified)
            if isinstance(gm, dict):
                # Check citations array
                for cit in gm.get('citations', []):
                    url = cit.get('uri') or cit.get('url')
                    if url and url not in seen_urls:
                        seen_urls[url] = {
                            "provider": "vertex",
                            "url": url,
                            "title": cit.get('title'),
                            "snippet": cit.get('snippet'),
                            "source_domain": registrable_domain_from_url(url),
                            "source_type": "legacy",
                            "rank": len(citations) + 1
                        }
                        citations.append(seen_urls[url])
    
    return citations


def _extract_vertex_citations(resp) -> List[Dict]:
    """
    Extract citations from Vertex/Gemini response following uniform schema.
    Handles multiple SDK variants and field names, including the v1 JOIN pattern.
    
    V1 pattern: citations (spans with sourceIds) → citedSources (actual URLs)
    Legacy patterns: groundingAttributions, groundingChunks, etc. with direct URLs
    """
    citations = []
    seen_urls = {}  # normalized_url -> citation dict (for deduplication)
    
    # DEBUG: Log what type of response we got
    print(f"[CITATIONS_DEBUG] Response type: {type(resp)}")
    if hasattr(resp, 'candidates'):
        print(f"[CITATIONS_DEBUG] Has candidates: {len(resp.candidates) if resp.candidates else 0}")
        if resp.candidates and len(resp.candidates) > 0:
            cand = resp.candidates[0]
            print(f"[CITATIONS_DEBUG] Candidate type: {type(cand)}")
            if hasattr(cand, 'grounding_metadata'):
                print(f"[CITATIONS_DEBUG] Has grounding_metadata attr")
            if hasattr(cand, 'groundingMetadata'):
                print(f"[CITATIONS_DEBUG] Has groundingMetadata attr")
    
    def add_citation(raw_item: dict, source_type: Optional[str] = None):
        if not raw_item:
            return
        
        # Look for end-site URLs in various fields (prioritize non-redirect URLs)
        end_url = None
        redirect_url = None
        title = ""
        snippet = ""
        source_domain = None
        
        # 1. Check for direct URLs in various fields
        for url_field in ["sourceUrl", "pageUrl", "source_uri", "url", "uri"]:
            if url_field in raw_item and raw_item[url_field]:
                url = raw_item[url_field]
                # Check if it's a Vertex redirect
                if "vertexaisearch.cloud.google.com/grounding-api-redirect" in url:
                    redirect_url = url
                else:
                    end_url = url
                    break
        
        # 2. Check nested structures for end-site URLs
        if not end_url:
            for nested_key in ["web", "source", "reference", "support"]:
                if nested_key in raw_item and isinstance(raw_item[nested_key], dict):
                    nested = raw_item[nested_key]
                    for url_field in ["uri", "url", "sourceUrl", "pageUrl"]:
                        if url_field in nested and nested[url_field]:
                            url = nested[url_field]
                            if "vertexaisearch.cloud.google.com" not in url:
                                end_url = url
                                break
                    
                    # Also check for domain/host fields
                    if not source_domain:
                        source_domain = nested.get("domain") or nested.get("host")
                    
                    if end_url:
                        break
        
        # Use whichever URL we found
        final_url = end_url or redirect_url
        if not final_url:
            return
        
        # Normalize URL for deduplication
        normalized = _normalize_url(final_url)
        
        # Extract title and snippet
        title = raw_item.get("title", "")
        snippet = raw_item.get("snippet") or raw_item.get("text") or raw_item.get("summary", "")
        
        # Determine source_domain
        if end_url:
            # Extract from actual end URL
            source_domain = _get_registrable_domain(end_url)
        elif source_domain:
            # Already extracted from nested fields
            pass
        elif title and '.' in title and not ' ' in title[:20]:
            # Title might be a domain (e.g., "consensus.app", "nih.gov")
            domain_match = re.match(r'^([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)', title)
            if domain_match:
                source_domain = domain_match.group(1).lower()
        
        # If still no source_domain and we only have redirect, extract from redirect
        if not source_domain and redirect_url:
            source_domain = _get_registrable_domain(redirect_url)
        
        # Check for duplicate
        if normalized in seen_urls:
            # Update rank if lower
            existing = seen_urls[normalized]
            new_rank = len(citations) + 1
            if existing.get('rank') is None or new_rank < existing['rank']:
                existing['rank'] = new_rank
            return
        
        # Create citation with raw data preserved
        citation = {
            "provider": "vertex",
            "url": final_url,
            "source_domain": "",  # Will be set after resolution
            "title": title,
            "snippet": snippet,
            "source_type": (source_type or "web"),
            "rank": len(citations) + 1,
            "raw": raw_item
        }
        
        # Don't resolve here - will batch resolve at the end
        # Just set source_domain from what we have
        citation["source_domain"] = source_domain or _get_registrable_domain(final_url)
        
        seen_urls[normalized] = citation
        citations.append(citation)
    
    try:
        # STEP 1: Materialize both views up front
        typed_candidates = list(getattr(resp, "candidates", None) or [])
        
        # Get dict view from model_dump if available
        dict_resp = None
        if isinstance(resp, dict):
            dict_resp = resp
        elif hasattr(resp, 'model_dump'):
            try:
                dict_resp = resp.model_dump()
            except Exception:
                pass
        
        dict_candidates = dict_resp.get("candidates", []) if dict_resp else []
        
        # Process max of both views
        n = max(len(typed_candidates), len(dict_candidates))
        
        # STEP 2: Iterate by index to handle both views
        for idx in range(n):
            # Get typed candidate at this index (if exists)
            typed_cand = typed_candidates[idx] if idx < len(typed_candidates) else None
            
            # Get dict candidate at this index (if exists)
            cand_dict = {}
            if idx < len(dict_candidates):
                cand_dict = dict_candidates[idx]
            elif typed_cand and hasattr(typed_cand, 'model_dump'):
                # Fallback: try to get dict from typed candidate
                try:
                    cand_dict = typed_cand.model_dump()
                except:
                    pass
            
            # STEP 3: Always consult dict fields first (more stable)
            gm_dict = {}
            cm_dict = {}
            
            if cand_dict:
                # Extract from dict (both camel and snake case)
                gm_dict = cand_dict.get('groundingMetadata') or cand_dict.get('grounding_metadata') or {}
                cm_dict = cand_dict.get('citationMetadata') or cand_dict.get('citation_metadata') or {}
            
            # STEP 4: Also check typed attributes for enrichment
            gm_attr = None
            cm_attr = None
            
            if typed_cand:
                gm_attr = getattr(typed_cand, "grounding_metadata", None) or getattr(typed_cand, "groundingMetadata", None)
                cm_attr = getattr(typed_cand, "citation_metadata", None) or getattr(typed_cand, "citationMetadata", None)
            
            # Skip ONLY if we have no data from any source
            if not gm_dict and not cm_dict and not gm_attr and not cm_attr:
                continue
            
            # STEP 5: Merge typed attributes into dict if dict is empty
            if not gm_dict and gm_attr:
                try:
                    gm_dict = dict(gm_attr)
                except:
                    # Introspect if dict conversion fails
                    for key in dir(gm_attr):
                        if not key.startswith("_"):
                            try:
                                val = getattr(gm_attr, key)
                                if isinstance(val, list) and val:
                                    converted = []
                                    for item in val:
                                        if hasattr(item, '__dict__'):
                                            converted.append(vars(item))
                                        else:
                                            converted.append(item)
                                    gm_dict[key] = converted
                                else:
                                    gm_dict[key] = val
                            except:
                                pass
            
            if not cm_dict and cm_attr:
                try:
                    cm_dict = dict(cm_attr)
                except:
                    # Introspect if dict conversion fails
                    for key in dir(cm_attr):
                        if not key.startswith("_"):
                            try:
                                val = getattr(cm_attr, key)
                                if isinstance(val, list) and val:
                                    converted = []
                                    for item in val:
                                        if hasattr(item, '__dict__'):
                                            converted.append(vars(item))
                                        else:
                                            converted.append(item)
                                    cm_dict[key] = converted
                                else:
                                    cm_dict[key] = val
                            except:
                                pass
            
            # Merge citation metadata into grounding metadata dict
            if cm_dict:
                for key, value in cm_dict.items():
                    if key not in gm_dict:
                        gm_dict[key] = value
            
            # Now gm_dict has everything - continue with extraction
            
            # STEP 1: Build source pool and ID map for v1 JOIN pattern
            source_id_map = {}  # sourceId -> source dict
            source_pool = []    # All sources for fallback emission
            
            # Collect citedSources (v1 pattern) - these have the actual URLs
            cited_sources = gm_dict.get("citedSources") or gm_dict.get("cited_sources") or []
            for idx, source in enumerate(cited_sources):
                source_dict = source if isinstance(source, dict) else {}
                if not isinstance(source, dict):
                    # Convert object to dict
                    for attr in ["id", "uri", "url", "title", "snippet", "web"]:
                        if hasattr(source, attr):
                            source_dict[attr] = getattr(source, attr)
                
                # Store in ID map - use 'id' field or index as string
                source_id = source_dict.get("id") or str(idx)
                source_id_map[source_id] = source_dict
                source_id_map[str(idx)] = source_dict  # Also map by index
                source_pool.append(source_dict)
            
            # DEBUG: Log what we have in gm_dict
            if DEBUG_GROUNDING and gm_dict:
                logger.info(f"[CITATIONS_DEBUG] gm_dict keys: {list(gm_dict.keys())}")
                # Log sample of each key
                for key in list(gm_dict.keys())[:5]:
                    val = gm_dict[key]
                    if isinstance(val, list) and val:
                        logger.info(f"[CITATIONS_DEBUG] {key}[0]: {str(val[0])[:200]}")
                        # Check if val is empty after conversion
                        if key == "grounding_chunks":
                            logger.info(f"[CITATIONS_DEBUG] grounding_chunks has {len(val)} items")
                            for i, chunk in enumerate(val[:2]):
                                logger.info(f"[CITATIONS_DEBUG] chunk[{i}] type: {type(chunk)}, is_dict: {isinstance(chunk, dict)}")
                    elif val:
                        logger.info(f"[CITATIONS_DEBUG] {key}: {str(val)[:200]}")
            
            # Also collect other source arrays into the pool - check MORE variants
            other_source_fields = [
                ("groundingAttributions", gm_dict.get("grounding_attributions") or gm_dict.get("groundingAttributions")),
                ("groundingChunks", gm_dict.get("grounding_chunks") or gm_dict.get("groundingChunks")),
                ("groundingSupports", gm_dict.get("grounding_supports") or gm_dict.get("groundingSupports")),
                ("supportingContent", gm_dict.get("supporting_content") or gm_dict.get("supportingContent")),
                ("webSearchSources", gm_dict.get("webSearchSources") or gm_dict.get("web_search_sources")),
                ("sources", gm_dict.get("sources")),
                # Add more field variants that appear in newer SDKs
                ("citedChunks", gm_dict.get("cited_chunks") or gm_dict.get("citedChunks")),
                ("searchEntryPoint", gm_dict.get("search_entry_point") or gm_dict.get("searchEntryPoint")),
                ("retrievedContexts", gm_dict.get("retrieved_contexts") or gm_dict.get("retrievedContexts")),
            ]
            
            # Also check citationMetadata if present
            if "citationMetadata" in gm_dict or "citation_metadata" in gm_dict:
                cit_meta = gm_dict.get("citationMetadata") or gm_dict.get("citation_metadata") or {}
                if isinstance(cit_meta, dict):
                    if "citations" in cit_meta:
                        other_source_fields.append(("citationMetadata.citations", cit_meta["citations"]))
            
            for field_name, field_value in other_source_fields:
                if field_value:
                    for item in field_value:
                        item_dict = item if isinstance(item, dict) else {}
                        if not isinstance(item, dict):
                            # Convert object to dict
                            for attr in ["uri", "url", "source_uri", "title", "snippet", "text", 
                                       "pageUrl", "sourceUrl", "summary", "domain", "host", "web"]:
                                if hasattr(item, attr):
                                    item_dict[attr] = getattr(item, attr)
                            
                            # Check nested objects
                            for nested_attr in ["source", "web", "reference", "support"]:
                                try:
                                    nested = getattr(item, nested_attr, None)
                                    if nested:
                                        item_dict[nested_attr] = {}
                                        for sub_attr in ["uri", "url", "title", "domain", "host"]:
                                            try:
                                                val = getattr(nested, sub_attr, None)
                                                if val:
                                                    item_dict[nested_attr][sub_attr] = val
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                        
                        # Special handling for grounding_chunks which have nested web field
                        if field_name == "groundingChunks" and isinstance(item_dict, dict):
                            # grounding_chunks have structure: {'web': {'uri': '...', 'domain': '...', ...}}
                            if 'web' in item_dict and isinstance(item_dict['web'], dict):
                                web_data = item_dict['web']
                                # Flatten the web field into the top level for easier processing
                                if 'uri' in web_data:
                                    item_dict['url'] = web_data['uri']
                                if 'domain' in web_data:
                                    item_dict['source_domain'] = web_data['domain']
                                if 'title' in web_data:
                                    item_dict['title'] = web_data.get('title', '')
                        
                        if item_dict:
                            source_pool.append(item_dict)
            
            # STEP 2: Process citations (v1 pattern - these reference sourceIds)
            citations_refs = gm_dict.get("citations") or []
            anchored_sources = set()  # Track which sources have been anchored
            
            for cit_ref in citations_refs:
                cit_dict = cit_ref if isinstance(cit_ref, dict) else {}
                if not isinstance(cit_ref, dict):
                    # Convert object to dict
                    for attr in ["sourceId", "sourceIds", "sourceIndices", "url", "uri"]:
                        if hasattr(cit_ref, attr):
                            cit_dict[attr] = getattr(cit_ref, attr)
                
                # Check for sourceId references (v1 JOIN pattern)
                source_ids = []
                if "sourceId" in cit_dict:
                    source_ids.append(str(cit_dict["sourceId"]))
                elif "sourceIds" in cit_dict:
                    source_ids.extend([str(sid) for sid in cit_dict["sourceIds"]])
                elif "sourceIndices" in cit_dict:
                    source_ids.extend([str(idx) for idx in cit_dict["sourceIndices"]])
                
                # JOIN: resolve sourceIds to actual sources
                if source_ids:
                    for sid in source_ids:
                        if sid in source_id_map:
                            source_dict = source_id_map[sid]
                            add_citation(source_dict, source_type="v1_join")
                            anchored_sources.add(sid)  # Mark as anchored
                # Direct URL in citation (some variants)
                elif cit_dict.get("url") or cit_dict.get("uri"):
                    add_citation(cit_dict, source_type="direct_uri")
            
            # Determine if tools were called for this candidate (cheap, typed-path only)
            tools_called = False
            try:
                if typed_cand and hasattr(typed_cand, "content") and hasattr(typed_cand.content, "parts"):
                    for _part in typed_cand.content.parts:
                        if hasattr(_part, "function_call") and _part.function_call:
                            tools_called = True
                            break
            except Exception:
                pass
            
            # STEP 3: Optionally flush unlinked sources
            # Emit sources that weren't referenced by citations (unlinked) when:
            #  - at least one anchored citation exists, OR
            #  - explicit override via CITATION_EXTRACTOR_EMIT_UNLINKED=true, OR
            #  - tools were called (evidence came back without text-anchored spans)
            if anchored_sources or EMIT_UNLINKED_SOURCES or tools_called:
                for idx, source_dict in enumerate(source_pool[:10]):
                    source_id = source_dict.get("id") or str(idx)
                    if source_id not in anchored_sources:
                        add_citation(source_dict, source_type="unlinked")
        
        # Log forensics if tools called but no citations
        if DEBUG_GROUNDING and not citations:
            # Check if tools were used
            tool_count = 0
            if hasattr(resp, "candidates") and resp.candidates:
                for cand in resp.candidates:
                    if hasattr(cand, "content") and hasattr(cand.content, "parts"):
                        for part in cand.content.parts:
                            if hasattr(part, "function_call"):
                                tool_count += 1
            
            if tool_count > 0:
                # Log warning with metadata keys found
                gm_keys = []
                if gm_dict:
                    gm_keys = list(gm_dict.keys())[:10]  # First 10 keys
                
                logger.warning(f"[CITATIONS] Vertex: {tool_count} tool calls but 0 citations extracted. "
                             f"Grounding metadata keys found: {gm_keys}")
                
                # Log first raw object for debugging
                if gm_dict:
                    first_items = {}
                    for key, val in gm_dict.items():
                        if val and hasattr(val, '__iter__'):
                            try:
                                first_items[key] = str(list(val)[:2])[:200]  # First 2 items, truncated
                            except:
                                pass
                    if first_items:
                        logger.debug(f"[CITATIONS] Sample grounding data: {first_items}")
    
    except Exception as e:
        logger.debug(f"Error in _extract_vertex_citations: {e}")
    
    # Enhanced forensics for tools>0 & citations==0
    tool_count = 0
    anchored_count = len([c for c in citations if c.get('source_type') != 'unlinked'])
    
    # Count tool calls
    if hasattr(resp, 'candidates'):
        for cand in resp.candidates:
            if hasattr(cand, 'content') and hasattr(cand.content, 'parts'):
                for part in cand.content.parts:
                    if hasattr(part, 'function_call'):
                        tool_count += 1
    
    # Forensics logging when tools called but no anchored citations
    if tool_count > 0 and anchored_count == 0:
        forensics = {
            'tool_call_count': tool_count,
            'anchored_citations_count': anchored_count,
            'unlinked_sources_count': len(citations),
            'typed_candidates_count': len(typed_candidates) if 'typed_candidates' in locals() else 0,
            'dict_candidates_count': len(dict_candidates) if 'dict_candidates' in locals() else 0,
            'citations_shape_set': list(set(c.get('source_type', 'unknown') for c in citations)),
            'citations_status_reason': 'no_anchored_citations'
        }
        
        # Add candidate preview (capped to 1KB)
        if 'n' in locals() and n > 0:
            candidate_preview = []
            for i in range(min(2, n)):  # First 2 candidates
                preview = {
                    'index': i,
                    'has_typed': i < len(typed_candidates) if 'typed_candidates' in locals() else False,
                    'has_dict': i < len(dict_candidates) if 'dict_candidates' in locals() else False
                }
                candidate_preview.append(preview)
            
            forensics['candidate_preview'] = str(candidate_preview)[:1024]
        
        logger.warning(f"[CITATIONS_FORENSICS] Tools called but no anchored citations: {forensics}")
    
    # Text-harvest fallback (AUTO-only, when enabled)
    if settings.text_harvest_auto_only and tool_count > 0 and anchored_count == 0:
        # Extract URLs from response text
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?\'"()]'
        
        # Get response text
        response_text = ""
        try:
            if hasattr(resp, 'candidates'):
                for cand in resp.candidates:
                    if hasattr(cand, 'content') and hasattr(cand.content, 'parts'):
                        for part in cand.content.parts:
                            if hasattr(part, 'text'):
                                response_text += part.text + " "
        except:
            pass
        
        if response_text:
            harvested_urls = re.findall(url_pattern, response_text)
            # Dedupe against existing citations
            existing_urls = {c['url'] for c in citations}
            
            for url in harvested_urls[:5]:  # Limit to 5 harvested URLs
                if url not in existing_urls:
                    citations.append({
                        'provider': 'vertex',
                        'url': url,
                        'source_domain': _get_registrable_domain(url),
                        'title': '',
                        'snippet': '',
                        'source_type': 'text_harvest',
                        'rank': len(citations) + 1,
                        'raw': {'harvested_from_text': True}
                    })
            
            if harvested_urls:
                logger.info(f"[TEXT_HARVEST] Added {len(harvested_urls)} URLs from text (AUTO mode)")
    
    # Apply budget-limited batch resolution to all citations
    if citations:
        citations = resolve_citations_with_budget(citations)
        
        # Update source_domain for resolved citations
        for citation in citations:
            resolved_url = citation.get("resolved_url") or citation.get("url")
            if resolved_url:
                # Re-extract domain using resolved URL
                citation["source_domain"] = registrable_domain_from_url(resolved_url) or citation.get("source_domain", "")
    
    return citations

def _audit_grounding_metadata(resp: Any) -> dict:
    """Forensic audit of grounding metadata structure when citations are missing."""
    audit = {"candidates": 0, "grounding_metadata_keys": [], "example": {}}
    try:
        if hasattr(resp, "candidates") and resp.candidates:
            audit["candidates"] = len(resp.candidates)
            cand = resp.candidates[0]
            gm = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None)
            if gm is None:
                return audit
            # Try to introspect available attributes / keys
            keys = set()
            try:
                gm_dict = dict(gm)  # works on some SDKs
                keys.update(gm_dict.keys())
                audit["example"] = {k: gm_dict[k] for k in list(gm_dict)[:3]}
            except Exception:
                for k in dir(gm):
                    if not k.startswith("_"):
                        keys.add(k)
                # sample a few attributes safely
                sample = {}
                for k in list(keys)[:5]:
                    try:
                        v = getattr(gm, k, None)
                        # avoid large dumps
                        if isinstance(v, (str, int, float, bool)) or v is None:
                            sample[k] = v
                    except Exception:
                        pass
                audit["example"] = sample
            audit["grounding_metadata_keys"] = sorted(list(keys))[:20]
    except Exception:
        pass
    return audit

# Models are now validated against allowlist in orchestrator
# No hard-coding or silent rewrites (Adapter PRD)

async def _call_vertex_model(model, *args, **kwargs):
    """
    Use async API if available, otherwise call the sync method in a thread.
    """
    gen_async = getattr(model, "generate_content_async", None)
    if gen_async and asyncio.iscoroutinefunction(gen_async):
        return await gen_async(*args, **kwargs)
    # fall back to sync generate_content in a thread
    gen_sync = getattr(model, "generate_content", None)
    if not gen_sync:
        raise RuntimeError("Vertex model has neither generate_content_async nor generate_content")
    return await run_in_threadpool(gen_sync, *args, **kwargs)

class GroundingRequiredError(Exception):
    """Raised when grounding is REQUIRED but not achieved"""
    pass

def _extract_vertex_usage(resp: Any) -> Dict[str, int]:
    """Extract token usage from Vertex response and normalize keys for telemetry."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    meta = getattr(resp, "usage_metadata", None)
    if meta:
        usage["prompt_tokens"] = getattr(meta, "prompt_token_count", 0)
        usage["completion_tokens"] = getattr(meta, "candidates_token_count", 0) 
        usage["total_tokens"] = getattr(meta, "total_token_count", 0)
    
    # Add synonyms for cross-adapter parity
    usage["input_tokens"] = usage["prompt_tokens"]
    usage["output_tokens"] = usage["completion_tokens"]
    
    return usage

def _extract_text_from_candidates(resp: Any) -> str:
    """Extract text from Vertex response - checks ALL candidates and ALL parts."""
    text_pieces = []
    
    try:
        # Check ALL candidates, not just first
        if hasattr(resp, "candidates") and resp.candidates:
            for idx, candidate in enumerate(resp.candidates):
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    parts = candidate.content.parts
                    if parts:
                        # Collect text from ALL parts in this candidate
                        for part_idx, part in enumerate(parts):
                            # Try text first
                            if hasattr(part, "text") and part.text:
                                text_pieces.append(part.text)
                                logger.debug(f"Found text in candidate[{idx}].part[{part_idx}]")
                            
                            # Try JSON data parts (for JSON mode responses)
                            elif hasattr(part, "json_data") and part.json_data is not None:
                                import json
                                json_text = json.dumps(part.json_data, ensure_ascii=False)
                                text_pieces.append(json_text)
                                logger.debug(f"Found json_data in candidate[{idx}].part[{part_idx}]")
                            
                            # Try inline_data (base64 encoded)
                            elif hasattr(part, "inline_data") and hasattr(part.inline_data, "data"):
                                try:
                                    import base64
                                    raw = base64.b64decode(part.inline_data.data)
                                    # Try to parse as JSON first
                                    try:
                                        parsed = json.loads(raw)
                                        text_pieces.append(json.dumps(parsed, ensure_ascii=False))
                                        logger.debug(f"Found inline JSON in candidate[{idx}].part[{part_idx}]")
                                    except:
                                        decoded = raw.decode("utf-8", errors="ignore")
                                        text_pieces.append(decoded)
                                        logger.debug(f"Found inline text in candidate[{idx}].part[{part_idx}]")
                                except Exception as e:
                                    logger.debug(f"Could not decode inline_data: {e}")
                else:
                    # Candidate has no parts - check for finish_reason
                    if hasattr(candidate, "finish_reason"):
                        logger.debug(f"Candidate[{idx}] has no parts, finish_reason: {candidate.finish_reason}")
        
        # If we got text from candidates, return it
        if text_pieces:
            return "\n".join(text_pieces)
        
        # Fallback to resp.text property (may raise ValueError)
        if hasattr(resp, "text"):
            try:
                return resp.text
            except ValueError as e:
                # Handle safety filters or empty response
                logger.warning(f"Could not extract text via .text property: {e}")
                
                # Log detailed response structure for debugging
                if hasattr(resp, "candidates") and resp.candidates:
                    for idx, cand in enumerate(resp.candidates):
                        if hasattr(cand, "finish_reason"):
                            logger.debug(f"Candidate[{idx}] finish_reason: {cand.finish_reason}")
                        if hasattr(cand, "safety_ratings"):
                            logger.debug(f"Candidate[{idx}] has safety_ratings")
                
    except Exception as e:
        logger.warning(f"Error extracting text from response: {e}")
        # Compact audit dump
        try:
            import json
            audit = {
                "has_candidates": hasattr(resp, "candidates"),
                "num_candidates": len(resp.candidates) if hasattr(resp, "candidates") else 0,
                "has_text": hasattr(resp, "text"),
                "error": str(e)
            }
            logger.debug(f"Extraction audit: {json.dumps(audit)}")
        except:
            pass
    
    return ""

def _sha256_text(text: str) -> str:
    """Generate SHA256 hash of text for attestation."""
    return hashlib.sha256(text.encode()).hexdigest()

def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Remove SDK objects from metadata to prevent serialization issues."""
    clean_metadata = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            clean_metadata[key] = value
        elif isinstance(value, dict):
            clean_metadata[key] = _sanitize_metadata(value)
        elif isinstance(value, list):
            # Deep-sanitize lists: recursively clean nested dicts
            clean_list = []
            for item in value:
                if isinstance(item, (str, int, float, bool, type(None))):
                    clean_list.append(item)
                elif isinstance(item, dict):
                    # Recursively sanitize nested dict
                    clean_list.append(_sanitize_metadata(item))
                elif isinstance(item, list):
                    # Handle nested lists recursively
                    clean_list.append(_sanitize_list(item))
                # Skip SDK objects
            clean_metadata[key] = clean_list
        # Skip SDK objects like Tool, FunctionTool, GoogleSearch, etc.
    return clean_metadata

def _sanitize_list(items: list) -> list:
    """Helper to recursively sanitize lists"""
    clean_list = []
    for item in items:
        if isinstance(item, (str, int, float, bool, type(None))):
            clean_list.append(item)
        elif isinstance(item, dict):
            clean_list.append(_sanitize_metadata(item))
        elif isinstance(item, list):
            clean_list.append(_sanitize_list(item))
        # Skip SDK objects
    return clean_list

def _extract_vertex_citations_old(resp: Any) -> list:
    """
    [DEPRECATED - kept for reference only]
    Old Vertex citation extractor.
    """
    out = []
    try:
        rank = 1
        # 1) SDK typed path - try multiple attribute names
        if hasattr(resp, "candidates") and resp.candidates:
            cand = resp.candidates[0]
            meta = getattr(cand, "grounding_metadata", None)
            
            # Try standard grounding_attributions first
            atts = getattr(meta, "grounding_attributions", None)
            if atts:
                for a in atts:
                    # Different SDKs may expose .web.uri or .uri directly
                    url = None
                    if hasattr(a, "web") and hasattr(a.web, "uri"):
                        url = a.web.uri
                    elif hasattr(a, "uri"):
                        url = a.uri
                    
                    title = getattr(a, "title", None)
                    snippet = getattr(a, "snippet", None) or getattr(a, "passage", None)
                    
                    if url:
                        out.append({
                            "provider": "vertex",
                            "url": url,
                            "title": title,
                            "snippet": snippet,
                            "source_type": "google_search",
                            "rank": rank
                        })
                        rank += 1
            
            # Try grounding_chunks if grounding_attributions wasn't found
            if not out:
                chunks = getattr(meta, "grounding_chunks", None)
                if chunks:
                    for chunk in chunks:
                        # Extract URL from various possible locations
                        url = None
                        if hasattr(chunk, "web") and hasattr(chunk.web, "uri"):
                            url = chunk.web.uri
                        elif hasattr(chunk, "web") and hasattr(chunk.web, "url"):
                            url = chunk.web.url
                        elif hasattr(chunk, "reference") and hasattr(chunk.reference, "url"):
                            url = chunk.reference.url
                        elif hasattr(chunk, "source") and hasattr(chunk.source, "url"):
                            url = chunk.source.url
                        elif hasattr(chunk, "uri"):
                            url = chunk.uri
                        elif hasattr(chunk, "url"):
                            url = chunk.url
                        
                        title = getattr(chunk, "title", None)
                        snippet = getattr(chunk, "snippet", None) or getattr(chunk, "text", None) or getattr(chunk, "content", None)
                        
                        if url:
                            citation = {
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            }
                            
                            # Extract actual domain from title if it looks like a domain
                            if title and '.' in title:
                                # Title appears to be a domain (e.g., "consensus.app", "nih.gov", "webmd.com")
                                # Even if it has extra text, try to extract the domain part
                                domain_match = re.match(r'^([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)', title)
                                if domain_match:
                                    citation["source_domain"] = domain_match.group(1)
                            
                            out.append(citation)
                            rank += 1
            
            # Try grounding_supports if no citations found yet
            if not out:
                supports = getattr(meta, "grounding_supports", None)
                if supports:
                    for support in supports:
                        # Extract URL from various possible locations
                        url = None
                        if hasattr(support, "web") and hasattr(support.web, "uri"):
                            url = support.web.uri
                        elif hasattr(support, "web") and hasattr(support.web, "url"):
                            url = support.web.url
                        elif hasattr(support, "reference") and hasattr(support.reference, "url"):
                            url = support.reference.url
                        elif hasattr(support, "source") and hasattr(support.source, "url"):
                            url = support.source.url
                        elif hasattr(support, "uri"):
                            url = support.uri
                        elif hasattr(support, "url"):
                            url = support.url
                        
                        title = getattr(support, "title", None)
                        snippet = getattr(support, "snippet", None) or getattr(support, "text", None) or getattr(support, "content", None)
                        
                        if url:
                            citation = {
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            }
                            
                            # Extract actual domain from title if it looks like a domain
                            if title and '.' in title:
                                # Title appears to be a domain (e.g., "consensus.app", "nih.gov", "webmd.com")
                                # Even if it has extra text, try to extract the domain part
                                domain_match = re.match(r'^([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)', title)
                                if domain_match:
                                    citation["source_domain"] = domain_match.group(1)
                            
                            out.append(citation)
                            rank += 1
        
        # 2) Dict/camelCase path (google-genai model_dump)
        if hasattr(resp, "model_dump") and not out:  # Only if SDK path didn't find citations
            d = resp.model_dump()
            cands = d.get("candidates") or []
            if cands:
                # Try both camelCase and snake_case
                gm = cands[0].get("groundingMetadata") or cands[0].get("grounding_metadata") or {}
                atts = gm.get("groundingAttributions") or gm.get("grounding_attributions") or []
                for a in atts:
                    web = a.get("web") or {}
                    url = web.get("uri") or a.get("uri")
                    title = a.get("title")
                    snippet = a.get("snippet") or a.get("passage")
                    if url:
                        out.append({
                            "provider": "vertex",
                            "url": url,
                            "title": title,
                            "snippet": snippet,
                            "source_type": "google_search",
                            "rank": rank
                        })
                        rank += 1
                
                # Also check for grounding_chunks and grounding_supports in dict format
                if not out:
                    # Try grounding_chunks
                    chunks = gm.get("groundingChunks") or gm.get("grounding_chunks") or []
                    for chunk in chunks:
                        web = chunk.get("web") or {}
                        url = (web.get("uri") or web.get("url") or 
                               chunk.get("uri") or chunk.get("url") or
                               (chunk.get("reference") or {}).get("url") or
                               (chunk.get("source") or {}).get("url"))
                        
                        title = chunk.get("title")
                        snippet = chunk.get("snippet") or chunk.get("text") or chunk.get("content")
                        
                        if url:
                            citation = {
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            }
                            
                            # Extract actual domain from title if it looks like a domain
                            if title and '.' in title:
                                # Title appears to be a domain (e.g., "consensus.app", "nih.gov", "webmd.com")
                                # Even if it has extra text, try to extract the domain part
                                domain_match = re.match(r'^([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)', title)
                                if domain_match:
                                    citation["source_domain"] = domain_match.group(1)
                            
                            out.append(citation)
                            rank += 1
                
                # Try grounding_supports if still no citations
                if not out:
                    supports = gm.get("groundingSupports") or gm.get("grounding_supports") or []
                    for support in supports:
                        web = support.get("web") or {}
                        url = (web.get("uri") or web.get("url") or 
                               support.get("uri") or support.get("url") or
                               support.get("pageUrl") or support.get("sourceUrl") or
                               (support.get("reference") or {}).get("url") or
                               (support.get("source") or {}).get("url"))
                        
                        title = support.get("title")
                        snippet = support.get("snippet") or support.get("text") or support.get("content")
                        
                        if url:
                            citation = {
                                "provider": "vertex",
                                "url": url,
                                "title": title,
                                "snippet": snippet,
                                "source_type": "google_search",
                                "rank": rank
                            }
                            
                            # Extract actual domain from title if it looks like a domain
                            if title and '.' in title:
                                # Title appears to be a domain (e.g., "consensus.app", "nih.gov", "webmd.com")
                                # Even if it has extra text, try to extract the domain part
                                domain_match = re.match(r'^([a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+)', title)
                                if domain_match:
                                    citation["source_domain"] = domain_match.group(1)
                            
                            out.append(citation)
                            rank += 1
    except Exception as e:
        logger.debug(f"Error extracting Vertex citations: {e}")
    return out

def _make_google_search_tool():
    """Create GoogleSearch tool using google-genai SDK for API v1 compatibility."""
    try:
        # Use google-genai SDK which supports the new google_search field
        from google.genai import types
        return types.Tool(google_search=types.GoogleSearch())
    except ImportError:
        logger.warning("google-genai SDK not available, falling back to deprecated method")
        # Fall back to old SDK (will likely fail with API v1)
        try:
            return Tool.from_google_search_retrieval(
                grounding.GoogleSearchRetrieval()
            )
        except TypeError:
            return Tool.from_google_search_retrieval(
                google_search_retrieval=grounding.GoogleSearchRetrieval()
            )

class VertexAdapter:
    """
    Vertex AI adapter using ONLY publishers/google/models/gemini-2.5-pro.
    Implements two-step grounded JSON policy.
    """
    
    def __init__(self):
        """Initialize Vertex AI with project and location."""
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("VERTEX_PROJECT_ID"))
        self.location = os.getenv("VERTEX_LOCATION", "europe-west4")
        
        if not self.project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT or VERTEX_PROJECT_ID required - set in backend/.env"
            )
        
        # Initialize Vertex AI
        vertexai.init(project=self.project, location=self.location)
        
        # Initialize google-genai client if available and enabled
        self.use_genai = os.getenv("VERTEX_USE_GENAI_CLIENT", "true").lower() == "true" and GENAI_AVAILABLE
        self.genai_client = None
        
        # Startup check for google-genai availability
        if not GENAI_AVAILABLE:
            logger.warning(
                "[VERTEX_STARTUP] google-genai not available. Grounded requests will fail. "
                "To fix: pip install google-genai>=0.8.3"
            )
        elif os.getenv("VERTEX_USE_GENAI_CLIENT", "true").lower() == "false":
            logger.warning(
                "[VERTEX_STARTUP] google-genai disabled by VERTEX_USE_GENAI_CLIENT=false. "
                "Grounded requests will fail. To fix: unset or set VERTEX_USE_GENAI_CLIENT=true"
            )
        
        if self.use_genai:
            try:
                # Create genai client in Vertex mode
                self.genai_client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location,
                    http_options=genai_types.HttpOptions(api_version="v1")
                )
                logger.info(f"[VERTEX_STARTUP] google-genai client initialized successfully (grounding enabled)")
                logger.info(f"Initialized google-genai client for Vertex (project={self.project}, location={self.location})")
            except Exception as e:
                logger.error(
                    f"[VERTEX_STARTUP] Failed to initialize google-genai client: {e}. "
                    f"Grounded requests will fail."
                )
                self.use_genai = False
        else:
            logger.warning(
                f"[VERTEX_STARTUP] google-genai not initialized. "
                f"GENAI_AVAILABLE={GENAI_AVAILABLE}, VERTEX_USE_GENAI_CLIENT={os.getenv('VERTEX_USE_GENAI_CLIENT', 'true')}. "
                f"Grounded requests will fail with clear error."
            )
        
        # Log SDK version for debugging
        try:
            import google.cloud.aiplatform as aiplat
            sdk_info = f"google-cloud-aiplatform={aiplat.__version__}"
            if self.use_genai:
                sdk_info += f", google-genai={genai.__version__ if hasattr(genai, '__version__') else 'unknown'}"
            logger.info(f"Vertex adapter initialized: project={self.project}, location={self.location}, {sdk_info}")
        except:
            logger.info(f"Vertex adapter initialized: project={self.project}, location={self.location}")
    
    def _build_content_with_als(self, messages: List[Dict], als_block: str = None) -> tuple[str, List[gm.Content]]:
        """
        Build Vertex Content objects from messages.
        Returns (system_instruction, contents).
        Keeps system separate, ALS goes in first user message.
        Order: system → ALS → user (ALS is in user message, not system).
        """
        contents = []
        system_text = None
        user_texts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            
            if not text:
                continue
            
            if role == "system":
                # Keep system text separate for system_instruction
                if system_text is None:
                    system_text = text
                else:
                    system_text = f"{system_text}\n\n{text}"
            elif role == "user":
                # For first user message, prepend ALS if provided
                if als_block and not user_texts and not contents:
                    # ALS goes BEFORE user content in the user message
                    user_texts.append(als_block)
                user_texts.append(text)
            elif role == "assistant":
                # First, add any accumulated user text
                if user_texts:
                    user_part = gm.Part.from_text("\n\n".join(user_texts))
                    user_content = gm.Content(role="user", parts=[user_part])
                    contents.append(user_content)
                    user_texts = []
                
                # Then add assistant message as model role
                assistant_part = gm.Part.from_text(text)
                assistant_content = gm.Content(role="model", parts=[assistant_part])
                contents.append(assistant_content)
        
        # Add any remaining user text
        if user_texts:
            user_part = gm.Part.from_text("\n\n".join(user_texts))
            user_content = gm.Content(role="user", parts=[user_part])
            contents.append(user_content)
        
        return system_text, contents
    
    def _create_generation_config_step1(self, req: LLMRequest) -> gm.GenerationConfig:
        """Create generation config for Step 1 (grounded or ungrounded, NO JSON)."""
        # For ungrounded requests, ensure minimum tokens to avoid empty responses
        # Vertex doesn't return partial content when hitting MAX_TOKENS
        requested_tokens = getattr(req, "max_tokens", 6000)
        is_grounded = getattr(req, "grounded", False)
        
        # For ungrounded: increase minimum tokens to avoid empty responses
        if not is_grounded:
            # Increase minimum to 1500 for news-style prompts (more verbose)
            if requested_tokens < 1500:
                logger.warning(f"Increasing max_tokens from {requested_tokens} to 1500 for Vertex ungrounded (avoids empty responses)")
                max_tokens = 1500
            else:
                max_tokens = requested_tokens
        else:
            max_tokens = requested_tokens
            
        config_dict = {
            "temperature": getattr(req, "temperature", 0.7),
            "top_p": getattr(req, "top_p", 0.95),
            "max_output_tokens": max_tokens,
        }
        
        # For ungrounded: slightly reduce temperature for stability, but DON'T force text/plain on first attempt
        if not is_grounded:
            # Only slightly reduce temperature for more stable ungrounded generation
            if config_dict["temperature"] > 0.5:
                config_dict["temperature"] = max(0.5, config_dict["temperature"] - 0.2)
                logger.debug(f"Reduced temperature to {config_dict['temperature']} for ungrounded stability")
            # DON'T set response_mime_type here - only use it in retry
        # For grounded: NO response_mime_type - we want prose with citations
        
        return gm.GenerationConfig(**config_dict)
    
    def _create_generation_config_step2_json(self) -> gm.GenerationConfig:
        """Create generation config for Step 2 (JSON reshape, NO tools)."""
        return gm.GenerationConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json"  # JSON only in Step 2
        )
    
    async def _step1_grounded(self, model: gm.GenerativeModel, contents: List[gm.Content], 
                             generation_config: gm.GenerationConfig, timeout: int, 
                             mode: str = "AUTO") -> tuple[Any, bool, int]:
        """
        Step 1: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Create GoogleSearch tool for grounding (Step-1 ONLY)
        # Use version-tolerant helper
        tools = [_make_google_search_tool()]
        
        # [WIRE_DEBUG] Log what we're sending
        logger.debug(f"[WIRE_DEBUG] Vertex Step-1 grounded call:")
        logger.debug(f"  Tool class: {type(tools[0])}")
        logger.debug("  Using: Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())")
        logger.debug(f"  Mode: {mode}")
        logger.debug(f"  Generation config has JSON mime: {hasattr(generation_config, 'response_mime_type')}")
        
        # Add tool_config for REQUIRED mode
        tool_config = None
        if mode == "REQUIRED":
            # Try to import ToolConfig from vertexai
            try:
                from vertexai.generative_models import ToolConfig
                # For REQUIRED mode, we need to enforce at least one tool call
                tool_config = ToolConfig(
                    function_calling_config=ToolConfig.FunctionCallingConfig(
                        mode=ToolConfig.FunctionCallingConfig.Mode.ANY
                    )
                )
            except ImportError:
                # Fallback if ToolConfig not available
                logger.warning("ToolConfig not available in vertexai SDK, REQUIRED mode may not enforce tool calls")
        
        try:
            call_kwargs = {
                "contents": contents,
                "generation_config": generation_config,
                "tools": tools
            }
            if tool_config:
                call_kwargs["tool_config"] = tool_config
                
            response = await asyncio.wait_for(
                _call_vertex_model(model, **call_kwargs),
                timeout=timeout
            )
            
            # Check if grounding was actually used
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
            # Count tool calls (grounding citations)
            tool_call_count = 0
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "grounding_metadata"):
                    meta = candidate.grounding_metadata
                    if hasattr(meta, "grounding_attributions"):
                        tool_call_count = len(meta.grounding_attributions)
            
            # REQUIRED mode enforcement
            if mode == "REQUIRED" and not grounded_effective:
                raise GroundingRequiredError(
                    f"No Vertex grounding evidence found (mode=REQUIRED). "
                    f"tool_call_count={tool_call_count}"
                )
            
            return response, grounded_effective, grounding_count
            
        except asyncio.TimeoutError:
            raise
        except GroundingRequiredError:
            raise
        except Exception as e:
            logger.error(f"Step 1 grounded generation failed: {e}")
            raise
    
    async def _step2_reshape_json(self, model: gm.GenerativeModel, step1_text: str, 
                                  original_request: str, timeout: int) -> tuple[Any, Dict]:
        """
        Step 2: Reshape to JSON without tools.
        Returns (response, attestation).
        """
        # Build reshape prompt
        reshape_prompt = f"""Based on this grounded answer, provide a structured JSON response.

Original Question: {original_request}

Grounded Answer: {step1_text}

Provide your response as valid JSON with appropriate keys for the information."""
        
        # Create content for reshape - single user message
        reshape_part = gm.Part.from_text(reshape_prompt)
        reshape_content = gm.Content(role="user", parts=[reshape_part])
        
        # JSON config for Step 2
        json_config = self._create_generation_config_step2_json()
        
        # [WIRE_DEBUG] Log Step-2 config
        logger.debug(f"[WIRE_DEBUG] Vertex Step-2 JSON reshape:")
        logger.debug(f"  Tools: None (enforced)")
        logger.debug(f"  Response mime type: application/json")
        logger.debug(f"  Temperature: {json_config.temperature if hasattr(json_config, 'temperature') else 'default'}")
        
        try:
            # Step 2 MUST have NO tools
            response = await asyncio.wait_for(
                _call_vertex_model(
                    model,
                    contents=[reshape_content],
                    generation_config=json_config,
                    tools=None  # NO TOOLS in step 2 - enforced
                ),
                timeout=timeout
            )
            
            # Verify no tools were invoked (they shouldn't be since we passed None)
            tools_invoked = False
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "function_calls") and candidate.function_calls:
                    tools_invoked = True
                    logger.error("VIOLATION: Tools invoked in Step 2 (should be impossible)")
            
            # Create attestation
            attestation = {
                "step2_tools_invoked": tools_invoked,  # Must be false
                "step2_source_ref": _sha256_text(step1_text)
            }
            
            return response, attestation
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"Step 2 JSON reshape failed: {e}")
            raise
    
    async def _step1_grounded_genai(self, req: LLMRequest, contents: List[gm.Content], 
                                    generation_config: gm.GenerationConfig, timeout: int, 
                                    mode: str = "AUTO", system_instruction: str = None) -> tuple[Any, bool, int]:
        """
        Step 1 using google-genai: Generate grounded response with GoogleSearch tool.
        Returns (response, grounded_effective, tool_call_count).
        """
        # Build messages in genai format - use passed system_instruction
        combined_text = []
        
        for content in contents:
            text = content.parts[0].text if content.parts else ""
            if text:
                combined_text.append(text)
        
        # Create genai contents format with parts
        final_text = "\n\n".join(combined_text)
        contents_genai = [{"role": "user", "parts": [{"text": final_text}]}]
        
        # Create GoogleSearch tool using genai
        tools = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
        
        # Create generation config
        # Map our mode to SDK mode: REQUIRED -> ANY (at least one tool call), AUTO -> AUTO
        sdk_mode = "ANY" if mode == "REQUIRED" else "AUTO"
        config_params = {
            "temperature": generation_config.temperature if hasattr(generation_config, 'temperature') else 0.7,
            "top_p": generation_config.top_p if hasattr(generation_config, 'top_p') else 0.95,
            "max_output_tokens": generation_config.max_output_tokens if hasattr(generation_config, 'max_output_tokens') else 6000,
            "tools": tools,
            "tool_config": genai_types.ToolConfig(function_calling_config={"mode": sdk_mode})
        }
        
        # Add system instruction to config if available
        if system_instruction:
            config_params["system_instruction"] = system_instruction
            
        # DO NOT use response_mime_type='text/plain' for grounded - it strips citations!
        config = genai_types.GenerateContentConfig(**config_params)
        
        # Wire debug logging
        logger.debug(f"[GENAI] Step-1 grounded call:")
        logger.debug(f"  contents[0].keys(): {list(contents_genai[0].keys())}")
        logger.debug(f"  contents[0].role: {contents_genai[0]['role']}")
        logger.debug(f"  len(contents[0].parts): {len(contents_genai[0]['parts'])}")
        logger.debug(f"  text preview: {final_text[:120]}...")
        logger.debug(f"  tools: {[type(t).__name__ for t in tools]}")
        logger.debug(f"  system_instruction length: {len(system_instruction) if system_instruction else 0}")
        
        try:
            # Use genai client to generate
            response = await asyncio.wait_for(
                self.genai_client.aio.models.generate_content(
                    model=req.model,
                    contents=contents_genai,
                    config=config
                ),
                timeout=timeout
            )
            
            # Check if grounding was actually used - use existing detector for genai responses
            grounded_effective, grounding_count = detect_vertex_grounding(response)
            
            logger.debug(f"[GENAI] Step-1 grounding detection: used={grounded_effective}, count={grounding_count}")
            
            # REQUIRED mode enforcement
            if mode == "REQUIRED" and not grounded_effective:
                raise GroundingRequiredError(
                    f"No grounding evidence found (mode=REQUIRED). "
                    f"tool_call_count={grounding_count}"
                )
            
            return response, grounded_effective, grounding_count
            
        except asyncio.TimeoutError:
            raise
        except GroundingRequiredError:
            raise
        except Exception as e:
            logger.error(f"[GENAI] Step 1 grounded generation failed: {e}")
            raise
    
    async def _step2_reshape_json_genai(self, req: LLMRequest, step1_text: str, 
                                        original_request: str, timeout: int) -> tuple[Any, Dict]:
        """
        Step 2 using google-genai: Reshape to JSON without tools.
        Returns (response, attestation).
        """
        # Build reshape prompt
        reshape_prompt = f"""Based on this grounded answer, provide a structured JSON response.

Original Question: {original_request}

Grounded Answer: {step1_text}

Provide your response as valid JSON with appropriate keys for the information."""
        
        contents_genai = [{"role": "user", "parts": [{"text": reshape_prompt}]}]
        
        # JSON config for Step 2 - EXPLICITLY NO TOOLS
        config = genai_types.GenerateContentConfig(
            temperature=0.1,  # Low temp for consistent JSON
            max_output_tokens=6000,
            response_mime_type="application/json",
            tools=[]  # Explicitly empty tools list
        )
        
        logger.debug(f"[GENAI] Step-2 JSON reshape:")
        logger.debug(f"  tools explicitly set to: []")
        logger.debug(f"  response_mime_type: application/json")
        
        try:
            response = await asyncio.wait_for(
                self.genai_client.aio.models.generate_content(
                    model=req.model,
                    contents=contents_genai,
                    config=config
                ),
                timeout=timeout
            )
            
            # Verify no tools were invoked using existing detector
            tools_invoked_result, tool_count = detect_vertex_grounding(response)
            tools_invoked = tools_invoked_result  # Should be False for Step-2
            
            if tools_invoked:
                logger.error(f"[GENAI] VIOLATION: Tools invoked in Step 2 (count={tool_count})")
            else:
                logger.debug(f"[GENAI] Step-2 verification: no tools invoked (as expected)")
            
            # Create attestation
            attestation = {
                "step2_tools_invoked": tools_invoked,  # Must be false
                "step2_source_ref": _sha256_text(step1_text)
            }
            
            return response, attestation
            
        except asyncio.TimeoutError:
            raise
        except Exception as e:
            logger.error(f"[GENAI] Step 2 JSON reshape failed: {e}")
            raise
    
    async def complete(self, req: LLMRequest, timeout: int = 60) -> LLMResponse:
        """
        Complete request using Vertex AI with Gemini 2.5-pro ONLY.
        Implements two-step grounded JSON policy when needed.
        """
        t0 = time.perf_counter()
        
        # Use the requested model (already validated in orchestrator)
        model_id = req.model
        logger.info(f"Using requested model: {model_id}")
        
        # Double-check validation (belt and suspenders)
        is_valid, error_msg = validate_model("vertex", model_id)
        if not is_valid:
            raise ValueError(f"MODEL_NOT_ALLOWED: {error_msg}")
        
        # Initialize metadata with feature flags
        metadata = {
            "model": model_id,
            "response_api": "vertex_genai",
            "provider_api_version": "vertex:genai-v1",
            "region": os.getenv("VERTEX_LOCATION", "europe-west4"),  # Match init default
            "proxies_enabled": False,
            "proxy_mode": "disabled",
            "vantage_policy": str(getattr(req, "vantage_policy", "NONE")),
            # Feature flags for monitoring
            "feature_flags": {
                "citation_extractor_v2": settings.citation_extractor_v2,
                "citation_extractor_enable_legacy": settings.citation_extractor_enable_legacy,
                "ungrounded_retry_policy": settings.ungrounded_retry_policy,
                "text_harvest_auto_only": settings.text_harvest_auto_only,
                "citations_extractor_enable": settings.citations_extractor_enable,
            }
        }
        
        # Extract ALS block if present (should be in messages already)
        als_block = None
        # ALS is handled at template_runner level, included in messages
        
        # Build contents and extract system instruction
        # Returns (system_text, contents) - system separate, ALS in user message
        system_instruction, contents = self._build_content_with_als(req.messages, als_block)
        
        # Create model with system_instruction if present
        if system_instruction:
            model = gm.GenerativeModel(model_id, system_instruction=system_instruction)
            logger.debug(f"Using system_instruction: {len(system_instruction)} chars")
        else:
            model = gm.GenerativeModel(model_id)
        
        # Check if JSON mode is needed
        is_json_mode = getattr(req, "json_mode", False)
        is_grounded = getattr(req, "grounded", False)
        
        # Extract grounding mode (AUTO or REQUIRED)
        grounding_mode = getattr(req, "grounding_mode", "AUTO")
        if hasattr(req, "meta") and isinstance(req.meta, dict):
            grounding_mode = req.meta.get("grounding_mode", grounding_mode)
        # Surface requested mode for QA/telemetry parity
        metadata["grounding_mode_requested"] = grounding_mode
        
        # Allow SDK fallback for grounded requests (Priority 1 fix)
        # Log warning but don't block - the SDK path may work
        if is_grounded and not self.use_genai:
            logger.warning(
                f"[VERTEX_GROUNDING] Using SDK fallback for grounded request. "
                f"google-genai not available (GENAI_AVAILABLE={GENAI_AVAILABLE}). "
                f"This may have limited functionality compared to google-genai client."
            )
        
        # Determine two-step requirement
        needs_two_step = is_grounded and is_json_mode
        
        if needs_two_step:
            logger.info(f"Two-step grounded JSON mode activated (mode={grounding_mode})")
            logger.debug(f"[VERTEX_GROUNDING] Attempting two-step grounded JSON: model={req.model}, mode={grounding_mode}")
            
            # Step 1: Grounded generation (NO JSON)
            generation_config = self._create_generation_config_step1(req)
            if self.use_genai and self.genai_client:
                logger.debug(f"[VERTEX_GROUNDING] Using genai client for Step 1 grounding")
                step1_resp, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                    req, contents, generation_config, timeout, mode=grounding_mode, 
                    system_instruction=system_instruction
                )
            else:
                logger.debug(f"[VERTEX_GROUNDING] Using vertex SDK for Step 1 grounding")
                step1_resp, grounded_effective, tool_call_count = await self._step1_grounded(
                    model, contents, generation_config, timeout, mode=grounding_mode
                )
            
            logger.debug(f"[VERTEX_GROUNDING] Step 1 complete: grounded_effective={grounded_effective}, "
                        f"tool_calls={tool_call_count}")
            
            # Citations from Step-1 with A/B selection
            # Extract stable identifiers from request metadata
            tenant_id = None
            account_id = None
            template_id = None
            if hasattr(req, "meta") and isinstance(req.meta, dict):
                tenant_id = req.meta.get("tenant_id")
                account_id = req.meta.get("account_id")
                template_id = req.meta.get("template_id")
            
            step1_citations, citation_telemetry = _select_and_extract_citations(
                step1_resp, tenant_id=tenant_id, account_id=account_id, template_id=template_id
            )
            metadata.update(citation_telemetry)
            step1_text = _extract_text_from_candidates(step1_resp)
            
            # Step 2: Reshape to JSON (NO TOOLS)
            # Get the last USER message (not just last message which could be assistant)
            original_request = ""
            for msg in reversed(req.messages):
                if msg.get("role") == "user":
                    original_request = msg.get("content", "")
                    break
            logger.debug(f"[VERTEX_GROUNDING] Starting Step 2 JSON reshape")
            if self.use_genai and self.genai_client:
                step2_resp, attestation = await self._step2_reshape_json_genai(
                    req, step1_text, original_request, timeout
                )
            else:
                step2_resp, attestation = await self._step2_reshape_json(
                    model, step1_text, original_request, timeout
                )
            logger.debug(f"[VERTEX_GROUNDING] Step 2 complete: tools_invoked={attestation.get('step2_tools_invoked', False)}")
            
            # Use step2 response as final
            response = step2_resp
            text = _extract_text_from_candidates(step2_resp)
            
            # Update metadata
            metadata["two_step_used"] = True
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_call_count
            metadata.update(attestation)
            if step1_citations:
                metadata["citations"] = step1_citations
            else:
                # Forensic audit when tools were used but no citations found
                if metadata.get("tool_call_count", 0) > 0:
                    metadata["citations_status_reason"] = "citations_missing_despite_tool_calls"
                    audit = _audit_grounding_metadata(step1_resp)
                    metadata["citations_audit"] = audit
                    
                    # Structured log for easy grep
                    structured_log = {
                        "vendor": "vertex",
                        "tool_calls": tool_call_count,
                        "citations": 0,
                        "keys": audit.get("grounding_metadata_keys", []),
                        "citations_status_reason": "citations_missing_despite_tool_calls"
                    }
                    logger.info(f"[VERTEX_CITATION_AUDIT] {json.dumps(structured_log)}")
            
        elif is_grounded:
            # Single-step grounded (non-JSON)
            logger.debug(f"[VERTEX_GROUNDING] Attempting single-step grounding: model={req.model}, mode={grounding_mode}")
            generation_config = self._create_generation_config_step1(req)
            if self.use_genai and self.genai_client:
                logger.debug(f"[VERTEX_GROUNDING] Using genai client for single-step grounding")
                response, grounded_effective, tool_call_count = await self._step1_grounded_genai(
                    req, contents, generation_config, timeout, mode=grounding_mode,
                    system_instruction=system_instruction
                )
            else:
                logger.debug(f"[VERTEX_GROUNDING] Using vertex SDK for single-step grounding")
                response, grounded_effective, tool_call_count = await self._step1_grounded(
                    model, contents, generation_config, timeout, mode=grounding_mode
                )
            
            logger.debug(f"[VERTEX_GROUNDING] Single-step complete: grounded_effective={grounded_effective}, "
                        f"tool_calls={tool_call_count}")
            
            text = _extract_text_from_candidates(response)
            metadata["grounded_effective"] = grounded_effective
            metadata["tool_call_count"] = tool_call_count
            
            # Citations from Step-1 with A/B selection
            try:
                # Extract stable identifiers from request metadata
                tenant_id = None
                account_id = None
                template_id = None
                if hasattr(req, "meta") and isinstance(req.meta, dict):
                    tenant_id = req.meta.get("tenant_id")
                    account_id = req.meta.get("account_id")
                    template_id = req.meta.get("template_id")
                
                cits, citation_telemetry = _select_and_extract_citations(
                    response, tenant_id=tenant_id, account_id=account_id, template_id=template_id
                )
                metadata.update(citation_telemetry)
                if cits:
                    metadata["citations"] = cits
                else:
                    # Forensic audit when tools were used but no citations found
                    if metadata.get("tool_call_count", 0) > 0:
                        metadata["citations_status_reason"] = "citations_missing_despite_tool_calls"
                        audit = _audit_grounding_metadata(response)
                        metadata["citations_audit"] = audit
                        
                        # Structured log for easy grep
                        structured_log = {
                            "vendor": "vertex",
                            "tool_calls": tool_call_count,
                            "citations": 0,
                            "keys": audit.get("grounding_metadata_keys", []),
                            "citations_status_reason": "citations_missing_despite_tool_calls"
                        }
                        logger.info(f"[VERTEX_CITATION_AUDIT] {json.dumps(structured_log)}")
            except Exception:
                pass
            
            # Add finish_reason for grounded responses too
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, "finish_reason"):
                    metadata["finish_reason"] = str(candidate.finish_reason)
            
        else:
            # Regular generation (no grounding, may have JSON)
            logger.debug(f"[VERTEX_GROUNDING] Ungrounded request: model={req.model}, json_mode={is_json_mode}")
            if is_json_mode:
                generation_config = self._create_generation_config_step2_json()
                max_tokens_used = 6000  # JSON mode uses fixed 6000
                first_attempt_max_tokens = 6000  # Track for consistency, though JSON doesn't retry
            else:
                generation_config = self._create_generation_config_step1(req)
                # Track both original and actual tokens for retry logic
                requested_tokens = getattr(req, "max_tokens", 6000)
                first_attempt_max_tokens = requested_tokens  # Keep original for retry calculation
                max_tokens_used = max(requested_tokens, 500) if requested_tokens < 500 else requested_tokens
            
            # First attempt with normal settings
            try:
                response = await asyncio.wait_for(
                    _call_vertex_model(
                        model,
                        contents=contents,
                        generation_config=generation_config,
                        tools=None  # No tools for ungrounded
                    ),
                    timeout=timeout
                )
                text = _extract_text_from_candidates(response)
                metadata["grounded_effective"] = False
                metadata["tool_call_count"] = 0
                
                # Check if we need to retry
                should_retry = False
                retry_reason = ""
                
                # Get token count and finish reason
                candidates_token_count = 0
                if hasattr(response, "usage_metadata"):
                    candidates_token_count = getattr(response.usage_metadata, "candidates_token_count", 0)
                
                finish_reason = None
                if hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, "finish_reason"):
                        finish_reason = candidate.finish_reason
                
                # Determine if retry is needed
                if not text:
                    should_retry = True
                    retry_reason = "empty_text"
                elif candidates_token_count == 0:
                    should_retry = True
                    retry_reason = "zero_tokens"
                elif finish_reason and (str(finish_reason) == "2" or 
                                       finish_reason == 2 or
                                       "MAX_TOKENS" in str(finish_reason)):
                    should_retry = True
                    retry_reason = f"max_tokens_hit (finish_reason={finish_reason})"
                
                # Perform retry if needed (SDK-only, no JSON mode, and policy allows)
                retry_allowed = settings.ungrounded_retry_policy in ["aggressive", "conservative"]
                if should_retry and not is_json_mode and retry_allowed:
                    logger.info(f"Retrying Vertex ungrounded due to: {retry_reason}")
                    metadata["retry_attempted"] = True
                    metadata["retry_reason"] = retry_reason
                    
                    # Create retry config with text/plain and increased tokens
                    # Use request temperature, slightly reduced
                    original_temp = getattr(req, "temperature", 0.7)
                    retry_temp = min(original_temp * 0.9, 0.6)  # Slight reduction, but stay user-like
                    
                    # Fix: Use original tokens for retry calculation, ensure retry >= first attempt
                    # Cap at model max (8192) to prevent infinite MAX_TOKENS loops
                    model_max = 8192
                    retry_max_tokens = min(
                        max(int((first_attempt_max_tokens or 1500) * 2), 3000, max_tokens_used),
                        model_max
                    )
                    
                    retry_config = gm.GenerationConfig(
                        temperature=retry_temp,
                        top_p=getattr(req, "top_p", 0.95),
                        max_output_tokens=retry_max_tokens,
                        response_mime_type="text/plain"  # Force single text part
                    )
                    
                    logger.debug(f"Retry config: temp={retry_temp}, max_tokens={retry_max_tokens}, mime=text/plain")
                    
                    try:
                        retry_response = await asyncio.wait_for(
                            _call_vertex_model(
                                model,
                                contents=contents,
                                generation_config=retry_config,
                                tools=None
                            ),
                            timeout=timeout
                        )
                        retry_text = _extract_text_from_candidates(retry_response)
                        
                        if retry_text:
                            text = retry_text
                            response = retry_response  # Use retry response for metadata
                            metadata["retry_successful"] = True
                            logger.info("Retry successful, got text response")
                        else:
                            metadata["retry_successful"] = False
                            logger.warning("Retry still produced empty text")
                            
                    except Exception as retry_error:
                        logger.error(f"Retry failed: {retry_error}")
                        metadata["retry_error"] = str(retry_error)
                        metadata["retry_successful"] = False
                
            except asyncio.TimeoutError:
                elapsed = time.perf_counter() - t0
                logger.error(f"Vertex timeout after {elapsed:.2f}s")
                raise
        
        # Add finish_reason to metadata if available
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, "finish_reason"):
                metadata["finish_reason"] = str(candidate.finish_reason)
        
        # Extract usage
        usage = _extract_vertex_usage(response)
        
        # Calculate latency
        latency_ms = int((time.perf_counter() - t0) * 1000)
        
        # Add model version if available (Gemini fingerprint)
        if hasattr(response, "_raw_response"):
            raw = response._raw_response
            if hasattr(raw, "model_version"):
                metadata["modelVersion"] = raw.model_version
        elif hasattr(response, "model_version"):
            metadata["modelVersion"] = response.model_version
        
        # Log telemetry
        logger.info(
            f"Vertex completed in {latency_ms}ms, "
            f"grounded={is_grounded}, grounded_effective={metadata.get('grounded_effective', False)}, "
            f"tool_calls={metadata.get('tool_call_count', 0)}, "
            f"usage={usage}"
        )
        
        # Sanitize metadata to remove SDK objects
        clean_metadata = _sanitize_metadata(metadata)
        
        # Extract commonly-read fields for telemetry parity
        grounded_effective_flag = bool(clean_metadata.get("grounded_effective", False))
        
        # Determine success based on content
        success = True
        error_type = None
        why_no_content = None
        
        if not text:
            success = False
            error_type = "EMPTY_COMPLETION"
            
            # Build detailed why_no_content
            reasons = []
            if clean_metadata.get("retry_attempted"):
                reasons.append(f"retry_attempted={clean_metadata.get('retry_successful', False)}")
            if clean_metadata.get("retry_reason"):
                reasons.append(f"retry_reason={clean_metadata['retry_reason']}")
            if clean_metadata.get("finish_reason"):
                reasons.append(f"finish_reason={clean_metadata['finish_reason']}")
            if usage and usage.get("candidates_token_count") == 0:
                reasons.append("candidates_token_count=0")
            
            why_no_content = " | ".join(reasons) if reasons else "extraction_empty_all_parts"
            clean_metadata["error_type"] = error_type
            clean_metadata["why_no_content"] = why_no_content
            
            logger.warning(f"Returning empty response: {why_no_content}")
        
        # Final success/empty evaluation
        success_flag = success  # Keep existing success value
        error_type = clean_metadata.get("error_type", None)
        error_message = None
        
        # Additional check for truly empty ungrounded responses
        if not is_grounded and (not text or not str(text).strip()):
            if success_flag:  # Only override if not already marked as failure
                success_flag = False
                error_type = "EMPTY_COMPLETION"
                # Try to attach a concise reason if available
                try:
                    reason = None
                    if hasattr(response, "candidates") and response.candidates:
                        fr = getattr(response.candidates[0], "finish_reason", None)
                        reason = str(fr) if fr is not None else None
                    meta_reason = "unknown"
                    if usage.get("completion_tokens", 0) == 0:
                        meta_reason = "candidates_token_count=0"
                    clean_metadata.setdefault("why_no_content", reason or meta_reason)
                except Exception:
                    pass
        
        # --- ALS propagation into response metadata ---
        try:
            req_meta = getattr(req, 'metadata', {}) or {}
            if isinstance(req_meta, dict) and req_meta.get('als_present'):
                # copy whitelisted ALS fields
                for k in ('als_present','als_block_sha256','als_variant_id','seed_key_id','als_country','als_locale','als_nfc_length','als_template_id'):
                    if k in req_meta:
                        clean_metadata[k] = req_meta[k]
        except Exception as _:
            pass
        
        return LLMResponse(
            content=text,
            model_version=model_id,
            model_fingerprint=clean_metadata.get("modelVersion"),
            grounded_effective=grounded_effective_flag,
            usage=usage,
            latency_ms=latency_ms,
            raw_response=None,
            success=success_flag,  # truthy empty handling
            vendor="vertex",
            model=model_id,
            metadata=clean_metadata,
            error_type=error_type,
            error_message=error_message
        )