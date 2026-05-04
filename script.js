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
  nextStepTitle: document.querySelector("#nextStepTitle"),
  nextStepHint: document.querySelector("#nextStepHint"),
  pipelineStatus: document.querySelector("#pipelineStatus"),
  stageCount: document.querySelector("#stageCount"),
  stageList: document.querySelector("#stageList"),
  currentAgent: document.querySelector("#currentAgent"),
  artifactEmpty: document.querySelector("#artifactEmpty"),
  artifactCard: document.querySelector("#artifactCard"),
  artifactStage: document.querySelector("#artifactStage"),
  artifactTime: document.querySelector("#artifactTime"),
  artifactContent: document.querySelector("#artifactContent"),
  visualPlan: document.querySelector("#visualPlan"),
  visualPlanTitle: document.querySelector("#visualPlanTitle"),
  visualPlanSummary: document.querySelector("#visualPlanSummary"),
  blueprintFlow: document.querySelector("#blueprintFlow"),
  blueprintRisks: document.querySelector("#blueprintRisks"),
  reviewPanel: document.querySelector("#review"),
  reviewState: document.querySelector("#reviewState"),
  reviewEmpty: document.querySelector("#reviewEmpty"),
  reviewControls: document.querySelector("#reviewControls"),
  rejectReason: document.querySelector("#rejectReason"),
  approveButton: document.querySelector("#approveButton"),
  rejectButton: document.querySelector("#rejectButton"),
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
      title: "先输入需求并开始",
      hint: "把你想做的功能写在上方，点击“开始生成研发流程”。系统会先整理需求，再一步步带你确认方案。",
      runLabel: "继续下一步",
    };
  }

  if (pipeline.status === "completed") {
    return {
      title: "演示完成",
      hint: "已经从需求跑到了交付总结。你可以查看最后产物，或者重置后换一个需求再试。",
      runLabel: "已完成",
    };
  }

  const stage = getCurrentStage();
  if (pipeline.status === "waiting_review") {
    return {
      title: `需要你确认：${stage.name}`,
      hint: "先看“系统刚刚产出了什么”。认可就点通过；觉得不完整就写一句原因打回，系统会重新生成这一阶段。",
      runLabel: "等待你确认",
    };
  }

  return {
    title: `下一步：${stage.name}`,
    hint: `点击“继续下一步”，系统会生成“${stage.name}”结果。想快速演示，可以点“自动跑到需要我确认”。`,
    runLabel: `继续：${stage.name}`,
  };
}

function setStatusBadge() {
  const instruction = getNextInstruction();
  elements.pipelineStatus.classList.remove("is-running", "is-review", "is-done");
  elements.nextStepTitle.textContent = instruction.title;
  elements.nextStepHint.textContent = instruction.hint;
  elements.runButton.textContent = instruction.runLabel;

  if (!pipeline) {
    elements.pipelineStatus.textContent = "未开始";
    return;
  }

  if (pipeline.status === "completed") {
    elements.pipelineStatus.textContent = "已完成";
    elements.pipelineStatus.classList.add("is-done");
    return;
  }

  if (pipeline.status === "waiting_review") {
    elements.pipelineStatus.textContent = "等待你确认";
    elements.pipelineStatus.classList.add("is-review");
    return;
  }

  elements.pipelineStatus.textContent = "可继续运行";
  elements.pipelineStatus.classList.add("is-running");
}

