import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import parse_qs, urlparse


def load_j_y_term_bank(directory: str = ".") -> Dict[str, List[list]]:
    """Load term_bank*.json files into an index keyed by expression."""
    index: Dict[str, List[list]] = {}

    for path in Path(directory).glob("term_bank*.json"):
        with path.open(encoding="utf-8") as f:
            entries = json.load(f)

        for entry in entries:
            if isinstance(entry, list) and entry and isinstance(entry[0], str):
                index.setdefault(entry[0], []).append(entry)

    return index


def search_j_y_entries(
    term_bank: Dict[str, List[list]], expression: str
) -> List[list]:
    """Return entries whose expression exactly matches the search string."""
    return term_bank.get(expression, [])


def _walk_j_y_nodes(node: Any) -> Iterator[Any]:
    """Visit every nested list and dictionary in an entry."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_j_y_nodes(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_j_y_nodes(value)


def is_j_y_redirect(entry: list) -> bool:
    """Return True if the entry contains a redirect marker."""
    for node in _walk_j_y_nodes(entry):
        if isinstance(node, dict):
            data = node.get("data")
            if isinstance(data, dict) and data.get("content") == "redirect-glossary":
                return True

        if (
            isinstance(node, list)
            and len(node) >= 2
            and isinstance(node[0], str)
            and isinstance(node[1], list)
            and any(
                isinstance(item, str) and item.startswith("redirected from ")
                for item in node[1]
            )
        ):
            return True

    return False


def _get_j_y_reading(entry: list) -> Optional[str]:
    # Fall back to the entry's explicit reading.
    if len(entry) > 1 and isinstance(entry[1], str) and entry[1]:
        return entry[1]

    # Or combine readings from ruby annotations (the "rt" tags).
    readings = []
    for node in _walk_j_y_nodes(entry):
        if isinstance(node, dict) and node.get("tag") == "rt":
            content = node.get("content")
            if isinstance(content, str):
                readings.append(content)

    return "".join(readings) or None


def get_j_y_redirect_target(
    entry: list,
) -> Optional[tuple[str, Optional[str]]]:
    """Return (redirect target, reading), or None if the entry isn't a redirect."""
    if not is_j_y_redirect(entry):
        return None

    target = None
    primary_reading = None

    # Prefer the target and reading specified in the redirect link's href.
    for node in _walk_j_y_nodes(entry):
        if isinstance(node, dict) and isinstance(node.get("href"), str):
            params = parse_qs(urlparse(node["href"]).query)
            if target is None and params.get("query"):
                target = params["query"][0]
            if primary_reading is None and params.get("primary_reading"):
                primary_reading = params["primary_reading"][0]

    # Fall back to metadata such as ["萬", ["redirected from 万"]].
    if target is None:
        for node in _walk_j_y_nodes(entry):
            if (
                isinstance(node, list)
                and len(node) >= 2
                and isinstance(node[0], str)
                and isinstance(node[1], list)
                and any(
                    isinstance(item, str) and item.startswith("redirected from ")
                    for item in node[1]
                )
            ):
                target = node[0]
                break

    if target is None:
        return None

    reading = primary_reading or _get_j_y_reading(entry)
    return target, reading


# Example:
# bank = load_j_y_term_bank(".")
# matches = search_j_y_entries(bank, "さ来年")

# for entry in matches:
#     if is_j_y_redirect(entry):
#         print(get_j_y_redirect_target(entry))  # 再来年