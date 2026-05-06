import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import llm_runner
from backend.main import app
from backend.storage import store


client = TestClient(app)

# --- Fake LLM response builders ---

def _make_code_patch_json():
    return json.dumps({
        "files": [
            {
                "path": "index.html",
                "content": (
                    '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
                    '  <meta charset="UTF-8">\n  <title>Target App</title>\n'
                    '</head>\n<body>\n  <main class="task-shell">\n'
                    '    <header><h1>任务管理</h1>\n'
                    '      <nav class="priority-filter">\n'
                    '        <button data-priority="all" class="active">全部</button>\n'
                    '        <button data-priority="high">高</button>\n'
                    '        <button data-priority="medium">中</button>\n'
                    '        <button data-priority="low">低</button>\n'
                    '      </nav>\n    </header>\n'
                    '    <ul id="taskList"></ul>\n'
                    '    <p id="emptyState" hidden></p>\n'
                    '  </main>\n  <script src="app.js"></script>\n</body>\n</html>\n'
                ),
            },
            {
                "path": "app.js",
                "content": (
                    'const tasks = [\n'
                    '  { id: 1, title: "整理需求文档", priority: "high", done: false },\n'
                    '  { id: 2, title: "补充接口说明", priority: "medium", done: false },\n'
                    '  { id: 3, title: "同步测试结果", priority: "low", done: true },\n'
                    '];\n\n'
                    'let priorityFilter = "all";\n\n'
                    'function getFilteredTasks() {\n'
                    '  if (priorityFilter === "all") return tasks;\n'
                    '  return tasks.filter(t => t.priority === priorityFilter);\n'
                    '}\n\n'
                    'function renderTasks() {\n'
                    '  const visible = getFilteredTasks();\n'
                    '  document.querySelector("#taskList").innerHTML = '
                    'visible.map(t => `<li>${t.title} [${t.priority}]</li>`).join("");\n'
                    '  document.querySelector("#emptyState").hidden = visible.length > 0;\n'
                    '}\n\n'
                    'renderTasks();\n'
                ),
            },
        ]
    })


def _make_test_patch_json():
    return json.dumps({
        "files": [
            {
                "path": "tests/priority-filter.test.js",
                "content": (
                    "const assert = require('assert');\n"
                    "const fs = require('fs');\n"
                    "const path = require('path');\n\n"
                    "const appJs = fs.readFileSync(path.join(__dirname, '..', 'app.js'), 'utf-8');\n"
                    "const indexHtml = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf-8');\n\n"
                    "assert(appJs.includes('priorityFilter'), 'app.js should contain priorityFilter');\n"
                    "assert(appJs.includes('getFilteredTasks'), 'app.js should contain getFilteredTasks');\n"
                    'assert(indexHtml.includes(\'data-priority="high"\'), "index.html should expose high priority filter");\n'
                    "assert(indexHtml.includes('emptyState'), 'index.html should include empty state');\n\n"
                    "console.log('priority filter tests passed');\n"
                ),
            }
        ]
    })


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.setenv("DEVFLOW_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DEVFLOW_LLM_BASE_URL", "https://api.lingyaai.cn")

    code_json = _make_code_patch_json()
    test_json = _make_test_patch_json()

    def fake_post(payload):
        model = payload["model"]
        system_content = str(payload.get("messages", [{}])[0].get("content", ""))
        # Requirement prototype generation: return valid low-fi HTML
        if "产品原型设计师" in system_content:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
                                "<title>需求原型</title></head><body><main><h1>任务筛选原型</h1>"
                                "<button>全部</button><button>高优先级</button><ul><li>整理需求文档</li></ul>"
                                "</main></body></html>"
                            ),
                        }
                    }
                ]
            }
        # Visual plan generation: return valid JSON with dynamic title from requirement
        if "可视化" in system_content:
            user_content = payload.get("messages", [{}])[1].get("content", "")
            req_text = ""
            if "用户需求：" in user_content:
                req_text = user_content.split("用户需求：")[1].split("\n")[0][:20]
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "title": f"{req_text}技术方案",
                                "summary": "通过LLM调用生成的可视化方案蓝图",
                                "nodes": [
                                    {"label": "核心模块", "detail": "识别并描述需要变更的核心模块"},
                                    {"label": "数据流", "detail": "定义数据如何在各模块间流转"},
                                    {"label": "关键算法", "detail": "描述核心算法或业务逻辑"},
                                    {"label": "边界处理", "detail": "覆盖空状态、异常和边缘情况"},
                                ],
                                "risks": ["技术选型风险", "边界情况遗漏"],
                            }),
                        }
                    }
                ]
            }
        if model.startswith("claude-sonnet"):
            return {"choices": [{"message": {"content": code_json}}]}
        if model.startswith("deepseek-v4-pro") and "测试文件生成器" in system_content:
            return {"choices": [{"message": {"content": test_json}}]}
        # Other stages
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "## 需求目标\n实现按优先级筛选任务功能\n\n"
                            "## 用户故事\n作为用户，我希望筛选任务\n\n"
                            "## 验收标准\n1. 可切换优先级\n2. 列表实时更新\n\n"
                            "## 方案标题\n优先级筛选技术方案\n\n"
                            "## 涉及模块\nTaskToolbar, TaskList\n\n"
                            "## 风险点\n筛选与搜索状态共存风险\n\n"
                            "## 评审结论\n建议交付\n\n"
                            f"MR 描述草稿\n{model} 输出\n"
                            "缺少空状态处理"
                        ),
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_runner, "post_chat_completion", fake_post)


