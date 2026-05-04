from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from shutil import copytree, rmtree

from backend.schemas import Pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_APP = PROJECT_ROOT / "target-app"
RUNS_DIR = PROJECT_ROOT / "devflow-runs"


@dataclass
class CodeExecutionResult:
    content: str
    changed_files: list[str]
    workspace_path: str


APP_JS_WITH_PRIORITY = """const tasks = [
  { id: 1, title: "整理需求文档", priority: "high", done: false },
  { id: 2, title: "补充接口说明", priority: "medium", done: false },
  { id: 3, title: "同步测试结果", priority: "low", done: true },
];

let priorityFilter = "all";

const priorityLabels = {
  all: "全部",
  high: "高",
  medium: "中",
  low: "低",
};

const taskList = document.querySelector("#taskList");
const emptyState = document.querySelector("#emptyState");
const filterButtons = document.querySelectorAll("[data-priority]");

function getFilteredTasks() {
  if (priorityFilter === "all") {
    return tasks;
  }
  return tasks.filter((task) => task.priority === priorityFilter);
}

function renderTasks() {
  const visibleTasks = getFilteredTasks();
  taskList.innerHTML = "";
  emptyState.hidden = visibleTasks.length > 0;

  visibleTasks.forEach((task) => {
    const item = document.createElement("li");
    item.className = task.done ? "task-item is-done" : "task-item";
    item.innerHTML = `
      <span>${task.title}</span>
      <strong>${priorityLabels[task.priority]}</strong>
    `;
    taskList.appendChild(item);
  });
}

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    priorityFilter = button.dataset.priority;
    filterButtons.forEach((item) => item.classList.toggle("active", item === button));
    renderTasks();
  });
});

renderTasks();
"""


PRIORITY_FILTER_TEST = """const { readFileSync } = require("fs");
const { join } = require("path");
const assert = require("assert");

const appSource = readFileSync(join(__dirname, "..", "app.js"), "utf-8");
const htmlSource = readFileSync(join(__dirname, "..", "index.html"), "utf-8");

assert(appSource.includes("priorityFilter"), "app.js should keep priorityFilter state");
assert(appSource.includes("getFilteredTasks"), "app.js should filter tasks before rendering");
assert(appSource.includes("task.priority === priorityFilter"), "tasks should be filtered by priority");
assert(htmlSource.includes("data-priority=\\"high\\""), "UI should expose high priority filter");
assert(htmlSource.includes("emptyState"), "UI should include empty state for no matching tasks");

console.log("priority filter tests passed");
"""


INDEX_WITH_FILTER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Target Task App</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="task-shell">
    <header>
      <p>Target App</p>
      <h1>任务管理</h1>
    </header>

    <nav class="priority-filter" aria-label="按优先级筛选任务">
      <button class="active" data-priority="all" type="button">全部</button>
      <button data-priority="high" type="button">高</button>
      <button data-priority="medium" type="button">中</button>
      <button data-priority="low" type="button">低</button>
    </nav>

    <ul id="taskList" class="task-list"></ul>
    <p id="emptyState" class="empty-state" hidden>当前优先级下暂无任务。</p>
  </main>
  <script src="app.js"></script>
</body>
</html>
"""


STYLES_WITH_FILTER = """:root {
  color-scheme: light;
  font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
}

body {
  margin: 0;
  color: #1f2329;
  background: #f6f8fc;
}

.task-shell {
  width: min(680px, calc(100% - 32px));
  margin: 48px auto;
  padding: 24px;
  border: 1px solid #dfe5ef;
  border-radius: 14px;
  background: #fff;
}

header p {
  margin: 0;
  color: #1664ff;
  font-size: 12px;
  font-weight: 800;
}

header h1 {
  margin: 4px 0 18px;
}

.priority-filter {
  display: inline-flex;
  gap: 6px;
  padding: 4px;
  border-radius: 10px;
  background: #f1f4fb;
}

.priority-filter button {
  min-width: 54px;
  border: 0;
  border-radius: 8px;
  padding: 8px 12px;
  color: #646a73;
  background: transparent;
  font-weight: 800;
}

.priority-filter button.active {
  color: #fff;
  background: #1664ff;
}

.task-list {
  display: grid;
  gap: 10px;
  padding: 0;
  margin: 18px 0 0;
  list-style: none;
}

.task-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  border: 1px solid #dfe5ef;
  border-radius: 10px;
}

.task-item.is-done span {
  color: #8f959e;
  text-decoration: line-through;
}

.task-item strong {
  color: #1664ff;
}

.empty-state {
  margin: 18px 0 0;
  padding: 18px;
  border: 1px dashed #dfe5ef;
  border-radius: 10px;
  color: #646a73;
  text-align: center;
}
"""


def unified_file_diff(relative_path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )


def prepare_workspace(pipeline: Pipeline) -> Path:
    RUNS_DIR.mkdir(exist_ok=True)
    workspace = RUNS_DIR / pipeline.id / "target-app"
    if workspace.exists():
        rmtree(workspace)
    copytree(TARGET_APP, workspace)
    return workspace


def apply_priority_filter_change(pipeline: Pipeline) -> CodeExecutionResult:
    workspace = prepare_workspace(pipeline)
    updates = {
        "target-app/index.html": INDEX_WITH_FILTER,
        "target-app/styles.css": STYLES_WITH_FILTER,
        "target-app/app.js": APP_JS_WITH_PRIORITY,
    }

    diff_parts = []
    for relative_path, after in updates.items():
        file_path = workspace / Path(relative_path).name
        before = file_path.read_text(encoding="utf-8")
        file_path.write_text(after, encoding="utf-8")
        diff_parts.append(f"diff --git a/{relative_path} b/{relative_path}\n")
        diff_parts.append(unified_file_diff(relative_path, before, after))

    changed_files = list(updates.keys())
    content = "\n".join(
        [
            "已对示例任务管理项目生成真实代码改动。",
            "",
            f"运行副本：{workspace}",
            "",
            "修改文件：",
            *[f"- {item}" for item in changed_files],
            "",
            "真实 diff：",
            "".join(diff_parts),
        ]
    )
    return CodeExecutionResult(
        content=content,
        changed_files=changed_files,
        workspace_path=str(workspace),
    )


def add_priority_filter_tests(pipeline: Pipeline) -> CodeExecutionResult | None:
    code_artifact = pipeline.artifacts.get("code")
    if not code_artifact or not code_artifact.workspacePath:
        return None

    workspace = Path(code_artifact.workspacePath)
    tests_dir = workspace / "tests"
    tests_dir.mkdir(exist_ok=True)
    test_file = tests_dir / "priority-filter.test.js"
    before = test_file.read_text(encoding="utf-8") if test_file.exists() else ""
    test_file.write_text(PRIORITY_FILTER_TEST, encoding="utf-8")

    relative_path = "target-app/tests/priority-filter.test.js"
    diff = "diff --git a/{0} b/{0}\n".format(relative_path)
    diff += unified_file_diff(relative_path, before, PRIORITY_FILTER_TEST)
    content = "\n".join(
        [
            "已为真实代码改动生成测试文件。",
            "",
            f"测试文件：{test_file}",
            "",
            "可运行命令：",
            "node tests/priority-filter.test.js",
            "",
            "测试覆盖：",
            "- priorityFilter 状态存在",
            "- getFilteredTasks 过滤函数存在",
            "- 高优先级筛选入口存在",
            "- 空状态节点存在",
            "",
            "真实 diff：",
            diff,
        ]
    )
    return CodeExecutionResult(
        content=content,
        changed_files=[relative_path],
        workspace_path=str(workspace),
    )
