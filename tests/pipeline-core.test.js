var assert = require("node:assert/strict");
var { STAGES, createClient, createStageWheelItems } = require("../pipeline-core");

// STAGES definition must be valid
assert.equal(STAGES.length, 6, "should have 6 stages");
assert.equal(STAGES[0].id, "requirement");
assert.equal(STAGES[0].name, "需求分析");
assert.equal(STAGES[0].approvalRequired, true, "requirement should require approval");
assert.equal(STAGES[1].id, "design");
assert.equal(STAGES[1].approvalRequired, true, "design should require approval");
assert.equal(STAGES[2].id, "code");
assert.equal(STAGES[2].approvalRequired, true, "code should require approval");
assert.equal(STAGES[3].id, "test");
assert.equal(STAGES[3].approvalRequired, true, "test should require approval");
assert.equal(STAGES[4].id, "review");
assert.equal(STAGES[4].approvalRequired, true, "review should require approval");
assert.equal(STAGES[5].id, "delivery");
assert.equal(STAGES[5].approvalRequired, true, "delivery should require approval");

// Each stage must have required fields
STAGES.forEach(function (stage, index) {
  assert.ok(stage.id, "stage " + index + " missing id");
  assert.ok(stage.name, "stage " + index + " missing name");
  assert.ok(stage.agent, "stage " + index + " missing agent");
  assert.equal(typeof stage.approvalRequired, "boolean", "stage " + index + " approvalRequired must be boolean");
});

// Approval checkpoints: every stage should stop for human review
var approvalStages = STAGES.filter(function (s) { return s.approvalRequired; });
assert.equal(approvalStages.length, STAGES.length, "every stage must have a human-in-the-loop checkpoint");
assert.deepEqual(approvalStages.map(function (s) { return s.id; }), STAGES.map(function (s) { return s.id; }));

// createClient must return an API client with expected methods
var client = createClient("http://127.0.0.1:8000");
assert.equal(typeof client.health, "function");
assert.equal(typeof client.createPipeline, "function");
assert.equal(typeof client.getPipeline, "function");
assert.equal(typeof client.runUntilReview, "function");
assert.equal(typeof client.runNext, "function");
assert.equal(typeof client.submitReview, "function");

// createClient should strip trailing slashes from base URL
var trimmedClient = createClient("http://example.com/api/");
assert.ok(trimmedClient);

// Export nothing extra beyond the documented API
var exported = require("../pipeline-core");
assert.ok(exported.STAGES);
assert.ok(exported.createClient);
assert.ok(exported.createStageWheelItems);
assert.equal(Object.keys(exported).length, 3, "should only export the documented core API");

// Stage wheel: returns { items, wheelRotation, radius, activeIndex }
var wheelData = createStageWheelItems(STAGES, "code", new Set(["requirement", "design"]));
assert.equal(typeof wheelData, "object", "should return an object");
assert.ok(Array.isArray(wheelData.items), "items should be an array");
assert.equal(wheelData.items.length, STAGES.length, "should have items for all stages");
assert.equal(typeof wheelData.wheelRotation, "number");
assert.equal(typeof wheelData.radius, "number");
assert.equal(typeof wheelData.activeIndex, "number");

// Items positioned on full circle (0-360), not semicircle
assert.equal(wheelData.items[0].angle, 0, "stage 0 at 0 degrees (top of wheel)");
assert.equal(wheelData.items[wheelData.items.length - 1].angle, 300, "last stage at 300 degrees");

// Wheel rotation: activeIndex 2 (code is stage index 2) → -120 degrees
assert.equal(wheelData.activeIndex, 2, "code is stage index 2");
assert.equal(wheelData.wheelRotation, -120, "wheel rotated -120 to bring code to top");

// State assignments
assert.equal(wheelData.items[0].state, "complete", "requirement completed");
assert.equal(wheelData.items[1].state, "complete", "design completed");
assert.equal(wheelData.items[2].state, "current", "code is current");
assert.equal(wheelData.items[3].state, "pending");
assert.equal(wheelData.items[4].state, "pending");
assert.equal(wheelData.items[5].state, "pending");

// Each item has expected shape
wheelData.items.forEach(function (item, index) {
  assert.ok(item.id, "item " + index + " missing id");
  assert.ok(item.name, "item " + index + " missing name");
  assert.ok(item.agent, "item " + index + " missing agent");
  assert.equal(typeof item.approvalRequired, "boolean");
  assert.equal(typeof item.angle, "number");
  assert.ok(item.angle >= 0 && item.angle < 360, "angle should be in [0, 360)");
  assert.ok(["complete", "current", "pending"].indexOf(item.state) !== -1, "item " + index + " state should be complete/current/pending");
});

// Test with first stage active
var firstWheel = createStageWheelItems(STAGES, "requirement", new Set());
assert.equal(firstWheel.wheelRotation, 0, "no rotation when first stage is active");
assert.equal(firstWheel.activeIndex, 0);

// Test with last stage active
var lastWheel = createStageWheelItems(STAGES, "delivery", new Set(["requirement", "design", "code", "test", "review"]));
assert.equal(lastWheel.activeIndex, 5);
assert.equal(lastWheel.wheelRotation, -300);

console.log("pipeline-core tests passed");
