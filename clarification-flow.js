(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DevFlowClarificationFlow = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var QUESTIONS = [
    {
      id: "targetUser",
      label: "目标用户",
      question: "这个需求主要给谁用？",
      recommended: "学生、自学者或需要理解概念的普通用户",
      placeholder: "例如：学生和算法初学者",
    },
    {
      id: "scenario",
      label: "使用场景",
      question: "用户会在什么场景下使用它？",
      recommended: "学习、演示或快速验证一个核心流程",
      placeholder: "例如：课堂演示和自学复盘",
    },
    {
      id: "scope",
      label: "范围边界",
      question: "这次明确要做什么，不做什么？",
      recommended: "先做核心功能，不扩展到无关模块",
      placeholder: "例如：只做冒泡排序，不做其他算法",
    },
    {
      id: "acceptanceFocus",
      label: "验收重点",
      question: "你最希望最终验收时重点看什么？",
      recommended: "核心交互可用、状态反馈清楚、边界情况不崩",
      placeholder: "例如：必须支持暂停、单步、速度调节",
    },
  ];

  var LABELS = {
    targetUser: "目标用户",
    scenario: "使用场景",
    scope: "范围边界",
    acceptanceFocus: "验收关注",
  };

  function getClarificationQuestions() {
    return QUESTIONS.map(function (question) {
      return Object.assign({}, question);
    });
  }

  function shouldAskClarification(requirement) {
    return String(requirement || "").indexOf("需求澄清回答：") === -1;
  }

  function mergeClarificationAnswers(requirement, answers) {
    var lines = [
      "原始需求：",
      String(requirement || "").trim(),
      "",
      "需求澄清回答：",
    ];

    Object.keys(LABELS).forEach(function (key) {
      var value = String((answers && answers[key]) || "").trim();
      if (value) {
        lines.push("- " + LABELS[key] + "：" + value);
      }
    });

    lines.push("");
    lines.push("请需求分析 Agent 优先基于以上用户回答生成正式 PRD；如果仍有关键不确定项，再进入下一轮澄清。");
    return lines.join("\n");
  }

  return {
    getClarificationQuestions: getClarificationQuestions,
    mergeClarificationAnswers: mergeClarificationAnswers,
    shouldAskClarification: shouldAskClarification,
  };
});
