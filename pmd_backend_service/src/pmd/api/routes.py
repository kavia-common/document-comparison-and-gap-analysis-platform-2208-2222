from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.pmd.core.llm import get_llm_provider
from src.pmd.core.matching import compute_template_inventory_matches
from src.pmd.core.pmd_generation import generate_pmd_from_matches
from src.pmd.db.sqlite import get_db
from src.pmd.db.runs import (
    RunRecord,
    create_run,
    get_run,
    list_runs,
    update_run_error,
    update_run_result,
    update_run_status,
)

router = APIRouter(prefix="", tags=["PMD Workflow"])


class UploadPlaceholderRequest(BaseModel):
    """Request body for upload placeholder endpoint."""

    filename: str = Field(..., description="Name of the file being 'uploaded'.")
    content_type: Optional[str] = Field(
        default=None, description="Optional MIME type of the file."
    )
    notes: Optional[str] = Field(
        default=None, description="Optional notes about the uploaded file."
    )


class UploadPlaceholderResponse(BaseModel):
    """Response for upload placeholder endpoint."""

    upload_id: str = Field(..., description="Generated identifier for the placeholder upload.")
    received_at: str = Field(..., description="ISO-8601 timestamp when placeholder was received.")


class TemplateSection(BaseModel):
    """A section in the PMD template."""

    id: str = Field(..., description="Unique identifier for the template section.")
    title: str = Field(..., description="Human-readable title of the section.")
    content: Optional[str] = Field(
        default=None, description="Optional existing text content of the template section."
    )


class InventorySection(BaseModel):
    """A section in the inventory (source content)."""

    id: str = Field(..., description="Unique identifier for the inventory section.")
    title: str = Field(..., description="Human-readable title of the inventory section.")
    summary: str = Field(..., description="Summary text available for matching.")


class SubmitTemplateInventoryRequest(BaseModel):
    """Submit template and inventory to create a run."""

    template: List[TemplateSection] = Field(
        ..., description="List of template sections to be populated."
    )
    inventory: List[InventorySection] = Field(
        ..., description="List of inventory sections used as source summaries."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Optional metadata associated with the run."
    )


class SubmitTemplateInventoryResponse(BaseModel):
    """Response for submission endpoint."""

    run_id: str = Field(..., description="Run identifier used for subsequent workflow steps.")
    status: str = Field(..., description="Current status of the run.")


class RunMatchingRequest(BaseModel):
    """Request body for /run_matching."""

    run_id: str = Field(..., description="Run identifier returned by /submit_template_inventory.")
    top_k: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Number of top inventory matches per template section.",
    )


class GapAnalysisRequest(BaseModel):
    """Request body for /gap_analysis."""

    run_id: str = Field(..., description="Run identifier.")
    min_score: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score to consider content sufficiently matched.",
    )


class GeneratePMDRequest(BaseModel):
    """Request body for /generate_pmd."""

    run_id: str = Field(..., description="Run identifier.")
    provider: str = Field(
        default="mock",
        description=(
            "LLM provider name. Default 'mock' returns deterministic placeholder output. "
            "This is an abstraction point for real providers."
        ),
    )


class StatusResponse(BaseModel):
    """Status payload for a run."""

    run: RunRecord = Field(..., description="Run record including status and timestamps.")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# PUBLIC_INTERFACE
@router.post(
    "/upload_placeholder",
    response_model=UploadPlaceholderResponse,
    summary="Placeholder upload endpoint",
    description=(
        "Accepts upload metadata to simulate document upload. This is a placeholder for future "
        "binary upload support; current implementation only stores a record in SQLite."
    ),
    operation_id="upload_placeholder",
)
def upload_placeholder(req: UploadPlaceholderRequest) -> UploadPlaceholderResponse:
    """Record a placeholder upload.

    Args:
        req: Upload placeholder metadata.

    Returns:
        A generated upload_id and timestamp.
    """
    db = get_db()
    upload_id = db.insert_placeholder_upload(
        filename=req.filename, content_type=req.content_type, notes=req.notes
    )
    return UploadPlaceholderResponse(upload_id=upload_id, received_at=_utc_now().isoformat())


# PUBLIC_INTERFACE
@router.post(
    "/submit_template_inventory",
    response_model=SubmitTemplateInventoryResponse,
    summary="Submit template and inventory",
    description=(
        "Creates a new run and stores the submitted template and inventory payloads in SQLite."
    ),
    operation_id="submit_template_inventory",
)
def submit_template_inventory(
    req: SubmitTemplateInventoryRequest,
) -> SubmitTemplateInventoryResponse:
    """Create a run and persist template+inventory.

    Args:
        req: Template and inventory submission request.

    Returns:
        run_id and current status.
    """
    run = create_run(
        template=[s.model_dump() for s in req.template],
        inventory=[s.model_dump() for s in req.inventory],
        metadata=req.metadata,
    )
    return SubmitTemplateInventoryResponse(run_id=run.run_id, status=run.status)


