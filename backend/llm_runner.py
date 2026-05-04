import os
from typing import Any

import httpx

from backend.schemas import Pipeline, Stage
from backend.skills import read_skill


MODEL_ROUTER = {
    "requirement": "deepseek-v4-flash",
    "design": "gpt-5.4",
    "code": "claude-sonnet-4-5-20250929",
    "test": "deepseek-v4-pro",
    "review": "claude-opus-4-5-20251101",
    "delivery": "deepseek-v4-flash",
}

DEFAULT_BASE_URL = "https://api.lingyaai.cn"


def llm_enabled() -> bool:
    return os.getenv("DEVFLOW_LLM_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def get_api_key() -> str:
    return os.getenv("DEVFLOW_LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def get_base_url() -> str:
    return os.getenv("DEVFLOW_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def build_messages(stage: Stage, pipeline: Pipeline) -> list[dict[str, str]]:
    skill_text = read_skill(stage.id)
    review_context = "\n".join(
        f"- {record.stageName}: {record.decision} {record.reason}".strip()
        for record in pipeline.reviewHistory
    ) or "暂无"
    previous_artifacts = "\n\n".join(
        f"【{artifact.stageName}】\n{artifact.content}"
        for artifact in pipeline.artifacts.values()
    ) or "暂无"

    return [
        {
            "role": "system",
            "content": (
                "你是 DevFlow Engine 中的研发流程 Agent。"
                "请严格围绕当前阶段输出，使用中文，结构清晰，避免空泛表述。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"当前阶段：{stage.name}\n"
                f"当前 Agent：{stage.agent}\n"
                f"用户需求：{pipeline.requirement}\n\n"
                f"阶段 Skill 规范：\n{skill_text}\n\n"
                f"历史审批记录：\n{review_context}\n\n"
                f"已有阶段产物：\n{previous_artifacts}\n\n"
                "请直接输出这一阶段的最终产物。"
            ),
        },
    ]


def build_payload(stage: Stage, pipeline: Pipeline) -> dict[str, Any]:
    return {
        "model": MODEL_ROUTER[stage.id],
        "messages": build_messages(stage, pipeline),
        "temperature": 0.3,
    }


def post_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = get_api_key()
    response = httpx.post(
        f"{get_base_url()}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def run_llm_agent(stage: Stage, pipeline: Pipeline) -> tuple[str, str] | None:
    if not llm_enabled() or not get_api_key():
        return None

    try:
        payload = build_payload(stage, pipeline)
        content = extract_content(post_chat_completion(payload))
    except Exception:
        return None

    if not content:
        return None

    return content, payload["model"]
