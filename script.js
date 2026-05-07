// ── Global error trap for debugging ──
window.addEventListener("error", function (event) {
  console.error("[global error]", event.message, "at", event.filename, ":", event.lineno, ":", event.colno, "source:", event.target);
});
window.addEventListener("unhandledrejection", function (event) {
  console.error("[unhandled rejection]", event.reason);
});

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
var pendingTemplate = "feature";
var liveOutputEventSource = null;
var clarificationStepIndex = 0;
var clarificationAnswers = {};

var elements = {
  form: document.querySelector("#requestForm"),
  requirementInput: document.querySelector("#requirementInput"),
  templateSelector: document.querySelector("#templateSelector"),
  resetButton: document.querySelector("#resetButton"),
  deliveryPackage: document.querySelector("#deliveryPackage"),
  productPreviewSection: document.querySelector("#productPreviewSection"),
  productPreviewFrame: document.querySelector("#productPreviewFrame"),
  productPreviewLink: document.querySelector("#productPreviewLink"),
  productExpandBtn: document.querySelector("#productExpandBtn"),
  productFrameWrap: document.querySelector("#productFrameWrap"),
  prototypeFrameWrap: document.querySelector("#prototypeFrameWrap"),
  deliverySummaryTitle: document.querySelector("#deliverySummaryTitle"),
  deliverySummaryText: document.querySelector("#deliverySummaryText"),
  deliveryValidationTitle: document.querySelector("#deliveryValidationTitle"),
  deliveryValidationText: document.querySelector("#deliveryValidationText"),
  deliveryFiles: document.querySelector("#deliveryFiles"),
  pipelineStatus: document.querySelector("#pipelineStatus"),
  stageCount: document.querySelector("#stageCount"),
  stageList: document.querySelector("#stageList"),
  // Live output
  liveOutput: document.querySelector("#liveOutput"),
  obsPanel: document.querySelector("#obsPanel"),
  obsCards: document.querySelector("#obsCards"),
  obsSummary: document.querySelector("#obsSummary"),
  liveOutputStream: document.querySelector("#liveOutputStream"),
  liveOutputTitle: document.querySelector("#liveOutputTitle"),
  liveOutputStage: document.querySelector("#liveOutputStage"),
  liveOutputEmpty: document.querySelector("#liveOutputEmpty"),
  // Artifacts
  currentAgent: document.querySelector("#currentAgent"),
  artifactEmpty: document.querySelector("#artifactEmpty"),
  artifactCard: document.querySelector("#artifactCard"),
  artifactSections: document.querySelector("#artifactSections"),
  // Template elements (kept in hidden div, moved into sections when rendering)
  prdMap: document.querySelector("#prdMap"),
  prdMapTitle: document.querySelector("#prdMapTitle"),
  prdMapSummary: document.querySelector("#prdMapSummary"),
  prdMapFlow: document.querySelector("#prdMapFlow"),
  visualPlan: document.querySelector("#visualPlan"),
  visualPlanTitle: document.querySelector("#visualPlanTitle"),
  visualPlanSummary: document.querySelector("#visualPlanSummary"),
  blueprintFlow: document.querySelector("#blueprintFlow"),
  blueprintRisks: document.querySelector("#blueprintRisks"),
  prototypePreview: document.querySelector("#prototypePreview"),
  prototypeTitle: document.querySelector("#prototypeTitle"),
  prototypeDesc: document.querySelector("#prototypeDesc"),
  prototypeFrame: document.querySelector("#prototypeFrame"),
  prototypeExpandBtn: document.querySelector("#prototypeExpandBtn"),
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
  clarificationProgress: document.querySelector("#clarificationProgress"),
  clarificationStepLabel: document.querySelector("#clarificationStepLabel"),
  clarificationStepQuestion: document.querySelector("#clarificationStepQuestion"),
  clarificationStepHint: document.querySelector("#clarificationStepHint"),
  clarificationStepAnswer: document.querySelector("#clarificationStepAnswer"),
  clarificationDots: document.querySelector("#clarificationDots"),
  clarificationPrev: document.querySelector("#clarificationPrev"),
  clarificationNext: document.querySelector("#clarificationNext"),
  // Workspace
  workspace: document.querySelector("#workspace"),
  workspaceFileList: document.querySelector("#workspaceFileList"),
  workspaceFileCount: document.querySelector("#workspaceFileCount"),
  workspaceEmpty: document.querySelector("#workspaceEmpty"),
  workspacePath: document.querySelector("#workspacePath"),
  exportWorkspaceLink: document.querySelector("#exportWorkspaceLink"),
  workspaceGit: document.querySelector("#workspaceGit"),
  gitBranch: document.querySelector("#gitBranch"),
  gitCommit: document.querySelector("#gitCommit"),
  codeSearch: document.querySelector("#codeSearch"),
  codeSearchInput: document.querySelector("#codeSearchInput"),
  codeSearchResults: document.querySelector("#codeSearchResults"),
};

// ── Pipeline helpers ──

