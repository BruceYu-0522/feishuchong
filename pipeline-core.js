(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DevFlowCore = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const STAGES = [
    {
      id: "requirement",
      name: "需求分析",
      agent: "需求分析 Agent",
      approvalRequired: false,
    },
    {
      id: "design",
      name: "方案设计",
      agent: "方案设计 Agent",
      approvalRequired: true,
    },
    {
      id: "code",
      name: "代码生成",
      agent: "代码生成 Agent",
      approvalRequired: false,
    },
    {
      id: "test",
      name: "测试生成",
      agent: "测试生成 Agent",
      approvalRequired: false,
    },
    {
      id: "review",
      name: "代码评审",
      agent: "代码评审 Agent",
      approvalRequired: true,
    },
    {
      id: "delivery",
      name: "交付总结",
      agent: "交付总结 Agent",
      approvalRequired: false,
    },
  ];

  const DEFAULT_REQUIREMENT = "给任务管理系统增加按优先级筛选任务的功能";

  function clonePipeline(pipeline) {
    return {
      ...pipeline,
      artifacts: { ...pipeline.artifacts },
      reviewHistory: [...pipeline.reviewHistory],
    };
  }

  function getCurrentStage(pipeline) {
    return STAGES.find((stage) => stage.id === pipeline.currentStageId);
  }

  function getStageIndex(stageId) {
    return STAGES.findIndex((stage) => stage.id === stageId);
  }

  function getLatestRejectReason(pipeline, stageId) {
    const review = [...pipeline.reviewHistory]
      .reverse()
      .find((item) => item.stageId === stageId && item.decision === "reject");
    return review ? review.reason : "";
  }

  function createDesignVisualPlan(rejectReason) {
    return {
      title: "优先级筛选方案蓝图",
      summary: rejectReason
        ? `本版方案已补充处理：${rejectReason}`
        : "从任务数据、筛选控件、列表渲染和空状态四个点完成优先级筛选。",
      nodes: [
        { id: "data", label: "Task 数据结构", detail: "新增 priority: high / medium / low" },
        { id: "toolbar", label: "筛选控件", detail: "全部 / 高 / 中 / 低 segmented filter" },
        { id: "list", label: "列表过滤", detail: "按 priorityFilter 过滤任务集合" },
        { id: "empty", label: "空状态", detail: "无匹配任务时提示并提供重置入口" },
      ],
      edges: [
        ["data", "toolbar"],
        ["toolbar", "list"],
        ["list", "empty"],
      ],
      risks: ["筛选条件需要和搜索、排序共存", "priority 字段需要默认值"],
    };
  }

  function createArtifact(stage, content, extra = {}) {
    return {
      stageId: stage.id,
      stageName: stage.name,
      agent: stage.agent,
      content,
      createdAt: new Date().toISOString(),
      ...extra,
    };
  }

  function createPipeline(requirement) {
    return {
      id: `df-${Date.now()}`,
      requirement: requirement && requirement.trim() ? requirement.trim() : DEFAULT_REQUIREMENT,
      status: "ready",
      currentStageId: "requirement",
      stages: STAGES.map((stage) => ({ ...stage })),
      artifacts: {},
      reviewHistory: [],
    };
  }

  function generateRequirement(pipeline) {
    return [
      "用户故事：作为任务管理系统用户，我希望可以按高、中、低优先级筛选任务，以便优先处理重要事项。",
      "功能范围：在任务列表上方增加优先级筛选控件，支持全部、高、中、低四种选项。",
      "验收标准：切换筛选项后，列表只显示匹配任务；选择全部时恢复完整列表；无匹配任务时显示空状态。",
      `原始需求：${pipeline.requirement}`,
    ].join("\n\n");
  }

  function generateDesign(pipeline) {
    const rejectReason = getLatestRejectReason(pipeline, "design");
    const reviewNote = rejectReason
      ? `\n\n针对上次驳回补充：已加入“${rejectReason}”处理，空状态会显示提示文案，并保留重置筛选入口。`
      : "";

    return [
      "技术方案：在任务列表顶部增加 segmented filter 控件，筛选状态由前端维护。",
      "涉及模块：TaskToolbar、TaskList、Task 数据结构、空状态组件。",
      "数据结构：Task 增加 priority 字段，可取 high / medium / low。",
      "UI 变化：新增优先级筛选按钮组，并在无结果时展示空状态。",
      "风险点：筛选条件需要与搜索条件共存，避免状态互相覆盖。",
    ].join("\n\n") + reviewNote;
  }

  function generateCode(pipeline) {
    return [
      "修改文件列表：",
      "- src/components/TaskToolbar.tsx",
      "- src/components/TaskList.tsx",
      "- src/types/task.ts",
      "",
      "Diff 摘要：",
      "+ 为 Task 类型增加 priority 字段。",
      "+ 新增 priorityFilter 状态，并按筛选条件过滤任务列表。",
      "+ 增加空状态提示：当前优先级下暂无任务。",
      "",
      "关键实现：筛选逻辑保持在列表层，后续可平滑迁移到 API 查询参数。",
    ].join("\n");
  }

  function generateTest(pipeline) {
    return [
      "测试用例：",
      "1. 默认显示全部任务。",
      "2. 选择高优先级后，只显示 high 任务。",
      "3. 选择中/低优先级后，列表正确更新。",
      "4. 无匹配任务时显示空状态。",
      "",
      "模拟测试结果：4/4 通过。",
      "未覆盖风险：暂未覆盖筛选条件与搜索关键词组合的边界情况。",
    ].join("\n");
  }

  function generateReview(pipeline) {
    return [
      "评审结论：建议交付。",
      "",
      "正确性：筛选逻辑与需求一致，默认态和空状态均已覆盖。",
      "稳定性：当前方案只影响任务列表展示层，不改变存储结构。",
      "代码质量建议：后续可将 priority 选项抽成常量，避免多处硬编码。",
      "风险列表：与搜索、排序组合使用时需要补充集成测试。",
    ].join("\n");
  }

  function generateDelivery(pipeline) {
    return [
      "交付总结：已完成任务管理系统按优先级筛选任务的功能设计与交付材料生成。",
      "",
      "变更摘要：新增优先级筛选控件、任务 priority 字段、空状态提示和筛选逻辑。",
      "测试摘要：已覆盖默认展示、高/中/低优先级筛选、无匹配任务空状态。",
      "",
      "MR 描述草稿：",
      "本次变更新增任务优先级筛选能力，用户可以在任务列表中快速查看不同优先级的任务。实现包含筛选控件、列表过滤逻辑和空状态提示。",
      "",
      "后续建议：补充搜索 + 优先级组合筛选的集成测试。",
    ].join("\n");
  }

  const agentGenerators = {
    requirement: generateRequirement,
    design: generateDesign,
    code: generateCode,
    test: generateTest,
    review: generateReview,
    delivery: generateDelivery,
  };

  function runNextStage(pipeline) {
    const next = clonePipeline(pipeline);
    if (next.status === "completed" || next.status === "waiting_review") {
      return next;
    }

    const stage = getCurrentStage(next);
    if (!stage) {
      return { ...next, status: "completed" };
    }

    const content = agentGenerators[stage.id](next);
    const visualPlan = stage.id === "design"
      ? { visualPlan: createDesignVisualPlan(getLatestRejectReason(next, "design")) }
      : {};
    next.artifacts[stage.id] = createArtifact(stage, content, visualPlan);

    if (stage.approvalRequired) {
      next.status = "waiting_review";
      return next;
    }

    if (stage.id === "delivery") {
      next.status = "completed";
      return next;
    }

    const currentIndex = getStageIndex(stage.id);
    next.currentStageId = STAGES[currentIndex + 1].id;
    next.status = "ready";
    return next;
  }

  function runUntilReviewOrComplete(pipeline) {
    let next = pipeline;
    while (next.status === "ready") {
      next = runNextStage(next);
    }
    return next;
  }

  function submitReview(pipeline, review) {
    const next = clonePipeline(pipeline);
    const stage = getCurrentStage(next);
    if (!stage || next.status !== "waiting_review") {
      throw new Error("当前没有等待审批的阶段");
    }

    const decision = review && review.decision;
    if (decision !== "approve" && decision !== "reject") {
      throw new Error("审批结果必须是 approve 或 reject");
    }

    const reason = review.reason ? review.reason.trim() : "";
    if (decision === "reject" && !reason) {
      throw new Error("Reject 必须填写原因");
    }

    next.reviewHistory.push({
      stageId: stage.id,
      stageName: stage.name,
      decision,
      reason,
      createdAt: new Date().toISOString(),
    });

    if (decision === "reject") {
      next.status = "ready";
      return next;
    }

    const currentIndex = getStageIndex(stage.id);
    next.currentStageId = STAGES[currentIndex + 1].id;
    next.status = "ready";
    return next;
  }

  return {
    STAGES,
    createPipeline,
    runNextStage,
    runUntilReviewOrComplete,
    submitReview,
  };
});
