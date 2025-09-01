"""
Test helpers for Vertex adapter testing.
Provides consistent response mocks for different scenarios.
"""

from unittest.mock import Mock
from typing import Dict, List, Optional, Any


def create_vertex_response(
    dict_data: Optional[Dict] = None,
    typed_candidates: Optional[List] = None,
    has_grounding_metadata: bool = False,
    has_citation_metadata: bool = False,
    metadata_values: Optional[Dict] = None
) -> Mock:
    """
    Create a consistent Vertex response mock for testing.
    
    Args:
        dict_data: Full response dict (for model_dump)
        typed_candidates: List of typed candidate objects
        has_grounding_metadata: Whether typed candidates have grounding_metadata
        has_citation_metadata: Whether typed candidates have citation_metadata
        metadata_values: Actual metadata values for typed candidates
    
    Returns:
        Mock response object with proper structure
    """
    mock_resp = Mock()
    
    # Set up model_dump if dict_data provided
    if dict_data is not None:
        mock_resp.model_dump = Mock(return_value=dict_data)
    else:
        mock_resp.model_dump = Mock(return_value={'candidates': []})
    
    # Set up typed candidates
    if typed_candidates is not None:
        mock_resp.candidates = typed_candidates
    elif dict_data and not typed_candidates:
        # Dict-only case - empty typed candidates
        mock_resp.candidates = []
    else:
        # Create mock candidates based on flags
        mock_cands = []
        if has_grounding_metadata or has_citation_metadata:
            mock_cand = Mock()
            
            # Set all possible attribute names to None by default
            mock_cand.grounding_metadata = None
            mock_cand.groundingMetadata = None
            mock_cand.citation_metadata = None
            mock_cand.citationMetadata = None
            
            # Set actual values if provided
            if metadata_values:
                if 'grounding_metadata' in metadata_values:
                    mock_cand.grounding_metadata = metadata_values['grounding_metadata']
                if 'groundingMetadata' in metadata_values:
                    mock_cand.groundingMetadata = metadata_values['groundingMetadata']
                if 'citation_metadata' in metadata_values:
                    mock_cand.citation_metadata = metadata_values['citation_metadata']
                if 'citationMetadata' in metadata_values:
                    mock_cand.citationMetadata = metadata_values['citationMetadata']
            
            mock_cands.append(mock_cand)
        
        mock_resp.candidates = mock_cands
    
    return mock_resp


def create_typed_none_dict_data_response(dict_data: Dict) -> Mock:
    """
    Create response with typed candidates that have None metadata,
    but dict view has the data (common with google-genai).
    
    This is the case that was failing before the fix.
    """
    mock_resp = Mock()
    mock_resp.model_dump = Mock(return_value=dict_data)
    
    # Create typed candidate with all None metadata
    mock_cand = Mock()
    mock_cand.grounding_metadata = None
    mock_cand.groundingMetadata = None
    mock_cand.citation_metadata = None
    mock_cand.citationMetadata = None
    
    # Add content.parts structure (needed for extraction logic)
    mock_content = Mock()
    mock_content.parts = []
    mock_cand.content = mock_content
    
    mock_resp.candidates = [mock_cand]
    return mock_resp


def create_mixed_view_response(
    dict_candidates_count: int,
    typed_candidates_count: int,
    dict_data: Dict
) -> Mock:
    """
    Create response with mismatched typed and dict candidate counts.
    Tests that we process max(typed, dict) candidates.
    """
    mock_resp = Mock()
    mock_resp.model_dump = Mock(return_value=dict_data)
    
    # Create different number of typed candidates
    typed_cands = []
    for _ in range(typed_candidates_count):
        mock_cand = Mock()
        mock_cand.grounding_metadata = None
        mock_cand.groundingMetadata = None
        mock_cand.citation_metadata = None
        mock_cand.citationMetadata = None
        typed_cands.append(mock_cand)
    
    mock_resp.candidates = typed_cands
    return mock_resp


def create_legacy_response(
    has_grounding_attributions: bool = False,
    has_grounding_chunks: bool = False,
    has_supporting_content: bool = False,
    dict_data: Optional[Dict] = None
) -> Mock:
    """
    Create response with legacy citation formats.
    """
    if dict_data is None:
        dict_data = {
            'candidates': [{
                'content': {'parts': [{'text': 'Response'}]},
                'groundingMetadata': {}
            }]
        }
        
        gm = dict_data['candidates'][0]['groundingMetadata']
        
        if has_grounding_attributions:
            gm['groundingAttributions'] = [
                {'web': {'uri': 'https://legacy1.example.com'}}
            ]
        
        if has_grounding_chunks:
            gm['groundingChunks'] = [
                {'web': {'uri': 'https://legacy2.example.com'}}
            ]
        
        if has_supporting_content:
            gm['supportingContent'] = [
                {'uri': 'https://legacy3.example.com'}
            ]
    
    return create_vertex_response(dict_data=dict_data)