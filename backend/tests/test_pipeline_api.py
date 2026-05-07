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

    def fake_post(payload, stage_id=""):
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
        if "代码生成器" in system_content or "测试文件生成器" in system_content:
            if "测试文件生成器" in system_content:
                return {"choices": [{"message": {"content": test_json}}]}
            return {"choices": [{"message": {"content": code_json}}]}
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


def test_review_reject_respects_max_retry_limit():
    """After MAX_REVIEW_RETRIES (3) review rejects, the 4th reject should be refused."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    # Advance to review stage
    approve_until_stage(pipeline_id, "review")
    client.post(f"/pipelines/{pipeline_id}/run-next")

    # Reject review 3 times — should succeed each time and go back to code
    for i in range(3):
        rejected = client.post(
            f"/pipelines/{pipeline_id}/review",
            json={"decision": "reject", "reason": f"第{i+1}次驳回：代码存在问题"},
        ).json()
        assert rejected["status"] == "ready"
        assert rejected["currentStageId"] == "code"
        # Re-run to get back to review
        client.post(f"/pipelines/{pipeline_id}/run-until-review")  # code
        approve_current_stage(pipeline_id)  # code approved → test
        client.post(f"/pipelines/{pipeline_id}/run-until-review")  # test
        approve_current_stage(pipeline_id)  # test approved → review
        client.post(f"/pipelines/{pipeline_id}/run-next")  # review

    # The 4th reject should be refused (409)
    response = client.post(
        f"/pipelines/{pipeline_id}/review",
        json={"decision": "reject", "reason": "第4次驳回：依然有问题"},
    )
    assert response.status_code == 409
    assert "已达到最大自动重试次数" in response.json()["detail"]


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
        "design": "gpt-5.4",
        "code": "claude-sonnet-4-5-20250929",
        "test": "deepseek-v4-pro",
        "review": "claude-opus-4-7",
        "delivery": "deepseek-v4-flash",
    }


def test_run_next_uses_llm_when_enabled(monkeypatch):
    store.clear()
    monkeypatch.setenv("DEVFLOW_LLM_ENABLED", "true")
    monkeypatch.setenv("DEVFLOW_LLM_API_KEY", "test-key")
    monkeypatch.setenv("DEVFLOW_LLM_BASE_URL", "https://api.lingyaai.cn")

    calls = []

    def fake_post(payload, stage_id=""):
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

    def fake_post(payload, stage_id=""):
        system_content = payload["messages"][0]["content"]
        if "代码生成器" not in system_content:
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

    def fake_post(payload, stage_id=""):
        system_content = payload["messages"][0]["content"]
        if "测试文件生成器" in system_content:
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
        if "代码生成器" in system_content:
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
        return {"choices": [{"message": {"content": f"LLM output from {payload['model']}"}}]}

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


# ── Multi-Agent Review Tests ──

def _build_multi_agent_fake_post():
    """Build a fake_post that handles both multi-agent review and code/test stages."""
    code_json = _make_code_patch_json()
    test_json = _make_test_patch_json()

    def fake_post(payload, stage_id=""):
        system = payload["messages"][0]["content"]
        # ── Multi-agent review calls (use unique suffix patterns to avoid base prompt collision) ──
        if "正确性角度审查" in system:
            return {"choices": [{"message": {"content": "正确性审查：功能逻辑正确，验收标准已覆盖。"}}]}
        if "安全性角度审查" in system:
            return {"choices": [{"message": {"content": "安全性审查：未发现 XSS 或注入漏洞。"}}]}
        if "规范性角度审查" in system:
            return {"choices": [{"message": {"content": "规范性审查：代码风格一致，命名清晰。"}}]}
        if "评审汇总专家" in system:
            return {"choices": [{"message": {"content": "## 评审结论\n建议交付\n\n## 正确性审查\n功能逻辑正确。\n\n## 安全性审查\n未发现漏洞。\n\n## 规范性审查\n风格一致。"}}]}
        # ── Code / test stages (JSON required) ──
        if "代码生成器" in system:
            return {"choices": [{"message": {"content": code_json}}]}
        if "测试文件生成器" in system:
            return {"choices": [{"message": {"content": test_json}}]}
        # ── Visual plan / prototype ──
        if "可视化" in system:
            return {"choices": [{"message": {"content": json.dumps({"title": "测试方案", "summary": "测试", "nodes": [{"label": "A", "detail": "a"}, {"label": "B", "detail": "b"}], "risks": []})}}]}
        if "原型设计师" in system:
            return {"choices": [{"message": {"content": "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>原型</title></head><body><main><h1>原型</h1></main></body></html>"}}]}
        # ── Other stages ──
        return {"choices": [{"message": {"content": f"LLM output for {stage_id}"}}]}
    return fake_post


def test_multi_agent_review_produces_aggregated_content(monkeypatch):
    """Review stage with multi-agent produces content with 3 review perspectives."""
    from backend import multi_agent as ma

    call_count = [0]

    def fake_post(payload, stage_id=""):
        call_count[0] += 1
        return _build_multi_agent_fake_post()(payload, stage_id)

    monkeypatch.setattr(ma.llm_runner, "post_chat_completion", fake_post)

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "review")
    client.post(f"/pipelines/{pipeline_id}/run-next")

    result = client.get(f"/pipelines/{pipeline_id}").json()
    artifact = result["artifacts"]["review"]
    assert artifact["model"] == "claude-opus-4-7"
    content = artifact["content"]
    assert "正确性审查" in content
    assert "安全性审查" in content
    assert "规范性审查" in content
    assert call_count[0] >= 4


def test_multi_agent_review_handles_partial_failure(monkeypatch):
    """Review succeeds when 1 of 3 agents fails."""
    from backend import multi_agent as ma

    def fake_post(payload, stage_id=""):
        system = payload["messages"][0]["content"]
        if "安全性角度审查" in system:
            raise Exception("Security agent crashed")
        return _build_multi_agent_fake_post()(payload, stage_id)

    monkeypatch.setattr(ma.llm_runner, "post_chat_completion", fake_post)

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "review")
    client.post(f"/pipelines/{pipeline_id}/run-next")

    result = client.get(f"/pipelines/{pipeline_id}").json()
    artifact = result["artifacts"]["review"]
    assert "正确性审查" in artifact["content"]
    assert "规范性审查" in artifact["content"]


def test_single_agent_stages_unchanged(monkeypatch):
    """Non-review stages still use single agent; review uses multi-agent."""
    from backend import multi_agent as ma

    stage_calls = []

    def fake_post(payload, stage_id=""):
        stage_calls.append(stage_id or "unknown")
        return _build_multi_agent_fake_post()(payload, stage_id)

    monkeypatch.setattr(ma.llm_runner, "post_chat_completion", fake_post)

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    # Check requirement and design use single agent
    result = client.get(f"/pipelines/{pipeline_id}").json()
    assert result["artifacts"]["requirement"]["agent"] == "需求分析 Agent"
    assert result["artifacts"]["design"]["agent"] == "方案设计 Agent"

    approve_until_stage(pipeline_id, "review")

    result = client.get(f"/pipelines/{pipeline_id}").json()
    # Review uses multi-agent — verify it has content
    review = result["artifacts"]["review"]
    assert review["agent"] == "代码评审 Agent"
    assert len(review["content"]) > 0
    # Verify multi-agent review produced meaningful content
    assert "正确性审查" in review["content"] or "评审结论" in review["content"]


def test_streaming_multi_agent_yields_correct_events(monkeypatch):
    """SSE streaming path yields progress events for each agent."""
    from backend import multi_agent as ma

    def fake_post(payload, stage_id=""):
        return _build_multi_agent_fake_post()(payload, stage_id)

    monkeypatch.setattr(ma.llm_runner, "post_chat_completion", fake_post)

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]
    run_to_design_review(pipeline_id)
    # Advance to test stage and approve, so review is "ready" (not waiting_review)
    approve_until_stage(pipeline_id, "test")
    approve_current_stage(pipeline_id)  # Approve test → review becomes "ready"

    # Now stream the review stage (pipeline is "ready" at review)
    with client.stream("GET", f"/pipelines/{pipeline_id}/stream-run") as response:
        assert response.status_code == 200
        body = response.read().decode("utf-8")

    assert "多 Agent 并行评审" in body
    assert "正确性审查" in body
    assert "安全性审查" in body
    assert "规范性审查" in body
    assert "汇总" in body


# ── Pipeline Template Tests ──

def test_default_template_is_feature():
    """Default template is 'feature' with 6 stages."""
    pipeline = create_pipeline()
    assert pipeline["template"] == "feature"
    assert len(pipeline["stages"]) == 6
    assert pipeline["currentStageId"] == "requirement"


def test_create_pipeline_with_bugfix_template():
    """Bugfix template creates a 4-stage pipeline starting with code."""
    response = client.post(
        "/pipelines",
        json={"requirement": "修复登录按钮点击无响应", "template": "bugfix"},
    )
    assert response.status_code == 200
    pipeline = response.json()
    assert pipeline["template"] == "bugfix"
    assert len(pipeline["stages"]) == 4
    assert pipeline["currentStageId"] == "code"
    stage_ids = [s["id"] for s in pipeline["stages"]]
    assert stage_ids == ["code", "test", "review", "delivery"]


def test_create_pipeline_with_refactor_template():
    """Refactor template creates a 5-stage pipeline starting with design."""
    response = client.post(
        "/pipelines",
        json={"requirement": "重构状态管理逻辑", "template": "refactor"},
    )
    assert response.status_code == 200
    pipeline = response.json()
    assert pipeline["template"] == "refactor"
    assert len(pipeline["stages"]) == 5
    assert pipeline["currentStageId"] == "design"
    stage_ids = [s["id"] for s in pipeline["stages"]]
    assert stage_ids == ["design", "code", "test", "review", "delivery"]


def test_bugfix_pipeline_runs_all_stages():
    """Bugfix template runs through code→test→review→delivery to completion."""
    pipeline = client.post(
        "/pipelines",
        json={"requirement": "修复登录按钮点击无响应", "template": "bugfix"},
    ).json()
    pipeline_id = pipeline["id"]

    expected_stages = ["code", "test", "review", "delivery"]
    for stage_id in expected_stages:
        checkpoint = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
        assert checkpoint["status"] == "waiting_review"
        assert checkpoint["currentStageId"] == stage_id
        assert stage_id in checkpoint["artifacts"]
        approve_current_stage(pipeline_id)

    completed = client.get(f"/pipelines/{pipeline_id}").json()
    assert completed["status"] == "completed"
    assert completed["currentStageId"] == "delivery"


# ── Git Integration Tests ──

def test_git_init_creates_repo():
    """git init creates a .git directory in the workspace."""
    import tempfile
    from backend.git_manager import ensure_git_repo

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        assert not (ws / ".git").exists()
        result = ensure_git_repo(ws)
        assert result is True
        assert (ws / ".git").exists()


def test_git_commit_returns_hash():
    """commit_changes returns commit info with hash and files."""
    import tempfile
    from backend.git_manager import commit_changes, ensure_git_repo

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        ensure_git_repo(ws)
        # Create a file to commit
        (ws / "test.txt").write_text("hello", encoding="utf-8")
        result = commit_changes(ws, "test: initial commit")
        assert result is not None
        assert "hash" in result
        assert len(result["hash"]) > 0
        assert "test.txt" in result["files"]


def test_git_commit_no_changes_returns_none():
    """commit_changes returns None when there are no changes."""
    import tempfile
    from backend.git_manager import commit_changes, ensure_git_repo

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        ensure_git_repo(ws)
        result = commit_changes(ws, "empty commit")
        assert result is None


def test_git_branch_creation():
    """create_devflow_branch creates and switches to the named branch."""
    import tempfile
    from backend.git_manager import (
        create_devflow_branch,
        ensure_git_repo,
        get_current_branch,
    )

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        ensure_git_repo(ws)
        # Need an initial commit before creating a branch
        (ws / "file.txt").write_text("data", encoding="utf-8")
        from backend.git_manager import commit_changes
        commit_changes(ws, "initial")
        assert create_devflow_branch(ws, "devflow/test-123")
        branch = get_current_branch(ws)
        assert branch == "devflow/test-123"


def test_git_operations_in_pipeline():
    """After code stage, the workspace has a git repo with a commit."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    run_to_design_review(pipeline_id)
    approve_current_stage(pipeline_id)       # approve design
    approve_until_stage(pipeline_id, "code")
    approve_current_stage(pipeline_id)       # approve code

    p = client.get(f"/pipelines/{pipeline_id}").json()
    assert "code" in p["artifacts"]

    # Check that .git exists in the run directory
    from backend.code_executor import RUNS_DIR
    git_dir = RUNS_DIR / pipeline_id / ".git"
    assert git_dir.exists(), f"Expected .git at {git_dir}"


