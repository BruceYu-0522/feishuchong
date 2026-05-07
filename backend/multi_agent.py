"""Multi-Agent Collaboration: run multiple LLM agents in parallel for the same stage
and aggregate their results into a single artifact.

Currently configured for the "review" stage with 3 parallel reviewers:
  - 正确性审查 (Correctness)
  - 安全性审查 (Security)
  - 规范性审查 (Style)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import AsyncGenerator

import backend.llm_runner as llm_runner
from backend.schemas import Pipeline, Stage
from backend.skills import read_skill

MULTI_AGENT_CONFIG = {
    "review": {
        "agents": [
            {
                "id": "review-correctness",
                "name": "正确性审查",
                "suffix": (
                    "\n\n## 审查重点\n"
                    "请重点从正确性角度审查：\n"
                    "1. 代码是否满足需求描述中的功能要求\n"
                    "2. 业务逻辑是否正确、完整\n"
                    "3. 边界情况和异常处理是否到位\n"
                    "4. 验收标准是否被满足"
                ),
            },
            {
                "id": "review-security",
                "name": "安全性审查",
                "suffix": (
                    "\n\n## 审查重点\n"
                    "请重点从安全性角度审查：\n"
                    "1. 是否存在 XSS 漏洞（未转义的用户输入插入 DOM）\n"
                    "2. 是否存在注入风险（eval、innerHTML 等）\n"
                    "3. 是否存在敏感信息泄露（API Key、密码等）\n"
                    "4. 第三方依赖是否安全可控"
                ),
            },
            {
                "id": "review-style",
                "name": "规范性审查",
                "suffix": (
                    "\n\n## 审查重点\n"
                    "请重点从规范性角度审查：\n"
                    "1. 代码风格是否一致（缩进、命名、注释）\n"
                    "2. 函数和变量命名是否语义清晰\n"
                    "3. 是否有明显的性能问题（内存泄漏、不必要的重渲染等）\n"
                    "4. 代码结构是否清晰、可维护"
                ),
            },
        ],
        "synthesizer_prompt": (
            "你是代码评审汇总专家。请将以下多份独立审查报告整合为一份综合评审报告。\n\n"
            "**重要：这些报告来自 3 个独立的 AI Agent（正确性审查 Agent、安全性审查 Agent、规范性审查 Agent），"
            "它们并行工作，各自从不同维度审查同一份代码。你的汇总报告必须体现多 Agent 协作的特征。**\n\n"
            "要求：\n"
            "- 用中文输出\n"
            "- 结构：\n"
            "  ## 多 Agent 并行评审汇总\n\n"
            "  ## 评审结论\n  建议交付 / 需要修改（二选一，给出明确结论）\n\n"
            "  ## ✅ 正确性审查 Agent 发现\n  提炼正确性审查的关键发现\n\n"
            "  ## 🔒 安全性审查 Agent 发现\n  提炼安全性审查的关键发现\n\n"
            "  ## 📐 规范性审查 Agent 发现\n  提炼规范性审查的关键发现\n\n"
            "  ## 风险汇总\n  合并所有报告中提到的风险点\n\n"
            "  ## 改进建议\n  合并所有改进建议，按优先级排列\n\n"
            "- 每个章节开头注明来源 Agent（如「正确性审查 Agent 指出…」）\n"
            "- 不要遗漏任何报告中标记为严重或高危的问题\n"
            "- 如果所有报告都认为代码质量良好，评审结论应为「建议交付」"
        ),
    },
}


def is_multi_agent_stage(stage_id: str) -> bool:
    return stage_id in MULTI_AGENT_CONFIG


def _run_single_agent(stage: Stage, pipeline: Pipeline, agent_spec: dict) -> tuple[str, str] | None:
    """Run one agent with a customised system prompt. Returns (content, model) or None."""
    base_prompt = llm_runner.STAGE_SYSTEM_PROMPTS.get(
        stage.id,
        "你是 DevFlow Engine 中的研发流程 Agent。请严格围绕当前阶段输出。",
    )
    skill_text = read_skill(stage.id)
    system_prompt = base_prompt + agent_spec["suffix"]
    if skill_text and len(skill_text) > 50:
        system_prompt += f"\n\n工作规范（Skill）：\n{skill_text[:2000]}"

    payload = {
        "model": llm_runner.MODEL_ROUTER[stage.id],
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"当前阶段：{stage.name} — {agent_spec['name']}\n"
                    f"用户原始需求：{pipeline.requirement}\n\n"
                    f"{llm_runner.build_context(pipeline)}\n\n"
                    f"请从「{agent_spec['name']}」的角度输出审查结果，用中文，结构清晰。"
                ),
            },
        ],
        "temperature": 0.3,
    }

    try:
        response = llm_runner.post_chat_completion(payload, stage.id)
        content = llm_runner.extract_content(response)
        if content:
            return content, payload["model"]
    except Exception:
        pass

    return None


def _fallback_merge(results: list[tuple[str, str]]) -> str:
    """Concatenate results directly when synthesis fails."""
    parts = [
        "## 多 Agent 并行评审报告",
        "",
        f"本次评审由 {len(results)} 个独立 AI Agent 并行审查，各自从不同维度（正确性、安全性、规范性）"
        "对代码进行独立评估。以下是各 Agent 的完整评审结果：",
        "",
        "> 💡 每个 Agent 使用相同的代码但不同的审查视角（System Prompt），确保审查覆盖全面。",
        "",
    ]
    emoji_map = {
        "正确性审查": "✅",
        "安全性审查": "🔒",
        "规范性审查": "📐",
    }
    for agent_name, content in results:
        emoji = emoji_map.get(agent_name, "📋")
        parts.append(f"---\n## {emoji} Agent: {agent_name}\n{content}\n")
    return "\n".join(parts)


def _try_synthesize(stage_id: str, results: list[tuple[str, str]]) -> str:
    """Try using a synthesizer LLM call to merge results; fall back to direct merge."""
    config = MULTI_AGENT_CONFIG.get(stage_id)
    if not config or len(results) <= 1:
        return _fallback_merge(results)

    reports_block = "\n\n---\n\n".join(
        f"### {agent_name}\n{content}" for agent_name, content in results
    )
    payload = {
        "model": llm_runner.MODEL_ROUTER.get(stage_id, "deepseek-v4-flash"),
        "messages": [
            {"role": "system", "content": config["synthesizer_prompt"]},
            {"role": "user", "content": f"以下是 {len(results)} 份独立审查报告，请整合：\n\n{reports_block}"},
        ],
        "temperature": 0.2,
    }

    try:
        response = llm_runner.post_chat_completion(payload, stage_id)
        content = llm_runner.extract_content(response)
        if content and len(content) > 50:
            return content
    except Exception:
        pass

    return _fallback_merge(results)


def run_multi_agent_stage(stage: Stage, pipeline: Pipeline) -> tuple[str, str] | None:
    """Run multiple agents in parallel and aggregate their output.

    Returns (aggregated_content, model_name) or None if all agents fail.
    """
    config = MULTI_AGENT_CONFIG.get(stage.id)
    if not config:
        return None

    agents = config["agents"]
    model = llm_runner.MODEL_ROUTER.get(stage.id, "unknown")

    results: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=len(agents)) as executor:
        futures = {
            executor.submit(_run_single_agent, stage, pipeline, agent_spec): agent_spec
            for agent_spec in agents
        }
        for future in as_completed(futures):
            agent_spec = futures[future]
            try:
                result = future.result()
                if result:
                    content, _ = result
                    results.append((agent_spec["name"], content))
            except Exception:
                pass

    if not results:
        return None

    aggregated = _try_synthesize(stage.id, results)
    return aggregated, model


async def stream_multi_agent_stage(stage: Stage, pipeline: Pipeline) -> AsyncGenerator[str, None]:
    """Streaming variant: runs agents in parallel via thread pool, yielding progress events.

    Yields SSE-formatted strings:
        event: system  — per-agent progress
        event: result  — final aggregated content
        event: fail    — if all agents fail
    """
    import asyncio
    import json

    config = MULTI_AGENT_CONFIG.get(stage.id)
    if not config:
        yield "event: fail\ndata: 多 Agent 配置缺失\n\n"
        return

    agents = config["agents"]
    model = llm_runner.MODEL_ROUTER.get(stage.id, "unknown")

    yield f"event: stage\ndata: {stage.name}\n\n"
    yield f"event: system\ndata: 启动多 Agent 并行评审（{len(agents)} 个独立 Agent 同时审查，模型 {model}）…\n\n"
    yield f"event: system\ndata: Agent 1️⃣ 正确性审查 · Agent 2️⃣ 安全性审查 · Agent 3️⃣ 规范性审查 同时工作中…\n\n"

    loop = asyncio.get_event_loop()
    results: list[tuple[str, str]] = []

    # Submit all agents to thread pool
    agent_futures = []
    for agent_spec in agents:
        yield f"event: system\ndata: {agent_spec['name']} 审查中…\n\n"
        future = loop.run_in_executor(
            None, _run_single_agent, stage, pipeline, agent_spec
        )
        agent_futures.append((agent_spec, future))

    # Wait for each to complete and report
    for agent_spec, future in agent_futures:
        try:
            result = await future
            if result:
                content, _ = result
                results.append((agent_spec["name"], content))
                yield f"event: system\ndata: {agent_spec['name']} 完成（{len(content)} 字符）\n\n"
            else:
                yield f"event: system\ndata: {agent_spec['name']} 未返回有效结果\n\n"
        except Exception:
            yield f"event: system\ndata: {agent_spec['name']} 执行失败\n\n"

    if not results:
        yield "event: fail\ndata: 所有审查者均未返回有效结果\n\n"
        return

    yield "event: system\ndata: 正在汇总多 Agent 审查结果…\n\n"

    aggregated = _try_synthesize(stage.id, results)
    yield f"event: system\ndata: 已接收汇总结果（{len(aggregated)} 字符），正在处理产物…\n\n"
    yield f"event: result\ndata: {json.dumps({'content': aggregated, 'model': model})}\n\n"
