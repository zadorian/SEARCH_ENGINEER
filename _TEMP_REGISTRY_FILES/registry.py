#!/usr/bin/env python3
from __future__ import annotations

from typing import Literal


Segment = Literal['subject', 'location', 'object']

SEARCH_TYPE_TO_SEGMENT: dict[str, Segment] = {
    # Subject
    'people': 'subject',
    'email': 'subject',
    'phone': 'subject',
    'username': 'subject',
    'password': 'subject',
    'linkedin': 'subject',
    'recruitment': 'subject',
    'academic': 'subject',
    'author': 'subject',

    # Location
    'site': 'location',
    'language': 'location',
    'date': 'location',
    'filetype': 'location',
    'dataset': 'location',

    # Object
    'proximity': 'object',
    'book': 'object',
}


def get_segment(search_type: str) -> Segment:
    key = (search_type or '').lower()
    return SEARCH_TYPE_TO_SEGMENT.get(key, 'subject')