def create_pipeline(requirement="给任务管理系统增加按优先级筛选任务的功能"):
    response = client.post("/pipelines", json={"requirement": requirement})
    assert response.status_code == 200
    return response.json()


def approve_current_stage(pipeline_id):
    response = client.post(
        f"/pipelines/{pipeline_id}/review",
        json={"decision": "approve"},
    )
    assert response.status_code == 200
    return response.json()


def run_to_design_review(pipeline_id):
    requirement = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
    assert requirement["status"] == "waiting_review"
    assert requirement["currentStageId"] == "requirement"
    approve_current_stage(pipeline_id)
    design = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
    assert design["status"] == "waiting_review"
    assert design["currentStageId"] == "design"
    return design


def approve_until_stage(pipeline_id, expected_stage_id):
    while True:
        result = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
        assert result["status"] == "waiting_review"
        if result["currentStageId"] == expected_stage_id:
            return result
        approve_current_stage(pipeline_id)


# --- Tests ---

def test_create_pipeline_returns_ready_state():
    pipeline = create_pipeline()
    assert pipeline["status"] == "ready"
    assert pipeline["currentStageId"] == "requirement"
    assert len(pipeline["stages"]) == 6
    assert all(stage["approvalRequired"] for stage in pipeline["stages"])
    assert pipeline["artifacts"] == {}


def test_create_pipeline_rejects_empty_requirement():
    response = client.post("/pipelines", json={"requirement": ""})
    assert response.status_code == 422


def test_create_pipeline_accepts_project_path():
    response = client.post(
        "/pipelines",
        json={
            "requirement": "给任务管理系统增加按优先级筛选任务的功能",
            "projectPath": "C:/tmp/my-app",
        },
    )
    pipeline = response.json()
    assert pipeline["projectPath"] == "C:/tmp/my-app"


