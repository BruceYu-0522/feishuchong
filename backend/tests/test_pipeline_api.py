from fastapi.testclient import TestClient
from pathlib import Path

from backend import llm_runner
from backend.main import app
from backend.storage import store


client = TestClient(app)


def create_pipeline():
    response = client.post(
        "/pipelines",
        json={"requirement": "给任务管理系统增加按优先级筛选任务的功能"},
    )
    assert response.status_code == 200
    return response.json()


def test_create_pipeline_returns_ready_state():
    pipeline = create_pipeline()

    assert pipeline["status"] == "ready"
    assert pipeline["currentStageId"] == "requirement"
    assert len(pipeline["stages"]) == 6
    assert pipeline["artifacts"] == {}


def test_run_next_reaches_design_review_checkpoint():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    requirement = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert requirement["currentStageId"] == "design"
    assert requirement["artifacts"]["requirement"]["agent"] == "需求分析 Agent"

    design = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert design["status"] == "waiting_review"
    assert design["currentStageId"] == "design"
    assert design["artifacts"]["design"]["agent"] == "方案设计 Agent"
    assert design["artifacts"]["design"]["skill"]["id"] == "technical-design"
    assert design["artifacts"]["design"]["visualPlan"]["title"] == "优先级筛选方案蓝图"
    assert len(design["artifacts"]["design"]["visualPlan"]["nodes"]) >= 4


def test_reject_requires_reason_and_regenerates_design_with_reason():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    client.post(f"/pipelines/{pipeline_id}/run-until-review")

    bad_review = client.post(
        f"/pipelines/{pipeline_id}/review",
        json={"decision": "reject", "reason": ""},
    )
    assert bad_review.status_code == 422

    rejected = client.post(
        f"/pipelines/{pipeline_id}/review",
        json={"decision": "reject", "reason": "缺少空状态处理"},
    ).json()
    assert rejected["status"] == "ready"
    assert rejected["currentStageId"] == "design"
    assert rejected["reviewHistory"][0]["decision"] == "reject"

    regenerated = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert regenerated["status"] == "waiting_review"
    assert "缺少空状态处理" in regenerated["artifacts"]["design"]["content"]


def test_approve_and_run_until_next_review_then_complete():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    client.post(f"/pipelines/{pipeline_id}/run-until-review")

    approved_plan = client.post(
        f"/pipelines/{pipeline_id}/review",
        json={"decision": "approve"},
    ).json()
    assert approved_plan["currentStageId"] == "code"

    review_checkpoint = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
    assert review_checkpoint["status"] == "waiting_review"
    assert review_checkpoint["currentStageId"] == "review"
    assert review_checkpoint["artifacts"]["code"]["agent"] == "代码生成 Agent"
    assert review_checkpoint["artifacts"]["test"]["agent"] == "测试生成 Agent"
    assert review_checkpoint["artifacts"]["review"]["agent"] == "代码评审 Agent"

    client.post(
        f"/pipelines/{pipeline_id}/review",
        json={"decision": "approve"},
    )
    completed = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert completed["status"] == "completed"
    assert completed["artifacts"]["delivery"]["agent"] == "交付总结 Agent"
    assert "MR 描述草稿" in completed["artifacts"]["delivery"]["content"]


def test_get_pipeline_returns_current_state():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    client.post(f"/pipelines/{pipeline_id}/run-next")

    fetched = client.get(f"/pipelines/{pipeline_id}").json()
    assert fetched["id"] == pipeline_id
    assert fetched["currentStageId"] == "design"
    assert "requirement" in fetched["artifacts"]


def test_model_router_uses_mixed_latest_models():
    assert llm_runner.MODEL_ROUTER == {
        "requirement": "deepseek-v4-flash",
        "design": "gpt-5.4",
        "code": "claude-sonnet-4-5-20250929",
        "test": "deepseek-v4-pro",
        "review": "claude-opus-4-5-20251101",
        "delivery": "deepseek-v4-flash",
    }


def test_run_next_uses_llm_when_enabled(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.setenv("DEVFLOW_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DEVFLOW_LLM_BASE_URL", "https://api.lingyaai.cn")

    calls = []

    def fake_post(payload):
        calls.append(payload)
        return {
            "choices": [
                {
                    "message": {
                        "content": "真实模型输出：需求分析结果",
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_runner, "post_chat_completion", fake_post)

    pipeline = create_pipeline()
    result = client.post(f"/pipelines/{pipeline['id']}/run-next").json()

    artifact = result["artifacts"]["requirement"]
    assert artifact["content"] == "真实模型输出：需求分析结果"
    assert artifact["model"] == "deepseek-v4-flash"
    assert calls[0]["model"] == "deepseek-v4-flash"


def test_run_next_falls_back_to_mock_without_api_key(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.delenv("DEVFLOW_LLM_API_KEY", raising=False)

    pipeline = create_pipeline()
    result = client.post(f"/pipelines/{pipeline['id']}/run-next").json()

    artifact = result["artifacts"]["requirement"]
    assert artifact["model"] == "mock"
    assert "用户故事" in artifact["content"]


def test_code_stage_creates_real_target_app_workspace(monkeypatch):
    store.clear()
    monkeypatch.delenv("DEVFLOW_LLM_API_KEY", raising=False)

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    client.post(f"/pipelines/{pipeline_id}/run-until-review")
    client.post(f"/pipelines/{pipeline_id}/review", json={"decision": "approve"})

    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    artifact = result["artifacts"]["code"]
    workspace = Path(artifact["workspacePath"])
    app_js = workspace / "app.js"

    assert workspace.exists()
    assert app_js.exists()
    assert "priorityFilter" in app_js.read_text(encoding="utf-8")
    assert "target-app/app.js" in artifact["changedFiles"]
    assert "diff --git" in artifact["content"]


def test_test_stage_creates_real_test_file(monkeypatch):
    store.clear()
    monkeypatch.delenv("DEVFLOW_LLM_API_KEY", raising=False)

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    client.post(f"/pipelines/{pipeline_id}/run-until-review")
    client.post(f"/pipelines/{pipeline_id}/review", json={"decision": "approve"})
    client.post(f"/pipelines/{pipeline_id}/run-next")

    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    artifact = result["artifacts"]["test"]
    workspace = Path(result["artifacts"]["code"]["workspacePath"])
    test_file = workspace / "tests" / "priority-filter.test.js"

    assert test_file.exists()
    assert "priorityFilter" in test_file.read_text(encoding="utf-8")
    assert "target-app/tests/priority-filter.test.js" in artifact["changedFiles"]