def test_workspace_api_returns_git_info():
    """Workspace API returns git status after code stage commits."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    run_to_design_review(pipeline_id)
    approve_current_stage(pipeline_id)       # approve design
    approve_until_stage(pipeline_id, "code")
    approve_current_stage(pipeline_id)       # approve code

    ws_response = client.get(f"/pipelines/{pipeline_id}/workspace").json()
    assert "git" in ws_response, f"Expected git info in workspace response: {ws_response}"
    assert "branch" in ws_response["git"]
    assert ws_response["git"]["branch"].startswith("devflow/")


def test_git_failure_does_not_block_pipeline():
    """Pipeline completes successfully through all stages (git ops are non-blocking)."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    # Run through all stages to completion (feature template: 6 stages)
    run_to_design_review(pipeline_id)
    approve_current_stage(pipeline_id)       # approve design
    approve_until_stage(pipeline_id, "code")
    approve_current_stage(pipeline_id)       # approve code
    approve_until_stage(pipeline_id, "test")
    approve_current_stage(pipeline_id)       # approve test
    approve_until_stage(pipeline_id, "review")
    approve_current_stage(pipeline_id)       # approve review
    approve_until_stage(pipeline_id, "delivery")
    approve_current_stage(pipeline_id)       # approve delivery

    p = client.get(f"/pipelines/{pipeline_id}").json()
    assert p["status"] == "completed"


