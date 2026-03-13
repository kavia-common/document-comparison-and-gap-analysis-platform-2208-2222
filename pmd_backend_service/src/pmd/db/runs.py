from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.pmd.db.sqlite import get_db


class RunRecord(BaseModel):
    """Run record as stored/retrieved from SQLite."""

    run_id: str = Field(..., description="Unique identifier for this run.")
    status: str = Field(..., description="Current run status.")
    error: Optional[str] = Field(default=None, description="Error message if run failed.")
    created_at: str = Field(..., description="ISO timestamp when run was created.")
    updated_at: str = Field(..., description="ISO timestamp when run was last updated.")

    template: Any = Field(..., description="Template payload (JSON).")
    inventory: Any = Field(..., description="Inventory payload (JSON).")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary run metadata.")

    matching: Optional[Dict[str, Any]] = Field(
        default=None, description="Matching results, if computed."
    )
    gap_analysis: Optional[Dict[str, Any]] = Field(
        default=None, description="Gap analysis results, if computed."
    )
    generated_pmd: Optional[Dict[str, Any]] = Field(
        default=None, description="Generated PMD output, if computed."
    )


def _hydrate_run(row: Dict[str, Any]) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        status=row["status"],
        error=row.get("error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        template=json.loads(row["template_json"]),
        inventory=json.loads(row["inventory_json"]),
        metadata=json.loads(row["metadata_json"] or "{}"),
        matching=json.loads(row["matching_json"]) if row.get("matching_json") else None,
        gap_analysis=(
            json.loads(row["gap_analysis_json"]) if row.get("gap_analysis_json") else None
        ),
        generated_pmd=(
            json.loads(row["generated_pmd_json"])
            if row.get("generated_pmd_json")
            else None
        ),
    )


# PUBLIC_INTERFACE
def create_run(*, template: Any, inventory: Any, metadata: Dict[str, Any]) -> RunRecord:
    """Create a new run and persist template+inventory.

    Args:
        template: Template payload (JSON-serializable).
        inventory: Inventory payload (JSON-serializable).
        metadata: Optional metadata.

    Returns:
        Created RunRecord.
    """
    run_id = str(uuid.uuid4())
    db = get_db()
    db.insert_run(
        run_id=run_id,
        status="SUBMITTED",
        template=template,
        inventory=inventory,
        metadata=metadata or {},
    )
    row = db.fetch_run(run_id)
    if not row:
        raise RuntimeError("Failed to create run")
    return _hydrate_run(row)


# PUBLIC_INTERFACE
def get_run(run_id: str) -> Optional[RunRecord]:
    """Fetch a run.

    Args:
        run_id: Run identifier.

    Returns:
        RunRecord if found else None.
    """
    row = get_db().fetch_run(run_id)
    return _hydrate_run(row) if row else None


# PUBLIC_INTERFACE
def list_runs(*, limit: int = 50, offset: int = 0) -> list[RunRecord]:
    """List runs.

    Args:
        limit: Max runs to return.
        offset: Pagination offset.

    Returns:
        List of RunRecord.
    """
    rows = get_db().list_runs(limit=limit, offset=offset)
    return [_hydrate_run(r) for r in rows]


# PUBLIC_INTERFACE
def update_run_status(run_id: str, status: str) -> None:
    """Update run status."""
    get_db().update_run_status(run_id, status)


# PUBLIC_INTERFACE
def update_run_error(run_id: str, error: str) -> None:
    """Update run error message."""
    get_db().update_run_error(run_id, error)


# PUBLIC_INTERFACE
def update_run_result(
    run_id: str,
    *,
    matching: Optional[Dict[str, Any]] = None,
    gap_analysis: Optional[Dict[str, Any]] = None,
    generated_pmd: Optional[Dict[str, Any]] = None,
) -> None:
    """Update one or more run result fields.

    Args:
        run_id: Target run.
        matching: Matching results.
        gap_analysis: Gap analysis results.
        generated_pmd: Generated PMD output.
    """
    db = get_db()
    if matching is not None:
        db.update_run_result_json(run_id, field="matching_json", value=matching)
    if gap_analysis is not None:
        db.update_run_result_json(run_id, field="gap_analysis_json", value=gap_analysis)
    if generated_pmd is not None:
        db.update_run_result_json(run_id, field="generated_pmd_json", value=generated_pmd)