def test_run_next_reaches_requirement_and_design_review_checkpoints():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    requirement = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert requirement["status"] == "waiting_review"
    assert requirement["currentStageId"] == "requirement"
    assert requirement["artifacts"]["requirement"]["agent"] == "需求分析 Agent"
    assert requirement["artifacts"]["requirement"]["skill"]["id"] == "requirements-analysis"
    assert "<html" in requirement["artifacts"]["requirement"]["prototypeHtml"].lower()

    approve_current_stage(pipeline_id)
    design = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert design["status"] == "waiting_review"
    assert design["currentStageId"] == "design"
    assert design["artifacts"]["design"]["agent"] == "方案设计 Agent"
    assert design["artifacts"]["design"]["skill"]["id"] == "technical-design"
    assert design["artifacts"]["design"]["visualPlan"] is not None
    assert len(design["artifacts"]["design"]["visualPlan"]["nodes"]) >= 2


def test_design_blueprint_is_dynamic_from_llm_output():
    response = client.post(
        "/pipelines",
        json={"requirement": "给登录页面增加短信验证码校验"},
    )
    pipeline = response.json()
    design = run_to_design_review(pipeline["id"])

    visual_plan = design["artifacts"]["design"]["visualPlan"]
    assert visual_plan is not None
    assert "短信验证码" in visual_plan["title"]


def test_reject_requires_reason_and_regenerates_design():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)

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
    assert rejected["reviewHistory"][-1]["decision"] == "reject"

    regenerated = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert regenerated["status"] == "waiting_review"
    assert "缺少空状态处理" in regenerated["artifacts"]["design"]["content"]


def test_every_stage_requires_approval_before_next_stage_runs():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    expected_stages = ["requirement", "design", "code", "test", "review", "delivery"]
    for stage_id in expected_stages:
        checkpoint = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
        assert checkpoint["status"] == "waiting_review"
        assert checkpoint["currentStageId"] == stage_id
        assert stage_id in checkpoint["artifacts"]
        approve_current_stage(pipeline_id)

    completed = client.get(f"/pipelines/{pipeline_id}").json()
    assert completed["status"] == "completed"
    assert completed["currentStageId"] == "delivery"
    assert completed["artifacts"]["delivery"]["agent"] == "交付总结 Agent"
    assert "MR 描述草稿" in completed["artifacts"]["delivery"]["content"]


def test_get_pipeline_returns_current_state():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    client.post(f"/pipelines/{pipeline_id}/run-next")

    fetched = client.get(f"/pipelines/{pipeline_id}").json()
    assert fetched["id"] == pipeline_id
    assert fetched["currentStageId"] == "requirement"
    assert "requirement" in fetched["artifacts"]


def test_model_router_uses_mixed_models():
    assert llm_runner.MODEL_ROUTER == {
        "requirement": "deepseek-v4-flash",
        "design": "deepseek-v4-pro",
        "code": "claude-sonnet-4-5-20250929",
        "test": "deepseek-v4-pro",
        "review": "deepseek-v4-flash",
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
                        "content": "真实模型输出：需求分析结果\n\n## 目标\n实现功能\n\n验收标准：\n1. 标准1",
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_runner, "post_chat_completion", fake_post)

    pipeline = create_pipeline()
    result = client.post(f"/pipelines/{pipeline['id']}/run-next").json()

    artifact = result["artifacts"]["requirement"]
    assert artifact["content"] == "真实模型输出：需求分析结果\n\n## 目标\n实现功能\n\n验收标准：\n1. 标准1"
    assert artifact["model"] == "deepseek-v4-flash"
    assert calls[0]["model"] == "deepseek-v4-flash"
    assert len(calls[0]["messages"]) == 2
    assert calls[0]["messages"][0]["role"] == "system"
    assert calls[0]["messages"][1]["role"] == "user"
    assert "工作规范" in calls[0]["messages"][0]["content"]


def test_run_next_returns_503_without_api_key(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.delenv("DEVFLOW_LLM_API_KEY", raising=False)

    pipeline = create_pipeline()
    response = client.post(f"/pipelines/{pipeline['id']}/run-next")

    assert response.status_code == 503
    assert "大模型支持" in response.json()["detail"]


def test_code_stage_creates_real_target_app_workspace():
    store.clear()

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "code")

    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    artifact = result["artifacts"]["code"]
    workspace = Path(artifact["workspacePath"])
    app_js = workspace / "app.js"

    assert workspace.exists()
    assert app_js.exists()
    content = app_js.read_text(encoding="utf-8")
    assert len(content) > 0
    assert "target-app/app.js" in artifact["changedFiles"]
    assert "diff --git" in artifact["content"]