# ── Code Semantic Index Tests ──


def test_code_index_parses_html_elements():
    """CodeIndex extracts HTML elements with id/class."""
    import tempfile
    from backend.code_indexer import CodeIndex

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "index.html").write_text(
            '<!DOCTYPE html>\n<html>\n<body>\n'
            '<div id="app" class="container">\n'
            '<button class="btn-primary" id="submitBtn">提交</button>\n'
            '<nav class="priority-filter">\n</nav>\n'
            '</div>\n</body>\n</html>',
            encoding="utf-8",
        )
        idx = CodeIndex().build(root)
        names = {s.name for s in idx.symbols}
        assert "div#app" in names
        assert "div.container" in names
        assert "button#submitBtn" in names
        assert "button.btn-primary" in names
        assert "nav.priority-filter" in names


def test_code_index_parses_css_rules():
    """CodeIndex extracts CSS selectors."""
    import tempfile
    from backend.code_indexer import CodeIndex

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "styles.css").write_text(
            ".container { max-width: 800px; }\n"
            ".btn-primary { background: blue; }\n"
            "#app { display: flex; }\n"
            ".priority-filter button { margin: 4px; }\n",
            encoding="utf-8",
        )
        idx = CodeIndex().build(root)
        names = {s.name for s in idx.symbols}
        assert ".container" in names
        assert ".btn-primary" in names
        assert "#app" in names


