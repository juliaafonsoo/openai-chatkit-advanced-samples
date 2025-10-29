"""FastAPI entrypoint for the MEDICALS Gmail Agent workflow."""

from __future__ import annotations

from fastapi import FastAPI

from .gmail_agent import WorkflowInput, run_workflow

app = FastAPI(title="MEDICALS Gmail Agent API")


@app.post("/run")
async def run_medicals_gmail_agent(payload: WorkflowInput) -> dict:
    """Execute the Gmail workflow with the provided input text."""
    return await run_workflow(payload)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
