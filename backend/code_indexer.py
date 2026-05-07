"""Lightweight semantic code index: extracts symbols from HTML/CSS/JS files
and provides search over the workspace codebase. No external dependencies.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CodeSymbol:
    name: str
    kind: str  # function, class, variable, html_element, css_rule, event
    file: str  # relative path from workspace root
    line: int
    snippet: str  # one-line summary of what it does/contains


@dataclass
class CodeIndex:
    symbols: list[CodeSymbol] = field(default_factory=list)
    file_map: dict[str, str] = field(default_factory=dict)  # rel_path → content

    def build(self, root: Path) -> "CodeIndex":
        """Walk root and index all supported files."""
        supported = {".html", ".css", ".js", ".ts", ".jsx", ".tsx", ".json"}
        skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__", "tests"}

        for f in sorted(root.rglob("*")):
            if f.is_dir() or any(part in skip_dirs for part in f.parts):
                continue
            if f.suffix.lower() not in supported:
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            rel = f.relative_to(root).as_posix()
            self.file_map[rel] = content
            self._index_file(rel, content)
        return self

    # ── Parsers ──

    def _index_file(self, rel: str, content: str):
        ext = Path(rel).suffix.lower()
        if ext == ".html":
            self._parse_html(rel, content)
        elif ext == ".css":
            self._parse_css(rel, content)
        elif ext in (".js", ".ts", ".jsx", ".tsx"):
            self._parse_js(rel, content)

    def _parse_html(self, rel: str, content: str):
        seen = set()  # deduplicate: (line, name)
        for m in re.finditer(r"""<(\w+)([^>]*?)>""", content, re.IGNORECASE):
            tag = m.group(1)
            attrs = m.group(2)
            line = content[: m.start()].count("\n") + 1
            # Extract id
            id_m = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs)
            if id_m:
                name = f"{tag}#{id_m.group(1)}"
                key = (line, name)
                if key not in seen:
                    seen.add(key)
                    self.symbols.append(CodeSymbol(
                        name=name, kind="html_element", file=rel,
                        line=line, snippet=self._snip(content, m.start(), 80),
                    ))
            # Extract class(es)
            class_m = re.search(r'\bclass\s*=\s*["\']([^"\']+)["\']', attrs)
            if class_m:
                for cls in class_m.group(1).split():
                    name = f"{tag}.{cls}"
                    key = (line, name)
                    if key not in seen:
                        seen.add(key)
                        self.symbols.append(CodeSymbol(
                            name=name, kind="html_element", file=rel,
                            line=line, snippet=self._snip(content, m.start(), 80),
                        ))

    def _parse_css(self, rel: str, content: str):
        for m in re.finditer(
            r'([.#@]?[\w-]+(?:\s*[,>+~]\s*[.#@]?[\w-]+)*)\s*\{',
            content,
        ):
            selector = m.group(1).strip()
            if len(selector) > 100:
                continue
            line = content[: m.start()].count("\n") + 1
            self.symbols.append(CodeSymbol(
                name=selector,
                kind="css_rule",
                file=rel,
                line=line,
                snippet=self._snip(content, m.start(), 100),
            ))

    def _parse_js(self, rel: str, content: str):
        # function declarations: function name(...) or name = function(...)
        for m in re.finditer(
            r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function)',
            content,
        ):
            name = m.group(1) or m.group(2)
            line = content[: m.start()].count("\n") + 1
            self.symbols.append(CodeSymbol(
                name=name,
                kind="function",
                file=rel,
                line=line,
                snippet=self._snip(content, m.start(), 100),
            ))

        # class declarations
        for m in re.finditer(r'class\s+(\w+)', content):
            line = content[: m.start()].count("\n") + 1
            self.symbols.append(CodeSymbol(
                name=m.group(1),
                kind="class",
                file=rel,
                line=line,
                snippet=self._snip(content, m.start(), 80),
            ))

        # arrow functions assigned to names
        for m in re.finditer(
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
            content,
        ):
            line = content[: m.start()].count("\n") + 1
            self.symbols.append(CodeSymbol(
                name=m.group(1),
                kind="function",
                file=rel,
                line=line,
                snippet=self._snip(content, m.start(), 100),
            ))

        # event listeners
        for m in re.finditer(
            r'\.addEventListener\s*\(\s*["\'](\w+)["\']',
            content,
        ):
            line = content[: m.start()].count("\n") + 1
            self.symbols.append(CodeSymbol(
                name=m.group(1),
                kind="event",
                file=rel,
                line=line,
                snippet=self._snip(content, m.start(), 120),
            ))

    @staticmethod
    def _snip(content: str, pos: int, width: int) -> str:
        start = max(0, pos - 10)
        end = min(len(content), pos + width)
        snip = content[start:end].replace("\n", " ").replace("\r", " ").strip()
        return snip[:width]

    # ── Search ──

    def search(self, query: str, max_results: int = 15) -> list[CodeSymbol]:
        """Find symbols matching query in name or content. Returns ranked results."""
        q = query.lower().strip()
        if not q:
            return []
        scored: list[tuple[float, CodeSymbol]] = []
        for sym in self.symbols:
            score = 0.0
            if q in sym.name.lower():
                score += 3.0
            if q in sym.snippet.lower():
                score += 1.0
            if q in sym.kind.lower():
                score += 0.5
            if score > 0:
                scored.append((score, sym))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:max_results]]

    def search_content(self, query: str, max_results: int = 10) -> list[dict]:
        """Full-text search across file contents. Returns matching snippets with context."""
        q = query.lower().strip()
        if not q:
            return []
        results: list[dict] = []
        for path, content in self.file_map.items():
            lower = content.lower()
            pos = 0
            while True:
                idx = lower.find(q, pos)
                if idx == -1:
                    break
                line_no = content[:idx].count("\n") + 1
                start = max(0, content.rfind("\n", 0, idx) + 1)
                end = content.find("\n", idx + len(q))
                if end == -1:
                    end = len(content)
                snip = content[start:end].strip()[:200]
                results.append({
                    "file": path,
                    "line": line_no,
                    "snippet": snip,
                })
                pos = idx + 1
                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break
        return results[:max_results]

    def summary(self) -> dict:
        """Return a summary of the indexed codebase."""
        by_kind: dict[str, int] = {}
        by_file: dict[str, int] = {}
        for s in self.symbols:
            by_kind[s.kind] = by_kind.get(s.kind, 0) + 1
            by_file[s.file] = by_file.get(s.file, 0) + 1
        return {
            "total_symbols": len(self.symbols),
            "total_files": len(self.file_map),
            "by_kind": by_kind,
            "by_file": by_file,
        }

    def context_for_llm(self, query: str, max_chars: int = 2000) -> str:
        """Build a compact context string for LLM prompts from search results."""
        by_file: dict[str, list[CodeSymbol]] = {}
        for sym in self.search(query):
            by_file.setdefault(sym.file, []).append(sym)

        if not by_file:
            return ""

        parts = [f"代码索引搜索结果（查询：{query}）："]
        total = 0
        for fname, syms in by_file.items():
            content = self.file_map.get(fname, "")
            parts.append(f"\n📄 {fname}")
            for sym in syms[:8]:
                ctx = f"  L{sym.line} [{sym.kind}] {sym.name}"
                if total < max_chars:
                    parts.append(ctx)
                    total += len(ctx)
        return "\n".join(parts)