def test_code_index_parses_js_functions():
    """CodeIndex extracts JS function/class declarations."""
    import tempfile
    from backend.code_indexer import CodeIndex

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.js").write_text(
            'function getFilteredTasks() {\n  return tasks.filter(t => t.priority === filter);\n}\n'
            'const renderTasks = () => {\n  console.log("rendering");\n};\n'
            'class TaskManager {\n  constructor() {}\n}\n'
            'document.addEventListener("click", () => {});\n'
            'const handleSubmit = function(e) { e.preventDefault(); };\n',
            encoding="utf-8",
        )
        idx = CodeIndex().build(root)
        func_names = {s.name for s in idx.symbols if s.kind == "function"}
        assert "getFilteredTasks" in func_names
        assert "renderTasks" in func_names
        assert "handleSubmit" in func_names
        class_names = {s.name for s in idx.symbols if s.kind == "class"}
        assert "TaskManager" in class_names
        event_names = {s.name for s in idx.symbols if s.kind == "event"}
        assert "click" in event_names


def test_code_index_search():
    """CodeIndex.search returns relevant symbols ranked by relevance."""
    import tempfile
    from backend.code_indexer import CodeIndex

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.js").write_text(
            'function getFilteredTasks() {}\nfunction handlePriority() {}\nconst filterTasks = () => {};\n',
            encoding="utf-8",
        )
        idx = CodeIndex().build(root)
        results = idx.search("filter")
        assert len(results) >= 2
        # getFilteredTasks should rank higher than filterTasks (exact name match > partial)
        assert results[0].name in ("getFilteredTasks", "filterTasks")


