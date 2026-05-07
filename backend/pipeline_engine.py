import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import HTTPException

from backend.code_executor import apply_llm_code_patch, apply_llm_test_patch
from backend.llm_runner import (
    MODEL_ROUTER,
    generate_requirement_prototype,
    generate_visual_plan,
    run_llm_agent,
    run_llm_agent_with_metrics,
    stream_llm_agent,
)
from backend.multi_agent import (
    is_multi_agent_stage,
    run_multi_agent_stage,
    stream_multi_agent_stage,
)
from pathlib import Path

from backend.code_executor import RUNS_DIR
from backend.code_indexer import CodeIndex
from backend.git_manager import (
    commit_changes,
    create_devflow_branch,
    ensure_git_repo,
    get_branch_name,
    get_diff_summary,
    get_git_status_for_display,
)
from backend.schemas import Artifact, Pipeline, ReviewRecord, ReviewRequest, Stage
from backend.skills import get_skill_info


PIPELINE_TEMPLATES = {
    "feature": {
        "name": "新功能",
        "stages": [
            ("requirement", "需求分析", "需求分析 Agent", True),
            ("design", "方案设计", "方案设计 Agent", True),
            ("code", "代码生成", "代码生成 Agent", True),
            ("test", "测试生成", "测试生成 Agent", True),
            ("review", "代码评审", "代码评审 Agent", True),
            ("delivery", "交付总结", "交付总结 Agent", True),
        ],
    },
    "bugfix": {
        "name": "Bug修复",
        "stages": [
            ("code", "代码生成", "代码生成 Agent", True),
            ("test", "测试生成", "测试生成 Agent", True),
            ("review", "代码评审", "代码评审 Agent", True),
            ("delivery", "交付总结", "交付总结 Agent", True),
        ],
    },
    "refactor": {
        "name": "重构",
        "stages": [
            ("design", "方案设计", "方案设计 Agent", True),
            ("code", "代码生成", "代码生成 Agent", True),
            ("test", "测试生成", "测试生成 Agent", True),
            ("review", "代码评审", "代码评审 Agent", True),
            ("delivery", "交付总结", "交付总结 Agent", True),
        ],
    },
}

# Legacy alias — STAGE_DEFS points to the feature template's stages
STAGE_DEFS = PIPELINE_TEMPLATES["feature"]["stages"]

STAGE_FILE_NAMES = {
    "requirement": "01-requirement.md",
    "design": "02-design.md",
    "code": "03-code.md",
    "test": "04-test.md",
    "review": "05-review.md",
    "delivery": "06-delivery.md",
}


# In-memory code index cache, keyed by pipeline ID
_code_index_cache: dict[str, CodeIndex] = {}


def get_code_index(pipeline_id: str) -> CodeIndex | None:
    """Return the cached code index for a pipeline, or None."""
    return _code_index_cache.get(pipeline_id)


def build_and_cache_index(pipeline_id: str) -> CodeIndex | None:
    """Build a CodeIndex from pipeline workspace files and cache it."""
    run_root = RUNS_DIR / pipeline_id
    if not run_root.exists():
        return None
    idx = CodeIndex().build(run_root)
    if idx.symbols:
        _code_index_cache[pipeline_id] = idx
    return idx


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_workspace_files(pipeline: Pipeline) -> Path:
    """Save all pipeline artifacts as files in the workspace directory."""
    workspace = RUNS_DIR / pipeline.id / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    for stage_id, artifact in pipeline.artifacts.items():
        if stage_id in STAGE_FILE_NAMES:
            file_path = workspace / STAGE_FILE_NAMES[stage_id]
            file_path.write_text(artifact.content, encoding="utf-8")

        if artifact.prototypeHtml:
            (workspace / "prototype.html").write_text(artifact.prototypeHtml, encoding="utf-8")

    return workspace


def _get_template_stages(template: str) -> list[tuple[str, str, str, bool]]:
    """Return the stage definition list for the given template."""
    t = PIPELINE_TEMPLATES.get(template, PIPELINE_TEMPLATES["feature"])
    return t["stages"]


def build_stages(template: str = "feature") -> list[Stage]:
    return [
        Stage(
            id=stage_id,
            name=name,
            agent=agent,
            approvalRequired=approval_required,
            skill=get_skill_info(stage_id),
        )
        for stage_id, name, agent, approval_required in _get_template_stages(template)
    ]


