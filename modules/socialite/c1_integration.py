"""
SOCIALITE C1 Integration Helper

Provides a unified interface for platforms to push results to C1 via output handlers.
This module bridges platform API results to the output handlers that create C1 nodes.

Usage in platforms:
    from ..c1_integration import push_to_c1
    
    # After getting API results:
    result = await collect_profile(url)
    push_to_c1('instagram_url', url, result, context={'project_id': 'proj123'})
"""

import logging
from typing import Dict, Any, Optional, Union, List

from .output import (
    UsernameOutputHandler,
    PersonNameOutputHandler,
    CompanyNameOutputHandler,
    FacebookUrlOutputHandler,
    InstagramUrlOutputHandler,
    TwitterUrlOutputHandler,
    ThreadsUrlOutputHandler,
    PersonLinkedInUrlOutputHandler,
    CompanyLinkedInUrlOutputHandler,
)

logger = logging.getLogger(__name__)


# Handler registry - maps entity types to their handlers
HANDLER_REGISTRY = {
    'username': UsernameOutputHandler,
    'person_name': PersonNameOutputHandler,
    'person': PersonNameOutputHandler,
    'company_name': CompanyNameOutputHandler,
    'company': CompanyNameOutputHandler,
    'facebook_url': FacebookUrlOutputHandler,
    'instagram_url': InstagramUrlOutputHandler,
    'twitter_url': TwitterUrlOutputHandler,
    'threads_url': ThreadsUrlOutputHandler,
    'linkedin_url': PersonLinkedInUrlOutputHandler,
    'person_linkedin_url': PersonLinkedInUrlOutputHandler,
    'company_linkedin_url': CompanyLinkedInUrlOutputHandler,
}

# Platform to URL handler mapping
PLATFORM_HANDLERS = {
    'facebook': FacebookUrlOutputHandler,
    'instagram': InstagramUrlOutputHandler,
    'twitter': TwitterUrlOutputHandler,
    'x': TwitterUrlOutputHandler,
    'threads': ThreadsUrlOutputHandler,
    'linkedin': PersonLinkedInUrlOutputHandler,
}

# Cached handler instances
_handler_cache = {}


def get_handler(entity_type: str):
    """Get or create a handler instance for the given entity type."""
    if entity_type not in _handler_cache:
        handler_class = HANDLER_REGISTRY.get(entity_type)
        if handler_class:
            _handler_cache[entity_type] = handler_class()
        else:
            logger.warning(f"No handler registered for entity type: {entity_type}")
            return None
    return _handler_cache[entity_type]


def push_to_c1(
    entity_type: str,
    value: str,
    raw_data: Dict[str, Any] = None,
    context: Dict[str, Any] = None,
    is_input: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Push an entity to C1 via the appropriate output handler.

    Args:
        entity_type: Type of entity (username, person_name, facebook_url, etc.)
        value: The entity value (username, URL, name, etc.)
        raw_data: Raw API response data
        context: Context dict with project_id, aggregator_id, etc.
        is_input: Whether this entity is the search input (affects verification status)

    Returns:
        The created node dict, or None if handler not found

    Example:
        # From Instagram platform after collecting profile data
        result = await collect_profile('https://instagram.com/johndoe')
        node = push_to_c1(
            entity_type='instagram_url',
            value='https://instagram.com/johndoe',
            raw_data=result,
            context={'project_id': 'proj123', 'is_input': True}
        )
    """
    handler = get_handler(entity_type)
    if not handler:
        logger.error(f"No handler for entity type: {entity_type}")
        return None

    ctx = context or {}
    ctx['is_input'] = is_input

    try:
        node = handler.process(value, ctx, raw_data)
        logger.info(f"✓ Pushed to C1: {entity_type}:{value[:50]}...")
        return node
    except Exception as e:
        logger.error(f"Error pushing to C1: {e}")
        return None


def push_profile_to_c1(
    platform: str,
    profile_url: str,
    raw_data: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Push a social media profile to C1.

    Convenience function that determines the correct handler based on platform.

    Args:
        platform: Platform name (facebook, instagram, twitter, linkedin, threads)
        profile_url: The profile URL
        raw_data: Raw API response data
        context: Context dict with project_id, etc.

    Returns:
        The created node dict
    """
    handler_class = PLATFORM_HANDLERS.get(platform.lower())
    if not handler_class:
        logger.error(f"No handler for platform: {platform}")
        return None

    handler = handler_class()
    ctx = context or {}

    try:
        node = handler.process(profile_url, ctx, raw_data)
        logger.info(f"✓ Pushed profile to C1: {platform}:{profile_url[:50]}...")
        return node
    except Exception as e:
        logger.error(f"Error pushing profile to C1: {e}")
        return None


def push_batch_to_c1(
    entity_type: str,
    items: List[Dict[str, Any]],
    context: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    Push multiple entities to C1 in batch.

    Args:
        entity_type: Type of entity
        items: List of dicts with 'value' and optional 'raw_data' keys
        context: Shared context for all items

    Returns:
        List of created node dicts
    """
    handler = get_handler(entity_type)
    if not handler:
        logger.error(f"No handler for entity type: {entity_type}")
        return []

    ctx = context or {}
    nodes = []

    for item in items:
        value = item.get('value')
        raw_data = item.get('raw_data', {})

        if not value:
            continue

        try:
            node = handler.process(value, ctx, raw_data)
            nodes.append(node)
        except Exception as e:
            logger.error(f"Error in batch push: {e}")

    logger.info(f"✓ Batch pushed {len(nodes)}/{len(items)} items to C1")
    return nodes


def extract_and_push_entities(
    raw_data: Dict[str, Any],
    context: Dict[str, Any] = None
) -> Dict[str, List[Dict]]:
    """
    Extract all recognizable entities from raw data and push to C1.

    Automatically detects and processes:
    - profile URLs (facebook, instagram, twitter, linkedin, threads)
    - person names
    - company names
    - usernames
    - emails
    - phone numbers

    Args:
        raw_data: Raw API response containing potential entities
        context: Context dict

    Returns:
        Dict mapping entity types to lists of created nodes
    """
    ctx = context or {}
    results = {
        'profiles': [],
        'persons': [],
        'companies': [],
        'usernames': [],
    }

    # Extract profile URLs
    profile_fields = [
        ('linkedin_url', 'linkedin'),
        ('facebook_url', 'facebook'),
        ('twitter_url', 'twitter'),
        ('instagram_url', 'instagram'),
        ('threads_url', 'threads'),
    ]

    for field, platform in profile_fields:
        if raw_data.get(field):
            node = push_profile_to_c1(platform, raw_data[field], raw_data, ctx)
            if node:
                results['profiles'].append(node)

    # Extract person name
    name = raw_data.get('name') or raw_data.get('full_name')
    if name:
        node = push_to_c1('person_name', name, raw_data, ctx)
        if node:
            results['persons'].append(node)

    # Extract company
    company = raw_data.get('company') or raw_data.get('current_company')
    if company:
        node = push_to_c1('company_name', company, {'name': company}, ctx)
        if node:
            results['companies'].append(node)

    # Extract username
    username = raw_data.get('username')
    if username:
        node = push_to_c1('username', username, raw_data, ctx)
        if node:
            results['usernames'].append(node)

    total = sum(len(v) for v in results.values())
    logger.info(f"✓ Extracted and pushed {total} entities to C1")

    return results


__all__ = [
    'push_to_c1',
    'push_profile_to_c1',
    'push_batch_to_c1',
    'extract_and_push_entities',
    'get_handler',
    'HANDLER_REGISTRY',
    'PLATFORM_HANDLERS',
]