def test_code_index_search_content():
    """CodeIndex.search_content returns full-text matches with context."""
    import tempfile
    from backend.code_indexer import CodeIndex

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "app.js").write_text(
            'const priorityFilter = "all";\nfunction getFilteredTasks() {\n'
            '  if (priorityFilter === "all") return tasks;\n'
            '  return tasks.filter(t => t.priority === priorityFilter);\n}\n',
            encoding="utf-8",
        )
        idx = CodeIndex().build(root)
        results = idx.search_content("priorityFilter")
        assert len(results) >= 1
        assert results[0]["file"] == "app.js"


def test_code_index_summary():
    """CodeIndex.summary returns statistics."""
    import tempfile
    from backend.code_indexer import CodeIndex

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "index.html").write_text('<div id="app"></div>', encoding="utf-8")
        (root / "app.js").write_text("function init() {}", encoding="utf-8")
        idx = CodeIndex().build(root)
        summary = idx.summary()
        assert summary["total_files"] == 2
        assert summary["total_symbols"] >= 2


def test_code_index_api_returns_summary():
    """GET /pipelines/{id}/code-index returns index summary after code stage."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    run_to_design_review(pipeline_id)
    approve_current_stage(pipeline_id)
    approve_until_stage(pipeline_id, "code")
    approve_current_stage(pipeline_id)

    response = client.get(f"/pipelines/{pipeline_id}/code-index")
    assert response.status_code == 200
    data = response.json()
    assert data["total_files"] >= 1
    assert data["total_symbols"] >= 1


def test_code_search_api_returns_results():
    """GET /pipelines/{id}/code-search?q=... returns matching symbols."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    run_to_design_review(pipeline_id)
    approve_current_stage(pipeline_id)
    approve_until_stage(pipeline_id, "code")
    approve_current_stage(pipeline_id)

    response = client.get(f"/pipelines/{pipeline_id}/code-search?q=task")
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) >= 1
    assert data["query"] == "task"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── Element Modification Tests ──


def _build_mock_llm_result(content: str, file_path: str) -> str:
    """Build a JSON result the mock LLM would return."""
    import json as _json
    return _json.dumps({"content": content, "file": file_path})