def stage_index(pipeline: Pipeline, stage_id: str) -> int:
    """Find a stage's index within the pipeline's own stage list."""
    for i, s in enumerate(pipeline.stages):
        if s.id == stage_id:
            return i
    raise ValueError(f"Stage {stage_id} not found in pipeline {pipeline.id}")


def current_stage(pipeline: Pipeline) -> Stage:
    return pipeline.stages[stage_index(pipeline, pipeline.currentStageId)]


def create_pipeline(requirement: str, project_path: str | None = None, template: str = "feature") -> Pipeline:
    clean_requirement = requirement.strip() if requirement and requirement.strip() else ""
    if not clean_requirement:
        raise HTTPException(status_code=422, detail="需求描述不能为空。请输入你想要实现的功能需求。")
    stages = build_stages(template)
    pipeline = Pipeline(
        id=f"df-{uuid4().hex[:10]}",
        requirement=clean_requirement,
        template=template,
        projectPath=project_path.strip() if project_path and project_path.strip() else None,
        status="ready",
        currentStageId=stages[0].id,
        stages=stages,
    )

    # Eagerly build code index when projectPath is set
    if pipeline.projectPath:
        build_and_cache_index(pipeline.id)

    return pipeline


def run_next_stage(pipeline: Pipeline) -> Pipeline:
    if pipeline.status in {"completed", "waiting_review"}:
        return pipeline

    from time import perf_counter

    stage = current_stage(pipeline)
    started_at = now_iso()
    start_perf = perf_counter()

    changed_files = []
    workspace_path = None
    visual_plan = None
    prototype_html = None
    content = ""
    model = ""
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    reasoning_content = ""

    if stage.id == "code":
        result = apply_llm_code_patch(pipeline)
        if not result:
            from backend.code_executor import get_last_code_error
            reason = get_last_code_error() or "未知错误"
            raise HTTPException(
                status_code=503,
                detail=f"代码生成阶段失败：{reason}",
            )
        content = result.content
        model = result.model
        changed_files = result.changed_files
        workspace_path = result.workspace_path

        run_root = RUNS_DIR / pipeline.id
        ensure_git_repo(run_root)
        commit_changes(run_root, f"feat: {pipeline.requirement[:80]}")
        create_devflow_branch(run_root, get_branch_name(pipeline.id))
        build_and_cache_index(pipeline.id)

    elif stage.id == "test":
        result = apply_llm_test_patch(pipeline)
        if not result:
            from backend.code_executor import get_last_code_error
            reason = get_last_code_error() or "未知错误"
            raise HTTPException(
                status_code=503,
                detail=f"测试生成阶段失败：{reason}",
            )
        content = result.content
        model = result.model
        changed_files = result.changed_files
        workspace_path = result.workspace_path

        run_root = RUNS_DIR / pipeline.id
        commit_changes(run_root, f"test: add tests for {pipeline.requirement[:60]}")
        build_and_cache_index(pipeline.id)

    else:
        if is_multi_agent_stage(stage.id):
            llm_result = run_multi_agent_stage(stage, pipeline)
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
            usage = {}
            reasoning_content = ""
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
        else:
            llm_result = run_llm_agent_with_metrics(stage, pipeline)
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
            content, model, usage, reasoning_content = llm_result
            prompt_tokens = usage.get("prompt_tokens", 0) if usage else 0
            completion_tokens = usage.get("completion_tokens", 0) if usage else 0
            total_tokens = usage.get("total_tokens", 0) if usage else 0

        if stage.id == "requirement":
            prototype_html = generate_requirement_prototype(pipeline.requirement, content)
        elif stage.id == "design":
            visual_plan = generate_visual_plan(pipeline.requirement, content)

    completed_at = now_iso()
    latency_ms = int((perf_counter() - start_perf) * 1000)

    pipeline.artifacts[stage.id] = Artifact(
        stageId=stage.id,
        stageName=stage.name,
        agent=stage.agent,
        skill=stage.skill,
        content=content,
        createdAt=completed_at,
        startedAt=started_at,
        completedAt=completed_at,
        latencyMs=latency_ms,
        model=model,
        promptTokens=prompt_tokens,
        completionTokens=completion_tokens,
        totalTokens=total_tokens,
        reasoningContent=reasoning_content,
        changedFiles=changed_files,
        workspacePath=workspace_path,
        visualPlan=visual_plan,
        prototypeHtml=prototype_html,
    )

    save_workspace_files(pipeline)

    if stage.approvalRequired:
        pipeline.status = "waiting_review"
        return pipeline

    if stage.id == "delivery":
        pipeline.status = "completed"
        return pipeline

    pipeline.currentStageId = pipeline.stages[stage_index(pipeline, stage.id) + 1].id
    pipeline.status = "ready"
    return pipeline