function getStages() {
  return (pipeline && pipeline.stages) ? pipeline.stages : STAGES;
}

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
  getStages().forEach(function (stage) {
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

function setStatusBadge() {
  elements.pipelineStatus.classList.remove("is-running", "is-review", "is-done");

  if (runErrorMessage) {
    elements.pipelineStatus.textContent = "错误：" + runErrorMessage;
    elements.pipelineStatus.style.color = "var(--accent-danger)";
    elements.pipelineStatus.style.borderColor = "rgba(245,74,69,0.28)";
    elements.pipelineStatus.style.background = "rgba(245,74,69,0.12)";
    return;
  }
  elements.pipelineStatus.style.color = "";
  elements.pipelineStatus.style.borderColor = "";
  elements.pipelineStatus.style.background = "";

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

// ── Live output panel ──

function showLiveOutput() {
  elements.liveOutputEmpty.classList.add("hidden");
}

function hideLiveOutput() {
  clearLiveOutput();
}

function clearLiveOutput() {
  // Remove dynamically-added children but keep liveOutputEmpty in the DOM
  var children = elements.liveOutputStream.children;
  for (var i = children.length - 1; i >= 0; i--) {
    if (children[i].id !== "liveOutputEmpty") {
      children[i].remove();
    }
  }
  elements.liveOutputEmpty.classList.remove("hidden");
  elements.liveOutputTitle.textContent = "AI 正在工作…";
  elements.liveOutputStage.textContent = "等待中";
}

function appendLiveChunk(text) {
  showLiveOutput();
  elements.liveOutputEmpty.classList.add("hidden");
  var span = document.createElement("span");
  span.className = "stream-chunk";
  span.textContent = text;
  elements.liveOutputStream.appendChild(span);
  elements.liveOutputStream.scrollTop = elements.liveOutputStream.scrollHeight;
}

function appendSystemMessage(text) {
  showLiveOutput();
  elements.liveOutputEmpty.classList.add("hidden");
  var div = document.createElement("div");
  div.className = "stream-system";
  div.textContent = "⚙ " + text;
  elements.liveOutputStream.appendChild(div);
  elements.liveOutputStream.scrollTop = elements.liveOutputStream.scrollHeight;
}

function appendErrorMessage(text) {
  showLiveOutput();
  elements.liveOutputEmpty.classList.add("hidden");
  var div = document.createElement("div");
  div.className = "stream-error";
  div.textContent = "✕ " + text;
  elements.liveOutputStream.appendChild(div);
  elements.liveOutputStream.scrollTop = elements.liveOutputStream.scrollHeight;
}

function setLiveOutputStage(stageName) {
  elements.liveOutputStage.textContent = stageName;
  elements.liveOutputTitle.textContent = "正在执行：" + stageName;
}

// ── Observability Panel ──

var _statsCards = {};  // stageId → stats data

function addStatsCard(stats) {
  _statsCards[stats.stageId] = stats;
  renderStatsPanel();
}

function renderStatsPanel() {
  var cards = Object.values(_statsCards);
  if (cards.length === 0) {
    elements.obsPanel.classList.add("hidden");
    return;
  }

  elements.obsPanel.classList.remove("hidden");

  // Summary
  var totalLatency = 0;
  var totalTokens = 0;
  cards.forEach(function (s) {
    totalLatency += s.latencyMs || 0;
    totalTokens += s.totalTokens || 0;
  });

  var latencyDisplay = totalLatency > 1000
    ? (totalLatency / 1000).toFixed(1) + "s"
    : totalLatency + "ms";
  elements.obsSummary.innerHTML =
    '<span class="obs-metric">⏱ 总耗时 <strong>' + latencyDisplay + '</strong></span>' +
    '<span class="obs-metric">🔤 总 Token <strong>' + formatNumber(totalTokens) + '</strong></span>' +
    '<span class="obs-metric">✅ 阶段 <strong>' + cards.length + '</strong></span>';

  // Cards — sort by stage order
  var stageOrder = ["requirement", "design", "code", "test", "review", "delivery"];
  var sorted = cards.slice().sort(function (a, b) {
    return stageOrder.indexOf(a.stageId) - stageOrder.indexOf(b.stageId);
  });

  elements.obsCards.innerHTML = sorted.map(function (s) {
    var latencyStr = s.latencyMs > 1000
      ? (s.latencyMs / 1000).toFixed(1) + "s"
      : s.latencyMs + "ms";
    return (
      '<div class="obs-card">' +
        '<div class="obs-card-head">' +
          '<span class="obs-card-stage ' + s.stageId + '">' + escapeHtml(s.stageName) + '</span>' +
          '<span class="obs-card-model">' + escapeHtml(s.model) + '</span>' +
        '</div>' +
        '<div class="obs-card-metrics">' +
          '<div class="obs-metric-item">' +
            '<span class="obs-metric-label">耗时</span>' +
            '<span class="obs-metric-value">' + latencyStr + '</span>' +
          '</div>' +
          '<div class="obs-metric-item">' +
            '<span class="obs-metric-label">Prompt Tokens</span>' +
            '<span class="obs-metric-value">' + formatNumber(s.promptTokens) + '</span>' +
          '</div>' +
          '<div class="obs-metric-item">' +
            '<span class="obs-metric-label">Completion Tokens</span>' +
            '<span class="obs-metric-value">' + formatNumber(s.completionTokens) + '</span>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }).join("");
}

function formatNumber(n) {
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

function disconnectLiveOutput() {
  if (liveOutputEventSource) {
    liveOutputEventSource.close();
    liveOutputEventSource = null;
  }
}

function connectLiveOutput(pipelineId) {
  disconnectLiveOutput();
  clearLiveOutput();
  showLiveOutput();

  return new Promise(function (resolve, reject) {
    try {
      liveOutputEventSource = new EventSource(
        "http://127.0.0.1:8001/pipelines/" + pipelineId + "/stream-run"
      );

      liveOutputEventSource.addEventListener("chunk", function (event) {
        appendLiveChunk(event.data);
      });

      liveOutputEventSource.addEventListener("system", function (event) {
        appendSystemMessage(event.data);
      });

      liveOutputEventSource.addEventListener("stage", function (event) {
        setLiveOutputStage(event.data);
      });

      liveOutputEventSource.addEventListener("stats", function (event) {
        try {
          var statsData = JSON.parse(event.data);
          addStatsCard(statsData);
        } catch (_) {}
      });

      liveOutputEventSource.addEventListener("auto_regression", function (event) {
        try {
          var regData = JSON.parse(event.data);
          appendSystemMessage(
            "⚠️ 自动回归：检测到评审问题，自动打回重新生成 " +
              regData.stageName +
              " (" + regData.retry + "/" + regData.maxRetries + ")\n" +
              "原因：" + regData.reason
          );
        } catch (_) {}
      });

      liveOutputEventSource.addEventListener("fail", function (event) {
        if (event.data) {
          appendErrorMessage(event.data);
        }
      });

      liveOutputEventSource.addEventListener("done", function () {
        appendSystemMessage("阶段执行完成");
        disconnectLiveOutput();
        resolve();
      });

      liveOutputEventSource.onerror = function () {
        if (liveOutputEventSource && liveOutputEventSource.readyState === EventSource.CLOSED) {
          resolve();
        }
        disconnectLiveOutput();
      };
    } catch (_e) {
      liveOutputEventSource = null;
      reject(_e);
    }
  });
}

// ── Render functions ──

function renderStages() {
  var completedIds = getCompletedStageIds();
  var currentId = pipeline ? pipeline.currentStageId : STAGES[0].id;
  var isCompleted = pipeline && pipeline.status === "completed";
  var stateLabels = { complete: "已完成", current: "进行中", pending: "待处理" };

  elements.stageList.innerHTML = getStages().map(function (stage, index) {
    var state = completedIds.has(stage.id)
      ? "complete"
      : stage.id === currentId
        ? "current"
        : "pending";
    var stateLabel = stateLabels[state];

    if (isCompleted && completedIds.has(stage.id)) {
      state = "complete";
      stateLabel = "已完成";
    }

    return (
      '<li class="stage-card is-' + state + '" data-stage-id="' + stage.id + '">' +
        '<span class="card-num">' + (index + 1) + "</span>" +
        '<span class="card-name">' + stage.name + "</span>" +
        '<span class="card-agent">' + stage.agent + "</span>" +
        '<span class="card-state">' + stateLabel + "</span>" +
      "</li>"
    );
  }).join("");

  elements.stageCount.textContent = completedIds.size + " / " + getStages().length;

  // Click-to-scroll for completed stages
  elements.stageList.querySelectorAll(".stage-card.is-complete").forEach(function (card) {
    card.addEventListener("click", function () {
      var stageId = card.dataset.stageId;
      var target = document.querySelector("#artifact-" + stageId);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        // Expand the section if collapsed
        var body = target.querySelector(".artifact-section-body");
        if (body && body.classList.contains("collapsed")) {
          var bar = target.querySelector(".artifact-section-bar");
          if (bar) bar.click();
        }
        // Brief highlight
        target.style.boxShadow = "0 0 0 3px rgba(74,159,216,0.4)";
        setTimeout(function () { target.style.boxShadow = ""; }, 1500);
      }
    });
  });
}

function renderArtifact() {
  var completedIds = Object.keys(pipeline ? pipeline.artifacts : {});

  if (completedIds.length === 0) {
    elements.artifactEmpty.classList.remove("hidden");
    elements.artifactCard.classList.add("hidden");
    elements.currentAgent.textContent = pipeline ? "等待 AI Agent 生成" : "等待开始";
    return;
  }

  elements.artifactEmpty.classList.add("hidden");
  elements.artifactCard.classList.remove("hidden");

  var latestArtifact = getLatestArtifact();
  elements.currentAgent.textContent = latestArtifact && latestArtifact.model
    ? latestArtifact.agent + " · " + latestArtifact.model
    : latestArtifact ? latestArtifact.agent : "";

  var tagClassMap = {
    "requirement": "stage-tag-req",
    "design": "stage-tag-design",
    "code": "stage-tag-code",
    "test": "stage-tag-test",
    "review": "stage-tag-review",
    "delivery": "stage-tag-delivery",
  };

  // Track existing sections to reuse DOM elements
  var existingSections = {};
  var children = elements.artifactSections.children;
  for (var i = 0; i < children.length; i++) {
    existingSections[children[i].dataset.stageId] = children[i];
  }

  // Sort artifacts by stage order, latest first
  var orderedIds = [];
  getStages().forEach(function (stage) {
    if (pipeline.artifacts[stage.id]) orderedIds.push(stage.id);
  });
  orderedIds.reverse();

  orderedIds.forEach(function (stageId) {
    var artifact = pipeline.artifacts[stageId];
    var existing = existingSections[stageId];
    var section = existing || document.createElement("section");
    section.className = "artifact-section";
    section.id = "artifact-" + stageId;
    section.dataset.stageId = stageId;

    var isCollapsed = section.dataset.collapsed === "true";
    var time = new Date(artifact.createdAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

    var tagClass = tagClassMap[stageId] || "";

    section.innerHTML =
      '<div class="artifact-section-bar">' +
        '<span class="stage-tag ' + tagClass + '">' + artifact.stageName + '</span>' +
        '<span class="artifact-section-agent">' + artifactRenderer.escapeHtml(artifact.model || "") + '</span>' +
        '<span class="artifact-section-time">' + time + '</span>' +
        '<button class="artifact-section-toggle" type="button">' + (isCollapsed ? "▸" : "▾") + '</button>' +
      '</div>' +
      '<div class="artifact-section-body' + (isCollapsed ? " collapsed" : "") + '">' +
        '<div class="markdown-document">' + artifactRenderer.renderMarkdown(artifact.content) + '</div>' +
        '<div class="section-extras" id="extras-' + stageId + '"></div>' +
      '</div>';

    if (!existing) {
      elements.artifactSections.appendChild(section);
    } else {
      // Re-append to move to correct position (newest first)
      elements.artifactSections.appendChild(section);
    }

    // Bind toggle click
    var bar = section.querySelector(".artifact-section-bar");
    bar.addEventListener("click", function (s, sid) {
      return function () {
        var body = s.querySelector(".artifact-section-body");
        var toggleBtn = s.querySelector(".artifact-section-toggle");
        var isNowCollapsed = !body.classList.contains("collapsed");
        body.classList.toggle("collapsed");
        toggleBtn.textContent = isNowCollapsed ? "▸" : "▾";
        s.dataset.collapsed = isNowCollapsed ? "true" : "false";
      };
    }(section, stageId));

    delete existingSections[stageId];
  });

  // Remove sections for stages that no longer have artifacts
  Object.keys(existingSections).forEach(function (id) {
    existingSections[id].remove();
  });

  // Render stage-specific extras
  renderPrdMap();
  renderPrototype();
  renderVisualPlan(getArtifact("design") ? getArtifact("design").visualPlan : null);
  renderCodeViewers();
  renderProductPreviewInCodeStage();
}

function renderPrdMap() {
  var reqArtifact = getArtifact("requirement");
  var extrasEl = document.querySelector("#extras-requirement");
  if (!reqArtifact || !extrasEl) return;

  // Remove old prdMap from extras
  var oldPrd = extrasEl.querySelector(".prd-map-inline");
  if (oldPrd) oldPrd.remove();

  var prdMap = artifactRenderer.buildPrdMap(reqArtifact.content);
  var wrapper = document.createElement("div");
  wrapper.className = "prd-map-inline";
  wrapper.innerHTML =
    '<div class="visual-plan-header">' +
      '<strong>' + artifactRenderer.escapeHtml(prdMap.title) + '</strong>' +
      '<p>' + artifactRenderer.escapeHtml(prdMap.summary || "") + '</p>' +
    '</div>' +
    '<div class="prd-map-flow">' + artifactRenderer.renderPrdMap(prdMap) + '</div>';
  extrasEl.appendChild(wrapper);
}

function renderPrototype() {
  var reqArtifact = getArtifact("requirement");
  var extrasEl = document.querySelector("#extras-requirement");
  if (!reqArtifact || !reqArtifact.prototypeHtml || !extrasEl) return;

  var oldProto = extrasEl.querySelector(".prototype-inline");
  if (oldProto) oldProto.remove();

  var wrapper = document.createElement("div");
  wrapper.className = "prototype-inline";
  wrapper.innerHTML =
    '<div class="visual-plan-header">' +
      '<strong>低保真原型预览</strong>' +
      '<p>AI 产品经理根据需求分析自动生成的原型页面</p>' +
      '<button class="ghost-button expand-preview-btn inline-expand-btn" type="button">⛶ 全屏</button>' +
    '</div>' +
    '<div class="product-preview-frame">' +
      '<iframe srcdoc="' + artifactRenderer.escapeHtml(reqArtifact.prototypeHtml).replace(/"/g, "&quot;") + '" sandbox="allow-scripts allow-same-origin allow-forms" title="需求原型预览"></iframe>' +
    '</div>';
  extrasEl.appendChild(wrapper);

  // Bind expand button
  var expandBtn = wrapper.querySelector(".inline-expand-btn");
  var frameWrap = wrapper.querySelector(".product-preview-frame");
  expandBtn.addEventListener("click", function () {
    if (expandedFrameWrap === frameWrap) {
      collapsePreview();
    } else {
      collapsePreview();
      expandPreview(frameWrap);
    }
  });
}

function renderVisualPlan(visualPlan) {
  var extrasEl = document.querySelector("#extras-design");
  if (!visualPlan || !extrasEl) return;

  var oldVp = extrasEl.querySelector(".visual-plan-inline");
  if (oldVp) oldVp.remove();

  var wrapper = document.createElement("div");
  wrapper.className = "visual-plan-inline";
  wrapper.innerHTML =
    '<div class="visual-plan-header">' +
      '<strong>' + artifactRenderer.escapeHtml(visualPlan.title) + '</strong>' +
      '<p>' + artifactRenderer.escapeHtml(visualPlan.summary || "") + '</p>' +
    '</div>' +
    '<div class="blueprint-flow"></div>' +
    '<div class="blueprint-risks"></div>';

  var flowEl = wrapper.querySelector(".blueprint-flow");
  visualPlan.nodes.forEach(function (node, index) {
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
    flowEl.appendChild(card);
  });

  var risksEl = wrapper.querySelector(".blueprint-risks");
  visualPlan.risks.forEach(function (risk) {
    var item = document.createElement("span");
    item.textContent = risk;
    risksEl.appendChild(item);
  });

  extrasEl.appendChild(wrapper);
}

function syntaxHighlightCode(code, ext) {
  var escaped = artifactRenderer.escapeHtml(code);
  if (ext === "js" || ext === "ts" || ext === "jsx" || ext === "tsx") {
    escaped = escaped
      .replace(/(\/\/.*)/g, '<span class="code-comment">$1</span>')
      .replace(/(&quot;[^&]*&quot;|&#39;[^&#39;]*&#39;|`[^`]*`)/g, '<span class="code-string">$1</span>')
      .replace(/\b(function|const|let|var|return|if|else|for|while|class|import|export|from|async|await|try|catch|throw|new|this|typeof|instanceof)\b/g, '<span class="code-keyword">$1</span>')
      .replace(/\b(true|false|null|undefined)\b/g, '<span class="code-keyword">$1</span>')
      .replace(/(\d+)/g, '<span class="code-number">$1</span>');
  } else if (ext === "html") {
    escaped = escaped
      .replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="code-comment">$1</span>')
      .replace(/(&lt;[\/]?[a-zA-Z][^&]*&gt;)/g, '<span class="code-keyword">$1</span>')
      .replace(/(&quot;[^&]*&quot;)/g, '<span class="code-string">$1</span>');
  } else if (ext === "css") {
    escaped = escaped
      .replace(/(\/\*[\s\S]*?\*\/)/g, '<span class="code-comment">$1</span>')
      .replace(/([.#@][a-zA-Z][\w-]*)/g, '<span class="code-variable">$1</span>')
      .replace(/(:[^;{]*;)/g, function (m) {
        return '<span class="code-string">' + m + '</span>';
      })
      .replace(/\b(px|em|rem|%|vh|vw|ms|s|deg|fr)\b/g, '<span class="code-number">$1</span>');
  } else if (ext === "md") {
    escaped = escaped
      .replace(/^(#{1,4}\s.*)$/gm, '<span class="code-keyword">$1</span>')
      .replace(/(\*\*[^*]+\*\*|`[^`]+`)/g, '<span class="code-string">$1</span>');
  }
  return escaped;
}

function getExt(filename) {
  var parts = filename.split(".");
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

function renderCodeViewers() {
  var codeArtifact = getArtifact("code");
  var extrasEl = document.querySelector("#extras-code");
  if (!codeArtifact || !extrasEl) return;

  var oldViewers = extrasEl.querySelector(".win98-viewers-wrap");
  if (oldViewers) oldViewers.remove();

  var changedFiles = codeArtifact.changedFiles || [];
  if (changedFiles.length === 0) return;

  var wrap = document.createElement("div");
  wrap.className = "win98-viewers-wrap";
  wrap.innerHTML = '<div class="visual-plan-header" style="margin-bottom:8px;"><strong>生成代码文件</strong><p>双击代码区域可全选</p></div>';

  var tabBar = document.createElement("div");
  tabBar.className = "win98-viewer__tabs";
  var bodyContainer = document.createElement("div");
  bodyContainer.className = "win98-viewer__body-container";
  var footerEl = document.createElement("div");
  footerEl.className = "win98-viewer__footer";
  footerEl.innerHTML = '<span class="win98-viewer__lang"></span><button class="win98-viewer__copy" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> 复制</button>';

  // Store file contents
  var fileContents = {};
  var activeFile = null;

  changedFiles.forEach(function (filePath) {
    fileContents[filePath] = null; // null = loading

    var tab = document.createElement("span");
    tab.className = "win98-viewer__tab";
    tab.textContent = filePath.replace("target-app/", "");
    tab.title = filePath;
    tab.addEventListener("click", function () {
      switchTab(filePath);
    });
    tabBar.appendChild(tab);
  });

  var viewerOuter = document.createElement("div");
  viewerOuter.className = "win98-viewer";

  var viewerInner = document.createElement("div");
  viewerInner.className = "win98-viewer__inner";

  var body = document.createElement("div");
  body.className = "win98-viewer__body";
  body.innerHTML = '<div class="win98-viewer__empty">正在加载文件…</div>';

  viewerInner.appendChild(tabBar);
  viewerInner.appendChild(body);
  viewerInner.appendChild(footerEl);
  viewerOuter.appendChild(viewerInner);

  // Double-click to select all code
  body.addEventListener("dblclick", function () {
    var range = document.createRange();
    range.selectNodeContents(body.querySelector(".win98-viewer__code") || body);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  });

  // Copy button
  var copyBtn = footerEl.querySelector(".win98-viewer__copy");
  copyBtn.addEventListener("click", function () {
    if (!activeFile || !fileContents[activeFile]) return;
    navigator.clipboard.writeText(fileContents[activeFile]).then(function () {
      copyBtn.textContent = "已复制!";
      setTimeout(function () {
        copyBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> 复制';
      }, 1500);
    }).catch(function () {
      copyBtn.textContent = "复制失败";
      setTimeout(function () {
        copyBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> 复制';
      }, 1500);
    });
  });

  function switchTab(filePath) {
    activeFile = filePath;
    // Update tabs
    tabBar.querySelectorAll(".win98-viewer__tab").forEach(function (t) {
      t.classList.toggle("active", t.textContent === filePath.replace("target-app/", ""));
    });
    // Update body
    var content = fileContents[filePath];
    var ext = getExt(filePath);
    if (content === null) {
      body.innerHTML = '<div class="win98-viewer__empty">加载中…</div>';
    } else {
      var lines = content.split("\n");
      var lineNums = "";
      for (var i = 0; i < lines.length; i++) {
        lineNums += '<span>' + (i + 1) + '</span>';
      }
      body.innerHTML =
        '<div class="win98-viewer__lines">' + lineNums + '</div>' +
        '<code class="win98-viewer__code">' + syntaxHighlightCode(content, ext) + '</code>';
    }
    var lineCount = content === null ? 0 : content.split("\n").length;
    footerEl.querySelector(".win98-viewer__lang").textContent = ext.toUpperCase() + " · " + lineCount + " lines";
  }

  // Fetch all files
  changedFiles.forEach(function (filePath) {
    var url = "http://127.0.0.1:8001/pipelines/" + pipeline.id + "/workspace/files/" + filePath;
    fetch(url)
      .then(function (res) { return res.text(); })
      .then(function (text) {
        fileContents[filePath] = text;
        if (activeFile === filePath || activeFile === null) {
          if (activeFile === null) activeFile = filePath;
          switchTab(filePath);
        }
      })
      .catch(function () {
        fileContents[filePath] = "// Failed to load: " + filePath;
        if (activeFile === filePath || activeFile === null) {
          if (activeFile === null) activeFile = filePath;
          switchTab(filePath);
        }
      });
  });

  wrap.appendChild(viewerOuter);
  extrasEl.appendChild(wrap);
}

function renderProductPreviewInCodeStage() {
  var codeArtifact = getArtifact("code");
  var extrasEl = document.querySelector("#extras-code");
  if (!codeArtifact || !extrasEl) return;

  var oldPreview = extrasEl.querySelector(".product-preview-inline");
  if (oldPreview) oldPreview.remove();

  var previewUrl = "http://127.0.0.1:8001/runs/" + pipeline.id + "/target-app/index.html";
  var wrapper = document.createElement("div");
  wrapper.className = "product-preview-inline";
  wrapper.innerHTML =
    '<div class="visual-plan-header">' +
      '<strong>产品预览</strong>' +
      '<p>当前生成的页面效果，不满意可在评审时打回修改</p>' +
      '<button class="ghost-button expand-preview-btn inline-expand-btn" type="button">⛶ 全屏</button>' +
    '</div>' +
    '<div class="product-preview-frame">' +
      '<iframe src="' + previewUrl + '" sandbox="allow-scripts allow-same-origin allow-forms" title="产品预览"></iframe>' +
    '</div>';
  extrasEl.appendChild(wrapper);

  var expandBtn = wrapper.querySelector(".inline-expand-btn");
  var frameWrap = wrapper.querySelector(".product-preview-frame");
  expandBtn.addEventListener("click", function () {
    if (expandedFrameWrap === frameWrap) {
      collapsePreview();
    } else {
      collapsePreview();
      expandPreview(frameWrap);
    }
  });
}

function renderReview() {
  var stage = getCurrentStage();
  var isWaitingReview = pipeline && pipeline.status === "waiting_review";

  elements.reviewState.textContent = isWaitingReview ? (stage ? stage.name + " 待确认" : "") : "暂时不用确认";
  elements.reviewEmpty.classList.toggle("hidden", isWaitingReview);
  elements.reviewControls.classList.toggle("hidden", !isWaitingReview);
  elements.rejectReason.disabled = !isWaitingReview;
  elements.approveButton.disabled = !isWaitingReview;
  elements.rejectButton.disabled = !isWaitingReview;
}

// Show product preview as soon as code is generated (BEFORE delivery stage)
function renderProductPreview() {
  var previewUrl = getProductPreviewUrl();
  var hasPreview = !!(pipeline && getArtifact("code"));
  elements.productPreviewSection.classList.toggle("hidden", !hasPreview);

  if (!hasPreview) {
    elements.productPreviewFrame.removeAttribute("src");
    return;
  }

  elements.productPreviewFrame.src = previewUrl;
  elements.productPreviewLink.href = previewUrl || "#";
  elements.productPreviewLink.classList.toggle("is-disabled", !previewUrl);
}

// Show delivery summary only when pipeline is fully completed
function renderDeliveryPackage() {
  var isComplete = pipeline && pipeline.status === "completed";
  elements.deliveryPackage.classList.toggle("hidden", !isComplete);

  if (!isComplete) return;

  var delivery = getArtifact("delivery");
  var code = getArtifact("code");
  var test = getArtifact("test");
  var review = getArtifact("review");

  elements.deliverySummaryTitle.textContent = pipeline.requirement;
  elements.deliverySummaryText.textContent = delivery
    ? "最终交付物已生成，包含代码变更、测试文件和交付总结。"
    : "产品已经生成，交付说明暂未生成。";
  elements.deliveryValidationTitle.textContent = test ? "已生成测试文件" : "等待测试产物";
  elements.deliveryValidationText.textContent = test
    ? "可在运行副本中执行测试验证代码改动。"
    : "等待测试阶段完成后会显示验证方式。";
  if (review && review.content) {
    elements.deliveryValidationText.textContent += " 已生成评审结论。";
  }

  var changedFiles = [];
  if (code && code.changedFiles) changedFiles = changedFiles.concat(code.changedFiles);
  if (test && test.changedFiles) changedFiles = changedFiles.concat(test.changedFiles);

  elements.deliveryFiles.replaceChildren.apply(
    elements.deliveryFiles,
    changedFiles.map(function (file) {
      var item = document.createElement("li");
      item.textContent = file;
      return item;
    })
  );
}

function renderWorkspace() {
  if (!pipeline) {
    elements.workspaceFileCount.textContent = "0 个文件";
    elements.workspacePath.textContent = "";
    elements.exportWorkspaceLink.href = "#";
    elements.workspaceEmpty.classList.remove("hidden");
    elements.workspaceFileList.querySelectorAll(".workspace-file-item").forEach(function (el) { el.remove(); });
    return;
  }

  var completedIds = Object.keys(pipeline.artifacts);
  if (completedIds.length === 0) {
    elements.workspaceFileCount.textContent = "0 个文件";
    elements.workspacePath.textContent = "";
    elements.exportWorkspaceLink.href = "#";
    elements.workspaceEmpty.classList.remove("hidden");
    elements.workspaceFileList.querySelectorAll(".workspace-file-item").forEach(function (el) { el.remove(); });
    elements.codeSearch.classList.add("hidden");
    return;
  }

  var hasCode = !!getArtifact("code");
  elements.codeSearch.classList.toggle("hidden", !hasCode);

  elements.exportWorkspaceLink.href =
    "http://127.0.0.1:8001/pipelines/" + pipeline.id + "/workspace/export";

  fetch("http://127.0.0.1:8001/pipelines/" + pipeline.id + "/workspace")
    .then(function (res) { return res.json(); })
    .then(function (data) {
      var files = data.files || [];
      elements.workspaceFileCount.textContent = files.length + " 个文件";
      elements.workspacePath.textContent = data.path || "";

      // Git status
      if (data.git) {
        elements.workspaceGit.classList.remove("hidden");
        elements.gitBranch.textContent = data.git.branch || "";
        elements.gitCommit.textContent = data.git.commit || "";
        if (data.git.log) {
          elements.gitCommit.title = data.git.log;
        }
      } else {
        elements.workspaceGit.classList.add("hidden");
      }

      if (files.length === 0) {
        elements.workspaceEmpty.classList.remove("hidden");
        elements.workspaceFileList.querySelectorAll(".workspace-file-item").forEach(function (el) { el.remove(); });
        return;
      }

      elements.workspaceEmpty.classList.add("hidden");

      var existingItems = {};
      elements.workspaceFileList.querySelectorAll(".workspace-file-item").forEach(function (el) {
        existingItems[el.dataset.filename] = el;
      });

      files.forEach(function (file) {
        var name = file.name;
        var size = file.size < 1024
          ? file.size + " B"
          : file.size < 1024 * 1024
            ? (file.size / 1024).toFixed(1) + " KB"
            : (file.size / (1024 * 1024)).toFixed(1) + " MB";

        if (existingItems[name]) {
          var sizeEl = existingItems[name].querySelector(".file-size");
          if (sizeEl) sizeEl.textContent = size;
          delete existingItems[name];
          return;
        }

        var item = document.createElement("div");
        item.className = "workspace-file-item";
        item.dataset.filename = name;
        item.title = "点击预览文件";

        var icon = document.createElement("span");
        icon.className = "file-icon";
        var ext = name.split(".").pop().toLowerCase();
        icon.textContent = ext === "md" ? "📄" : ext === "html" ? "🌐" : ext === "mmd" ? "📊" : "📁";

        var info = document.createElement("div");
        info.className = "file-info";

        var fileName = document.createElement("span");
        fileName.className = "file-name";
        fileName.textContent = name;

        var fileSize = document.createElement("span");
        fileSize.className = "file-size";
        fileSize.textContent = size;

        info.appendChild(fileName);
        info.appendChild(fileSize);

        var preview = document.createElement("a");
        preview.className = "file-link";
        preview.href = "http://127.0.0.1:8001/pipelines/" + pipeline.id + "/workspace/files/" + name;
        preview.target = "_blank";
        preview.textContent = "打开";

        item.appendChild(icon);
        item.appendChild(info);
        item.appendChild(preview);
        elements.workspaceFileList.appendChild(item);
      });

      Object.keys(existingItems).forEach(function (name) {
        existingItems[name].remove();
      });
    })
    .catch(function () {
      // Workspace not ready yet
    });
}

function render() {
  setStatusBadge();
  renderStages();
  renderArtifact();
  renderReview();
  renderWorkspace();
  renderProductPreview();
  renderDeliveryPackage();
}

// ── API actions ──

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
    await connectLiveOutput(pipeline.id);
    pipeline = await client.getPipeline(pipeline.id);
  } catch (error) {
    runErrorMessage = error.message || "执行失败";
    if (error.message) {
      appendErrorMessage(error.message);
    }
  } finally {
    isRunning = false;
    abortController = null;
    runningStageName = "";
    disconnectLiveOutput();
    render();
  }
}

function openClarificationModal(requirement) {
  console.log("[openClarificationModal] opening for requirement:", requirement ? requirement.substring(0, 60) : "(empty)");
  pendingRequirement = requirement;
  pendingTemplate = elements.templateSelector ? elements.templateSelector.value : "feature";
  clarificationStepIndex = 0;
  clarificationAnswers = {};
  elements.clarificationRequirement.textContent = requirement;
  elements.clarificationModal.classList.remove("hidden");
  console.log("[openClarificationModal] modal shown, calling renderClarificationStep");
  renderClarificationStep();
}

function closeClarificationModal() {
  elements.clarificationModal.classList.add("hidden");
  clarificationStepIndex = 0;
  clarificationAnswers = {};
}

function renderClarificationDots() {
  var questions = clarificationFlow.getClarificationQuestions(pendingRequirement);
  elements.clarificationDots.innerHTML = questions.map(function (_, index) {
    var cls = "dot";
    if (index < clarificationStepIndex) cls += " done";
    if (index === clarificationStepIndex) cls += " active";
    return '<span class="' + cls + '"></span>';
  }).join("");
}

function renderClarificationStep() {
  console.log("[renderClarificationStep] stepIndex=", clarificationStepIndex);
  var questions = clarificationFlow.getClarificationQuestions(pendingRequirement);
  var total = questions.length;
  var question = questions[clarificationStepIndex];
  console.log("[renderClarificationStep] question:", question.label);

  elements.clarificationProgress.textContent = (clarificationStepIndex + 1) + " / " + total;
  elements.clarificationStepLabel.textContent = question.label;
  elements.clarificationStepQuestion.textContent = question.question;
  elements.clarificationStepHint.textContent = "推荐：" + question.recommended;
  elements.clarificationStepAnswer.placeholder = question.placeholder;
  elements.clarificationStepAnswer.value = clarificationAnswers[question.id] || "";

  var isLast = clarificationStepIndex === total - 1;
  var isFirst = clarificationStepIndex === 0;

  elements.clarificationPrev.classList.toggle("hidden", isFirst);
  elements.clarificationNext.textContent = isLast ? "提交回答并生成 PRD" : "下一题";
  elements.clarificationNext.type = "button";
  elements.clarificationNext.classList.toggle("primary-button", true);
  elements.clarificationNext.classList.toggle("secondary-button", !isLast);
  elements.clarificationRecommend.textContent = "使用推荐回答";

  renderClarificationDots();
  elements.clarificationStepAnswer.focus();
  console.log("[renderClarificationStep] done, button text:", elements.clarificationNext.textContent);
}

function collectClarificationAnswers() {
  return clarificationAnswers;
}

async function startPipeline(requirement, projectPath, template) {
  console.log("[startPipeline] called, requirement length:", requirement ? requirement.length : 0);
  runErrorMessage = "";
  abortController = new AbortController();
  isRunning = true;
  runningStageName = "创建 Pipeline";
  try {
    render();
  } catch (e) {
    console.error("[startPipeline] render threw:", e);
  }

  try {
    console.log("[startPipeline] POST /pipelines with requirement:", requirement ? requirement.substring(0, 80) : "");
    pipeline = await client.createPipeline(requirement, projectPath, template);
    console.log("[startPipeline] pipeline created:", pipeline.id);
  } catch (error) {
    console.error("[startPipeline] createPipeline failed:", error.message);
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
  console.log("[startPipeline] calling runUntilReviewOrComplete...");
  await runUntilReviewOrComplete();
}

// ── Event listeners ──

elements.form.addEventListener("submit", async function (event) {
  event.preventDefault();
  var requirement = elements.requirementInput.value.trim();
  var template = elements.templateSelector ? elements.templateSelector.value : "feature";
  if (!requirement) {
    await startPipeline(requirement, "", template);
    return;
  }
  if (clarificationFlow.shouldAskClarification(requirement)) {
    openClarificationModal(requirement);
    return;
  }
  await startPipeline(requirement, "", template);
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
    clearLiveOutput();
    render();
    await runUntilReviewOrComplete();
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
  closeClarificationModal();
});

elements.clarificationRecommend.addEventListener("click", function () {
  var questions = clarificationFlow.getClarificationQuestions(pendingRequirement);
  var question = questions[clarificationStepIndex];
  elements.clarificationStepAnswer.value = question.recommended;
  clarificationAnswers[question.id] = question.recommended;
});

elements.clarificationPrev.addEventListener("click", function () {
  var questions = clarificationFlow.getClarificationQuestions(pendingRequirement);
  // Save current answer
  var question = questions[clarificationStepIndex];
  var value = elements.clarificationStepAnswer.value.trim();
  if (value) clarificationAnswers[question.id] = value;

  if (clarificationStepIndex > 0) {
    clarificationStepIndex -= 1;
    renderClarificationStep();
  }
});

elements.clarificationNext.addEventListener("click", function () {
  submitClarification();
});

elements.clarificationForm.addEventListener("submit", function (event) {
  event.preventDefault();
  submitClarification();
});

elements.clarificationStepAnswer.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitClarification();
  }
});

function submitClarification() {
  console.log("[submitClarification] called, stepIndex=", clarificationStepIndex);
  var questions = clarificationFlow.getClarificationQuestions(pendingRequirement);
  var total = questions.length;
  console.log("[submitClarification] total questions=", total);

  // Save current step answer
  var question = questions[clarificationStepIndex];
  var value = elements.clarificationStepAnswer.value.trim();
  if (value) clarificationAnswers[question.id] = value;

  // If not on last step, advance
  if (clarificationStepIndex < total - 1) {
    clarificationStepIndex += 1;
    console.log("[submitClarification] advancing to step", clarificationStepIndex);
    renderClarificationStep();
    return;
  }

  // Final step: submit with all answers
  console.log("[submitClarification] final step, submitting...");
  questions.forEach(function (q) {
    if (!clarificationAnswers[q.id]) {
      clarificationAnswers[q.id] = q.recommended;
    }
  });

  var enrichedRequirement = clarificationFlow.mergeClarificationAnswers(
    pendingRequirement,
    clarificationAnswers
  );
  console.log("[submitClarification] merged requirement length:", enrichedRequirement.length);
  closeClarificationModal();
  console.log("[submitClarification] calling startPipeline...");
  startPipeline(enrichedRequirement, "", pendingTemplate);
}

// ── Preview expand/collapse ──

var expandedFrameWrap = null;
var backdropEl = null;

function createBackdrop() {
  if (backdropEl) return;
  backdropEl = document.createElement("div");
  backdropEl.className = "preview-backdrop";
  backdropEl.addEventListener("click", collapsePreview);
  document.body.appendChild(backdropEl);
}

function removeBackdrop() {
  if (backdropEl) {
    backdropEl.remove();
    backdropEl = null;
  }
}

function expandPreview(frameWrap) {
  createBackdrop();
  frameWrap.classList.add("is-expanded");
  expandedFrameWrap = frameWrap;
}

function collapsePreview() {
  if (expandedFrameWrap) {
    expandedFrameWrap.classList.remove("is-expanded");
    expandedFrameWrap = null;
  }
  removeBackdrop();
}

document.addEventListener("keydown", function (event) {
  if (event.key === "Escape" && expandedFrameWrap) {
    collapsePreview();
  }
});

elements.prototypeExpandBtn.addEventListener("click", function () {
  if (expandedFrameWrap === elements.prototypeFrameWrap) {
    collapsePreview();
  } else {
    collapsePreview();
    expandPreview(elements.prototypeFrameWrap);
  }
});

elements.productExpandBtn.addEventListener("click", function () {
  if (expandedFrameWrap === elements.productFrameWrap) {
    collapsePreview();
  } else {
    collapsePreview();
    expandPreview(elements.productFrameWrap);
  }
});

// ── Code Search ──

var searchDebounceTimer = null;

function performCodeSearch(query) {
  if (!pipeline || !query.trim()) {
    elements.codeSearchResults.classList.add("hidden");
    elements.codeSearchResults.innerHTML = "";
    return;
  }

  var url = "http://127.0.0.1:8001/pipelines/" + pipeline.id + "/code-search?q=" + encodeURIComponent(query) + "&type=symbol";
  fetch(url)
    .then(function (res) { return res.json(); })
    .then(function (data) {
      var results = data.results || [];
      if (results.length === 0) {
        elements.codeSearchResults.classList.remove("hidden");
        elements.codeSearchResults.innerHTML = '<div class="code-search-empty">未找到匹配的符号</div>';
        return;
      }
      elements.codeSearchResults.classList.remove("hidden");
      var kindClassMap = {
        "function": "kind-function",
        "class": "kind-class",
        "html_element": "kind-html_element",
        "css_rule": "kind-css_rule",
        "event": "kind-event",
      };
      elements.codeSearchResults.innerHTML = results.map(function (r) {
        var kindClass = kindClassMap[r.kind] || "";
        return (
          '<div class="code-search-result-item" title="' + r.file + ':' + r.line + '">' +
            '<span class="code-search-kind ' + kindClass + '">' + r.kind + '</span>' +
            '<div>' +
              '<span class="code-search-name">' + artifactRenderer.escapeHtml(r.name) + '</span>' +
              ' <span class="code-search-file">' + r.file + ':' + r.line + '</span>' +
              '<div class="code-search-snippet">' + artifactRenderer.escapeHtml(r.snippet || "") + '</div>' +
            '</div>' +
          '</div>'
        );
      }).join("");
    })
    .catch(function () {
      elements.codeSearchResults.classList.add("hidden");
    });
}

elements.codeSearchInput.addEventListener("input", function () {
  clearTimeout(searchDebounceTimer);
  var query = elements.codeSearchInput.value;
  searchDebounceTimer = setTimeout(function () {
    performCodeSearch(query);
  }, 250);
});

elements.resetButton.addEventListener("click", function () {
  pipeline = null;
  runErrorMessage = "";
  pendingRequirement = "";
  disconnectLiveOutput();
  hideLiveOutput();
  if (abortController) {
    abortController.abort();
    abortController = null;
  }
  elements.rejectReason.value = "";
  render();
});

// On load, show initial state and check backend health
render();

// Validate all critical element references
(function validateElements() {
  var criticalIds = [
    "requirementInput", "clarificationNext", "clarificationStepAnswer",
    "clarificationModal", "clarificationForm", "requestForm", "liveOutputStream",
    "pipelineStatus", "approveButton", "rejectButton"
  ];
  criticalIds.forEach(function (id) {
    var el = document.querySelector("#" + id);
    if (el) {
      console.log("[validate] #" + id + " ✓");
    } else {
      console.error("[validate] #" + id + " ✗ NOT FOUND");
    }
  });
  console.log("[validate] elements.requirementInput:", elements.requirementInput);
  console.log("[validate] elements.clarificationNext:", elements.clarificationNext);
  console.log("[validate] elements.clarificationStepAnswer:", elements.clarificationStepAnswer);
  console.log("[validate] elements.form:", elements.form);
})();

checkHealth().then(function (healthy) {
  if (healthy) {
    console.log("DevFlow Engine 后端已连接。");
  } else {
    console.warn("DevFlow Engine 后端未连接。请启动后端：uvicorn backend.main:app --reload");
  }
});
