from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.pmd.api.routes import router as pmd_router

openapi_tags = [
    {
        "name": "System",
        "description": "Health checks and general service information.",
    },
    {
        "name": "PMD Workflow",
        "description": (
            "Endpoints for PMD template + inventory submission, matching, gap analysis, "
            "PMD generation, and run status tracking."
        ),
    },
]


app = FastAPI(
    title="PMD Template Comparison Service",
    description=(
        "Backend service to compare a Primary Master Document (PMD) template against an inventory "
        "of section summaries, perform matching and gap analysis, and generate a populated PMD "
        "via an LLM provider abstraction. All operations are tracked as runs stored in SQLite."
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pmd_router)


@app.get("/", tags=["System"], summary="Health check", operation_id="health_check")
def health_check():
    """Health check endpoint.

    Returns:
        A simple JSON payload indicating the service is running.
    """
    return {"message": "Healthy"}