def run_until_review(pipeline: Pipeline) -> Pipeline:
    while pipeline.status == "ready":
        run_next_stage(pipeline)
    return pipeline


MAX_REVIEW_RETRIES = 3
MAX_AUTO_REGRESSION_RETRIES = 3

# Keywords that indicate a negative review (should trigger auto-regression)
_AUTO_REJECT_SIGNALS = [
    "需要修改", "不建议交付", "必须修复", "严重问题", "安全漏洞",
    "存在风险", "不可交付", "需要重新", "建议驳回", "不符合要求",
    "代码有误", "逻辑错误", "不通过", "需要调整", "无法正常工作",
    "存在问题", "需要改进", "不建议合并",
]

_AUTO_APPROVE_SIGNALS = [
    "建议交付", "可以交付", "通过评审", "建议通过", "可以合并",
    "代码质量良好", "审查通过", "没有问题",
]


def auto_evaluate_review(review_content: str) -> tuple[bool, str]:
    """Analyze review content for auto-regression decisions.

    Returns (is_approved: bool, feedback: str).
    """
    if not review_content:
        return True, ""

    content_lower = review_content.lower()

    # Check for negative signals
    reject_reasons = []
    for signal in _AUTO_REJECT_SIGNALS:
        if signal in review_content:
            reject_reasons.append(signal)

    # Check for explicit approval signals
    has_approval = any(signal in review_content for signal in _AUTO_APPROVE_SIGNALS)

    if reject_reasons and not has_approval:
        # Extract the context around the first reject signal for feedback
        reason = "、".join(reject_reasons[:3])
        return False, f"自动检测到评审问题：{reason}"

    return True, ""


def run_until_review(pipeline: Pipeline, auto_mode: bool = False) -> Pipeline:
    while pipeline.status == "ready":
        run_next_stage(pipeline)

        if auto_mode and pipeline.status == "waiting_review":
            stage = current_stage(pipeline)
            artifact = pipeline.artifacts.get(stage.id)
            if artifact:
                approved, feedback = auto_evaluate_review(artifact.content)
                if not approved:
                    auto_retries = sum(
                        1 for r in pipeline.reviewHistory
                        if r.stageId == stage.id and r.decision == "reject"
                    )
                    if auto_retries >= MAX_AUTO_REGRESSION_RETRIES:
                        # Force approve after max retries
                        pipeline.reviewHistory.append(ReviewRecord(
                            stageId=stage.id,
                            stageName=stage.name,
                            decision="approve",
                            reason=f"自动回归已达最大重试次数({MAX_AUTO_REGRESSION_RETRIES})，强制通过",
                            createdAt=now_iso(),
                        ))
                    else:
                        # Auto-reject: remove artifacts and reset to code
                        pipeline.reviewHistory.append(ReviewRecord(
                            stageId=stage.id,
                            stageName=stage.name,
                            decision="reject",
                            reason=feedback,
                            createdAt=now_iso(),
                        ))
                        pipeline.artifacts.pop(stage.id, None)
                        if stage.id == "review":
                            pipeline.artifacts.pop("code", None)
                            pipeline.artifacts.pop("test", None)
                            pipeline.currentStageId = "code"
                        pipeline.status = "ready"
                        continue
                # Auto-approve
                pipeline.reviewHistory.append(ReviewRecord(
                    stageId=stage.id,
                    stageName=stage.name,
                    decision="approve",
                    reason="自动通过（auto mode）",
                    createdAt=now_iso(),
                ))
                if stage.id == "delivery":
                    pipeline.status = "completed"
                    return pipeline
                pipeline.currentStageId = pipeline.stages[stage_index(pipeline, stage.id) + 1].id
                pipeline.status = "ready"

    return pipeline


