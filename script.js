var STAGES = window.DevFlowCore.STAGES;
var client = window.DevFlowCore.createClient("http://127.0.0.1:8001");
var artifactRenderer = window.DevFlowArtifactRenderer;
var clarificationFlow = window.DevFlowClarificationFlow;

var pipeline = null;
var isRunning = false;
var runningStageName = "";
var runErrorMessage = "";
var abortController = null;
var pendingRequirement = "";
var pendingProjectPath = "";

var elements = {
  form: document.querySelector("#requestForm"),
  requirementInput: document.querySelector("#requirementInput"),
  projectPathInput: document.querySelector("#projectPathInput"),
  runButton: document.querySelector("#runButton"),
  stopButton: document.querySelector("#stopButton"),
  autoRunButton: document.querySelector("#autoRunButton"),
  resetButton: document.querySelector("#resetButton"),
  nextStepTitle: document.querySelector("#nextStepTitle"),
  nextStepHint: document.querySelector("#nextStepHint"),
  runMonitor: document.querySelector("#runMonitor"),
  runMonitorTitle: document.querySelector("#runMonitorTitle"),
  runMonitorDetail: document.querySelector("#runMonitorDetail"),
  deliveryPackage: document.querySelector("#deliveryPackage"),
  productPreviewFrame: document.querySelector("#productPreviewFrame"),
  productPreviewLink: document.querySelector("#productPreviewLink"),
  deliverySummaryTitle: document.querySelector("#deliverySummaryTitle"),
  deliverySummaryText: document.querySelector("#deliverySummaryText"),
  deliveryValidationTitle: document.querySelector("#deliveryValidationTitle"),
  deliveryValidationText: document.querySelector("#deliveryValidationText"),
  deliveryFiles: document.querySelector("#deliveryFiles"),
  mrDraft: document.querySelector("#mrDraft"),
  pipelineStatus: document.querySelector("#pipelineStatus"),
  stageCount: document.querySelector("#stageCount"),
  stageList: document.querySelector("#stageList"),
  currentAgent: document.querySelector("#currentAgent"),
  artifactEmpty: document.querySelector("#artifactEmpty"),
  artifactCard: document.querySelector("#artifactCard"),
  artifactStage: document.querySelector("#artifactStage"),
  artifactTime: document.querySelector("#artifactTime"),
  artifactContent: document.querySelector("#artifactContent"),
  prdMap: document.querySelector("#prdMap"),
  prdMapTitle: document.querySelector("#prdMapTitle"),
  prdMapFlow: document.querySelector("#prdMapFlow"),
  visualPlan: document.querySelector("#visualPlan"),
  visualPlanTitle: document.querySelector("#visualPlanTitle"),
  visualPlanSummary: document.querySelector("#visualPlanSummary"),
  blueprintFlow: document.querySelector("#blueprintFlow"),
  pencilSketchImage: document.querySelector("#pencilSketchImage"),
  blueprintRisks: document.querySelector("#blueprintRisks"),
  pencilSketchLink: document.querySelector("#pencilSketchLink"),
  prototypePreview: document.querySelector("#prototypePreview"),
  prototypeTitle: document.querySelector("#prototypeTitle"),
  prototypeDesc: document.querySelector("#prototypeDesc"),
  prototypeFrame: document.querySelector("#prototypeFrame"),
  reviewPanel: document.querySelector("#review"),
  reviewState: document.querySelector("#reviewState"),
  reviewEmpty: document.querySelector("#reviewEmpty"),
  reviewControls: document.querySelector("#reviewControls"),
  rejectReason: document.querySelector("#rejectReason"),
  approveButton: document.querySelector("#approveButton"),
  rejectButton: document.querySelector("#rejectButton"),
  clarificationModal: document.querySelector("#clarificationModal"),
  clarificationForm: document.querySelector("#clarificationForm"),
  clarificationRequirement: document.querySelector("#clarificationRequirement"),
  clarificationQuestions: document.querySelector("#clarificationQuestions"),
  clarificationCancel: document.querySelector("#clarificationCancel"),
  clarificationRecommend: document.querySelector("#clarificationRecommend"),
};

