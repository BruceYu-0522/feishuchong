const assert = require("node:assert/strict");
const {
  getClarificationQuestions,
  mergeClarificationAnswers,
  shouldAskClarification,
} = require("../clarification-flow");

const questions = getClarificationQuestions("做一个冒泡排序可视化网页");
assert.equal(questions.length, 4);
assert.ok(questions.every((question) => question.id));
assert.ok(questions.every((question) => question.recommended));

assert.equal(shouldAskClarification("做一个冒泡排序可视化网页"), true);
assert.equal(shouldAskClarification("原始需求：做页面\n\n需求澄清回答：\n- 目标用户：学生"), false);

const merged = mergeClarificationAnswers("做一个冒泡排序可视化网页", {
  targetUser: "学生和算法初学者",
  scenario: "课堂演示和自学复盘",
  scope: "只做冒泡排序，不做其他算法",
  acceptanceFocus: "必须支持暂停、单步、速度调节",
});

assert.match(merged, /原始需求：\n做一个冒泡排序可视化网页/);
assert.match(merged, /需求澄清回答：/);
assert.match(merged, /目标用户：学生和算法初学者/);
assert.match(merged, /验收关注：必须支持暂停、单步、速度调节/);

console.log("clarification-flow tests passed");