def submit_review(pipeline: Pipeline, request: ReviewRequest) -> Pipeline:
    if pipeline.status != "waiting_review":
        raise HTTPException(status_code=409, detail="当前没有等待审批的阶段")

    reason = (request.reason or "").strip()
    if request.decision == "reject" and not reason:
        raise HTTPException(status_code=422, detail="Reject 必须填写原因")

    stage = current_stage(pipeline)

    # Auto-retry limit: prevent infinite reject→re-generate loops
    if request.decision == "reject" and stage.id == "review":
        review_rejects = sum(
            1 for r in pipeline.reviewHistory
            if r.stageId == "review" and r.decision == "reject"
        )
        if review_rejects >= MAX_REVIEW_RETRIES:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"代码评审已连续驳回 {MAX_REVIEW_RETRIES} 次，已达到最大自动重试次数。"
                    "请选择「通过」以继续流程，或手动修改代码。"
                ),
            )

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
        # Remove the rejected stage's artifact so it will be re-generated
        pipeline.artifacts.pop(stage.id, None)
        # If rejecting review stage, go back to code stage and remove downstream artifacts
        if stage.id == "review":
            pipeline.artifacts.pop("code", None)
            pipeline.artifacts.pop("test", None)
            pipeline.currentStageId = "code"
        pipeline.status = "ready"
        return pipeline

    if stage.id == "delivery":
        pipeline.status = "completed"
        return pipeline

    pipeline.currentStageId = pipeline.stages[stage_index(pipeline, stage.id) + 1].id
    pipeline.status = "ready"
    return pipeline

# ── SSE Streaming Pipeline Runner ──

