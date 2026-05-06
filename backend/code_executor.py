import json
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from shutil import copytree, rmtree

from backend import llm_runner
from backend.schemas import Pipeline
from backend.skills import read_skill


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_APP = PROJECT_ROOT / "target-app"
RUNS_DIR = PROJECT_ROOT / "devflow-runs"

ALLOWED_EXTENSIONS = {".html", ".css", ".js", ".ts", ".tsx", ".jsx", ".json"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}


@dataclass
class CodeExecutionResult:
    content: str
    changed_files: list[str]
    workspace_path: str
    model: str


def unified_file_diff(relative_path: str, before: str, after: str) -> str:
    return "".join(
        unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
        )
    )


def summarize_diff(diff_text: str, max_lines: int = 80) -> str:
    lines = diff_text.splitlines()
    if len(lines) <= max_lines:
        return diff_text
    shown = "\n".join(lines[:max_lines])
    return f"{shown}\n... diff 已截断（共 {len(lines)} 行），完整文件在运行副本中。"


def prepare_workspace(pipeline: Pipeline) -> Path:
    if pipeline.projectPath:
        return Path(pipeline.projectPath)

    RUNS_DIR.mkdir(exist_ok=True)
    workspace = RUNS_DIR / pipeline.id / "target-app"
    if workspace.exists():
        rmtree(workspace)
    copytree(TARGET_APP, workspace)
    return workspace


def read_project_files(workspace: Path) -> list[dict[str, str]]:
    files = []
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        relative_path = path.relative_to(workspace).as_posix()
        files.append({"path": relative_path, "content": path.read_text(encoding="utf-8")})
    return files


def extract_json_object(content: str) -> dict | None:
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.startswith("json"):
            clean = clean[4:].strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(clean[start: end + 1])
    except json.JSONDecodeError:
        return None


def validate_patch_payload(payload: dict, workspace: Path) -> list[dict[str, str]] | None:
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        return None

    valid_files = []
    for item in files:
        if not isinstance(item, dict):
            return None
        relative_path = item.get("path")
        content = item.get("content")
        if not isinstance(relative_path, str) or not isinstance(content, str):
            return None
        candidate = (workspace / relative_path).resolve()
        if workspace.resolve() not in [candidate, *candidate.parents]:
            return None
        if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
            return None
        valid_files.append({"path": relative_path.replace("\\", "/"), "content": content})

    return valid_files


def build_code_patch_prompt(pipeline: Pipeline, project_files: list[dict[str, str]]) -> str:
    skill_text = read_skill("code")
    design_artifact = pipeline.artifacts.get("design")
    design_content = design_artifact.content if design_artifact else "暂无方案设计"

    files_block = "\n\n".join(
        f"FILE: {item['path']}\n```text\n{item['content']}\n```"
        for item in project_files
    )

    return (
        f"## 你的角色\n"
        f"你是 DevFlow 的代码生成 Agent。你的任务是根据用户需求和技术方案，"
        f"产出完整的、可运行的前端代码。\n\n"
        f"## 工作规范（Skill）\n{skill_text}\n\n"
        f"## 用户需求\n{pipeline.requirement}\n\n"
        f"## 技术方案\n{design_content}\n\n"
        f"## 当前工作区文件（仅供参考，了解项目环境）\n{files_block}\n\n"
        f"## 重要说明\n"
        f"- 如果用户需求是一个全新的功能（如游戏、工具等），**不要保留现有文件的内容**。\n"
        f"- 你可以完全重写现有文件（如 index.html, app.js, styles.css），也可以创建新文件。\n"
        f"- 当前文件只是模板/占位符，不是要保留的代码。请根据需求从头构建。\n"
        f"- 例如：用户要俄罗斯方块，就写俄罗斯方块的完整代码，不要在上面叠加任务管理功能。\n\n"
        f"## 输出要求\n"
        f"只返回一个 JSON 对象，不要 Markdown 代码块标记，不要任何解释文字。\n"
        f'JSON 格式：{{"files":[{{"path":"相对路径","content":"完整文件内容"}}]}}\n'
        f"每个文件必须提供完整内容（不是 diff），HTML/CSS/JS 都必须是完整可运行的文件。\n"
        f"不要引入 CDN 或其他外部依赖，所有代码自包含。"
    )


def build_test_patch_prompt(pipeline: Pipeline, project_files: list[dict[str, str]]) -> str:
    skill_text = read_skill("test")
    code_artifact = pipeline.artifacts.get("code")
    requirement_artifact = pipeline.artifacts.get("requirement")

    changed_files_text = (
        ", ".join(code_artifact.changedFiles) if code_artifact else "暂无"
    )
    requirement_text = (
        requirement_artifact.content if requirement_artifact else pipeline.requirement
    )

    files_block = "\n\n".join(
        f"FILE: {item['path']}\n```text\n{item['content'][:2000]}\n```"
        for item in project_files
    )

    return (
        f"## 你的角色\n"
        f"你是 DevFlow 的测试生成 Agent，负责为代码变更生成可运行的测试。\n\n"
        f"## 工作规范（Skill）\n{skill_text}\n\n"
        f"## 用户需求\n{pipeline.requirement}\n\n"
        f"## 需求分析\n{requirement_text[:2000]}\n\n"
        f"## 代码阶段修改的文件\n{changed_files_text}\n\n"
        f"## 当前项目文件（包含已修改的代码）\n{files_block}\n\n"
        f"## 输出要求\n"
        f"只返回一个 JSON 对象，不要 Markdown 代码块标记，不要任何解释文字。\n"
        f'JSON 格式：{{"files":[{{"path":"tests/xxx.test.js","content":"完整测试文件内容"}}]}}\n'
        f"测试文件必须放在 tests/ 目录下。\n"
        f"使用 Node.js 内置的 assert 模块，不依赖外部测试框架。\n"
        f"测试应该验证需求中描述的预期行为。"
    )


