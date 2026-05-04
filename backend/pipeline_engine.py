from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.code_executor import add_priority_filter_tests, apply_priority_filter_change
from backend.llm_runner import run_llm_agent
from backend.mock_agents import run_mock_agent
from backend.schemas import Artifact, Pipeline, ReviewRecord, ReviewRequest, Stage
from backend.skills import get_skill_info


DEFAULT_REQUIREMENT = "给任务管理系统增加按优先级筛选任务的功能"
PENCIL_SKETCH_PATH = "docs/pencil/design-blueprint.pen"


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


def design_visual_plan(pipeline: Pipeline) -> dict:
    reject_reason = ""
    for record in reversed(pipeline.reviewHistory):
        if record.stageId == "design" and record.decision == "reject":
            reject_reason = record.reason
            break

    return {
        "title": "优先级筛选方案蓝图",
        "summary": (
            f"本版方案已补充处理：{reject_reason}"
            if reject_reason
            else "从任务数据、筛选控件、列表渲染和空状态四个点完成优先级筛选。"
        ),
        "nodes": [
            {"id": "data", "label": "Task 数据结构", "detail": "新增 priority: high / medium / low"},
            {"id": "toolbar", "label": "筛选控件", "detail": "全部 / 高 / 中 / 低 segmented filter"},
            {"id": "list", "label": "列表过滤", "detail": "按 priorityFilter 过滤任务集合"},
            {"id": "empty", "label": "空状态", "detail": "无匹配任务时提示并提供重置入口"},
        ],
        "edges": [["data", "toolbar"], ["toolbar", "list"], ["list", "empty"]],
        "risks": ["筛选条件需要和搜索、排序共存", "priority 字段需要默认值"],
    }


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
    changed_files = []
    workspace_path = None

    if stage.id == "code":
        code_result = apply_priority_filter_change(pipeline)
        content = code_result.content
        model = "local-code-executor"
        changed_files = code_result.changed_files
        workspace_path = code_result.workspace_path
    elif stage.id == "test":
        test_result = add_priority_filter_tests(pipeline)
        if test_result:
            content = test_result.content
            model = "local-test-generator"
            changed_files = test_result.changed_files
            workspace_path = test_result.workspace_path
        else:
            content = run_mock_agent(stage.id, pipeline)
            model = "mock"
    else:
        llm_result = run_llm_agent(stage, pipeline)
        if llm_result:
            content, model = llm_result
        else:
            content = run_mock_agent(stage.id, pipeline)
            model = "mock"

    pipeline.artifacts[stage.id] = Artifact(
        stageId=stage.id,
        stageName=stage.name,
        agent=stage.agent,
        skill=stage.skill,
        content=content,
        createdAt=now_iso(),
        model=model,
        changedFiles=changed_files,
        workspacePath=workspace_path,
        pencilSketchPath=PENCIL_SKETCH_PATH if stage.id == "design" else None,
        visualPlan=design_visual_plan(pipeline) if stage.id == "design" else None,
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