async def run_until_review_with_stream(pipeline, auto_mode: bool = False):
    """Run pipeline stages with SSE streaming output. Yields SSE-formatted strings."""
    import json
    from time import perf_counter

    while pipeline.status == "ready":
        stage = current_stage(pipeline)
        stage_start_perf = perf_counter()
        stage_started_at = now_iso()

        if stage.id in ("code", "test"):
            model_name = MODEL_ROUTER.get(stage.id, "unknown")
            yield "event: stage\ndata: " + stage.name + "\n\n"
            yield "event: system\ndata: 正在调用 " + model_name + " 模型…\n\n"
            yield "event: system\ndata: 正在执行 " + stage.name + "（非流式）…\n\n"
            try:
                run_next_stage(pipeline)
            except HTTPException as exc:
                yield "event: fail\ndata: " + str(exc.detail) + "\n\n"
                return
            yield "event: system\ndata: " + stage.name + " 执行完成\n\n"

            # Emit stats event
            artifact = pipeline.artifacts.get(stage.id)
            if artifact:
                yield "event: stats\ndata: " + json.dumps({
                    "stageId": artifact.stageId,
                    "stageName": artifact.stageName,
                    "agent": artifact.agent,
                    "model": artifact.model,
                    "status": "completed",
                    "startedAt": artifact.startedAt,
                    "completedAt": artifact.completedAt,
                    "latencyMs": artifact.latencyMs,
                    "promptTokens": artifact.promptTokens,
                    "completionTokens": artifact.completionTokens,
                    "totalTokens": artifact.totalTokens,
                    "attempt": artifact.attempt,
                }) + "\n\n"
        else:
            full_content = ""
            result_model = ""
            stream_usage = {}
            if is_multi_agent_stage(stage.id):
                async for sse_event in stream_multi_agent_stage(stage, pipeline):
                    yield sse_event
                    if sse_event.startswith("event: result\ndata: "):
                        try:
                            data_str = sse_event[len("event: result\ndata: "):].strip()
                            result = json.loads(data_str)
                            full_content = result.get("content", "")
                            result_model = result.get("model", "")
                            if "usage" in result:
                                stream_usage = result["usage"]
                        except (json.JSONDecodeError, KeyError):
                            pass
            else:
                async for sse_event in stream_llm_agent(stage, pipeline):
                    yield sse_event
                    if sse_event.startswith("event: result\ndata: "):
                        try:
                            data_str = sse_event[len("event: result\ndata: "):].strip()
                            result = json.loads(data_str)
                            full_content = result.get("content", "")
                            result_model = result.get("model", "")
                            if "usage" in result:
                                stream_usage = result["usage"]
                        except (json.JSONDecodeError, KeyError):
                            pass

            if not full_content:
                yield "event: fail\ndata: LLM 返回了空内容\n\n"
                return

            prototype_html = None
            visual_plan = None

            if stage.id == "requirement":
                yield "event: system\ndata: 渲染 Markdown 格式…\n\n"
                prototype_html = generate_requirement_prototype(pipeline.requirement, full_content)
                if prototype_html:
                    yield "event: system\ndata: 原型 HTML 生成完成\n\n"
            elif stage.id == "design":
                yield "event: system\ndata: 正在生成方案蓝图…\n\n"
                visual_plan = generate_visual_plan(pipeline.requirement, full_content)
                if visual_plan:
                    yield "event: system\ndata: 方案蓝图生成完成\n\n"

            stage_completed_at = now_iso()
            stage_latency_ms = int((perf_counter() - stage_start_perf) * 1000)
            s_prompt_tokens = stream_usage.get("prompt_tokens", 0) if stream_usage else 0
            s_comp_tokens = stream_usage.get("completion_tokens", 0) if stream_usage else 0
            s_total_tokens = stream_usage.get("total_tokens", 0) if stream_usage else 0

            pipeline.artifacts[stage.id] = Artifact(
                stageId=stage.id,
                stageName=stage.name,
                agent=stage.agent,
                skill=stage.skill,
                content=full_content,
                createdAt=stage_completed_at,
                startedAt=stage_started_at,
                completedAt=stage_completed_at,
                latencyMs=stage_latency_ms,
                model=result_model or "unknown",
                promptTokens=s_prompt_tokens,
                completionTokens=s_comp_tokens,
                totalTokens=s_total_tokens,
                changedFiles=[],
                workspacePath=None,
                visualPlan=visual_plan,
                prototypeHtml=prototype_html,
            )

            save_workspace_files(pipeline)

            save_workspace_files(pipeline)

            # Emit stats event for streaming stages
            yield "event: stats\ndata: " + json.dumps({
                "stageId": stage.id,
                "stageName": stage.name,
                "agent": stage.agent,
                "model": result_model or "unknown",
                "status": "completed",
                "startedAt": stage_started_at,
                "completedAt": stage_completed_at,
                "latencyMs": stage_latency_ms,
                "promptTokens": s_prompt_tokens,
                "completionTokens": s_comp_tokens,
                "totalTokens": s_total_tokens,
                "attempt": 1,
            }) + "\n\n"

        if stage.approvalRequired and not auto_mode:
            pipeline.status = "waiting_review"
            yield "event: system\ndata: " + stage.name + " 完成，等待你的确认\n\n"
            yield "event: done\ndata: \n\n"
            return

        if stage.approvalRequired and auto_mode:
            # Auto-evaluate review content
            artifact = pipeline.artifacts.get(stage.id)
            approved, feedback = auto_evaluate_review(artifact.content if artifact else "")

            if not approved:
                auto_retries = sum(
                    1 for r in pipeline.reviewHistory
                    if r.stageId == stage.id and r.decision == "reject"
                )
                if auto_retries >= MAX_AUTO_REGRESSION_RETRIES:
                    yield f"event: system\ndata: 自动回归已达最大重试次数({MAX_AUTO_REGRESSION_RETRIES})，强制通过\n\n"
                    pipeline.reviewHistory.append(ReviewRecord(
                        stageId=stage.id,
                        stageName=stage.name,
                        decision="approve",
                        reason=f"自动回归已达最大重试次数({MAX_AUTO_REGRESSION_RETRIES})，强制通过",
                        createdAt=now_iso(),
                    ))
                else:
                    retry_num = auto_retries + 1
                    yield f"event: auto_regression\ndata: {json.dumps({'retry': retry_num, 'maxRetries': MAX_AUTO_REGRESSION_RETRIES, 'reason': feedback, 'stageName': stage.name})}\n\n"
                    yield f"event: system\ndata: 检测到评审问题（{feedback}），自动打回重新生成（{retry_num}/{MAX_AUTO_REGRESSION_RETRIES}）\n\n"
                    pipeline.reviewHistory.append(ReviewRecord(
                        stageId=stage.id,
                        stageName=stage.name,
                        decision="reject",
                        reason=feedback,
                        createdAt=now_iso(),
                    ))
                    pipeline.artifacts.pop(stage.id, None)
                    if stage.id == "review":
                        pipeline.artifacts.pop("code", None)
                        pipeline.artifacts.pop("test", None)
                        pipeline.currentStageId = "code"
                    pipeline.status = "ready"
                    continue
            else:
                pipeline.reviewHistory.append(ReviewRecord(
                    stageId=stage.id,
                    stageName=stage.name,
                    decision="approve",
                    reason="自动通过（auto mode）",
                    createdAt=now_iso(),
                ))

        if stage.id == "delivery":
            pipeline.status = "completed"
            yield "event: system\ndata: 全部阶段完成！\n\n"
            yield "event: done\ndata: \n\n"
            return

        pipeline.currentStageId = pipeline.stages[stage_index(pipeline, stage.id) + 1].id

    yield "event: done\ndata: \n\n"