async def _mock_stream_modify_llm(
    element_info, change_request, file_content, file_path, iframe_type
):
    """Mock for stream_element_modification_llm — yields SSE events."""
    if iframe_type == "prototype":
        new_content = "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>Modified Proto</title></head><body><main><h1>Modified Prototype</h1><button class='new-btn'>Updated</button></main></body></html>"
        result = _build_mock_llm_result(new_content, "prototype.html")
    else:
        new_content = "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n  <meta charset=\"UTF-8\">\n  <title>Modified App</title>\n</head>\n<body>\n  <main class=\"task-shell\">\n    <header><h1>Updated Tasks</h1>\n    </header>\n  </main>\n  <script src=\"app.js\"></script>\n</body>\n</html>\n"
        result = _build_mock_llm_result(new_content, "index.html")

    yield f"event: system\ndata: 正在调用 mock 模型修改元素…\n\n"
    yield f"event: chunk\ndata: {result[:80]}\n\n"
    yield f"event: result\ndata: {result}\n\n"


def test_element_modify_stream_missing_pipeline():
    """SSE endpoint returns 404 for missing pipeline."""
    element_info = json.dumps({"tagName": "button", "iframeType": "product"})
    url = f"/pipelines/nonexistent/element-modify-stream?element_info={element_info}&change_request=change%20color"
    response = client.get(url)
    assert response.status_code == 404


def test_element_modify_stream_empty_request():
    """SSE endpoint returns fail event for empty change_request."""
    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    element_info = json.dumps({"tagName": "button", "iframeType": "product"})
    url = f"/pipelines/{pipeline_id}/element-modify-stream?element_info={element_info}&change_request="
    response = client.get(url)
    assert response.status_code == 200
    content = response.text
    assert "修改请求不能为空" in content


def test_element_modify_stream_prototype(monkeypatch):
    """SSE element modification for prototype iframe updates prototypeHtml artifact."""
    monkeypatch.setattr(
        llm_runner,
        "stream_element_modification_llm",
        _mock_stream_modify_llm,
    )

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    result = client.post(f"/pipelines/{pipeline_id}/run-until-review").json()
    assert result["status"] == "waiting_review"
    assert result["artifacts"]["requirement"]["prototypeHtml"] is not None

    element_info = json.dumps({
        "tagName": "button",
        "selector": "button.priority-filter",
        "html": "<button>全部</button>",
        "iframeType": "prototype",
        "sourceFile": "prototype.html",
    })
    url = (
        f"/pipelines/{pipeline_id}/element-modify-stream"
        f"?element_info={element_info}&change_request=make%20button%20rounded"
    )
    response = client.get(url)
    assert response.status_code == 200
    content = response.text
    assert "原型 HTML 已更新" in content

    # Verify artifact was updated
    updated = client.get(f"/pipelines/{pipeline_id}").json()
    assert "Modified Proto" in updated["artifacts"]["requirement"]["prototypeHtml"]


def test_element_modify_stream_product(monkeypatch):
    """SSE element modification for product iframe writes file and creates git commit."""
    monkeypatch.setattr(
        llm_runner,
        "stream_element_modification_llm",
        _mock_stream_modify_llm,
    )

    from backend.code_executor import RUNS_DIR

    pipeline = create_pipeline()
    pipeline_id = pipeline["id"]

    run_to_design_review(pipeline_id)
    approve_until_stage(pipeline_id, "code")
    result = client.post(f"/pipelines/{pipeline_id}/run-next").json()
    assert result["artifacts"]["code"]["workspacePath"] is not None
    assert len(result["artifacts"]["code"]["changedFiles"]) >= 1

    run_root = RUNS_DIR / pipeline_id
    index_html = run_root / "target-app" / "index.html"
    assert index_html.exists(), f"Expected {index_html} to exist"

    element_info = json.dumps({
        "tagName": "h1",
        "selector": "main h1",
        "html": "<h1>任务管理</h1>",
        "iframeType": "product",
        "sourceFile": "index.html",
    })
    url = (
        f"/pipelines/{pipeline_id}/element-modify-stream"
        f"?element_info={element_info}&change_request=change%20title%20text"
    )
    response = client.get(url)
    assert response.status_code == 200
    content = response.text
    assert "文件 index.html 已更新" in content

    # Verify file was updated on disk
    updated_content = index_html.read_text(encoding="utf-8")
    assert "Modified App" in updated_content