function getCompletedStageIds() {
  if (!pipeline) return new Set();
  return new Set(Object.keys(pipeline.artifacts));
}

function getLatestArtifact() {
  if (!pipeline) return null;
  var completedIds = Object.keys(pipeline.artifacts);
  if (completedIds.length === 0) return null;
  return pipeline.artifacts[completedIds[completedIds.length - 1]];
}

function getCurrentStage() {
  if (!pipeline) return null;
  var found = null;
  STAGES.forEach(function (stage) {
    if (stage.id === pipeline.currentStageId) found = stage;
  });
  return found;
}

function getArtifact(stageId) {
  return pipeline && pipeline.artifacts ? pipeline.artifacts[stageId] : null;
}

function getProductPreviewUrl() {
  if (!pipeline) return "";
  var codeArtifact = getArtifact("code");
  if (!codeArtifact || !codeArtifact.workspacePath) return "";
  return "http://127.0.0.1:8001/runs/" + pipeline.id + "/target-app/index.html";
}

function getNextInstruction() {
  if (!pipeline) {
    return {
      title: "输入需求并开始",
      hint: "输入你想要实现的功能需求，点击「开始生成」。系统会先生成需求分析，并停在人工确认点。",
      runLabel: "开始生成",
    };
  }

  if (pipeline.status === "completed") {
    return {
      title: "Pipeline 已完成",
      hint: "已经从需求跑到了交付总结。你可以查看下方产物，或者重置后换一个需求再试。",
      runLabel: "已完成",
    };
  }

  var stage = getCurrentStage();
  if (pipeline.status === "waiting_review") {
    return {
      title: "需要你确认：" + (stage ? stage.name : ""),
      hint: "系统已经自动停在筛查点。先查看产物，认可就通过；觉得不完整就写一句原因打回重做。",
      runLabel: "等待你确认",
    };
  }

  return {
    title: "下一步：" + (stage ? stage.name : ""),
    hint: "点击「自动运行」，系统会从当前阶段开始连续执行，直到下一个人工筛查点。",
    runLabel: "自动运行",
  };
}

function setStatusBadge() {
  var instruction = getNextInstruction();
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
    elements.runMonitorTitle.textContent = "正在运行：" + (runningStageName || "自动工作流");
    elements.runMonitorDetail.textContent = "系统正在通过 AI Agent 自动执行当前阶段，遇到人工筛查点会停下来让你确认。";
    return;
  }

  if (runErrorMessage) {
    elements.runMonitorTitle.textContent = runErrorMessage.indexOf("已暂停") !== -1 ? "已暂停" : "运行失败";
    elements.runMonitorDetail.textContent = runErrorMessage;
    return;
  }

  if (!pipeline) {
    elements.runMonitorTitle.textContent = "尚未开始";
    elements.runMonitorDetail.textContent = "输入需求后点击「开始生成」，Pipeline 将依次经过 6 个研发阶段。";
    return;
  }

  if (pipeline.status === "waiting_review") {
    var stage = getCurrentStage();
    elements.runMonitorTitle.textContent = "已暂停：等待确认 " + (stage ? stage.name : "");
    elements.runMonitorDetail.textContent = "请查看当前产物，选择通过或打回。";
    return;
  }

  if (pipeline.status === "completed") {
    elements.runMonitorTitle.textContent = "已完成：交付总结已生成";
    elements.runMonitorDetail.textContent = "本次 AI 驱动的研发工作流已全部完成，可以查看最终产物。";
    return;
  }

  var nextStage = getCurrentStage();
  elements.runMonitorTitle.textContent = "待运行：" + (nextStage ? nextStage.name : "");
  elements.runMonitorDetail.textContent = "点击「自动运行」，AI Agent 会继续执行直到下一个审批点。";
}

