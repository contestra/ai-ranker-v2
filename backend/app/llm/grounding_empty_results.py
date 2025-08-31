"""
Grounding empty results handling
Distinguishes between tool not supported vs tool invoked but returned empty
"""

from typing import Tuple, Any
import logging

logger = logging.getLogger(__name__)


def analyze_openai_grounding(response: Any) -> dict:
    """
    Analyze OpenAI response for grounding status with detailed semantics
    
    Returns dict with:
    - grounding_attempted: bool - Was any web_search tool invoked?
    - grounded_effective: bool - Did we get actual results with citations?
    - tool_call_count: int - Number of tool invocations
    - tool_result_count: int - Number of actual results returned
    - web_search_count: int - Number of web search calls specifically
    - why_not_grounded: str - Precise reason if not effective
    """
    
    result = {
        "grounding_attempted": False,
        "grounded_effective": False,
        "tool_call_count": 0,
        "tool_result_count": 0,
        "web_search_count": 0,
        "web_search_queries": [],  # Actual query text
        "why_not_grounded": None
    }
    
    # Get output items
    output = []
    if hasattr(response, 'model_dump'):
        data = response.model_dump()
        output = data.get('output', [])
    elif isinstance(response, dict):
        output = response.get('output', [])
    
    # Analyze each output item
    has_message = False
    has_citations = False
    
    for item in output:
        if not isinstance(item, dict):
            continue
            
        item_type = item.get('type', '')
        
        # Check for web_search_call (OpenAI specific)
        if item_type == 'web_search_call':
            result['grounding_attempted'] = True
            result['tool_call_count'] += 1
            result['web_search_count'] += 1
            
            # Capture the query text
            action = item.get('action', {})
            if isinstance(action, dict):
                query = action.get('query', '')
                if query:
                    result['web_search_queries'].append(query)
                    logger.debug(f"[GROUNDING] web_search query: '{query}'")
            
            # Check if it has results
            results = item.get('results', [])
            if results:
                # Verify results have essential fields
                valid_results = 0
                for r in results:
                    if isinstance(r, dict) and (r.get('url') or r.get('title')):
                        valid_results += 1
                result['tool_result_count'] += valid_results
                logger.debug(f"[GROUNDING] web_search_call with {valid_results} valid results")
            else:
                logger.debug("[GROUNDING] web_search_call with EMPTY results")
        
        # Check for tool_call (alternative format)
        elif item_type == 'tool_call':
            name = item.get('name', '')
            if 'web' in name.lower() or 'search' in name.lower():
                result['grounding_attempted'] = True
                result['tool_call_count'] += 1
                result['web_search_count'] += 1
                
                # Check for results in the tool response
                if item.get('results'):
                    result['tool_result_count'] += len(item.get('results', []))
        
        # Check for message with citations
        elif item_type == 'message':
            has_message = True
            content = item.get('content', [])
            
            for block in content:
                if isinstance(block, dict):
                    # Check annotations for citations
                    annotations = block.get('annotations', [])
                    for ann in annotations:
                        if isinstance(ann, dict):
                            ann_type = ann.get('type', '')
                            if 'url' in ann_type.lower() or 'citation' in ann_type.lower():
                                has_citations = True
                                result['grounded_effective'] = True
    
    # Determine effectiveness and reason
    if result['grounding_attempted']:
        if result['tool_result_count'] == 0:
            result['why_not_grounded'] = "web_search_empty_results"
            logger.info("[GROUNDING] Attempted but got empty results")
        elif not has_message:
            result['why_not_grounded'] = "no_message_output"
            logger.info("[GROUNDING] Tool had results but no message produced")
        elif not has_citations:
            result['why_not_grounded'] = "no_citations_in_message"
            logger.info("[GROUNDING] Results exist but not cited in message")
        else:
            # Everything worked
            result['grounded_effective'] = True
            logger.info("[GROUNDING] Effective grounding with citations")
    else:
        if not has_message:
            result['why_not_grounded'] = "no_tool_invocation_no_message"
        else:
            result['why_not_grounded'] = "tool_not_invoked"
    
    return result


class GroundingEmptyResultsError(Exception):
    """Raised when grounding was attempted but returned empty results"""
    def __init__(self, message: str = "Grounding attempted but search returned no results"):
        self.message = message
        self.code = "GROUNDING_EMPTY_RESULTS"
        super().__init__(self.message)