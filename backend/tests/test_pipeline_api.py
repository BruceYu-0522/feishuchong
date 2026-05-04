from fastapi.testclient import TestClient

from backend.main import app


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