function renderStages() {
  var completedIds = getCompletedStageIds();
  var wheelItems = window.DevFlowCore.createStageWheelItems(
    STAGES,
    pipeline ? pipeline.currentStageId : STAGES[0].id,
    completedIds
  );

  elements.stageList.innerHTML = wheelItems.map(function (stage, index) {
    var isCurrent = stage.state === "current" && pipeline && pipeline.status !== "completed";
    var state = stage.state === "complete" ? "已完成" : isCurrent ? "当前" : "待处理";
    var classes = ["stage-item", "stage-wheel-item", "is-" + stage.state];
    if (isCurrent) classes.push("is-current");
    var approvalLabel = stage.approvalRequired ? "需要你确认" : "AI 自动处理";
    var style = "--wheel-x:" + stage.x + "%;--wheel-y:" + stage.y + "%;--wheel-angle:" + stage.angle + "deg;--wheel-offset:" + stage.offset + ";";

    return (
      '<li class="' + classes.join(" ") + '" style="' + style + '">' +
        '<span class="stage-index">' + (index + 1) + "</span>" +
        '<span class="stage-copy">' +
          "<strong>" + stage.name + "</strong>" +
          "<small>" + approvalLabel + " · " + stage.agent + "</small>" +
        "</span>" +
        '<span class="stage-state">' + state + "</span>" +
      "</li>"
    );
  }).join("");

  elements.stageCount.textContent = completedIds.size + " / " + STAGES.length;
}

