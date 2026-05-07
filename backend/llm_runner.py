import asyncio
import json
import os
from typing import Any, AsyncGenerator

import httpx

from backend.schemas import Pipeline, Stage
from backend.skills import read_skill


MODEL_ROUTER = {
    "requirement": "deepseek-v4-flash",
    "design": "gpt-5.4",
    "code": "claude-sonnet-4-5-20250929",
    "test": "deepseek-v4-pro",
    "review": "claude-opus-4-7",
    "delivery": "deepseek-v4-flash",
}

DEFAULT_BASE_URL = "https://api.lingyaai.cn"

STAGE_SYSTEM_PROMPTS = {
    "requirement": (
        "## 输出规则（最高优先级）\n"
        "- 禁止任何形式的问候语、确认语或自我介绍（如'好的'、'收到'、'作为 AI 产品经理'等）\n"
        "- 禁止输出'待澄清问题'章节（澄清已在流程中完成，此处无需重复）\n"
        "- 直接从需求目标或 SCQA 结构化分析开始输出正文\n"
        "- 用简洁、专业的语言，不要任何元描述或流程说明\n\n"
        "## 角色\n"
        "你是 DevFlow Engine 的资深 AI 产品经理，专精于需求澄清、结构化表达和原型设计。\n\n"
        "## 核心方法论：SCQA 框架\n"
        "使用 SCQA（情境-冲突-疑问-答案）框架分析每个需求：\n"
        "- Situation（情境）：识别业务背景、目标用户、使用场景\n"
        "- Complication（冲突）：分析当前痛点、核心矛盾、约束条件\n"
        "- Question（疑问）：提炼需要解决的核心问题\n"
        "- Answer（答案）：给出需求的核心解决思路\n\n"
        "## 主动澄清机制\n"
        "当用户输入缺失以下任一关键要素时，必须在输出开头明确列出「待澄清问题」：\n"
        "- 目标用户是谁？（给谁用，角色画像）\n"
        "- 核心痛点是什么？（解决什么问题）\n"
        "- 期望边界是什么？（绝对不能做什么、哪些由AI自由发挥）\n"
        "每个澄清问题必须附带你的建议方案和备选方案，降低用户决策成本。\n"
        "如果缺失信息会影响核心业务方向，不要假装已经确认；输出「待确认版」需求文档，并建议人类在 Checkpoint 打回补充。\n"
        "对于可以合理推断的内容，标注「推断」标记后继续，不要因小问题阻塞流程，但必须把推断点放入审核关注点。\n\n"
        "## 工作边界\n"
        "- 遇到不确定的方案时，列出 2-3 个选项及各自优劣，严禁编造确定性答案（幻觉）\n"
        "- 不跳入技术实现细节（那是方案设计阶段的事）\n"
        "- 不自行扩大需求范围，除非用户明确授权「AI 自由发挥」\n"
        "- 如果用户提供了 reject 原因，必须在输出中明确说明本次如何针对性改进\n\n"
        "## 输出结构\n"
        "按以下结构用中文直接输出正文：\n"
        "1. 需求目标（一句话说明本次要做什么）\n"
        "2. SCQA 结构化分析（S情境 - C冲突 - Q问题 - A答案，各用1-2句话）\n"
        "3. 需求详情（用户故事、核心功能范围、验收标准用 Given-When-Then 格式、边界情况）\n"
        "4. 原型说明（核心页面布局、关键交互、示意数据）\n"
        "5. 审核关注点（仅列核心业务逻辑是否正确、推断点需确认）\n\n"
        "## 验收标准要求\n"
        "验收标准必须使用 Given-When-Then 格式，确保可观测、可测试。\n"
        "例如：Given 用户在任务列表页，When 点击「高优先级」筛选项，Then 列表仅显示高优先级任务且筛选项高亮。\n\n"
        "## 任务分层原则\n"
        "你是 AI 产品经理，请自主完成以下「粗活」无需逐条确认：\n"
        "- 常规交互流程梳理\n"
        "- 基础数据埋点方案\n"
        "- 竞品功能参考（如适用）\n"
        "- 边缘情况枚举\n"
        "人类只审核「核心业务逻辑是否跑偏」和「验收标准是否合理」。\n\n"
        "## Checkpoint 规则\n"
        "需求分析阶段是人工确认点。你的产物要帮助用户快速做 Approve/Reject：\n"
        "- 如果建议 Approve，说明为什么当前信息足够进入方案设计。\n"
        "- 如果建议 Reject，明确列出用户需要补充的最少信息。\n"
        "- 不要把未确认的关键假设埋在正文里，必须集中列到审核建议中。"
    ),
    "design": (
        "你是 DevFlow Engine 的前端方案设计 Agent，使用 Gemini 模型驱动。"
        "你的职责是基于需求分析结果，设计具体的前端技术实现方案。\n\n"
        "## 设计原则\n"
        "- 专注前端设计：页面结构、组件树、状态管理、UI 交互、样式方案\n"
        "- 产出纯前端可运行代码所需的设计：HTML/CSS/JS 文件结构、关键算法、数据流\n"
        "- 每一个设计决策必须对应至少一个验收标准\n"
        "- 方案必须小到代码阶段可以一次性执行完毕\n\n"
        "## 输出格式要求（请严格遵循）\n"
        "用以下结构输出，每个标题用 ## 开头：\n"
        "## 方案概述\n简要说明整体方案思路，包括要构建什么、核心技术选型（1-2句）\n"
        "## 页面结构\n列出所有页面/视图及其层级关系，标注每个页面的核心 UI 元素\n"
        "## 组件树\n列出核心组件及其嵌套关系、每个组件的 props/状态\n"
        "## 数据与状态\n列出关键数据结构、状态变量、localStorage/sessionStorage 使用\n"
        "## 交互流程\n描述用户操作→系统响应的关键流程，覆盖正常流程+空状态+错误状态\n"
        "## 样式方案\n色彩系统、布局方式（Flex/Grid）、关键 CSS 变量、响应式策略\n"
        "## 文件清单\n列出需要创建或修改的所有文件及各自用途\n"
        "## 风险点\n列出实现中可能遇到的问题和注意事项\n\n"
        "如果历史审批中有驳回原因，在方案概述中说明如何处理。\n"
        "输出内容要具体、可执行，避免泛泛而谈。例如用户要俄罗斯方块，就具体到"
        "棋盘用二维数组、七种方块用坐标矩阵、消行算法如何实现、键盘事件绑定等。"
    ),
    "review": (
        "你是 DevFlow Engine 的代码评审 Agent。你的职责是多维度审查代码变更的质量。"
        "检查：正确性（是否符合需求）、安全性（是否有明显漏洞）、规范性（代码风格是否一致）。"
        "用中文输出，包含评审结论（建议交付/需要修改）、各项检查结果、风险列表、改进建议。"
        "不要因为代码风格偏好而阻塞交付。"
    ),
    "delivery": (
        "你是 DevFlow Engine 的交付总结 Agent。你的职责是整合全部阶段产物，"
        "生成一份完整的交付总结。包含：本次完成的需求、变更摘要、测试摘要、"
        "MR/PR 描述草稿、后续优化建议。用中文输出，面向团队其他成员和 Reviewer。"
    ),
}


