from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if t.strip()}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# PUBLIC_INTERFACE
def compute_template_inventory_matches(
    *, template: List[Dict[str, Any]], inventory: List[Dict[str, Any]], top_k: int = 3
) -> Dict[str, Any]:
    """Compute best matching inventory sections for each template section.

    This is a lightweight baseline matcher using token Jaccard similarity over
    title + content/summary. It is designed to be swapped later with embeddings-based
    similarity without changing endpoint contracts.

    Args:
        template: List of template section dicts.
        inventory: List of inventory section dicts.
        top_k: Top-K matches to return per template section.

    Returns:
        Dict with per-section matches.
    """
    inv_items: List[Tuple[Dict[str, Any], set[str]]] = []
    for inv in inventory:
        inv_text = f"{inv.get('title', '')}\n{inv.get('summary', '')}"
        inv_items.append((inv, _tokenize(inv_text)))

    sections: List[Dict[str, Any]] = []
    for tmpl in template:
        tmpl_text = f"{tmpl.get('title', '')}\n{tmpl.get('content', '') or ''}"
        tmpl_tokens = _tokenize(tmpl_text)

        scored: List[Dict[str, Any]] = []
        for inv, inv_tokens in inv_items:
            score = _jaccard(tmpl_tokens, inv_tokens)
            scored.append(
                {
                    "inventory_section_id": inv.get("id"),
                    "inventory_title": inv.get("title"),
                    "score": round(float(score), 6),
                    "inventory_summary": inv.get("summary"),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)

        sections.append(
            {
                "template_section_id": tmpl.get("id"),
                "template_title": tmpl.get("title"),
                "matches": scored[:top_k],
            }
        )

    return {"algorithm": "token_jaccard_v1", "top_k": top_k, "sections": sections}
