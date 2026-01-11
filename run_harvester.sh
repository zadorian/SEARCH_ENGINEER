#!/bin/bash
cd /data/SEARCH_ENGINEER/BACKEND/modules
export PYTHONPATH="/data/SEARCH_ENGINEER/BACKEND/modules:$PYTHONPATH"
/data/linklater/venv/bin/python3 -m TORPEDO.PROCESSING.entity_harvester "$@"
