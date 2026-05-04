const {
  STAGES,
  createPipeline,
  runUntilReviewOrComplete: runLocalUntilReviewOrComplete,
  submitReview,
} = window.DevFlowCore;

const API_BASE_URL = "http://127.0.0.1:8000";

let pipeline = null;
let runtimeMode = "local";
let isRunning = false;
let runningStageName = "";

const elements = {
  form: document.querySelector("#requestForm"),
  requirementInput: document.querySelector("#requirementInput"),
  projectPathInput: document.querySelector("#projectPathInput"),
  runButton: document.querySelector("#runButton"),
  autoRunButton: document.querySelector("#autoRunButton"),
  resetButton: document.querySelector("#resetButton"),
  nextStepTitle: document.querySelector("#nextStepTitle"),
  nextStepHint: document.querySelector("#nextStepHint"),
  runMonitor: document.querySelector("#runMonitor"),
  runMonitorTitle: document.querySelector("#runMonitorTitle"),
  runMonitorDetail: document.querySelector("#runMonitorDetail"),
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
  pencilSketchImage: document.querySelector("#pencilSketchImage"),
  blueprintRisks: document.querySelector("#blueprintRisks"),
  pencilSketchLink: document.querySelector("#pencilSketchLink"),
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
    body: JSON.stringify({
      requirement,
      projectPath: elements.projectPathInput.value,
    }),
  });
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
      hint: "输入需求后点击“开始生成”。系统会自动运行，直到需要你确认方案时才停下来。",
      runLabel: "自动运行",
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
      hint: "系统已经自动停在筛查点。先看产物，认可就通过；觉得不完整就写一句原因打回重做。",
      runLabel: "等待你确认",
    };
  }

  return {
    title: `下一步：${stage.name}`,
    hint: `点击“自动运行”，系统会从“${stage.name}”开始连续执行，直到下一个人工筛查点。`,
    runLabel: "自动运行",
  };
}

