from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.mock_agents import run_mock_agent
from backend.schemas import Artifact, Pipeline, ReviewRecord, ReviewRequest, Stage
from backend.skills import get_skill_info


DEFAULT_REQUIREMENT = "给任务管理系统增加按优先级筛选任务的功能"


STAGE_DEFS = [
    ("requirement", "需求分析", "需求分析 Agent", False),
    ("design", "方案设计", "方案设计 Agent", True),
    ("code", "代码生成", "代码生成 Agent", False),
    ("test", "测试生成", "测试生成 Agent", False),
    ("review", "代码评审", "代码评审 Agent", True),
    ("delivery", "交付总结", "交付总结 Agent", False),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_stages() -> list[Stage]:
    return [
        Stage(
            id=stage_id,
            name=name,
            agent=agent,
            approvalRequired=approval_required,
            skill=get_skill_info(stage_id),
        )
        for stage_id, name, agent, approval_required in STAGE_DEFS
    ]


def stage_index(stage_id: str) -> int:
    return next(index for index, stage in enumerate(STAGE_DEFS) if stage[0] == stage_id)


def current_stage(pipeline: Pipeline) -> Stage:
    return pipeline.stages[stage_index(pipeline.currentStageId)]


def create_pipeline(requirement: str) -> Pipeline:
    clean_requirement = requirement.strip() if requirement and requirement.strip() else DEFAULT_REQUIREMENT
    return Pipeline(
        id=f"df-{uuid4().hex[:10]}",
        requirement=clean_requirement,
        status="ready",
        currentStageId="requirement",
        stages=build_stages(),
    )


def run_next_stage(pipeline: Pipeline) -> Pipeline:
    if pipeline.status in {"completed", "waiting_review"}:
        return pipeline

    stage = current_stage(pipeline)
    content = run_mock_agent(stage.id, pipeline)
    pipeline.artifacts[stage.id] = Artifact(
        stageId=stage.id,
        stageName=stage.name,
        agent=stage.agent,
        skill=stage.skill,
        content=content,
        createdAt=now_iso(),
    )

    if stage.approvalRequired:
        pipeline.status = "waiting_review"
        return pipeline

    if stage.id == "delivery":
        pipeline.status = "completed"
        return pipeline

    pipeline.currentStageId = pipeline.stages[stage_index(stage.id) + 1].id
    pipeline.status = "ready"
    return pipeline


def run_until_review(pipeline: Pipeline) -> Pipeline:
    while pipeline.status == "ready":
        run_next_stage(pipeline)
    return pipeline


def submit_review(pipeline: Pipeline, request: ReviewRequest) -> Pipeline:
    if pipeline.status != "waiting_review":
        raise HTTPException(status_code=409, detail="当前没有等待审批的阶段")

    reason = (request.reason or "").strip()
    if request.decision == "reject" and not reason:
        raise HTTPException(status_code=422, detail="Reject 必须填写原因")

    stage = current_stage(pipeline)
    pipeline.reviewHistory.append(
        ReviewRecord(
            stageId=stage.id,
            stageName=stage.name,
            decision=request.decision,
            reason=reason,
            createdAt=now_iso(),
        )
    )

    if request.decision == "reject":
        pipeline.status = "ready"
        return pipeline

    pipeline.currentStageId = pipeline.stages[stage_index(stage.id) + 1].id
    pipeline.status = "ready"
    return pipeline
