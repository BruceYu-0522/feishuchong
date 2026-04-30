from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.pipeline_engine import create_pipeline, run_next_stage, run_until_review, submit_review
from backend.schemas import CreatePipelineRequest, Pipeline, ReviewRequest
from backend.storage import store


app = FastAPI(
    title="DevFlow Engine API",
    description="AI 研发流程引擎的 API-first 后端雏形，当前使用 Mock Agent 跑通 Pipeline 闭环。",
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
    return store.save(create_pipeline(request.requirement))


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


@app.post("/pipelines/{pipeline_id}/review", response_model=Pipeline)
def review_endpoint(pipeline_id: str, request: ReviewRequest) -> Pipeline:
    pipeline = store.get(pipeline_id)
    return store.save(submit_review(pipeline, request))
