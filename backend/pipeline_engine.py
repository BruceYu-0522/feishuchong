from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import HTTPException

from backend.code_executor import apply_llm_code_patch, apply_llm_test_patch
from backend.llm_runner import (
    generate_prd_image,
    generate_prd_mermaid,
    generate_requirement_prototype,
    generate_visual_plan,
    run_llm_agent,
    stream_llm_agent,
)
from backend.schemas import Artifact, Pipeline, ReviewRecord, ReviewRequest, Stage
from backend.skills import get_skill_info


STAGE_DEFS = [
    ("requirement", "需求分析", "需求分析 Agent", True),
    ("design", "方案设计", "方案设计 Agent", True),
    ("code", "代码生成", "代码生成 Agent", True),
    ("test", "测试生成", "测试生成 Agent", True),
    ("review", "代码评审", "代码评审 Agent", True),
    ("delivery", "交付总结", "交付总结 Agent", True),
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


def create_pipeline(requirement: str, project_path: str | None = None) -> Pipeline:
    clean_requirement = requirement.strip() if requirement and requirement.strip() else ""
    if not clean_requirement:
        raise HTTPException(status_code=422, detail="需求描述不能为空。请输入你想要实现的功能需求。")
    return Pipeline(
        id=f"df-{uuid4().hex[:10]}",
        requirement=clean_requirement,
        projectPath=project_path.strip() if project_path and project_path.strip() else None,
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
    visual_plan = None
    prototype_html = None
    mermaid_code = None
    prd_image_url = None
    content = ""
    model = ""

    if stage.id == "code":
        result = apply_llm_code_patch(pipeline)
        if not result:
            raise HTTPException(
                status_code=503,
                detail=(
                    "代码生成阶段需要大模型支持。请确认：\n"
                    "1. 已设置环境变量 DEVFLOW_LLM_ENABLED=true\n"
                    "2. 已设置 DEVFLOW_LLM_API_KEY\n"
                    "3. DEVFLOW_LLM_BASE_URL 指向有效的 API 端点"
                ),
            )
        content = result.content
        model = result.model
        changed_files = result.changed_files
        workspace_path = result.workspace_path

    elif stage.id == "test":
        result = apply_llm_test_patch(pipeline)
        if not result:
            raise HTTPException(
                status_code=503,
                detail=(
                    "测试生成阶段需要大模型支持。请确认：\n"
                    "1. 已设置环境变量 DEVFLOW_LLM_ENABLED=true\n"
                    "2. 已设置 DEVFLOW_LLM_API_KEY\n"
                    "3. 代码生成阶段已成功完成"
                ),
            )
        content = result.content
        model = result.model
        changed_files = result.changed_files
        workspace_path = result.workspace_path

    else:
        llm_result = run_llm_agent(stage, pipeline)
        if not llm_result:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{stage.agent} 需要大模型支持但返回了空内容。请确认：\n"
                    "1. 已设置环境变量 DEVFLOW_LLM_ENABLED=true\n"
                    "2. 已设置 DEVFLOW_LLM_API_KEY\n"
                    "3. DEVFLOW_LLM_BASE_URL 指向有效的 API 端点"
                ),
            )
        content, model = llm_result

        if stage.id == "requirement":
            prototype_html = generate_requirement_prototype(pipeline.requirement, content)

            # Generate Mermaid mindmap from PRD
            mermaid_result = generate_prd_mermaid(pipeline.requirement, content)
            if mermaid_result:
                mermaid_code = mermaid_result.get("code")

            # If Mermaid failed, try image generation as fallback
            if not mermaid_code:
                prd_image_url = generate_prd_image(pipeline.requirement, content)
        elif stage.id == "design":
            visual_plan = generate_visual_plan(pipeline.requirement, content)

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
        visualPlan=visual_plan,
        prototypeHtml=prototype_html,
        mermaidCode=mermaid_code,
        prdImageUrl=prd_image_url,
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

    if stage.id == "delivery":
        pipeline.status = "completed"
        return pipeline

    pipeline.currentStageId = pipeline.stages[stage_index(stage.id) + 1].id
    pipeline.status = "ready"
    return pipeline