# PUBLIC_INTERFACE
@router.post(
    "/run_matching",
    summary="Run template-to-inventory matching",
    description=(
        "Computes best matching inventory summaries for each template section and stores the "
        "results on the run."
    ),
    operation_id="run_matching",
)
def run_matching(req: RunMatchingRequest) -> Dict[str, Any]:
    """Run matching for a given run.

    Args:
        req: Includes run_id and matching parameters.

    Returns:
        Matching results payload.
    """
    run = get_run(req.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    update_run_status(req.run_id, "MATCHING")

    try:
        matches = compute_template_inventory_matches(
            template=run.template,
            inventory=run.inventory,
            top_k=req.top_k,
        )
        update_run_result(req.run_id, matching=matches)
        update_run_status(req.run_id, "MATCHED")
        return {"run_id": req.run_id, "matching": matches}
    except Exception as e:
        update_run_error(req.run_id, str(e))
        update_run_status(req.run_id, "ERROR")
        raise


# PUBLIC_INTERFACE
@router.post(
    "/gap_analysis",
    summary="Run gap analysis",
    description=(
        "Analyzes matching results to identify missing/weakly covered template sections. Stores "
        "gap analysis results on the run."
    ),
    operation_id="gap_analysis",
)
def gap_analysis(req: GapAnalysisRequest) -> Dict[str, Any]:
    """Run gap analysis for a run.

    Args:
        req: Gap analysis parameters including min_score.

    Returns:
        Gap analysis payload.
    """
    run = get_run(req.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if not run.matching:
        raise HTTPException(status_code=409, detail="Matching has not been run for this run_id")

    update_run_status(req.run_id, "GAP_ANALYSIS")
    try:
        gaps: List[Dict[str, Any]] = []
        for section_match in run.matching.get("sections", []):
            best = (section_match.get("matches") or [{}])[0]
            score = float(best.get("score", 0.0))
            if score < req.min_score:
                gaps.append(
                    {
                        "template_section_id": section_match.get("template_section_id"),
                        "template_title": section_match.get("template_title"),
                        "best_score": score,
                        "recommended_action": "Provide additional source material for this section.",
                    }
                )

        gap_result = {
            "min_score": req.min_score,
            "gap_count": len(gaps),
            "gaps": gaps,
        }
        update_run_result(req.run_id, gap_analysis=gap_result)
        update_run_status(req.run_id, "GAP_ANALYZED")
        return {"run_id": req.run_id, "gap_analysis": gap_result}
    except Exception as e:
        update_run_error(req.run_id, str(e))
        update_run_status(req.run_id, "ERROR")
        raise


# PUBLIC_INTERFACE
@router.post(
    "/generate_pmd",
    summary="Generate populated PMD",
    description=(
        "Generates populated PMD content using the configured LLM provider abstraction and the "
        "matching results. Stores the generated PMD on the run."
    ),
    operation_id="generate_pmd",
)
def generate_pmd(req: GeneratePMDRequest) -> Dict[str, Any]:
    """Generate PMD for a run.

    Args:
        req: Includes run_id and provider name.

    Returns:
        PMD generation payload (populated sections and full text).
    """
    run = get_run(req.run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not run.matching:
        raise HTTPException(status_code=409, detail="Matching has not been run for this run_id")

    update_run_status(req.run_id, "PMD_GENERATION")
    try:
        llm = get_llm_provider(req.provider)
        pmd_result = generate_pmd_from_matches(
            llm=llm,
            template=run.template,
            matching=run.matching,
        )
        update_run_result(req.run_id, generated_pmd=pmd_result)
        update_run_status(req.run_id, "PMD_GENERATED")
        return {"run_id": req.run_id, "generated_pmd": pmd_result}
    except Exception as e:
        update_run_error(req.run_id, str(e))
        update_run_status(req.run_id, "ERROR")
        raise


# PUBLIC_INTERFACE
@router.get(
    "/status/{run_id}",
    response_model=StatusResponse,
    summary="Get run status",
    description="Fetch the stored run state, including status, errors, and any computed results.",
    operation_id="status",
)
def status(run_id: str) -> StatusResponse:
    """Get status and stored results for a run.

    Args:
        run_id: Identifier for the run.

    Returns:
        Run record with timestamps and stored payloads.
    """
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return StatusResponse(run=run)


# PUBLIC_INTERFACE
@router.get(
    "/runs",
    summary="List runs",
    description="Lists recent runs (most recent first). Useful for debugging and demos.",
    operation_id="list_runs",
)
def runs(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """List runs with pagination.

    Args:
        limit: Max number of runs.
        offset: Offset for pagination.

    Returns:
        A list of run records.
    """
    items = list_runs(limit=limit, offset=offset)
    return {"items": [i.model_dump() for i in items], "limit": limit, "offset": offset}