# ── Element Modification SSE ──

async def stream_element_modification(
    pipeline: Pipeline,
    element_info: dict,
    change_request: str,
) -> AsyncGenerator[str, None]:
    """Stream element-level code modification via LLM. Yields SSE-formatted strings."""
    from backend.code_executor import validate_patch_payload
    from backend.git_manager import commit_changes
    from backend.llm_runner import stream_element_modification_llm

    iframe_type = element_info.get("iframeType", "product")
    source_file = element_info.get("sourceFile", "index.html")

    if iframe_type == "prototype":
        req_artifact = pipeline.artifacts.get("requirement")
        if not req_artifact or not req_artifact.prototypeHtml:
            yield "event: fail\ndata: 原型 HTML 不存在，请先运行需求分析阶段\n\n"
            return

        file_content = req_artifact.prototypeHtml
        file_path = "prototype.html"

        async for sse_event in stream_element_modification_llm(
            element_info, change_request, file_content, file_path, iframe_type
        ):
            if sse_event.startswith("event: result\ndata: "):
                data_str = sse_event[len("event: result\ndata: "):].strip()
                try:
                    result_data = json.loads(data_str)
                    new_html = result_data.get("content", "")
                    req_artifact.prototypeHtml = new_html
                    yield f"event: system\ndata: 原型 HTML 已更新\n\n"
                    yield f"event: result\ndata: {json.dumps({'file': 'prototype.html', 'prototypeHtml': new_html})}\n\n"
                except (json.JSONDecodeError, KeyError):
                    yield "event: fail\ndata: 解析修改结果失败\n\n"
            else:
                yield sse_event

    else:
        run_root = RUNS_DIR / pipeline.id
        target_file = (run_root / "target-app" / source_file).resolve()
        run_root_resolved = run_root.resolve()

        if run_root_resolved not in [target_file, *target_file.parents]:
            yield "event: fail\ndata: 文件路径不安全\n\n"
            return

        if not target_file.exists():
            yield f"event: fail\ndata: 目标文件 {source_file} 不存在\n\n"
            return

        file_content = target_file.read_text(encoding="utf-8", errors="replace")

        commit_hash = None
        async for sse_event in stream_element_modification_llm(
            element_info, change_request, file_content, source_file, iframe_type
        ):
            if sse_event.startswith("event: result\ndata: "):
                data_str = sse_event[len("event: result\ndata: "):].strip()
                try:
                    result_data = json.loads(data_str)
                    new_content = result_data.get("content", "")

                    rel_path = target_file.relative_to(run_root_resolved).as_posix()
                    validated = validate_patch_payload(
                        {"files": [{"path": rel_path, "content": new_content}]},
                        run_root_resolved,
                    )
                    if not validated:
                        yield "event: fail\ndata: 文件校验失败\n\n"
                        return

                    target_file.write_text(new_content, encoding="utf-8", errors="replace")
                    yield f"event: system\ndata: 文件 {source_file} 已更新\n\n"

                    try:
                        commit_hash = commit_changes(
                            run_root, f"edit: modify {source_file} - {change_request[:60]}"
                        )
                        if commit_hash:
                            yield f"event: system\ndata: Git 提交成功 ({commit_hash[:7]})\n\n"
                    except Exception:
                        yield "event: system\ndata: Git 提交失败，文件修改已生效\n\n"

                    yield f"event: result\ndata: {json.dumps({'file': source_file, 'commit': commit_hash})}\n\n"
                except (json.JSONDecodeError, KeyError):
                    yield "event: fail\ndata: 解析修改结果失败\n\n"
            else:
                yield sse_event

    yield "event: done\ndata: \n\n"