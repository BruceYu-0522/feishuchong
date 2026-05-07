from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root before anything else
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import io
import zipfile

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.code_executor import RUNS_DIR
from backend.pipeline_engine import (
    build_and_cache_index,
    create_pipeline,
    get_code_index,
    run_next_stage,
    run_until_review,
    run_until_review_with_stream,
    stream_element_modification,
    submit_review,
)
from backend.schemas import (
    CreatePipelineRequest,
    Pipeline,
    PipelineStats,
    ReviewRequest,
    StageStats,
)
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
    return store.save(create_pipeline(request.requirement, request.projectPath, request.template))


@app.get("/pipelines/{pipeline_id}", response_model=Pipeline)
def get_pipeline_endpoint(pipeline_id: str) -> Pipeline:
    return store.get(pipeline_id)


@app.post("/pipelines/{pipeline_id}/run-next", response_model=Pipeline)
def run_next_endpoint(pipeline_id: str) -> Pipeline:
    pipeline = store.get(pipeline_id)
    return store.save(run_next_stage(pipeline))


@app.post("/pipelines/{pipeline_id}/run-until-review", response_model=Pipeline)
def run_until_review_endpoint(pipeline_id: str, auto: bool = False) -> Pipeline:
    pipeline = store.get(pipeline_id)
    return store.save(run_until_review(pipeline, auto_mode=auto))


@app.get("/pipelines/{pipeline_id}/stream-run")
async def stream_run_endpoint(pipeline_id: str, auto: bool = False):
    """SSE endpoint that streams LLM output and system operations in real-time."""
    pipeline = store.get(pipeline_id)

    async def event_stream():
        async for event in run_until_review_with_stream(pipeline, auto_mode=auto):
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


@app.get("/pipelines/{pipeline_id}/workspace")
def list_workspace_endpoint(pipeline_id: str):
    run_dir = RUNS_DIR / pipeline_id
    workspace = run_dir / "workspace"
    target_app = run_dir / "target-app"

    files = []
    seen = set()

    # Collect workspace files
    if workspace.exists():
        for f in sorted(workspace.rglob("*")):
            if f.is_file():
                rel = f.relative_to(workspace).as_posix()
                files.append({"name": rel, "size": f.stat().st_size})
                seen.add(rel)

    # Also include target-app files with target-app/ prefix
    if target_app.exists():
        for f in sorted(target_app.rglob("*")):
            if f.is_file() and f.suffix.lower() in {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".json", ".md"}:
                rel = "target-app/" + f.relative_to(target_app).as_posix()
                if rel not in seen:
                    files.append({"name": rel, "size": f.stat().st_size})
                    seen.add(rel)

    # Git status for the run directory
    git_info = None
    try:
        from backend.git_manager import get_git_status_for_display
        git_info = get_git_status_for_display(run_dir)
    except Exception:
        pass

    if not files:
        result = {"files": [], "path": str(run_dir)}
    else:
        result = {"files": files, "path": str(run_dir)}

    if git_info:
        result["git"] = git_info

    return result


@app.get("/pipelines/{pipeline_id}/workspace/files/{file_path:path}")
def get_workspace_file_endpoint(pipeline_id: str, file_path: str):
    run_dir = (RUNS_DIR / pipeline_id).resolve()

    # Resolve the file under run_dir to support both workspace/ and target-app/ prefixes
    requested = (run_dir / file_path).resolve()
    if run_dir not in [requested, *requested.parents]:
        raise HTTPException(status_code=404, detail="File not found")
    if not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(requested)


@app.get("/pipelines/{pipeline_id}/workspace/export")
def export_workspace_endpoint(pipeline_id: str):
    run_dir = RUNS_DIR / pipeline_id
    workspace = run_dir / "workspace"
    target_app = run_dir / "target-app"

    has_files = False
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Export workspace files
        if workspace.exists():
            for f in sorted(workspace.rglob("*")):
                if f.is_file():
                    zf.write(f, "workspace/" + f.relative_to(workspace).as_posix())
                    has_files = True

        # Export target-app files
        if target_app.exists():
            for f in sorted(target_app.rglob("*")):
                if f.is_file():
                    zf.write(f, "target-app/" + f.relative_to(target_app).as_posix())
                    has_files = True

    if not has_files:
        raise HTTPException(status_code=404, detail="Workspace is empty")

    buf.seek(0)
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=workspace-{pipeline_id}.zip"},
    )


# ── Code Semantic Index Endpoints ──


