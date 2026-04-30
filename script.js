const {
  STAGES,
  createPipeline,
  runNextStage,
  submitReview,
} = window.DevFlowCore;

const API_BASE_URL = "http://127.0.0.1:8000";

let pipeline = null;
let runtimeMode = "local";

const elements = {
  form: document.querySelector("#requestForm"),
  requirementInput: document.querySelector("#requirementInput"),
  runButton: document.querySelector("#runButton"),
  autoRunButton: document.querySelector("#autoRunButton"),
  resetButton: document.querySelector("#resetButton"),
  dockStatus: document.querySelector("#dockStatus"),
  nextStepTitle: document.querySelector("#nextStepTitle"),
  nextStepHint: document.querySelector("#nextStepHint"),
  dockNextTitle: document.querySelector("#dockNextTitle"),
  dockRunButton: document.querySelector("#dockRunButton"),
  dockAutoRunButton: document.querySelector("#dockAutoRunButton"),
  dockRejectReason: document.querySelector("#dockRejectReason"),
  dockApproveButton: document.querySelector("#dockApproveButton"),
  dockRejectButton: document.querySelector("#dockRejectButton"),
  pipelineStatus: document.querySelector("#pipelineStatus"),
  stageCount: document.querySelector("#stageCount"),
  stageList: document.querySelector("#stageList"),
  currentAgent: document.querySelector("#currentAgent"),
  artifactEmpty: document.querySelector("#artifactEmpty"),
  artifactCard: document.querySelector("#artifactCard"),
  artifactStage: document.querySelector("#artifactStage"),
  artifactTime: document.querySelector("#artifactTime"),
  artifactContent: document.querySelector("#artifactContent"),
  reviewState: document.querySelector("#reviewState"),
  reviewEmpty: document.querySelector("#reviewEmpty"),
  reviewControls: document.querySelector("#reviewControls"),
  rejectReason: document.querySelector("#rejectReason"),
  approveButton: document.querySelector("#approveButton"),
  rejectButton: document.querySelector("#rejectButton"),
  artifactMetric: document.querySelector("#artifactMetric"),
  reviewMetric: document.querySelector("#reviewMetric"),
};

function getCompletedStageIds() {
  if (!pipeline) return new Set();
  return new Set(Object.keys(pipeline.artifacts));
}

function getLatestArtifact() {
  if (!pipeline) return null;
  const completedIds = Object.keys(pipeline.artifacts);
  if (completedIds.length === 0) return null;
  return pipeline.artifacts[completedIds[completedIds.length - 1]];
}

function getCurrentStage() {
  if (!pipeline) return null;
  return STAGES.find((stage) => stage.id === pipeline.currentStageId);
}

async function requestApi(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let message = `API 请求失败：${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch (error) {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  return response.json();
}

async function createPipelineFromApi(requirement) {
  return requestApi("/pipelines", {
    method: "POST",
    body: JSON.stringify({ requirement }),
  });
}

async function runNextFromApi() {
  return requestApi(`/pipelines/${pipeline.id}/run-next`, { method: "POST" });
}

async function runUntilReviewFromApi() {
  return requestApi(`/pipelines/${pipeline.id}/run-until-review`, { method: "POST" });
}

async function submitReviewToApi(decision, reason = "") {
  return requestApi(`/pipelines/${pipeline.id}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });
}

function getNextInstruction() {
  if (!pipeline) {
    return {
      title: "先创建 Pipeline",
      hint: "确认 Demo 需求后，点击“创建 Pipeline”。创建完成后，页面会告诉你下一步该执行哪个阶段。",
      runLabel: "执行当前阶段",
    };
  }

  if (pipeline.status === "completed") {
    return {
      title: "演示完成",
      hint: "你已经跑完从需求输入到交付总结的完整闭环。可以重置后再演示一次。",
      runLabel: "已完成",
    };
  }

  const stage = getCurrentStage();
  if (pipeline.status === "waiting_review") {
    return {
      title: `审批：${stage.name}`,
      hint: "先看右侧产物。如果认可，点 Approve 继续；如果想展示回退能力，填写 Reject 原因后点 Reject。",
      runLabel: "等待审批",
    };
  }

  return {
    title: `执行：${stage.name}`,
    hint: `点击“执行当前阶段”，让 ${stage.agent} 生成这一阶段的产物。想省步骤时，可以点“自动演示到下个决策点”。`,
    runLabel: `执行：${stage.name}`,
  };
}