def test_test_stage_creates_real_test_file():
    store.clear()

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "test")

    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    artifact = result["artifacts"]["test"]
    workspace = Path(result["artifacts"]["code"]["workspacePath"])
    test_file = workspace / "tests" / "priority-filter.test.js"

    assert test_file.exists()
    content = test_file.read_text(encoding="utf-8")
    assert len(content) > 0
    assert "target-app/tests/priority-filter.test.js" in artifact["changedFiles"]


def test_can_preview_generated_target_app():
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "code")
    client.post(f"/pipelines/{pipeline_id}/run-next")

    response = client.get(f"/runs/{pipeline_id}/target-app/index.html")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_code_stage_can_apply_llm_generated_patch_for_custom_requirement(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.setenv("DEVFLOW_LLM_API_KEY", "test-key")

    def fake_post(payload):
        if payload["model"] != "claude-sonnet-4-5-20250929":
            return {"choices": [{"message": {"content": f"LLM output from {payload['model']}"}}]}
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "files": [
                                {
                                    "path": "app.js",
                                    "content": "const message = '短信验证码校验已接入';\nconsole.log(message);\n",
                                }
                            ]
                        }),
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_runner, "post_chat_completion", fake_post)

    response = client.post(
        "/pipelines",
        json={"requirement": "给登录页面增加短信验证码校验"},
    )
    pipeline = response.json()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "code")

    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    artifact = result["artifacts"]["code"]
    workspace = Path(artifact["workspacePath"])

    assert artifact["model"] == "claude-sonnet-4-5-20250929"
    assert "target-app/app.js" in artifact["changedFiles"]
    assert "短信验证码校验已接入" in (workspace / "app.js").read_text(encoding="utf-8")


def test_test_stage_can_apply_llm_generated_test_patch(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.setenv("DEVFLOW_LLM_API_KEY", "test-key")

    def fake_post(payload):
        system_content = payload["messages"][0]["content"]
        if payload["model"] not in {"claude-sonnet-4-5-20250929", "deepseek-v4-pro"}:
            return {"choices": [{"message": {"content": f"LLM output from {payload['model']}"}}]}
        if payload["model"] == "deepseek-v4-pro" and "测试文件生成器" not in system_content:
            return {"choices": [{"message": {"content": f"LLM output from {payload['model']}"}}]}
        if payload["model"] == "claude-sonnet-4-5-20250929":
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "files": [
                                    {
                                        "path": "app.js",
                                        "content": "const message = '短信验证码校验已接入';\nconsole.log(message);\n",
                                    }
                                ]
                            }),
                        }
                    }
                ]
            }
        assert payload["model"] == "deepseek-v4-pro"
        assert "工作规范" in payload["messages"][1]["content"]
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "files": [
                                {
                                    "path": "tests/sms-code.test.js",
                                    "content": (
                                        "const assert = require('assert');\n"
                                        "assert(true, 'sms code test generated');\n"
                                        "console.log('sms code tests passed');\n"
                                    ),
                                }
                            ]
                        }),
                    }
                }
            ]
        }

    monkeypatch.setattr(llm_runner, "post_chat_completion", fake_post)

    response = client.post(
        "/pipelines",
        json={"requirement": "给登录页面增加短信验证码校验"},
    )
    pipeline = response.json()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "test")

    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    artifact = result["artifacts"]["test"]
    workspace = Path(result["artifacts"]["code"]["workspacePath"])

    assert artifact["model"] == "deepseek-v4-pro"
    assert "target-app/tests/sms-code.test.js" in artifact["changedFiles"]
    assert (workspace / "tests" / "sms-code.test.js").exists()


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
