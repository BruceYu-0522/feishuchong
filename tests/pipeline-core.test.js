const assert = require("node:assert/strict");
const { STAGES, createClient, createStageWheelItems } = require("../pipeline-core");

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
// Internal request would use "http://example.com/api" + path — we can't inspect private vars
// but we verify the function exists and works without throwing
assert.ok(trimmedClient);

// Export nothing extra beyond the documented API
var exported = require("../pipeline-core");
assert.ok(exported.STAGES);
assert.ok(exported.createClient);
assert.ok(exported.createStageWheelItems);
assert.equal(Object.keys(exported).length, 3, "should only export the documented core API");

// Stage wheel should place all stages on an upper semicircle and mark state
var wheelItems = createStageWheelItems(STAGES, "code", new Set(["requirement", "design"]));
assert.equal(wheelItems.length, STAGES.length);
assert.equal(wheelItems[0].angle, 180);
assert.equal(wheelItems[wheelItems.length - 1].angle, 0);
assert.ok(wheelItems.every(function (item) { return item.x >= 0 && item.x <= 100; }));
assert.ok(wheelItems.every(function (item) { return item.y >= 0 && item.y <= 100; }));
assert.equal(wheelItems[0].state, "complete");
assert.equal(wheelItems[1].state, "complete");
assert.equal(wheelItems[2].state, "current");
assert.equal(wheelItems[3].state, "pending");
assert.equal(wheelItems[2].offset, 0);
assert.equal(wheelItems[1].offset, -1);
assert.equal(wheelItems[3].offset, 1);

console.log("pipeline-core tests passed");