# ── SSE Streaming Pipeline Runner ──

async def run_until_review_with_stream(pipeline):
    """Run pipeline stages with SSE streaming output. Yields SSE-formatted strings."""
    while pipeline.status == "ready":
        stage = current_stage(pipeline)

        if stage.id in ("code", "test"):
            yield "event: stage\ndata: " + stage.name + "\n\n"
            yield "event: system\ndata: 正在执行 " + stage.name + "（非流式）…\n\n"
            try:
                run_next_stage(pipeline)
            except HTTPException as exc:
                yield "event: error\ndata: " + str(exc.detail) + "\n\n"
                return
            yield "event: system\ndata: " + stage.name + " 执行完成\n\n"
        else:
            full_content = ""
            result_model = ""
            async for sse_event in stream_llm_agent(stage, pipeline):
                yield sse_event
                if sse_event.startswith("event: result\ndata: "):
                    import json
                    try:
                        data_str = sse_event[len("event: result\ndata: "):].strip()
                        result = json.loads(data_str)
                        full_content = result.get("content", "")
                        result_model = result.get("model", "")
                    except (json.JSONDecodeError, KeyError):
                        pass

            if not full_content:
                yield "event: error\ndata: LLM 返回了空内容\n\n"
                return

            prototype_html = None
            visual_plan = None
            mermaid_code = None
            prd_image_url = None

            if stage.id == "requirement":
                yield "event: system\ndata: 渲染 Markdown 格式…\n\n"
                prototype_html = generate_requirement_prototype(pipeline.requirement, full_content)
                if prototype_html:
                    yield "event: system\ndata: 原型 HTML 生成完成\n\n"
                yield "event: system\ndata: 正在生成 PRD 思维导图…\n\n"
                mermaid_result = generate_prd_mermaid(pipeline.requirement, full_content)
                if mermaid_result:
                    mermaid_code = mermaid_result.get("code")
                    yield "event: system\ndata: 思维导图生成完成\n\n"
                else:
                    yield "event: system\ndata: 思维导图生成失败，尝试 AI 生图…\n\n"
                    prd_image_url = generate_prd_image(pipeline.requirement, full_content)
                    if prd_image_url:
                        yield "event: system\ndata: PRD 图示生成完成\n\n"
                    else:
                        yield "event: system\ndata: PRD 图示生成失败，跳过\n\n"
            elif stage.id == "design":
                yield "event: system\ndata: 正在生成方案蓝图…\n\n"
                visual_plan = generate_visual_plan(pipeline.requirement, full_content)
                if visual_plan:
                    yield "event: system\ndata: 方案蓝图生成完成\n\n"

            pipeline.artifacts[stage.id] = Artifact(
                stageId=stage.id,
                stageName=stage.name,
                agent=stage.agent,
                skill=stage.skill,
                content=full_content,
                createdAt=now_iso(),
                model=result_model or "unknown",
                changedFiles=[],
                workspacePath=None,
                visualPlan=visual_plan,
                prototypeHtml=prototype_html,
                mermaidCode=mermaid_code,
                prdImageUrl=prd_image_url,
            )

        if stage.approvalRequired:
            pipeline.status = "waiting_review"
            yield "event: system\ndata: " + stage.name + " 完成，等待你的确认\n\n"
            yield "event: done\ndata: \n\n"
            return

        if stage.id == "delivery":
            pipeline.status = "completed"
            yield "event: system\ndata: 全部阶段完成！\n\n"
            yield "event: done\ndata: \n\n"
            return

        pipeline.currentStageId = pipeline.stages[stage_index(stage.id) + 1].id

    yield "event: done\ndata: \n\n"