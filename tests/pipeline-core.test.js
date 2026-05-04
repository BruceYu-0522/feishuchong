const assert = require("node:assert/strict");
const { createPipeline, runNextStage, submitReview } = require("../pipeline-core");

function runToFirstReview(pipeline) {
  let current = pipeline;
  current = runNextStage(current);
  current = runNextStage(current);
  return current;
}

function runToFinalReview(pipeline) {
  let current = pipeline;
  current = runNextStage(current);
  current = runNextStage(current);
  current = runNextStage(current);
  return current;
}

const initial = createPipeline("给任务管理系统增加按优先级筛选任务的功能");
assert.equal(initial.status, "ready");
assert.equal(initial.currentStageId, "requirement");
assert.equal(initial.stages.length, 6);

const waitingForPlanReview = runToFirstReview(initial);
assert.equal(waitingForPlanReview.status, "waiting_review");
assert.equal(waitingForPlanReview.currentStageId, "design");
assert.equal(waitingForPlanReview.artifacts.requirement.agent, "需求分析 Agent");
assert.equal(waitingForPlanReview.artifacts.design.agent, "方案设计 Agent");
assert.equal(waitingForPlanReview.artifacts.design.visualPlan.title, "优先级筛选方案蓝图");
assert.ok(waitingForPlanReview.artifacts.design.visualPlan.nodes.length >= 4);

const rejected = submitReview(waitingForPlanReview, {
  decision: "reject",
  reason: "缺少空状态处理",
});
assert.equal(rejected.status, "ready");
assert.equal(rejected.currentStageId, "design");
assert.equal(rejected.reviewHistory.length, 1);
assert.equal(rejected.reviewHistory[0].decision, "reject");

const regeneratedDesign = runNextStage(rejected);
assert.equal(regeneratedDesign.status, "waiting_review");
assert.match(regeneratedDesign.artifacts.design.content, /缺少空状态处理/);

const approvedPlan = submitReview(regeneratedDesign, { decision: "approve" });
assert.equal(approvedPlan.status, "ready");
assert.equal(approvedPlan.currentStageId, "code");

const waitingForFinalReview = runToFinalReview(approvedPlan);
assert.equal(waitingForFinalReview.status, "waiting_review");
assert.equal(waitingForFinalReview.currentStageId, "review");
assert.equal(waitingForFinalReview.artifacts.code.agent, "代码生成 Agent");
assert.equal(waitingForFinalReview.artifacts.test.agent, "测试生成 Agent");
assert.equal(waitingForFinalReview.artifacts.review.agent, "代码评审 Agent");

const approvedFinal = submitReview(waitingForFinalReview, { decision: "approve" });
const completed = runNextStage(approvedFinal);
assert.equal(completed.status, "completed");
assert.equal(completed.currentStageId, "delivery");
assert.equal(completed.artifacts.delivery.agent, "交付总结 Agent");
assert.match(completed.artifacts.delivery.content, /MR 描述草稿/);

console.log("pipeline-core tests passed");
