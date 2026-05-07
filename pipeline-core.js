(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DevFlowCore = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var STAGES = [
    { id: "requirement", name: "需求分析", agent: "需求分析 Agent", approvalRequired: true },
    { id: "design", name: "方案设计", agent: "方案设计 Agent", approvalRequired: true },
    { id: "code", name: "代码生成", agent: "代码生成 Agent", approvalRequired: true },
    { id: "test", name: "测试生成", agent: "测试生成 Agent", approvalRequired: true },
    { id: "review", name: "代码评审", agent: "代码评审 Agent", approvalRequired: true },
    { id: "delivery", name: "交付总结", agent: "交付总结 Agent", approvalRequired: true },
  ];

  /**
   * Build a rotating stage wheel. Items are positioned on a circle;
   * the wheel rotates so the active stage sits at the top pointer.
   *
   * Returns { items, wheelRotation, radius, activeIndex }:
   *   - items[i].angle  — degrees clockwise from top (0 = top, 60 = right, …)
   *   - wheelRotation   — CSS deg to rotate the wheel so current stage is at top
   *   - radius          — wheel radius in px
   */
  function createStageWheelItems(stages, currentStageId, completedStageIds) {
    var safeStages = stages || [];
    var completed = completedStageIds || new Set();
    var count = Math.max(safeStages.length, 1);
    var activeIndex = safeStages.findIndex(function (stage) {
      return stage.id === currentStageId;
    });
    if (activeIndex < 0) activeIndex = 0;

    var segmentAngle = 360 / count;
    var radius = 195;
    var wheelRotation = -activeIndex * segmentAngle;

    var items = safeStages.map(function (stage, index) {
      var angle = index * segmentAngle;
      var state = completed.has(stage.id)
        ? "complete"
        : stage.id === currentStageId
          ? "current"
          : "pending";

      return {
        id: stage.id,
        name: stage.name,
        agent: stage.agent,
        approvalRequired: stage.approvalRequired,
        angle: Math.round(angle),
        state: state,
      };
    });

    return {
      items: items,
      wheelRotation: Math.round(wheelRotation) || 0,
      radius: radius,
      activeIndex: activeIndex,
    };
  }

  /**
   * Create a DevFlow API client bound to a base URL.
   * @param {string} [baseUrl="http://127.0.0.1:8000"]
   */
  function createClient(baseUrl) {
    var apiBase = (baseUrl || "http://127.0.0.1:8000").replace(/\/+$/, "");

    /**
     * @param {string} path
     * @param {RequestInit} [options]
     * @returns {Promise<any>}
     */
    async function request(path, options) {
      var headers = { "Content-Type": "application/json" };
      if (options && options.headers) {
        headers = Object.assign(headers, options.headers);
      }

      var url = apiBase + path;
      console.log("[pipeline-core request] " + (options ? options.method || "GET" : "GET") + " " + url);

      var response;
      try {
        response = await fetch(url, Object.assign({}, options, { headers: headers }));
        console.log("[pipeline-core request] response status:", response.status);
      } catch (_err) {
        console.error("[pipeline-core request] fetch failed:", _err.message || _err);
        throw new Error(
          "API 服务未连接。请先启动后端：\n" +
          "  pip install -r requirements.txt\n" +
          "  uvicorn backend.main:app --reload\n\n" +
          "然后确保设置了 LLM 环境变量：\n" +
          "  DEVFLOW_LLM_ENABLED=true\n" +
          "  DEVFLOW_LLM_API_KEY=你的API密钥\n" +
          "  DEVFLOW_LLM_BASE_URL=https://api.lingyaai.cn"
        );
      }

      if (!response.ok) {
        var message = "API 请求失败：" + response.status;
        try {
          var payload = await response.json();
          message = payload.detail || message;
        } catch (_e) {
          message = response.statusText || message;
        }
        throw new Error(message);
      }

      return response.json();
    }

    return {
      health: function () {
        return request("/health");
      },

      createPipeline: function (requirement, projectPath, template) {
        return request("/pipelines", {
          method: "POST",
          body: JSON.stringify({
            requirement: requirement,
            projectPath: projectPath || undefined,
            template: template || "feature",
          }),
        });
      },

      getPipeline: function (pipelineId) {
        return request("/pipelines/" + pipelineId);
      },

      runUntilReview: function (pipelineId) {
        return request("/pipelines/" + pipelineId + "/run-until-review", {
          method: "POST",
        });
      },

      runNext: function (pipelineId) {
        return request("/pipelines/" + pipelineId + "/run-next", {
          method: "POST",
        });
      },

      submitReview: function (pipelineId, decision, reason) {
        return request("/pipelines/" + pipelineId + "/review", {
          method: "POST",
          body: JSON.stringify({
            decision: decision,
            reason: reason || "",
          }),
        });
      },
    };
  }

  return {
    STAGES: STAGES,
    createClient: createClient,
    createStageWheelItems: createStageWheelItems,
  };
});