@app.get("/pipelines/{pipeline_id}/code-index")
def get_code_index_endpoint(pipeline_id: str):
    """Return the semantic code index summary for a pipeline."""
    idx = get_code_index(pipeline_id)
    if not idx:
        # Try building it on demand
        idx = build_and_cache_index(pipeline_id)
    if not idx:
        return {"total_symbols": 0, "total_files": 0, "by_kind": {}, "by_file": {}}
    return idx.summary()


@app.get("/pipelines/{pipeline_id}/code-search")
def search_code_endpoint(pipeline_id: str, q: str = "", type: str = "symbol"):
    """Search the code index. type=symbol (default) or type=content for full-text."""
    if not q.strip():
        return {"results": []}

    idx = get_code_index(pipeline_id)
    if not idx:
        idx = build_and_cache_index(pipeline_id)
    if not idx:
        return {"results": []}

    if type == "content":
        results = idx.search_content(q)
    else:
        results = [
            {"name": s.name, "kind": s.kind, "file": s.file, "line": s.line, "snippet": s.snippet}
            for s in idx.search(q)
        ]
    return {"results": results, "query": q, "type": type}


# ── Observability Endpoint ──


@app.get("/pipelines/{pipeline_id}/stats")
def get_pipeline_stats_endpoint(pipeline_id: str):
    """Return observability stats for a pipeline."""
    pipeline = store.get(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="流水线未找到")

    stage_stats = []
    total_latency = 0
    total_prompt = 0
    total_comp = 0
    total_all = 0
    completed_count = 0

    for stage in pipeline.stages:
        artifact = pipeline.artifacts.get(stage.id)
        if artifact:
            status = "completed"
            completed_count += 1
        else:
            status = "pending"

        stage_stats.append(StageStats(
            stageId=stage.id,
            stageName=stage.name,
            agent=stage.agent,
            model=artifact.model if artifact else "",
            status=status,
            startedAt=artifact.startedAt if artifact else "",
            completedAt=artifact.completedAt if artifact else "",
            latencyMs=artifact.latencyMs if artifact else 0,
            promptTokens=artifact.promptTokens if artifact else 0,
            completionTokens=artifact.completionTokens if artifact else 0,
            totalTokens=artifact.totalTokens if artifact else 0,
            attempt=artifact.attempt if artifact else 1,
        ))
        if artifact:
            total_latency += artifact.latencyMs
            total_prompt += artifact.promptTokens
            total_comp += artifact.completionTokens
            total_all += artifact.totalTokens

    success_rate = completed_count / len(pipeline.stages) if pipeline.stages else 0.0

    return PipelineStats(
        pipelineId=pipeline_id,
        totalLatencyMs=total_latency,
        totalPromptTokens=total_prompt,
        totalCompletionTokens=total_comp,
        totalTokens=total_all,
        stages=stage_stats,
        successRate=round(success_rate, 2),
    )


# ── Element Modification SSE Endpoint ──


@app.get("/pipelines/{pipeline_id}/element-modify-stream")
async def element_modify_stream_endpoint(
    pipeline_id: str,
    element_info: str = "",
    change_request: str = "",
):
    """SSE endpoint for element-level conversational modification."""
    import json as _json
    from urllib.parse import unquote

    pipeline = store.get(pipeline_id)

    if not change_request.strip():
        return StreamingResponse(
            iter(["event: fail\ndata: 修改请求不能为空\n\n"]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    try:
        info = _json.loads(unquote(element_info))
    except (ValueError, _json.JSONDecodeError):
        return StreamingResponse(
            iter(["event: fail\ndata: 元素信息格式不正确\n\n"]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    async def event_stream():
        async for event in stream_element_modification(pipeline, info, change_request):
            yield event
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


# ── Frontend static file serving ──

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FRONTEND_EXTENSIONS = {".html", ".css", ".js"}


@app.get("/")
async def serve_index():
    return FileResponse(_PROJECT_ROOT / "index.html")


@app.get("/{file_path:path}")
async def serve_frontend(file_path: str):
    if not file_path:
        return FileResponse(_PROJECT_ROOT / "index.html")
    target = (_PROJECT_ROOT / file_path).resolve()
    # Security: ensure target is under project root
    try:
        target.relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=404)
    if not target.is_file():
        raise HTTPException(status_code=404)
    if target.suffix.lower() not in _FRONTEND_EXTENSIONS:
        raise HTTPException(status_code=404)
    return FileResponse(target)