function renderArtifact() {
  var artifact = getLatestArtifact();

  if (!artifact) {
    elements.artifactEmpty.classList.remove("hidden");
    elements.artifactCard.classList.add("hidden");
    elements.prdMap.classList.add("hidden");
    elements.visualPlan.classList.add("hidden");
    elements.prototypePreview.classList.add("hidden");
    elements.currentAgent.textContent = pipeline ? "等待 AI Agent 生成" : "等待开始";
    return;
  }

  elements.artifactEmpty.classList.add("hidden");
  elements.artifactCard.classList.remove("hidden");
  elements.currentAgent.textContent = artifact.model
    ? artifact.agent + " · " + artifact.model
    : artifact.agent;
  elements.artifactStage.textContent = artifact.stageName;
  elements.artifactTime.textContent = new Date(artifact.createdAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  elements.artifactContent.innerHTML = artifactRenderer.renderMarkdown(artifact.content);
  renderPrdMap(artifact);
  renderPrototype(artifact);
  renderVisualPlan(artifact.visualPlan);
}

function renderPrdMap(artifact) {
  if (!artifact || artifact.stageId !== "requirement") {
    elements.prdMap.classList.add("hidden");
    return;
  }

  var prdMap = artifactRenderer.buildPrdMap(artifact.content);
  elements.prdMap.classList.remove("hidden");
  elements.prdMapTitle.textContent = prdMap.title;
  elements.prdMapFlow.innerHTML = artifactRenderer.renderPrdMap(prdMap);
}

function renderDeliveryPackage() {
  var previewUrl = getProductPreviewUrl();
  var isComplete = pipeline && pipeline.status === "completed";
  elements.deliveryPackage.classList.toggle("hidden", !isComplete);

  if (!isComplete) {
    elements.productPreviewFrame.removeAttribute("src");
    elements.mrDraft.value = "";
    return;
  }

  var delivery = getArtifact("delivery");
  var code = getArtifact("code");
  var test = getArtifact("test");
  var review = getArtifact("review");
  var changedFiles = [];
  if (code && code.changedFiles) changedFiles = changedFiles.concat(code.changedFiles);
  if (test && test.changedFiles) changedFiles = changedFiles.concat(test.changedFiles);

  elements.productPreviewFrame.src = previewUrl;
  elements.productPreviewLink.href = previewUrl || "#";
  elements.productPreviewLink.classList.toggle("is-disabled", !previewUrl);
  elements.deliverySummaryTitle.textContent = pipeline.requirement;
  elements.deliverySummaryText.textContent = delivery
    ? "最终交付物已生成，包含代码变更、测试文件和交付总结。"
    : "产品已经生成，交付说明暂未生成。";
  elements.deliveryValidationTitle.textContent = test ? "已生成测试文件" : "等待测试产物";
  elements.deliveryValidationText.textContent = test
    ? "可在运行副本中执行测试验证代码改动。"
    : "测试阶段完成后会显示验证方式。";
  if (review && review.content) {
    elements.deliveryValidationText.textContent += " 已生成评审结论。";
  }

  elements.deliveryFiles.replaceChildren.apply(
    elements.deliveryFiles,
    changedFiles.map(function (file) {
      var item = document.createElement("li");
      item.textContent = file;
      return item;
    })
  );
  elements.mrDraft.value = delivery ? delivery.content : "";
}

function renderVisualPlan(visualPlan) {
  if (!visualPlan) {
    elements.visualPlan.classList.add("hidden");
    return;
  }

  elements.visualPlan.classList.remove("hidden");
  elements.visualPlanTitle.textContent = visualPlan.title;
  elements.visualPlanSummary.textContent = visualPlan.summary;

  elements.blueprintFlow.replaceChildren.apply(
    elements.blueprintFlow,
    visualPlan.nodes.map(function (node, index) {
      var card = document.createElement("article");
      card.className = "blueprint-node";

      var step = document.createElement("span");
      var numStr = String(index + 1);
      step.textContent = numStr.length === 1 ? "0" + numStr : numStr;

      var label = document.createElement("strong");
      label.textContent = node.label;

      var detail = document.createElement("p");
      detail.textContent = node.detail || "";

      card.appendChild(step);
      card.appendChild(label);
      card.appendChild(detail);
      return card;
    })
  );

  elements.pencilSketchImage.src = createPencilSketchImage(visualPlan);
  elements.pencilSketchImage.alt = "Pencil 草图：" + visualPlan.title;

  elements.blueprintRisks.replaceChildren.apply(
    elements.blueprintRisks,
    visualPlan.risks.map(function (risk) {
      var item = document.createElement("span");
      item.textContent = risk;
      return item;
    })
  );

  elements.pencilSketchLink.classList.add("hidden");
}

function escapeSvgText(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function createPencilSketchImage(visualPlan) {
  var nodes = visualPlan.nodes.slice(0, 4);
  var colors = [
    ["#EEF4FF", "#8FB4FF"],
    ["#F0FBFF", "#73D5FF"],
    ["#F4F8F2", "#9ED08B"],
    ["#FFF7ED", "#FFC078"],
  ];
  var cards = nodes
    .map(function (node, index) {
      var x = 70 + index * 215;
      var color = colors[index % colors.length];
      var fill = color[0];
      var stroke = color[1];
      var arrow = "";
      if (index < nodes.length - 1) {
        arrow =
          '<path d="M' + (x + 180) + " 238 C" + (x + 198) + " 222, " + (x + 222) + " 222, " + (x + 244) +
          ' 238" stroke="#1664FF" stroke-width="3" stroke-linecap="round"/>' +
          '<path d="M' + (x + 234) + " 226 L" + (x + 246) + " 238 L" + (x + 233) +
          ' 249" stroke="#1664FF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>';
      }
      return (
        '<g filter="url(#shadow)">' +
        '<rect x="' + x + '" y="174" width="170" height="126" rx="12" fill="' + fill + '" stroke="' + stroke + '" stroke-width="2"/>' +
        '<text x="' + (x + 24) + '" y="212" fill="#1F2329" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="18" font-weight="900">' + escapeSvgText(node.label) + "</text>" +
        '<text x="' + (x + 24) + '" y="246" fill="#4E5969" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="14">' + escapeSvgText((node.detail || "").slice(0, 15)) + "</text>" +
        '<text x="' + (x + 24) + '" y="271" fill="#4E5969" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="14">' + escapeSvgText((node.detail || "").slice(15, 32)) + "</text>" +
        "</g>" +
        arrow
      );
    })
    .join("");

  var risksSvg = visualPlan.risks
    .slice(0, 2)
    .map(function (risk, index) {
      return '<text x="94" y="' + (407 + index * 30) + '" fill="#8A5A00" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="15">' + (index + 1) + ". " + escapeSvgText(risk) + "</text>";
    })
    .join("");

  var svg =
    '<svg width="960" height="520" viewBox="0 0 960 520" fill="none" xmlns="http://www.w3.org/2000/svg">' +
    '<rect width="960" height="520" rx="18" fill="#F8FAFF"/>' +
    '<rect x="28" y="28" width="904" height="464" rx="14" fill="#FFFFFF" stroke="#CCD6E6" stroke-width="2" stroke-dasharray="8 8"/>' +
    '<text x="56" y="70" fill="#1664FF" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="18" font-weight="800">方案蓝图（AI 生成）</text>' +
    '<text x="56" y="106" fill="#1F2329" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="27" font-weight="900">' + escapeSvgText(visualPlan.title) + "</text>" +
    '<text x="56" y="140" fill="#4E5969" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="16">' + escapeSvgText((visualPlan.summary || "").slice(0, 46)) + "</text>" +
    cards +
    '<rect x="70" y="360" width="820" height="108" rx="12" fill="#FFF9DB" stroke="#FFD43B" stroke-width="2"/>' +
    '<text x="94" y="384" fill="#8A5A00" font-family="Segoe UI, Microsoft YaHei, sans-serif" font-size="17" font-weight="900">审批关注点</text>' +
    risksSvg +
    "<defs>" +
    '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">' +
    '<feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#1F2329" flood-opacity="0.12"/>' +
    "</filter>" +
    "</defs>" +
    "</svg>";

  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}

function renderReview() {
  var stage = getCurrentStage();
  var isWaitingReview = pipeline && pipeline.status === "waiting_review";

  elements.reviewState.textContent = isWaitingReview ? (stage ? stage.name + " 待确认" : "") : "暂时不用确认";
  elements.reviewPanel.classList.toggle("hidden", !isWaitingReview);
  elements.reviewEmpty.classList.toggle("hidden", isWaitingReview);
  elements.reviewControls.classList.toggle("hidden", !isWaitingReview);
  elements.rejectReason.disabled = !isWaitingReview;
  elements.approveButton.disabled = !isWaitingReview;
  elements.rejectButton.disabled = !isWaitingReview;
}

function renderControls() {
  var canRun = pipeline && pipeline.status === "ready";
  elements.runButton.disabled = !canRun || isRunning;
  elements.autoRunButton.classList.add("hidden");
}

function render() {
  setStatusBadge();
  renderDeliveryPackage();
  renderStages();
  renderArtifact();
  renderReview();
  renderRunMonitor();
  renderControls();
}

async function checkHealth() {
  try {
    await client.health();
    return true;
  } catch (_e) {
    return false;
  }
}

async function runUntilReviewOrComplete() {
  if (!pipeline) return;
  isRunning = true;
  runErrorMessage = "";
  abortController = new AbortController();
  var stage = getCurrentStage();
  runningStageName = stage ? stage.name : "";
  render();

  try {
    pipeline = await client.runUntilReview(pipeline.id);
  } catch (error) {
    runErrorMessage = error.message;
  } finally {
    isRunning = false;
    abortController = null;
    runningStageName = "";
    render();
  }
}

function openClarificationModal(requirement) {
  pendingRequirement = requirement;
  pendingProjectPath = elements.projectPathInput.value;
  elements.clarificationRequirement.textContent = requirement;
  elements.clarificationQuestions.innerHTML = clarificationFlow.getClarificationQuestions(requirement)
    .map(function (question) {
      return (
        '<label class="clarification-question" for="clarification-' + question.id + '">' +
          "<span>" + question.label + "</span>" +
          "<strong>" + question.question + "</strong>" +
          "<small>推荐：" + question.recommended + "</small>" +
          '<textarea id="clarification-' + question.id + '" name="' + question.id + '" rows="2" placeholder="' + question.placeholder + '"></textarea>' +
        "</label>"
      );
    })
    .join("");
  elements.clarificationModal.classList.remove("hidden");
  var firstInput = elements.clarificationQuestions.querySelector("textarea");
  if (firstInput) firstInput.focus();
}

function closeClarificationModal() {
  elements.clarificationModal.classList.add("hidden");
}

function collectClarificationAnswers() {
  var answers = {};
  clarificationFlow.getClarificationQuestions(pendingRequirement).forEach(function (question) {
    var input = elements.clarificationForm.querySelector('[name="' + question.id + '"]');
    answers[question.id] = input && input.value.trim() ? input.value.trim() : question.recommended;
  });
  return answers;
}

async function startPipeline(requirement, projectPath) {
  runErrorMessage = "";
  abortController = new AbortController();
  isRunning = true;
  runningStageName = "创建 Pipeline";
  render();

  try {
    pipeline = await client.createPipeline(requirement, projectPath);
  } catch (error) {
    runErrorMessage = error.message;
    isRunning = false;
    abortController = null;
    runningStageName = "";
    render();
    return;
  }

  isRunning = false;
  abortController = null;
  runningStageName = "";
  elements.rejectReason.value = "";
  await runUntilReviewOrComplete();
}

elements.form.addEventListener("submit", async function (event) {
  event.preventDefault();
  var requirement = elements.requirementInput.value.trim();
  if (!requirement) {
    await startPipeline(requirement, elements.projectPathInput.value);
    return;
  }
  if (clarificationFlow.shouldAskClarification(requirement)) {
    openClarificationModal(requirement);
    return;
  }
  await startPipeline(requirement, elements.projectPathInput.value);
});

elements.runButton.addEventListener("click", runUntilReviewOrComplete);
elements.autoRunButton.addEventListener("click", runUntilReviewOrComplete);

elements.stopButton.addEventListener("click", function () {
  if (!isRunning) {
    runErrorMessage = "当前没有正在运行的任务。";
    render();
    return;
  }
  runErrorMessage = "已暂停运行。";
  if (abortController) {
    abortController.abort();
  }
  isRunning = false;
  runningStageName = "";
  render();
});

async function approveCurrentStage() {
  if (!pipeline) return;
  try {
    pipeline = await client.submitReview(pipeline.id, "approve");
    elements.rejectReason.value = "";
    await runUntilReviewOrComplete();
  } catch (error) {
    runErrorMessage = error.message;
    render();
  }
}

elements.approveButton.addEventListener("click", approveCurrentStage);

async function rejectCurrentStage(reasonElement) {
  if (!pipeline) return;
  try {
    pipeline = await client.submitReview(pipeline.id, "reject", reasonElement.value);
    elements.rejectReason.value = "";
    render();
  } catch (error) {
    reasonElement.focus();
    reasonElement.placeholder = error.message;
  }
}

elements.rejectButton.addEventListener("click", function () {
  rejectCurrentStage(elements.rejectReason);
});

elements.clarificationCancel.addEventListener("click", function () {
  pendingRequirement = "";
  pendingProjectPath = "";
  closeClarificationModal();
});

elements.clarificationRecommend.addEventListener("click", function () {
  clarificationFlow.getClarificationQuestions(pendingRequirement).forEach(function (question) {
    var input = elements.clarificationForm.querySelector('[name="' + question.id + '"]');
    if (input && !input.value.trim()) {
      input.value = question.recommended;
    }
  });
});

elements.clarificationForm.addEventListener("submit", async function (event) {
  event.preventDefault();
  var enrichedRequirement = clarificationFlow.mergeClarificationAnswers(
    pendingRequirement,
    collectClarificationAnswers()
  );
  closeClarificationModal();
  await startPipeline(enrichedRequirement, pendingProjectPath);
});

elements.resetButton.addEventListener("click", function () {
  pipeline = null;
  runErrorMessage = "";
  pendingRequirement = "";
  pendingProjectPath = "";
  closeClarificationModal();
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
  elements.rejectReason.value = "";
  render();
});

// On load, show initial state and check backend health
render();
checkHealth().then(function (healthy) {
  if (healthy) {
    console.log("DevFlow Engine 后端已连接。");
  } else {
    console.warn("DevFlow Engine 后端未连接。请启动后端：uvicorn backend.main:app --reload");
  }
});
