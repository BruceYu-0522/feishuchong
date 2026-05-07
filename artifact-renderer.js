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

  function findSectionText(lines, patterns) {
    // Accept either a single regex or an array of regexes
    var patternsArr = Array.isArray(patterns) ? patterns : [patterns];
    for (var i = 0; i < lines.length; i += 1) {
      var matchesAny = patternsArr.some(function (pat) {
        return pat.test(lines[i]);
      });
      if (!matchesAny) continue;
      // Collect paragraph text until blank line or next heading
      var text = "";
      for (var j = i + 1; j < lines.length; j += 1) {
        var raw = lines[j];
        var trimmed = raw.trim();
        if (!trimmed) break;
        if (/^#{1,4}\s+/.test(trimmed)) break;
        if (/^\s*(?:[-*]|\d+[.)])\s+/.test(raw)) break;
        text += (text ? " " : "") + normalizeItem(raw);
      }
      if (text) return text.slice(0, 120);
    }
    return "";
  }

  function collectItems(lines, pattern, limit) {
    var items = [];
    for (var i = 0; i < lines.length; i += 1) {
      if (!pattern.test(lines[i])) continue;
      // Collect items from subsequent list until next heading or empty section
      for (var j = i + 1; j < lines.length && items.length < limit; j += 1) {
        var raw = lines[j];
        var trimmed = raw.trim();
        // Stop at next heading (not within this section)
        if (/^#{1,4}\s+/.test(trimmed)) break;
        // Also stop at a blank line followed by non-list text
        if (!trimmed && j + 1 < lines.length && !/^\s*(?:[-*]|\d+[.)])\s+/.test(lines[j + 1]) && !/^#{1,4}\s+/.test(lines[j + 1].trim())) break;
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
    var goal = findSectionText(lines, [/需求目标/, /Situation/, /情境/, /背景/, /需求的核心是/, /目标是/]);
    var users = collectItems(lines, /用户故事|目标用户|使用者|Persona|角色|角色画像/i, 3);
    var features = collectItems(lines, /本次包含|Must-have|功能范围|核心功能|MVP/i, 5);
    var acceptance = collectItems(lines, /验收标准|Acceptance Criteria|Given/i, 4);
    var questions = collectItems(lines, /待澄清|待确认|未确认|疑问|Question|问题[:：]/i, 4);
    var prototype = findSectionText(lines, [/原型说明/, /核心页面/, /关键交互/, /示意/, /页面结构/]);

    // If no explicit goal found, try extracting from SCQA answer section
    if (!goal) {
      goal = findSectionText(lines, [/A（答案）/, /答案/]);
    }

    var summaryTexts = [];
    if (goal) summaryTexts.push(goal.slice(0, 50));
    if (users.length) summaryTexts.push("面向" + users[0]);
    if (features.length) summaryTexts.push(features.length + "个核心功能");

    return {
      title: "PRD 图谱",
      summary: summaryTexts.length ? summaryTexts.join(" · ") : "基于需求分析的结构化提炼",
      nodes: [
        {
          label: "需求目标",
          detail: goal || "从分析文档中提取业务目标",
          items: goal ? [goal] : [],
          tone: "goal",
        },
        {
          label: "目标用户",
          detail: users[0] || "从用户故事中确认角色",
          items: users,
          tone: "user",
        },
        {
          label: "核心功能",
          detail: features.length ? features.length + " 个 Must-have" : "从功能范围提取",
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
          detail: acceptance.length ? acceptance.length + " 条验收条件" : "用 Given-When-Then 锁定可测结果",
          items: acceptance,
          tone: "acceptance",
        },
        {
          label: "待澄清",
          detail: questions.length ? questions.length + " 个待确认" : "暂无集中待确认项",
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