def llm_enabled() -> bool:
    return os.getenv("DEVFLOW_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def get_api_key() -> str:
    return os.getenv("DEVFLOW_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def get_base_url() -> str:
    return os.getenv("DEVFLOW_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


# ── Multi-Provider Support ──
# Provider A = primary (existing env vars), Provider B = secondary (opt-in)
# Each stage can be routed to a different provider via STAGE_PROVIDER

STAGE_PROVIDER = {
    "requirement": "a",
    "design": "a",
    "code": "a",
    "test": "a",
    "review": "a",
    "delivery": "a",
}


def _resolve_provider_config(stage_id: str) -> dict:
    """Return {"base_url": str, "api_key": str} for the given stage."""
    provider = os.getenv("DEVFLOW_LLM_PROVIDER", "").strip().lower()
    # Runtime override: if DEVFLOW_LLM_PROVIDER is set (e.g. "b"), all stages use that provider
    if provider and provider in ("a", "b"):
        stage_provider = provider
    else:
        stage_provider = STAGE_PROVIDER.get(stage_id, "a")

    if stage_provider == "b":
        base_url = os.getenv("DEVFLOW_LLM_BASE_URL_B", "").strip().rstrip("/")
        api_key = os.getenv("DEVFLOW_LLM_API_KEY_B", "").strip()
        if base_url and api_key:
            return {"base_url": base_url, "api_key": api_key}
        # Fall back to provider A if B is not configured

    base_url = os.getenv("DEVFLOW_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.getenv("DEVFLOW_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    return {"base_url": base_url, "api_key": api_key}


def get_provider_name(stage_id: str) -> str:
    """Return a human-readable provider name for display."""
    config = _resolve_provider_config(stage_id)
    url = config["base_url"]
    if "lingyaai" in url:
        return "LingYaa AI"
    if "openai" in url:
        return "OpenAI"
    if "deepseek" in url:
        return "DeepSeek"
    # Extract hostname
    try:
        from urllib.parse import urlparse
        host = urlparse(url).hostname or url
        return host[:30]
    except Exception:
        return url[:30]


def build_context(pipeline: Pipeline, stage_id: str = "") -> str:
    """Build a summary of review history and previous stage artifacts for the current stage."""
    from backend.git_manager import get_diff_summary

    parts = []

    if pipeline.reviewHistory:
        review_lines = []
        for record in pipeline.reviewHistory:
            decision_label = "通过" if record.decision == "approve" else "驳回"
            review_lines.append(
                f"- {record.stageName}: {decision_label}"
                + (f"（原因：{record.reason}）" if record.reason else "")
            )
        parts.append("历史审批记录：\n" + "\n".join(review_lines))

    if pipeline.artifacts:
        artifact_lines = []
        for artifact in pipeline.artifacts.values():
            artifact_lines.append(
                f"【{artifact.stageName}】\n{artifact.content[:1500]}"
            )
        parts.append("已有阶段产物：\n\n" + "\n\n".join(artifact_lines))

    # Code index summary for design, code, review, and delivery stages
    if stage_id in ("design", "code", "review", "delivery"):
        try:
            from backend.pipeline_engine import get_code_index
            idx = get_code_index(pipeline.id)
            if idx:
                summary = idx.summary()
                idx_lines = [
                    f"代码索引：{summary['total_files']} 个文件，{summary['total_symbols']} 个符号",
                    f"符号分布：{summary['by_kind']}",
                ]
                # List top files by symbol count
                top_files = sorted(summary["by_file"].items(), key=lambda x: x[1], reverse=True)[:8]
                for fname, count in top_files:
                    key_symbols = [s.name for s in idx.symbols if s.file == fname][:5]
                    idx_lines.append(f"  {fname} ({count} 符号): {', '.join(key_symbols)}")
                parts.append("代码结构索引：\n" + "\n".join(idx_lines))
        except Exception:
            pass

    # Include git diff summary for delivery stage context
    from backend.code_executor import RUNS_DIR
    run_root = RUNS_DIR / pipeline.id
    if (run_root / ".git").exists():
        diff_text = get_diff_summary(run_root)
        if diff_text and diff_text != "暂无 Git 变更信息":
            parts.append(f"Git 变更信息：\n{diff_text[:2000]}")

    return "\n\n".join(parts) if parts else "暂无上下文"


def build_messages(stage: Stage, pipeline: Pipeline) -> list[dict[str, str]]:
    skill_text = read_skill(stage.id)
    system_prompt = STAGE_SYSTEM_PROMPTS.get(
        stage.id,
        "你是 DevFlow Engine 中的研发流程 Agent。请严格围绕当前阶段输出。",
    )

    # Add skill as working specification if it differs from the system prompt
    if skill_text and len(skill_text) > 50:
        system_prompt += (
            f"\n\n工作规范（Skill）：\n{skill_text[:2000]}"
        )

    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": (
                f"当前阶段：{stage.name}\n"
                f"用户原始需求：{pipeline.requirement}\n\n"
                f"{build_context(pipeline, stage.id)}\n\n"
                "请直接输出这一阶段的最终产物，用中文，结构清晰。"
            ),
        },
    ]


def build_payload(stage: Stage, pipeline: Pipeline) -> dict[str, Any]:
    return {
        "model": MODEL_ROUTER[stage.id],
        "messages": build_messages(stage, pipeline),
        "temperature": 0.3,
    }


def post_chat_completion(payload: dict[str, Any], stage_id: str = "") -> dict[str, Any]:
    config = _resolve_provider_config(stage_id)
    response = httpx.post(
        f"{config['base_url']}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def extract_content(response: dict[str, Any]) -> str:
    """Extract the best text content from an LLM response. For backward compat."""
    content, _usage, _reasoning = _parse_response(response)
    return content


def extract_content_and_usage(response: dict[str, Any]) -> tuple[str, dict, str]:
    """Extract content, token usage, and reasoning from an LLM response."""
    return _parse_response(response)


def _parse_response(response: dict[str, Any]) -> tuple[str, dict, str]:
    """Parse LLM response into (content, usage_dict, reasoning_content)."""
    choices = response.get("choices") or []
    if not choices:
        return "", {}, ""
    message = choices[0].get("message") or {}
    content = (message.get("content") or "").strip()
    reasoning = (message.get("reasoning_content") or "").strip()
    usage = response.get("usage") or {}

    # Try each source: content, reasoning, preferring the one with parseable JSON
    best = content  # default to content
    for source in (content, reasoning):
        if not source:
            continue
        if "{" in source or "```" in source:
            best = source
            break

    # If neither has obvious structured output, pick the longer one
    if best == content and len(reasoning) > len(content):
        best = reasoning

    return best, usage, reasoning


def run_llm_agent(stage: Stage, pipeline: Pipeline) -> tuple[str, str] | None:
    """Run single LLM agent. Returns (content, model) for backward compat."""
    if not llm_enabled():
        return None

    config = _resolve_provider_config(stage.id)
    if not config["api_key"]:
        return None

    try:
        payload = build_payload(stage, pipeline)
        response = post_chat_completion(payload, stage.id)
        content, _usage, _reasoning = extract_content_and_usage(response)
    except Exception:
        return None

    if not content:
        return None

    return content, payload["model"]


def run_llm_agent_with_metrics(stage: Stage, pipeline: Pipeline) -> tuple[str, str, dict, str] | None:
    """Run single LLM agent with metrics. Returns (content, model, usage, reasoning)."""
    if not llm_enabled():
        return None

    config = _resolve_provider_config(stage.id)
    if not config["api_key"]:
        return None

    try:
        payload = build_payload(stage, pipeline)
        response = post_chat_completion(payload, stage.id)
        content, usage, reasoning = extract_content_and_usage(response)
    except Exception:
        return None

    if not content:
        return None

    return content, payload["model"], usage, reasoning


def generate_visual_plan(requirement: str, design_text: str) -> dict | None:
    """Use a dedicated LLM call to produce a visual plan JSON from the design text.

    This is a focused, single-purpose call that reads the design document and
    extracts the key architectural decisions into a mind-map-style structure.
    Falls back to None on any failure (no fake template).
    """
    if not llm_enabled() or not get_api_key():
        return None

    system_prompt = (
        "你是一个技术方案可视化专家。你的任务是把一段技术方案文档提炼成思维导图式的结构化 JSON。\n"
        "只输出 JSON，不要 markdown，不要解释。\n\n"
        "JSON 格式：\n"
        '{"title":"方案标题","summary":"一句话总结方案核心思路","nodes":['
        '{"label":"节点标题（简短，≤10字）","detail":"这个节点的具体内容（≤40字）"},...],'
        '"risks":["风险1","风险2",...]}\n\n'
        "规则：\n"
        "- title：根据需求提炼一个具体的方案标题（不是套模板，要体现这个需求的独特之处）\n"
        "- summary：用一句话说清楚这个方案的核心思路是什么\n"
        "- nodes：4-6 个节点，每个节点代表方案中的一个关键设计决策或模块。label 要具体（如'10x20棋盘状态管理'而不是'数据结构'），detail 要写具体做法（如'二维数组board[row][col]存储，0为空1为占用'）\n"
        "- risks：2-4 个实现中需要注意的风险点\n"
        "- 整棵树应该让人一眼看懂这个系统是怎么设计的"
    )

    user_prompt = (
        f"用户需求：{requirement}\n\n"
        f"技术方案文档：\n{design_text[:3000]}\n\n"
        "请把上述方案提炼成思维导图式的 JSON 结构。"
    )

    try:
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        response = post_chat_completion(payload, "design")
        raw = extract_content(response)
    except Exception:
        return None

    if not raw:
        return None

    # Parse JSON from response
    from backend.code_executor import extract_json_object

    plan = extract_json_object(raw)
    if not plan:
        return None

    # Validate required fields
    if not isinstance(plan.get("title"), str) or not isinstance(plan.get("nodes"), list):
        return None
    if len(plan["nodes"]) < 2:
        return None

    # Ensure nodes have label and detail
    for node in plan["nodes"]:
        if not isinstance(node.get("label"), str):
            return None
        node.setdefault("detail", "")

    plan.setdefault("summary", "")
    plan.setdefault("risks", [])

    return plan


def generate_requirement_prototype(requirement: str, analysis_text: str) -> str | None:
    """Generate a low-fidelity HTML prototype from the requirements analysis.

    Makes a focused LLM call to produce a self-contained HTML page that
    visualises the core page layout, key UI elements, and interaction flow
    described in the requirements analysis. Falls back to None on any failure.
    """
    if not llm_enabled() or not get_api_key():
        return None

    system_prompt = (
        "你是一个产品原型设计师。你的任务是根据需求分析文档，生成一个低保真的 HTML 原型页面。\n\n"
        "要求：\n"
        "- 只输出完整的 HTML 代码（含 CSS），不要 markdown 包裹，不要解释\n"
        "- 展示核心页面的骨架布局和关键 UI 元素\n"
        "- 使用低保真风格：灰阶为主、简洁边框、无花哨颜色\n"
        "- 包含关键交互区域的标注（用虚线边框或浅色背景区分可交互区域）\n"
        "- 使用真实的中文示例数据填充，让原型看起来像一个真实产品\n"
        "- 如果需求分析中存在待确认或推断内容，在原型中用文案标注为「待确认」或「推断」\n"
        "- 不要加入需求文档没有要求的产品功能，除非需求分析明确标注为 AI 建议\n"
        "- 响应式设计不是必须的，聚焦桌面端展示\n"
        "- 代码整洁、结构清晰，总长度控制在 500 行以内"
    )

    user_prompt = (
        f"用户需求：{requirement}\n\n"
        f"需求分析文档：\n{analysis_text[:3000]}\n\n"
        "请生成一个低保真 HTML 原型页面，展示这个需求的核心交互和页面布局。"
    )

    try:
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        response = post_chat_completion(payload, "requirement")
        raw = extract_content(response)
    except Exception:
        return None

    if not raw:
        return None

    # Strip markdown code fences if present
    html = raw.strip()
    if html.startswith("```html"):
        html = html[7:]
    elif html.startswith("```"):
        html = html[3:]
    if html.endswith("```"):
        html = html[:-3]
    html = html.strip()

    # Must contain <html> or at least look like HTML
    if "<html" not in html.lower() and "<body" not in html.lower() and "<div" not in html.lower():
        return None

    return html


# ── Streaming LLM ──

async def stream_llm_agent(stage: Stage, pipeline: Pipeline) -> AsyncGenerator[str, None]:
    """Stream the LLM output token-by-token as SSE events.

    Yields:
        "data: <token>" for each text chunk
        "event: system\ndata: <message>" for system operations
        "event: done\ndata: " when complete
        "event: error\ndata: <message>" on failure
    """
    if not llm_enabled():
        yield "event: fail\ndata: LLM 未启用或 API Key 未设置\n\n"
        return

    config = _resolve_provider_config(stage.id)
    if not config["api_key"]:
        yield "event: fail\ndata: LLM API Key 未设置\n\n"
        return

    model_name = MODEL_ROUTER.get(stage.id, "unknown")
    provider_name = get_provider_name(stage.id)
    yield f"event: system\ndata: 正在调用 {model_name} 模型（{provider_name}）…\n\n"
    yield f"event: stage\ndata: {stage.name}\n\n"

    payload = build_payload(stage, pipeline)
    payload["stream"] = True

    full_content = ""
    stream_usage = {}  # token usage from streaming

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{config['base_url']}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        # Capture usage if present in this chunk
                        if "usage" in data:
                            stream_usage = data["usage"]
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            full_content += content
                            yield f"event: chunk\ndata: {content}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    except Exception as exc:
        yield f"event: fail\ndata: LLM 调用失败：{exc}\n\n"
        return

    if not full_content.strip():
        yield "event: fail\ndata: LLM 返回了空内容\n\n"
        return

    # Build result with usage data
    result_data = {"content": full_content, "model": payload["model"]}
    if stream_usage:
        result_data["usage"] = stream_usage

    yield f"event: system\ndata: 已接收 {len(full_content)} 个字符，正在处理产物…\n\n"
    yield f"event: result\ndata: {json.dumps(result_data)}\n\n"


# ── PRD Mermaid Diagram Generation ──

def generate_prd_mermaid(requirement: str, prd_text: str) -> dict | None:
    """Generate a Mermaid mindmap or flowchart from the PRD document.

    Returns:
        dict with 'code' (Mermaid source) and optionally 'svg' (if we could render it)
        None on failure
    """
    if not llm_enabled() or not get_api_key():
        return None

    system_prompt = (
        "你是一个技术文档可视化专家。你的任务是根据 PRD（产品需求文档）生成 Mermaid 格式的思维导图。\n\n"
        "严格要求（必须遵守，否则渲染失败）：\n"
        "- 只输出 Mermaid 代码，不要 markdown 包裹，不要解释\n"
        "- 必须使用 mindmap 格式（不要用 graph、flowchart 等其他格式）\n"
        "- root 节点必须使用双括号语法：root((中央主题))\n"
        "- 使用 2 个空格缩进表示层级，不要用 Tab\n"
        "- 同一层级的所有节点对齐（空格数相同）\n"
        "- 中文节点文本不需要引号，直接写；包含特殊字符时才用双引号\n"
        "- 不要超过 40 行\n\n"
        "正确示例（请严格模仿此格式）：\n"
        "mindmap\n"
        "  root((任务管理系统筛选功能))\n"
        "    用户角色\n"
        "      普通用户\n"
        "      管理员\n"
        "    核心功能\n"
        "      按优先级筛选\n"
        "      按状态筛选\n"
        "      组合筛选\n"
        "    验收标准\n"
        "      筛选结果准确\n"
        "      响应时间小于200ms\n"
        "    技术约束\n"
        "      纯前端实现\n"
        "      不依赖后端API\n"
    )

    user_prompt = (
        f"用户需求：{requirement}\n\n"
        f"PRD 文档：\n{prd_text[:3000]}\n\n"
        "请根据上述 PRD 生成 Mermaid 思维导图代码。"
    )

    try:
        payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        response = post_chat_completion(payload, "requirement")
        raw = extract_content(response)
    except Exception:
        return None

    if not raw:
        return None

    # Clean up the Mermaid code
    code = raw.strip()
    # Remove markdown code fences if present
    if code.startswith("```mermaid"):
        code = code[10:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    code = code.strip()

    # Basic validation: must contain a valid Mermaid diagram type
    valid_starters = ("mindmap", "graph ", "flowchart ", "gantt", "pie", "erDiagram", "sequenceDiagram", "classDiagram", "stateDiagram")
    if not any(code.startswith(starter) for starter in valid_starters):
        return None

    return {"code": code}


# ── PRD Image Generation Fallback ──

def _post_image_generation(payload: dict, stage_id: str = "") -> dict | None:
    """Call the /v1/images/generations endpoint (OpenAI-compatible)."""
    config = _resolve_provider_config(stage_id)
    try:
        response = httpx.post(
            f"{config['base_url']}/v1/images/generations",
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def generate_prd_image(requirement: str, prd_text: str) -> str | None:
    """Generate an image visualizing the PRD content using an image generation model.

    Returns a URL or base64 data URL of the generated image, or None on failure.
    """
    if not llm_enabled() or not get_api_key():
        return None

    # Generate a detailed illustration prompt from the PRD
    prompt_system = (
        "你是一个产品插画师。根据 PRD 文档，生成一段英文的插画/信息图描述，"
        "用于 AI 图像生成模型。描述要详细、视觉化，包含布局、颜色、元素。"
        "只输出英文 prompt，不超过 300 字符。"
    )

    try:
        prompt_payload = {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": f"需求：{requirement}\n\nPRD：{prd_text[:2000]}"},
            ],
            "temperature": 0.3,
        }
        prompt_response = post_chat_completion(prompt_payload, "requirement")
        image_prompt = extract_content(prompt_response)
    except Exception:
        return None

    if not image_prompt:
        return None

    # Try image generation via /v1/images/generations (OpenAI-compatible)
    models_to_try = ["gemini-2.5-flash-image", "dall-e-3", "image2"]
    for model in models_to_try:
        result = _post_image_generation({
            "model": model,
            "prompt": image_prompt.strip(),
            "n": 1,
            "size": "1024x768",
        }, "requirement")
        if result:
            data = (result.get("data") or [])[0] if result.get("data") else None
            if data:
                return data.get("url") or data.get("b64_json")

    return None


# ── Element Modification Streaming ──


async def stream_element_modification_llm(
    element_info: dict,
    change_request: str,
    file_content: str,
    file_path: str,
    iframe_type: str,
) -> "AsyncGenerator[str, None]":
    """Stream LLM response for element-level code modification. Yields SSE strings."""
    if not llm_enabled():
        yield "event: fail\ndata: LLM 未启用，请设置 DEVFLOW_LLM_ENABLED=true\n\n"
        return

    config = _resolve_provider_config("code")
    if not config["api_key"]:
        yield "event: fail\ndata: LLM API Key 未设置\n\n"
        return

    model_name = MODEL_ROUTER.get("code", "deepseek-v4-flash")
    yield f"event: system\ndata: 正在调用 {model_name} 模型修改元素…\n\n"

    system_prompt = (
        "你是一个前端代码修改助手。根据用户选中的 DOM 元素信息和自然语言修改请求，"
        "精确修改对应的前端代码。\n\n"
        "输出规则（最高优先级）：\n"
        "- 只返回一个 JSON 对象，不要 markdown 代码块，不要任何解释文字\n"
        '- JSON 格式：{"file":"文件路径","content":"完整的修改后文件内容"}\n'
        "- content 必须是完整的文件内容（不是 diff），直接覆盖写入目标文件\n"
        "- 只修改与用户要求相关的部分，严格保持其他代码不变\n"
        "- 确保修改后的代码语法正确、风格与原文件一致\n"
        "- 如果是原型 HTML 修改，保持低保真风格（灰阶为主、简洁边框）"
    )

    styles_text = ", ".join(
        f"{k}: {v}" for k, v in element_info.get("computedStyles", {}).items()
    ) if element_info.get("computedStyles") else "无"

    user_prompt = (
        f"## 修改目标\n"
        f"文件路径：{file_path}\n"
        f"预览类型：{iframe_type}\n\n"
        f"## 选中元素\n"
        f"标签名：{element_info.get('tagName', 'unknown')}\n"
        f"CSS 选择器：{element_info.get('selector', 'unknown')}\n"
        f"元素文本：{element_info.get('text', '')}\n"
        f"元素 HTML：\n```html\n{element_info.get('html', '')}\n```\n"
        f"计算样式：{styles_text}\n\n"
        f"## 用户修改请求\n"
        f"{change_request}\n\n"
        f"## 当前文件完整内容\n"
        f"```\n{file_content[:8000]}\n```\n\n"
        f"请输出修改后的完整文件内容。"
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "stream": True,
    }

    full_content = ""

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{config['base_url']}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content") or ""
                        if content:
                            full_content += content
                            yield f"event: chunk\ndata: {content}\n\n"
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    except Exception as exc:
        yield f"event: fail\ndata: LLM 调用失败：{exc}\n\n"
        return

    if not full_content.strip():
        yield "event: fail\ndata: LLM 返回了空内容\n\n"
        return

    from backend.code_executor import extract_json_object

    result = extract_json_object(full_content)
    if not result or not isinstance(result.get("content"), str):
        yield "event: fail\ndata: LLM 返回格式不正确，无法解析修改结果\n\n"
        return

    yield f"event: result\ndata: {json.dumps({'content': result['content'], 'file': result.get('file', file_path)})}\n\n"