function setStatusBadge() {
  const instruction = getNextInstruction();
  elements.pipelineStatus.classList.remove("is-running", "is-review", "is-done");
  elements.nextStepTitle.textContent = instruction.title;
  elements.nextStepHint.textContent = instruction.hint;
  elements.runButton.textContent = instruction.runLabel;

  if (isRunning) {
    elements.pipelineStatus.textContent = "运行中";
    elements.pipelineStatus.classList.add("is-running");
    return;
  }

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

function renderRunMonitor() {
  elements.runMonitor.classList.toggle("is-running", isRunning);
  elements.runMonitor.classList.toggle("is-review", pipeline && pipeline.status === "waiting_review");
  elements.runMonitor.classList.toggle("is-done", pipeline && pipeline.status === "completed");

  if (isRunning) {
    elements.runMonitorTitle.textContent = `正在运行：${runningStageName || "自动工作流"}`;
    elements.runMonitorDetail.textContent = "系统正在自动执行，遇到人工筛查点会停下来让你确认。";
    return;
  }

  if (!pipeline) {
    elements.runMonitorTitle.textContent = "尚未开始";
    elements.runMonitorDetail.textContent = "点击“开始生成”后，这里会实时显示当前正在执行的阶段。";
    return;
  }

  if (pipeline.status === "waiting_review") {
    const stage = getCurrentStage();
    elements.runMonitorTitle.textContent = `已暂停：等待确认 ${stage.name}`;
    elements.runMonitorDetail.textContent = "请查看当前产物，选择通过或打回。";
    return;
  }

  if (pipeline.status === "completed") {
    elements.runMonitorTitle.textContent = "已完成：交付总结已生成";
    elements.runMonitorDetail.textContent = "本次工作流已经跑完，可以查看最终产物。";
    return;
  }

  const stage = getCurrentStage();
  elements.runMonitorTitle.textContent = `待运行：${stage.name}`;
  elements.runMonitorDetail.textContent = "点击“自动运行”，系统会继续跑到下一个人工筛查点。";
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
  renderVisualPlan(artifact.visualPlan, artifact.pencilSketchPath);
}

function renderVisualPlan(visualPlan, pencilSketchPath) {
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
  elements.pencilSketchImage.src = createPencilSketchImage(visualPlan);
  elements.pencilSketchImage.alt = `Pencil 草图：${visualPlan.title}`;

  elements.blueprintRisks.replaceChildren(
    ...visualPlan.risks.map((risk) => {
      const item = document.createElement("span");
      item.textContent = risk;
      return item;
    })
  );

  elements.pencilSketchLink.classList.toggle("hidden", !pencilSketchPath);
  if (pencilSketchPath) {
    elements.pencilSketchLink.href = pencilSketchPath;
    elements.pencilSketchLink.textContent = `打开 Pencil 草图：${pencilSketchPath}`;
  }
}

function escapeSvgText(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function createPencilSketchImage(visualPlan) {
  const nodes = visualPlan.nodes.slice(0, 4);
  const colors = [
    ["#EEF4FF", "#8FB4FF"],
    ["#F0FBFF", "#73D5FF"],
    ["#F4F8F2", "#9ED08B"],
    ["#FFF7ED", "#FFC078"],
  ];
  const cards = nodes.map((node, index) => {
    const x = 70 + index * 215;
    const [fill, stroke] = colors[index % colors.length];
    const arrow = index < nodes.length - 1
      ? `<path d="M${x + 180} 238 C${x + 198} 222, ${x + 222} 222, ${x + 244} 238" stroke="#1664FF" stroke-width="3" stroke-linecap="round"/>
         <path d="M${x + 234} 226 L${x + 246} 238 L${x + 233} 249" stroke="#1664FF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`
      : "";
    return `
      <g filter="url(#shadow)">
        <rect x="${x}" y="174" width="170" height="126" rx="12" fill="${fill}" stroke="${stroke}" stroke-width="2"/>
        <text x="${x + 24}" y="212" fill="#1F2329" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="18" font-weight="900">${escapeSvgText(node.label)}</text>
        <text x="${x + 24}" y="246" fill="#4E5969" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="14">${escapeSvgText(node.detail.slice(0, 15))}</text>
        <text x="${x + 24}" y="271" fill="#4E5969" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="14">${escapeSvgText(node.detail.slice(15, 32))}</text>
      </g>
      ${arrow}
    `;
  }).join("");
  const risks = visualPlan.risks.slice(0, 2).map((risk, index) =>
    `<text x="94" y="${407 + index * 30}" fill="#8A5A00" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="15">${index + 1}. ${escapeSvgText(risk)}</text>`
  ).join("");
  const svg = `
    <svg width="960" height="520" viewBox="0 0 960 520" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="960" height="520" rx="18" fill="#F8FAFF"/>
      <rect x="28" y="28" width="904" height="464" rx="14" fill="#FFFFFF" stroke="#CCD6E6" stroke-width="2" stroke-dasharray="8 8"/>
      <text x="56" y="70" fill="#1664FF" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="18" font-weight="800">Pencil 草图</text>
      <text x="56" y="106" fill="#1F2329" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="27" font-weight="900">${escapeSvgText(visualPlan.title)}</text>
      <text x="56" y="140" fill="#4E5969" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="16">${escapeSvgText(visualPlan.summary.slice(0, 46))}</text>
      ${cards}
      <rect x="70" y="360" width="820" height="108" rx="12" fill="#FFF9DB" stroke="#FFD43B" stroke-width="2"/>
      <text x="94" y="384" fill="#8A5A00" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="17" font-weight="900">审批关注点</text>
      ${risks}
      <defs>
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#1F2329" flood-opacity="0.12"/>
        </filter>
      </defs>
    </svg>
  `;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
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
  elements.runButton.disabled = !canRun || isRunning;
  elements.autoRunButton.classList.add("hidden");
}

function render() {
  setStatusBadge();
  renderStages();
  renderArtifact();
  renderReview();
  renderRunMonitor();
  renderControls();
}

async function runUntilReviewOrComplete() {
  if (!pipeline) return;
  isRunning = true;
  runningStageName = getCurrentStage()?.name || "";
  render();

  try {
    if (runtimeMode === "api") {
      pipeline = await runUntilReviewFromApi();
    } else {
      pipeline = runLocalUntilReviewOrComplete(pipeline);
    }
  } finally {
    isRunning = false;
    runningStageName = "";
    render();
  }
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
  await runUntilReviewOrComplete();
});

elements.runButton.addEventListener("click", runUntilReviewOrComplete);
elements.autoRunButton.addEventListener("click", runUntilReviewOrComplete);

async function approveCurrentStage() {
  if (!pipeline) return;
  pipeline = runtimeMode === "api"
    ? await submitReviewToApi("approve")
    : submitReview(pipeline, { decision: "approve" });
  elements.rejectReason.value = "";
  await runUntilReviewOrComplete();
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
