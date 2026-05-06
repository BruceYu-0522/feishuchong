(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DevFlowArtifactRenderer = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderInline(value) {
    return escapeHtml(value)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }

  function isTableDivider(line) {
    return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
  }

  function splitTableCells(line) {
    return line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map(function (cell) {
        return cell.trim();
      });
  }

  function renderMarkdown(markdown) {
    var lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    var html = [];
    var listType = "";
    var inCode = false;
    var codeLines = [];

    function closeList() {
      if (!listType) return;
      html.push("</" + listType + ">");
      listType = "";
    }

    for (var index = 0; index < lines.length; index += 1) {
      var line = lines[index];
      var trimmed = line.trim();

      if (trimmed.indexOf("```") === 0) {
        if (inCode) {
          html.push("<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>");
          codeLines = [];
          inCode = false;
        } else {
          closeList();
          inCode = true;
        }
        continue;
      }

      if (inCode) {
        codeLines.push(line);
        continue;
      }

      if (!trimmed) {
        closeList();
        continue;
      }

      if (trimmed.indexOf("|") !== -1 && lines[index + 1] && isTableDivider(lines[index + 1])) {
        closeList();
        var headers = splitTableCells(trimmed);
        index += 1;
        var rows = [];
        while (lines[index + 1] && lines[index + 1].trim().indexOf("|") !== -1) {
          index += 1;
          rows.push(splitTableCells(lines[index]));
        }
        html.push("<table><thead><tr>" + headers.map(function (cell) {
          return "<th>" + renderInline(cell) + "</th>";
        }).join("") + "</tr></thead><tbody>");
        rows.forEach(function (row) {
          html.push("<tr>" + row.map(function (cell) {
            return "<td>" + renderInline(cell) + "</td>";
          }).join("") + "</tr>");
        });
        html.push("</tbody></table>");
        continue;
      }

      var heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
      if (heading) {
        closeList();
        var level = heading[1].length;
        html.push("<h" + level + ">" + renderInline(heading[2]) + "</h" + level + ">");
        continue;
      }

      var unordered = /^[-*]\s+(.+)$/.exec(trimmed);
      if (unordered) {
        if (listType !== "ul") {
          closeList();
          html.push("<ul>");
          listType = "ul";
        }
        html.push("<li>" + renderInline(unordered[1]) + "</li>");
        continue;
      }

      var ordered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
      if (ordered) {
        if (listType !== "ol") {
          closeList();
          html.push("<ol>");
          listType = "ol";
        }
        html.push("<li>" + renderInline(ordered[1]) + "</li>");
        continue;
      }

      closeList();
      html.push("<p>" + renderInline(trimmed) + "</p>");
    }

    closeList();
    if (inCode) {
      html.push("<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>");
    }
    return html.join("");
  }

  function normalizeItem(line) {
    return line
      .replace(/^\s*(?:[-*]|\d+[.)])\s+/, "")
      .replace(/\*\*/g, "")
      .replace(/`/g, "")
      .trim();
  }

  function firstNonEmptyAfter(lines, pattern) {
    for (var i = 0; i < lines.length; i += 1) {
      if (!pattern.test(lines[i])) continue;
      for (var j = i + 1; j < lines.length; j += 1) {
        var candidate = normalizeItem(lines[j]);
        if (!candidate) continue;
        if (/^#{1,4}\s+/.test(candidate)) break;
        return candidate.replace(/^[:：]\s*/, "");
      }
    }
    return "";
  }

  function collectItems(lines, pattern, limit) {
    var items = [];
    for (var i = 0; i < lines.length; i += 1) {
      if (!pattern.test(lines[i])) continue;
      for (var j = i + 1; j < lines.length && items.length < limit; j += 1) {
        var raw = lines[j];
        if (/^#{1,4}\s+/.test(raw.trim())) break;
        if (/^\s*(?:[-*]|\d+[.)])\s+/.test(raw)) {
          var item = normalizeItem(raw);
          if (item) items.push(item);
        }
      }
      if (items.length) break;
    }
    return items;
  }

  function buildPrdMap(markdown) {
    var lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    var goal = firstNonEmptyAfter(lines, /需求目标|目标|需求重述/i) || "等待需求目标沉淀";
    var users = collectItems(lines, /用户故事|目标用户|使用者|Persona/i, 3);
    var features = collectItems(lines, /本次包含|Must-have|功能范围|核心功能/i, 4);
    var acceptance = collectItems(lines, /验收标准|Acceptance Criteria/i, 4);
    var questions = collectItems(lines, /待澄清|待确认|疑问|Question/i, 4);
    var prototype = firstNonEmptyAfter(lines, /原型说明|核心页面|关键交互/i);

    return {
      title: "PRD 图谱",
      nodes: [
        {
          label: "需求目标",
          detail: goal,
          items: goal ? [goal] : [],
          tone: "goal",
        },
        {
          label: "目标用户",
          detail: users[0] || "从用户故事中确认使用者",
          items: users,
          tone: "user",
        },
        {
          label: "核心功能",
          detail: features[0] || "从 Must-have 中提炼功能范围",
          items: features,
          tone: "feature",
        },
        {
          label: "交互原型",
          detail: prototype || "对齐页面骨架和关键操作路径",
          items: prototype ? [prototype] : [],
          tone: "prototype",
        },
        {
          label: "验收标准",
          detail: acceptance[0] || "用 Given-When-Then 锁定可测结果",
          items: acceptance,
          tone: "acceptance",
        },
        {
          label: "待确认",
          detail: questions[0] || "暂无集中待确认项",
          items: questions,
          tone: questions.length ? "question" : "clear",
        },
      ],
    };
  }

  function renderPrdMap(prdMap) {
    var nodes = (prdMap && prdMap.nodes) || [];
    return nodes.map(function (node, index) {
      var items = (node.items || []).slice(0, 3);
      return (
        '<article class="prd-node prd-node-' + escapeHtml(node.tone || "default") + '">' +
          '<span class="prd-node-index">' + String(index + 1).padStart(2, "0") + "</span>" +
          "<strong>" + escapeHtml(node.label) + "</strong>" +
          "<p>" + renderInline(node.detail || "") + "</p>" +
          (items.length ? "<ul>" + items.map(function (item) {
            return "<li>" + renderInline(item) + "</li>";
          }).join("") + "</ul>" : "") +
        "</article>"
      );
    }).join("");
  }

  return {
    escapeHtml: escapeHtml,
    renderMarkdown: renderMarkdown,
    buildPrdMap: buildPrdMap,
    renderPrdMap: renderPrdMap,
  };
});