function setStatusBadge() {
  const instruction = getNextInstruction();
  elements.pipelineStatus.classList.remove("is-running", "is-review", "is-done");
  elements.nextStepTitle.textContent = instruction.title;
  elements.nextStepHint.textContent = instruction.hint;
  elements.dockNextTitle.textContent = instruction.title;
  elements.runButton.textContent = instruction.runLabel;
  elements.dockRunButton.textContent = instruction.runLabel;

  if (!pipeline) {
    elements.pipelineStatus.textContent = "未创建";
    elements.dockStatus.textContent = runtimeMode === "api" ? "API 模式" : "未创建";
    return;
  }

  if (pipeline.status === "completed") {
    elements.pipelineStatus.textContent = "已完成";
    elements.dockStatus.textContent = runtimeMode === "api" ? "API 已完成" : "本地已完成";
    elements.pipelineStatus.classList.add("is-done");
    return;
  }

  if (pipeline.status === "waiting_review") {
    elements.pipelineStatus.textContent = "等待人工审批";
    elements.dockStatus.textContent = runtimeMode === "api" ? "API 等待审批" : "本地等待审批";
    elements.pipelineStatus.classList.add("is-review");
    return;
  }

  elements.pipelineStatus.textContent = "可继续运行";
  elements.dockStatus.textContent = runtimeMode === "api" ? "API 可运行" : "本地可运行";
  elements.pipelineStatus.classList.add("is-running");
}

function renderStages() {
  const completedIds = getCompletedStageIds();

  elements.stageList.innerHTML = STAGES.map((stage, index) => {
    const isComplete = completedIds.has(stage.id);
    const isCurrent = pipeline && pipeline.currentStageId === stage.id && pipeline.status !== "completed";
    const state = isComplete ? "已生成" : isCurrent ? "当前阶段" : "待执行";
    const classes = [
      "stage-item",
      isComplete ? "is-complete" : "",
      isCurrent ? "is-current" : "",
    ].filter(Boolean).join(" ");

    return `
      <li class="${classes}">
        <span class="stage-index">${index + 1}</span>
        <span>
          <strong>${stage.name}</strong>
          <small>${stage.agent}${stage.approvalRequired ? " · 人工卡点" : ""}</small>
        </span>
        <span class="stage-state">${state}</span>
      </li>
    `;
  }).join("");

  elements.stageCount.textContent = `${completedIds.size} / ${STAGES.length}`;
}