function renderStages() {
  const completedIds = getCompletedStageIds();

  elements.stageList.innerHTML = STAGES.map((stage, index) => {
    const isComplete = completedIds.has(stage.id);
    const isCurrent = pipeline && pipeline.currentStageId === stage.id && pipeline.status !== "completed";
    const state = isComplete ? "已完成" : isCurrent ? "当前" : "待处理";
    const classes = [
      "stage-item",
      isComplete ? "is-complete" : "",
      isCurrent ? "is-current" : "",
    ].filter(Boolean).join(" ");
    const approvalLabel = stage.approvalRequired ? "需要你确认" : "自动处理";

    return `
      <li class="${classes}">
        <span class="stage-index">${index + 1}</span>
        <span>
          <strong>${stage.name}</strong>
          <small>${approvalLabel} · ${stage.agent}</small>
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
    elements.visualPlan.classList.add("hidden");
    elements.currentAgent.textContent = pipeline ? "等待生成" : "等待开始";
    return;
  }

  elements.artifactEmpty.classList.add("hidden");
  elements.artifactCard.classList.remove("hidden");
  elements.currentAgent.textContent = artifact.model ? `${artifact.agent} · ${artifact.model}` : artifact.agent;
  elements.artifactStage.textContent = artifact.stageName;
  elements.artifactTime.textContent = new Date(artifact.createdAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  elements.artifactContent.textContent = artifact.content;
  renderVisualPlan(artifact.visualPlan);
}

function renderVisualPlan(visualPlan) {
  if (!visualPlan) {
    elements.visualPlan.classList.add("hidden");
    return;
  }

  elements.visualPlan.classList.remove("hidden");
  elements.visualPlanTitle.textContent = visualPlan.title;
  elements.visualPlanSummary.textContent = visualPlan.summary;

  elements.blueprintFlow.replaceChildren(
    ...visualPlan.nodes.map((node, index) => {
      const card = document.createElement("article");
      card.className = "blueprint-node";

      const step = document.createElement("span");
      step.textContent = `0${index + 1}`;

      const label = document.createElement("strong");
      label.textContent = node.label;

      const detail = document.createElement("p");
      detail.textContent = node.detail;

      card.append(step, label, detail);
      return card;
    })
  );

  elements.blueprintRisks.replaceChildren(
    ...visualPlan.risks.map((risk) => {
      const item = document.createElement("span");
      item.textContent = risk;
      return item;
    })
  );
}

function renderReview() {
  const stage = getCurrentStage();
  const isWaitingReview = pipeline && pipeline.status === "waiting_review";

  elements.reviewState.textContent = isWaitingReview ? `${stage.name}待确认` : "暂时不用确认";
  elements.reviewPanel.classList.toggle("hidden", !isWaitingReview);
  elements.reviewEmpty.classList.toggle("hidden", isWaitingReview);
  elements.reviewControls.classList.toggle("hidden", !isWaitingReview);
  elements.rejectReason.disabled = !isWaitingReview;
  elements.approveButton.disabled = !isWaitingReview;
  elements.rejectButton.disabled = !isWaitingReview;
}

function renderControls() {
  const canRun = pipeline && pipeline.status === "ready";
  elements.runButton.disabled = !canRun;
  elements.autoRunButton.disabled = !canRun;
}

function render() {
  setStatusBadge();
  renderStages();
  renderArtifact();
  renderReview();
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
  render();
});

async function runOneStage() {
  if (!pipeline || pipeline.status !== "ready") return;
  pipeline = runtimeMode === "api" ? await runNextFromApi() : runNextStage(pipeline);
  render();
}

elements.runButton.addEventListener("click", runOneStage);

elements.autoRunButton.addEventListener("click", runUntilReviewOrComplete);

async function approveCurrentStage() {
  if (!pipeline) return;
  pipeline = runtimeMode === "api"
    ? await submitReviewToApi("approve")
    : submitReview(pipeline, { decision: "approve" });
  elements.rejectReason.value = "";
  render();
}

elements.approveButton.addEventListener("click", approveCurrentStage);

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
    render();
  } catch (error) {
    reasonElement.focus();
    reasonElement.placeholder = error.message;
  }
}

elements.rejectButton.addEventListener("click", () => {
  rejectCurrentStage(elements.rejectReason);
});

elements.resetButton.addEventListener("click", () => {
  pipeline = null;
  runtimeMode = "local";
  elements.rejectReason.value = "";
  render();
});

render();
