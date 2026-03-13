from __future__ import annotations

from typing import Any, Dict, List

from src.pmd.core.llm import LLMProvider


def _build_prompt(*, template_title: str, matched_summaries: List[str]) -> str:
    joined = "\n\n".join(f"- {s}" for s in matched_summaries if (s or "").strip())
    return (
        "You are generating a Primary Master Document (PMD) section.\n\n"
        f"SECTION TITLE:\n{template_title}\n\n"
        "AVAILABLE SOURCE SUMMARIES:\n"
        f"{joined if joined.strip() else '- (no summaries provided)'}\n\n"
        "INSTRUCTIONS:\n"
        "- Write a coherent section suitable for inclusion in a PMD.\n"
        "- Use the provided summaries; if insufficient, explicitly note missing information.\n"
    )


# PUBLIC_INTERFACE
def generate_pmd_from_matches(
    *, llm: LLMProvider, template: List[Dict[str, Any]], matching: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate populated PMD output from template and matching results.

    Args:
        llm: LLM provider implementation.
        template: Template sections.
        matching: Matching results (from compute_template_inventory_matches).

    Returns:
        Dict containing populated sections and a concatenated full_text.
    """
    match_by_template_id = {
        s.get("template_section_id"): s for s in matching.get("sections", [])
    }

    populated_sections: List[Dict[str, Any]] = []
    for sec in template:
        tid = sec.get("id")
        title = sec.get("title") or ""
        match_rec = match_by_template_id.get(tid, {})
        matches = match_rec.get("matches") or []
        summaries = [m.get("inventory_summary") or "" for m in matches]

        prompt = _build_prompt(template_title=title, matched_summaries=summaries)
        generated = llm.generate_section(prompt=prompt)

        populated_sections.append(
            {
                "template_section_id": tid,
                "title": title,
                "generated_text": generated,
                "used_inventory_section_ids": [m.get("inventory_section_id") for m in matches],
            }
        )

    full_text = "\n\n".join(
        f"# {s['title']}\n\n{s['generated_text']}".strip() for s in populated_sections
    )

    return {
        "provider": getattr(llm, "name", llm.__class__.__name__),
        "sections": populated_sections,
        "full_text": full_text,
    }
