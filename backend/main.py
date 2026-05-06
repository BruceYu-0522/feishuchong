from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root before anything else
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.code_executor import RUNS_DIR
from backend.pipeline_engine import (
    create_pipeline,
    run_next_stage,
    run_until_review,
    run_until_review_with_stream,
    submit_review,
)
from backend.schemas import CreatePipelineRequest, Pipeline, ReviewRequest
from backend.storage import store


app = FastAPI(
    title="DevFlow Engine API",
    description="AI 研发流程引擎的 API-first 后端雏形，使用 Skill-driven LLM 与本地代码执行器跑通 Pipeline 闭环。",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/pipelines", response_model=Pipeline)
def create_pipeline_endpoint(request: CreatePipelineRequest) -> Pipeline:
    return store.save(create_pipeline(request.requirement, request.projectPath))


@app.get("/pipelines/{pipeline_id}", response_model=Pipeline)
def get_pipeline_endpoint(pipeline_id: str) -> Pipeline:
    return store.get(pipeline_id)


@app.post("/pipelines/{pipeline_id}/run-next", response_model=Pipeline)
def run_next_endpoint(pipeline_id: str) -> Pipeline:
    pipeline = store.get(pipeline_id)
    return store.save(run_next_stage(pipeline))


@app.post("/pipelines/{pipeline_id}/run-until-review", response_model=Pipeline)
def run_until_review_endpoint(pipeline_id: str) -> Pipeline:
    pipeline = store.get(pipeline_id)
    return store.save(run_until_review(pipeline))


@app.get("/pipelines/{pipeline_id}/stream-run")
async def stream_run_endpoint(pipeline_id: str):
    """SSE endpoint that streams LLM output and system operations in real-time."""
    pipeline = store.get(pipeline_id)

    async def event_stream():
        async for event in run_until_review_with_stream(pipeline):
            yield event
        # Save pipeline state after streaming
        store.save(pipeline)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/pipelines/{pipeline_id}/review", response_model=Pipeline)
def review_endpoint(pipeline_id: str, request: ReviewRequest) -> Pipeline:
    pipeline = store.get(pipeline_id)
    return store.save(submit_review(pipeline, request))


@app.get("/runs/{pipeline_id}/target-app/{asset_path:path}")
def preview_target_app_endpoint(pipeline_id: str, asset_path: str) -> FileResponse:
    target_root = (RUNS_DIR / pipeline_id / "target-app").resolve()
    requested = (target_root / (asset_path or "index.html")).resolve()

    if target_root not in [requested, *requested.parents]:
        raise HTTPException(status_code=404, detail="Preview asset not found.")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="Preview asset not found.")

    return FileResponse(requested)