function renderArtifact() {
  const artifact = getLatestArtifact();

  if (!artifact) {
    elements.artifactEmpty.classList.remove("hidden");
    elements.artifactCard.classList.add("hidden");
    elements.currentAgent.textContent = pipeline ? "等待运行" : "等待创建";
    return;
  }

  elements.artifactEmpty.classList.add("hidden");
  elements.artifactCard.classList.remove("hidden");
  elements.currentAgent.textContent = artifact.agent;
  elements.artifactStage.textContent = artifact.stageName;
  elements.artifactTime.textContent = new Date(artifact.createdAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  elements.artifactContent.textContent = artifact.content;
}

function renderReview() {
  const stage = getCurrentStage();
  const isWaitingReview = pipeline && pipeline.status === "waiting_review";

  elements.reviewState.textContent = isWaitingReview ? `${stage.name}待审批` : "暂无卡点";
  elements.reviewEmpty.classList.toggle("hidden", isWaitingReview);
  elements.reviewControls.classList.toggle("hidden", !isWaitingReview);
  elements.rejectReason.disabled = !isWaitingReview;
  elements.approveButton.disabled = !isWaitingReview;
  elements.rejectButton.disabled = !isWaitingReview;
  elements.dockRejectReason.disabled = !isWaitingReview;
  elements.dockApproveButton.disabled = !isWaitingReview;
  elements.dockRejectButton.disabled = !isWaitingReview;
}

function renderMetrics() {
  const artifactCount = pipeline ? Object.keys(pipeline.artifacts).length : 0;
  const reviewCount = pipeline ? pipeline.reviewHistory.length : 0;
  elements.artifactMetric.textContent = artifactCount;
  elements.reviewMetric.textContent = reviewCount;
}

function renderControls() {
  const canRun = pipeline && pipeline.status === "ready";
  elements.runButton.disabled = !canRun;
  elements.autoRunButton.disabled = !canRun;
  elements.dockRunButton.disabled = !canRun;
  elements.dockAutoRunButton.disabled = !canRun;
}

function render() {
  setStatusBadge();
  renderStages();
  renderArtifact();
  renderReview();
  renderMetrics();
  renderControls();
}

async function runUntilReviewOrComplete() {
  if (!pipeline) return;
  if (runtimeMode === "api") {
    pipeline = await runUntilReviewFromApi();
  } else {
    while (pipeline.status === "ready") {
      pipeline = runNextStage(pipeline);
    }
  }
  render();
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    pipeline = await createPipelineFromApi(elements.requirementInput.value);
    runtimeMode = "api";
  } catch (error) {
    pipeline = createPipeline(elements.requirementInput.value);
    runtimeMode = "local";
  }
  elements.rejectReason.value = "";
  elements.dockRejectReason.value = "";
  render();
});

async function runOneStage() {
  if (!pipeline || pipeline.status !== "ready") return;
  pipeline = runtimeMode === "api" ? await runNextFromApi() : runNextStage(pipeline);
  render();
}

elements.runButton.addEventListener("click", runOneStage);
elements.dockRunButton.addEventListener("click", runOneStage);

elements.autoRunButton.addEventListener("click", runUntilReviewOrComplete);
elements.dockAutoRunButton.addEventListener("click", runUntilReviewOrComplete);

async function approveCurrentStage() {
  if (!pipeline) return;
  pipeline = runtimeMode === "api"
    ? await submitReviewToApi("approve")
    : submitReview(pipeline, { decision: "approve" });
  elements.rejectReason.value = "";
  elements.dockRejectReason.value = "";
  render();
}

elements.approveButton.addEventListener("click", approveCurrentStage);
elements.dockApproveButton.addEventListener("click", approveCurrentStage);

async function rejectCurrentStage(reasonElement) {
  if (!pipeline) return;
  try {
    pipeline = runtimeMode === "api"
      ? await submitReviewToApi("reject", reasonElement.value)
      : submitReview(pipeline, {
          decision: "reject",
          reason: reasonElement.value,
        });
    elements.rejectReason.value = "";
    elements.dockRejectReason.value = "";
    render();
  } catch (error) {
    reasonElement.focus();
    reasonElement.placeholder = error.message;
  }
}

elements.rejectButton.addEventListener("click", () => {
  const reason = elements.rejectReason.value || elements.dockRejectReason.value;
  elements.rejectReason.value = reason;
  rejectCurrentStage(elements.rejectReason);
});

elements.dockRejectButton.addEventListener("click", () => {
  const reason = elements.dockRejectReason.value || elements.rejectReason.value;
  elements.dockRejectReason.value = reason;
  rejectCurrentStage(elements.dockRejectReason);
});

elements.rejectReason.addEventListener("input", () => {
  elements.dockRejectReason.value = elements.rejectReason.value;
});

elements.dockRejectReason.addEventListener("input", () => {
  elements.rejectReason.value = elements.dockRejectReason.value;
});

elements.resetButton.addEventListener("click", () => {
  pipeline = null;
  runtimeMode = "local";
  elements.rejectReason.value = "";
  elements.dockRejectReason.value = "";
  render();
});

render();
