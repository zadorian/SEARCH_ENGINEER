#!/bin/bash
# Quick wrapper to search for a company using Corporella CLI

cd "/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/0. WIKIMAN"

if [ -z "${OPEN_CORPORATES_API_TOKEN}" ]; then
  echo "OPEN_CORPORATES_API_TOKEN is not set. Export your OpenCorporates token before running."
  exit 1
fi

if [ -z "${ALEPH_API_KEY}" ]; then
  echo "ALEPH_API_KEY is not set. Export your OCCRP Aleph API key before running."
  exit 1
fi

: "${ALEPH_CLI_PATH:=/Users/attic/Library/Mobile Documents/com~apple~CloudDocs/01_ACTIVE_PROJECTS/Development/0. WIKIMAN/01aleph.py}"

python3 corporella.py parallel "$1"
