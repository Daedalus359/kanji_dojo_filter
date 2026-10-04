#!/usr/bin/env bash

set -u

JMDICT_DIRECTORY="$(dirname "$0")/data/JMDict"
MODE="exact"

usage() {
    cat <<EOF
Usage:
  $0 QUERY
  $0 -p QUERY
  $0 QUERY DIRECTORY

Options:
  -p    Search for partial matches instead of exact matches.

Examples:
  $0 '無くてはいけません'
  $0 -p '無くて'
  $0 '檸檬' data/JMDict
EOF
}

if [[ $# -eq 0 ]]; then
    usage
    exit 1
fi

if [[ "$1" == "-p" || "$1" == "--partial" ]]; then
    MODE="partial"
    shift
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 1
fi

QUERY="$1"

if [[ $# -eq 2 ]]; then
    JMDICT_DIRECTORY="$2"
fi

if [[ ! -d "$JMDICT_DIRECTORY" ]]; then
    echo "Error: directory not found:"
    echo "  $JMDICT_DIRECTORY"
    exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq is not installed."
    echo "Install it with:"
    echo "  sudo apt update && sudo apt install jq"
    exit 1
fi

shopt -s nullglob
TERM_FILES=("$JMDICT_DIRECTORY"/term_bank_*.json)

if [[ ${#TERM_FILES[@]} -eq 0 ]]; then
    echo "Error: no term_bank_*.json files found in:"
    echo "  $JMDICT_DIRECTORY"
    exit 1
fi

if [[ "$MODE" == "exact" ]]; then
    JQ_FILTER='
        .[]
        | select(.[0] == $query or .[1] == $query)
    '
else
    JQ_FILTER='
        .[]
        | select(
            (.[0] | contains($query))
            or
            (.[1] | contains($query))
        )
    '
fi

MATCH_COUNT=0

for file in "${TERM_FILES[@]}"; do
    results="$(
        jq -c \
           --arg query "$QUERY" \
           "$JQ_FILTER" \
           "$file"
    )"

    if [[ -n "$results" ]]; then
        while IFS= read -r record; do
            printf '%s: %s\n' "$file" "$record"
            MATCH_COUNT=$((MATCH_COUNT + 1))
        done <<< "$results"
    fi
done

if [[ "$MATCH_COUNT" -eq 0 ]]; then
    echo "No matches found for: $QUERY"
else
    echo
    echo "Found $MATCH_COUNT matching record(s)."
fi