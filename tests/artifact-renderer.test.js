const assert = require("node:assert/strict");
const {
  renderMarkdown,
  buildPrdMap,
} = require("../artifact-renderer");

const markdown = [
  "## 需求目标",
  "做一个冒泡排序可视化网页。",
  "",
  "### 用户故事",
  "- 作为学生，我希望看到排序过程，以便理解比较和交换。",
  "",
  "### 本次包含（Must-have）",
  "- 柱状图展示数组",
  "- 开始、暂停、单步、重置",
  "",
  "### 验收标准",
  "1. Given 页面加载完成，When 用户点击开始，Then 柱状图开始排序。",
  "2. Given 排序运行中，When 用户点击暂停，Then 动画停止。",
  "",
  "### 待确认问题",
  "- 是否只做冒泡排序？",
].join("\n");

const html = renderMarkdown(markdown);
assert.match(html, /<h2>需求目标<\/h2>/);
assert.match(html, /<h3>用户故事<\/h3>/);
assert.match(html, /<ul>/);
assert.match(html, /<strong>|<li>作为学生/);
assert.doesNotMatch(html, /<script>/);

const malicious = renderMarkdown("hello <script>alert(1)</script> **world**");
assert.match(malicious, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.doesNotMatch(malicious, /<script>/);
assert.match(malicious, /<strong>world<\/strong>/);

const map = buildPrdMap(markdown);
assert.equal(map.title, "PRD 图谱");
assert.ok(map.nodes.length >= 5);
assert.ok(map.nodes.some((node) => node.label === "需求目标" && node.detail.includes("冒泡排序")));
assert.ok(map.nodes.some((node) => node.label === "核心功能" && node.items.includes("柱状图展示数组")));
assert.ok(map.nodes.some((node) => node.label === "验收标准" && node.items.length === 2));
assert.ok(map.nodes.some((node) => node.label === "待确认" && node.items.includes("是否只做冒泡排序？")));

console.log("artifact-renderer tests passed");
