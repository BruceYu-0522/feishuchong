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
    # Remove markdown code fences (including ```json ... ```), handling leading/trailing whitespace
    lines = clean.split("\n")
    if lines and lines[0].strip().startswith("```"):
        # Remove opening fence line
        lines = lines[1:]
        # Remove closing fence line
        if lines and lines[-1].strip().startswith("```") or lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    # Also handle case where ``` is on its own at end
    if clean.endswith("```"):
        clean = clean[:-3].strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end == -1 or end <= start:
        print(f"[extract-json] No JSON object found in content. First 300 chars: {content[:300]}")
        return None
    try:
        return json.loads(clean[start: end + 1])
    except json.JSONDecodeError as exc:
        print(f"[extract-json] JSON decode error: {exc}. Snippet: {clean[start:end+1][:300]}")

    # Repair attempt: LLMs often put literal newlines / unescaped chars inside JSON strings.
    # Strategy: track brace depth to find file-object boundaries structurally,
    # then extract path and content from each object with regex.
    try:
        import re

        # Find "files" array start
        files_start_m = re.search(r'"files"\s*:\s*\[', clean)
        if not files_start_m:
            return None

        arr_start = files_start_m.end()  # right after [

        # Walk the text tracking brace/bracket depth to find each file object
        files_payload = []
        pos = arr_start
        n = len(clean)

        while pos < n:
            # Skip whitespace
            while pos < n and clean[pos] in " \t\r\n":
                pos += 1
            if pos >= n:
                break
            if clean[pos] == "]":
                break
            if clean[pos] != "{":
                pos += 1
                continue

            # Find matching } for this file object (depth-based)
            obj_start = pos
            depth = 0
            in_str = False
            esc = False
            while pos < n:
                c = clean[pos]
                if esc:
                    esc = False
                    pos += 1
                    continue
                if c == "\\":
                    esc = True
                    pos += 1
                    continue
                if c == '"':
                    in_str = not in_str
                    pos += 1
                    continue
                if not in_str:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            pos += 1  # consume }
                            break
                pos += 1

            obj_text = clean[obj_start:pos]

            # Extract path
            path_m = re.search(r'"path"\s*:\s*"([^"]*)"', obj_text)
            if not path_m:
                continue
            file_path = path_m.group(1)

            # Extract content: find "content":" then grab everything until the last "} or " }
            content_m = re.search(r'"content"\s*:\s*"', obj_text)
            if not content_m:
                continue

            cstart = content_m.end()
            # Content is everything in obj_text from cstart to the last " before closing }
            # Find the closing " by looking for " followed by optional whitespace and }
            inner = obj_text[cstart:]
            closing = inner.rfind('"}')
            if closing == -1:
                closing = inner.rfind('" }')
            if closing == -1:
                closing = len(inner)
            content = inner[:closing]

            # Try to unescape JSON escapes
            try:
                content = json.loads(f'"{content}"')
            except json.JSONDecodeError:
                pass  # keep raw

            files_payload.append({"path": file_path, "content": content})

        if files_payload:
            return {"files": files_payload}
    except Exception as repair_exc:
        print(f"[extract-json] Repair also failed: {repair_exc}")

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

    # Collect review feedback for code re-generation
    review_feedback = ""
    if pipeline.reviewHistory:
        rejections = [r for r in pipeline.reviewHistory if r.decision == "reject" and r.reason]
        if rejections:
            latest = rejections[-1]
            review_feedback = (
                f"\n## 评审反馈（重要！请仔细阅读并修改）\n"
                f"上一次评审被驳回，原因：{latest.reason}\n"
                f"请根据这个反馈修改代码，解决评审中提到的问题。\n"
            )

    # Include code index summary if available
    code_index_text = ""
    try:
        from backend.pipeline_engine import get_code_index
        idx = get_code_index(pipeline.id)
        if idx:
            summary = idx.summary()
            idx_lines = [
                f"代码索引：{summary['total_files']} 个文件，{summary['total_symbols']} 个符号",
                f"符号分布：{summary['by_kind']}",
            ]
            top_files = sorted(summary["by_file"].items(), key=lambda x: x[1], reverse=True)[:8]
            for fname, count in top_files:
                key_symbols = [s.name for s in idx.symbols if s.file == fname][:5]
                idx_lines.append(f"  {fname} ({count} 符号): {', '.join(key_symbols)}")
            code_index_text = "## 项目代码结构索引\n" + "\n".join(idx_lines) + "\n\n"
    except Exception:
        pass

    return (
        f"## 你的角色\n"
        f"你是 DevFlow 的代码生成 Agent。你的任务是根据用户需求和技术方案，"
        f"产出完整的、可运行的前端代码。\n\n"
        f"## 工作规范（Skill）\n{skill_text}\n\n"
        f"## 用户需求\n{pipeline.requirement}\n\n"
        f"## 技术方案\n{design_content}\n"
        f"{code_index_text}"
        f"{review_feedback}\n"
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
        f"不要引入 CDN 或其他外部依赖，所有代码自包含。\n"
        f"重要：content 内换行写 \\n、缩进写 \\t、双引号写 \\\"、反斜杠写 \\\\，确保整个 JSON 合法可解析。"
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

    # Include code index summary if available
    code_index_text = ""
    try:
        from backend.pipeline_engine import get_code_index
        idx = get_code_index(pipeline.id)
        if idx:
            summary = idx.summary()
            idx_lines = [
                f"代码索引：{summary['total_files']} 个文件，{summary['total_symbols']} 个符号",
                f"符号分布：{summary['by_kind']}",
            ]
            top_files = sorted(summary["by_file"].items(), key=lambda x: x[1], reverse=True)[:8]
            for fname, count in top_files:
                key_symbols = [s.name for s in idx.symbols if s.file == fname][:5]
                idx_lines.append(f"  {fname} ({count} 符号): {', '.join(key_symbols)}")
            code_index_text = "## 项目代码结构索引\n" + "\n".join(idx_lines) + "\n\n"
    except Exception:
        pass

    return (
        f"## 你的角色\n"
        f"你是 DevFlow 的测试生成 Agent，负责为代码变更生成可运行的测试。\n\n"
        f"## 工作规范（Skill）\n{skill_text}\n\n"
        f"## 用户需求\n{pipeline.requirement}\n\n"
        f"## 需求分析\n{requirement_text[:2000]}\n\n"
        f"## 代码阶段修改的文件\n{changed_files_text}\n\n"
        f"{code_index_text}"
        f"## 当前项目文件（包含已修改的代码）\n{files_block}\n\n"
        f"## 输出要求\n"
        f"只返回一个 JSON 对象，不要 Markdown 代码块标记，不要任何解释文字。\n"
        f'JSON 格式：{{"files":[{{"path":"tests/xxx.test.js","content":"完整测试文件内容"}}]}}\n'
        f"测试文件必须放在 tests/ 目录下。\n"
        f"使用 Node.js 内置的 assert 模块，不依赖外部测试框架。\n"
        f"测试应该验证需求中描述的预期行为。\n"
        f"重要：content 内换行写 \\n、缩进写 \\t、双引号写 \\\"、反斜杠写 \\\\，确保整个 JSON 合法可解析。"
    )


# Module-level last-error store for surfacing LLM failures
_last_code_error: str = ""


def get_last_code_error() -> str:
    return _last_code_error


def apply_llm_code_patch(pipeline: Pipeline) -> CodeExecutionResult | None:
    global _last_code_error
    _last_code_error = ""

    if not llm_runner.llm_enabled():
        _last_code_error = "LLM 未启用 — DEVFLOW_LLM_ENABLED 环境变量未设为 true"
        print(f"[code-patch] {_last_code_error}")
        return None
    if not llm_runner.get_api_key():
        _last_code_error = "API Key 未设置 — 请设置 DEVFLOW_LLM_API_KEY 环境变量"
        print(f"[code-patch] {_last_code_error}")
        return None

    workspace = prepare_workspace(pipeline)
    project_files = read_project_files(workspace)
    if not project_files:
        _last_code_error = "工作区中没有找到项目文件"
        print(f"[code-patch] {_last_code_error}")
        return None

    model = llm_runner.MODEL_ROUTER["code"]
    print(f"[code-patch] Calling model {model}...")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个代码生成器。你的唯一任务是根据用户需求输出完整的代码文件。\n"
                    "必须严格按以下 JSON 格式输出，不要输出任何其他文字、解释或 Markdown：\n"
                    '{"files":[{"path":"index.html","content":"<完整的 HTML 文件内容>"},{"path":"styles.css","content":"/* 完整的 CSS 文件内容 */"},{"path":"app.js","content":"// 完整的 JS 文件内容"}]}\n'
                    "path 使用项目中的相对路径。每个 content 字段包含文件的完整内容。\n"
                    "只输出 JSON 对象，从 { 开始到 } 结束，不要 ```json 包裹。\n"
                    "重要：content 内的代码请使用 \\n 表示换行、\\t 表示缩进、\\\" 表示双引号、\\\\ 表示反斜杠。确保整个 JSON 是合法的单行或正确转义的多行 JSON。"
                ),
            },
            {
                "role": "user",
                "content": build_code_patch_prompt(pipeline, project_files),
            },
        ],
        "temperature": 0.2,
    }

    try:
        response = llm_runner.post_chat_completion(payload, "code")
        raw_content = llm_runner.extract_content(response)
        print(f"[code-patch] Raw content length: {len(raw_content)} chars, first 200: {raw_content[:200]}")
    except Exception as exc:
        _last_code_error = f"LLM API 调用失败 — {exc}"
        print(f"[code-patch] {_last_code_error}")
        return None

    patch_payload = extract_json_object(raw_content)
    if not patch_payload:
        _last_code_error = f"LLM 返回格式无法解析 — Raw content first 200 chars: {raw_content[:200]}"
        print(f"[code-patch] {_last_code_error}")
        return None

    files = validate_patch_payload(patch_payload, workspace)
    if not files:
        _last_code_error = "LLM 返回的文件路径校验失败（extension not allowed 或 path traversal）"
        print(f"[code-patch] {_last_code_error}")
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
    global _last_code_error
    _last_code_error = ""

    if not llm_runner.llm_enabled():
        _last_code_error = "LLM 未启用 — DEVFLOW_LLM_ENABLED 环境变量未设为 true"
        print(f"[test-patch] {_last_code_error}")
        return None
    if not llm_runner.get_api_key():
        _last_code_error = "API Key 未设置 — 请设置 DEVFLOW_LLM_API_KEY 环境变量"
        print(f"[test-patch] {_last_code_error}")
        return None

    code_artifact = pipeline.artifacts.get("code")
    if not code_artifact or not code_artifact.workspacePath:
        _last_code_error = "缺少代码阶段产物（需要先完成代码生成阶段）"
        print(f"[test-patch] Missing code artifact or workspacePath. code_artifact={code_artifact is not None}, workspacePath={code_artifact.workspacePath if code_artifact else 'N/A'}")
        return None

    workspace = Path(code_artifact.workspacePath)
    project_files = read_project_files(workspace)
    if not project_files:
        _last_code_error = "工作区中没有找到项目文件"
        print("[test-patch] No project files found in workspace")
        return None

    model = llm_runner.MODEL_ROUTER["test"]
    print(f"[test-patch] Calling model {model}...")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个测试文件生成器。你的唯一任务是根据代码变更生成完整的测试文件。\n"
                    "必须严格按以下 JSON 格式输出，不要输出任何其他文字、解释或 Markdown：\n"
                    '{"files":[{"path":"tests/xxx.test.js","content":"// 完整的测试文件内容"}]}\n'
                    "测试文件必须放在 tests/ 目录下。使用 Node.js 内置的 assert 模块。\n"
                    "只输出 JSON 对象，从 { 开始到 } 结束，不要 ```json 包裹。\n"
                    "重要：content 内的代码请使用 \\n 表示换行、\\t 表示缩进、\\\" 表示双引号、\\\\ 表示反斜杠。确保整个 JSON 合法。"
                ),
            },
            {
                "role": "user",
                "content": build_test_patch_prompt(pipeline, project_files),
            },
        ],
        "temperature": 0.2,
    }

    try:
        response = llm_runner.post_chat_completion(payload, "test")
        raw_content = llm_runner.extract_content(response)
        print(f"[test-patch] Raw content length: {len(raw_content)} chars, first 200: {raw_content[:200]}")
    except Exception as exc:
        _last_code_error = f"LLM API 调用失败 — {exc}"
        print(f"[test-patch] {_last_code_error}")
        return None

    patch_payload = extract_json_object(raw_content)
    if not patch_payload:
        _last_code_error = f"LLM 返回格式无法解析 — first 200 chars: {raw_content[:200]}"
        print("[test-patch] Failed to extract JSON from response")
        return None

    files = validate_patch_payload(patch_payload, workspace)
    if not files:
        print(f"[test-patch] Patch payload validation failed. payload keys: {list(patch_payload.keys()) if patch_payload else 'None'}")
        return None
    if any(not item["path"].startswith("tests/") for item in files):
        print(f"[test-patch] Files not in tests/ directory: {[item['path'] for item in files]}")
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