def apply_llm_code_patch(pipeline: Pipeline) -> CodeExecutionResult | None:
    if not llm_runner.llm_enabled() or not llm_runner.get_api_key():
        return None

    workspace = prepare_workspace(pipeline)
    project_files = read_project_files(workspace)
    if not project_files:
        return None

    payload = {
        "model": llm_runner.MODEL_ROUTER["code"],
        "messages": [
            {
                "role": "system",
                "content": "你是一个严谨的代码修改器。只输出可解析的 JSON，格式为 {\"files\":[{\"path\":\"...\",\"content\":\"...\"}]}。",
            },
            {
                "role": "user",
                "content": build_code_patch_prompt(pipeline, project_files),
            },
        ],
        "temperature": 0.2,
    }

    try:
        response = llm_runner.post_chat_completion(payload)
        raw_content = llm_runner.extract_content(response)
    except Exception:
        return None

    patch_payload = extract_json_object(raw_content)
    if not patch_payload:
        return None

    files = validate_patch_payload(patch_payload, workspace)
    if not files:
        return None

    diff_parts = []
    changed_files = []
    for item in files:
        file_path = workspace / item["path"]
        before = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(item["content"], encoding="utf-8")
        relative_path = f"target-app/{item['path']}"
        changed_files.append(relative_path)
        diff_parts.append(f"diff --git a/{relative_path} b/{relative_path}\n")
        diff_parts.append(unified_file_diff(relative_path, before, item["content"]))

    result_content = "\n".join(
        [
            "代码阶段已完成，变更已写入运行副本。",
            "",
            f"运行副本路径：{workspace}",
            "",
            "修改文件：",
            *[f"  - {f}" for f in changed_files],
            "",
            "Diff 摘要：",
            summarize_diff("".join(diff_parts)),
        ]
    )
    return CodeExecutionResult(
        content=result_content,
        changed_files=changed_files,
        workspace_path=str(workspace),
        model=llm_runner.MODEL_ROUTER["code"],
    )


def apply_llm_test_patch(pipeline: Pipeline) -> CodeExecutionResult | None:
    if not llm_runner.llm_enabled() or not llm_runner.get_api_key():
        return None

    code_artifact = pipeline.artifacts.get("code")
    if not code_artifact or not code_artifact.workspacePath:
        return None

    workspace = Path(code_artifact.workspacePath)
    project_files = read_project_files(workspace)
    if not project_files:
        return None

    payload = {
        "model": llm_runner.MODEL_ROUTER["test"],
        "messages": [
            {
                "role": "system",
                "content": "你是一个严谨的测试文件生成器。只输出可解析的 JSON，格式为 {\"files\":[{\"path\":\"tests/...\",\"content\":\"...\"}]}。",
            },
            {
                "role": "user",
                "content": build_test_patch_prompt(pipeline, project_files),
            },
        ],
        "temperature": 0.2,
    }

    try:
        response = llm_runner.post_chat_completion(payload)
        raw_content = llm_runner.extract_content(response)
    except Exception:
        return None

    patch_payload = extract_json_object(raw_content)
    if not patch_payload:
        return None

    files = validate_patch_payload(patch_payload, workspace)
    if not files:
        return None
    if any(not item["path"].startswith("tests/") for item in files):
        return None

    diff_parts = []
    changed_files = []
    for item in files:
        file_path = workspace / item["path"]
        before = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(item["content"], encoding="utf-8")
        relative_path = f"target-app/{item['path']}"
        changed_files.append(relative_path)
        diff_parts.append(f"diff --git a/{relative_path} b/{relative_path}\n")
        diff_parts.append(unified_file_diff(relative_path, before, item["content"]))

    result_content = "\n".join(
        [
            "测试阶段已完成，测试文件已写入运行副本。",
            "",
            f"运行副本路径：{workspace}",
            "",
            "测试文件：",
            *[f"  - {f}" for f in changed_files],
            "",
            "运行测试：",
            *[f"  node {f.replace('target-app/', '')}" for f in changed_files],
            "",
            "Diff 摘要：",
            summarize_diff("".join(diff_parts)),
        ]
    )
    return CodeExecutionResult(
        content=result_content,
        changed_files=changed_files,
        workspace_path=str(workspace),
        model=llm_runner.MODEL_ROUTER["test"],
    )
