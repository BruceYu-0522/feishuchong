(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DevFlowElementPicker = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  // ── State ──
  var editMode = false;
  var pipeline = null;
  var overlays = [];           // { overlayEl, iframeEl, styleEl }
  var highlightedEl = null;
  var selectedInfo = null;
  var pendingClickTimer = null;

  // ── Dialog elements (created lazily) ──
  var dialogModal = null;
  var dialogTagName = null;
  var dialogInfo = null;
  var dialogInput = null;
  var dialogStream = null;
  var dialogSubmit = null;
  var dialogClose = null;
  var dialogCancel = null;
  var modificationEventSource = null;

  // ── Public API ──

  function init(pipelineRef) {
    pipeline = pipelineRef;
  }

  function isEditMode() {
    return editMode;
  }

  function enableEditMode() {
    if (editMode) return;
    if (!pipeline) return;

    editMode = true;

    // Find all visible product-preview-frame containers with iframes
    var frames = document.querySelectorAll(".product-preview-frame");
    frames.forEach(function (frameWrap) {
      if (frameWrap.classList.contains("hidden")) return;
      var iframe = frameWrap.querySelector("iframe");
      if (!iframe) return;

      // Ensure container is positioned
      var computed = window.getComputedStyle(frameWrap);
      if (computed.position === "static") {
        frameWrap.style.position = "relative";
      }

      // Create overlay
      var overlay = document.createElement("div");
      overlay.className = "picker-overlay is-active";
      overlay.setAttribute("aria-label", "元素选择覆盖层");
      frameWrap.appendChild(overlay);

      // Inject highlight style into iframe
      var styleEl = injectHighlightStyle(iframe);
      if (!styleEl) {
        overlay.remove();
        return;
      }

      // Bind events
      overlay.addEventListener("mousemove", function (e) {
        onOverlayMove(e, iframe);
      });
      overlay.addEventListener("click", function (e) {
        onOverlayClick(e, iframe);
      });

      overlays.push({ overlayEl: overlay, iframeEl: iframe, styleEl: styleEl });
    });

    if (overlays.length === 0) {
      editMode = false;
      return;
    }

    // ESC listener
    document.addEventListener("keydown", onKeyDown);
  }

  function disableEditMode() {
    editMode = false;

    // Close dialog if open
    closeModificationDialog();

    // Remove all overlays
    overlays.forEach(function (entry) {
      try {
        entry.styleEl.remove();
      } catch (_) {}
      try {
        entry.overlayEl.removeEventListener("mousemove", function () {});
        entry.overlayEl.removeEventListener("click", function () {});
        entry.overlayEl.remove();
      } catch (_) {}
      try {
        removeHighlight(entry.iframeEl);
      } catch (_) {}
    });
    overlays = [];
    highlightedEl = null;
    selectedInfo = null;

    document.removeEventListener("keydown", onKeyDown);
  }

  // ── Internal: Overlay events ──

  function getElementAtPoint(iframe, clientX, clientY) {
    var rect = iframe.getBoundingClientRect();
    var doc = null;
    try { doc = iframe.contentDocument || iframe.contentWindow.document; } catch (_) { return null; }
    if (!doc) return null;

    var x = clientX - rect.left;
    var y = clientY - rect.top;
    try {
      return doc.elementFromPoint(x, y);
    } catch (_) {
      return null;
    }
  }

  function onOverlayMove(e, iframe) {
    var el = getElementAtPoint(iframe, e.clientX, e.clientY);
    if (el === highlightedEl) return;

    // Remove old highlight
    removeHighlight(iframe);

    if (!el || el === iframe.contentDocument.documentElement || el === iframe.contentDocument.body) {
      highlightedEl = null;
      return;
    }

    // Add new highlight
    try {
      el.classList.add("picker-highlight");
      highlightedEl = el;
    } catch (_) {}
  }

  function onOverlayClick(e, iframe) {
    // Debounce
    if (pendingClickTimer) return;
    pendingClickTimer = setTimeout(function () { pendingClickTimer = null; }, 300);

    var el = getElementAtPoint(iframe, e.clientX, e.clientY);
    if (!el || el === iframe.contentDocument.documentElement || el === iframe.contentDocument.body) return;

    var doc = null;
    try { doc = iframe.contentDocument || iframe.contentWindow.document; } catch (_) {}
    if (!doc) return;

    // Determine iframe type
    var iframeType = "product";
    if (iframe.hasAttribute("srcdoc")) {
      iframeType = "prototype";
    }

    selectedInfo = captureElementInfo(el, doc, iframeType);
    removeHighlight(iframe);
    highlightedEl = null;
    showModificationDialog();
  }

  // ── Internal: Element capture ──

  function captureElementInfo(element, doc, iframeType) {
    return {
      tagName: element.tagName.toLowerCase(),
      selector: getElementSelector(element),
      html: (element.outerHTML || "").substring(0, 500),
      computedStyles: getRelevantStyles(element),
      text: (element.textContent || "").trim().substring(0, 200),
      sourceFile: iframeType === "prototype" ? "prototype.html" : "index.html",
      iframeType: iframeType,
    };
  }

  function getElementSelector(element) {
    if (!element || element === document.body) return "";
    var path = [];
    var current = element;

    while (current && current !== document.body && current !== document.documentElement) {
      var selector = current.tagName.toLowerCase();

      if (current.id) {
        path.unshift("#" + CSS.escape(current.id));
        break;
      }

      // Add classes (filter out our injected class)
      if (current.classList && current.classList.length > 0) {
        var classes = [];
        for (var i = 0; i < current.classList.length; i++) {
          var c = current.classList[i];
          if (c !== "picker-highlight" && c.indexOf("_") !== 0) {
            classes.push(CSS.escape(c));
          }
        }
        if (classes.length > 0) {
          selector += "." + classes.slice(0, 2).join(".");
        }
      }

      // nth-of-type for uniqueness
      var parent = current.parentElement;
      if (parent) {
        var siblings = Array.prototype.filter.call(parent.children, function (s) {
          return s.tagName === current.tagName;
        });
        if (siblings.length > 1) {
          var index = siblings.indexOf(current) + 1;
          selector += ":nth-of-type(" + index + ")";
        }
      }

      path.unshift(selector);
      current = current.parentElement;
      if (path.length > 10) break;
    }

    var fullPath = path.join(" > ");

    // Verify uniqueness
    try {
      var matches = element.ownerDocument.querySelectorAll(fullPath);
      if (matches.length !== 1 && element.getAttribute("data-testid")) {
        fullPath += '[data-testid="' + element.getAttribute("data-testid") + '"]';
      }
    } catch (_) {
      fullPath = element.tagName.toLowerCase();
    }

    return fullPath;
  }

  function getRelevantStyles(element) {
    var relevant = [
      "display", "position", "color", "backgroundColor", "fontSize",
      "fontFamily", "fontWeight", "padding", "margin", "border",
      "borderRadius", "width", "height", "textAlign", "cursor",
      "boxShadow", "opacity", "zIndex",
    ];
    var computed = window.getComputedStyle(element);
    var styles = {};
    relevant.forEach(function (prop) {
      var val = computed.getPropertyValue(prop);
      if (val) styles[prop] = val;
    });
    return styles;
  }

  // ── Internal: Iframe helpers ──

  function injectHighlightStyle(iframe) {
    var doc = null;
    try { doc = iframe.contentDocument || iframe.contentWindow.document; } catch (_) { return null; }
    if (!doc || !doc.head) return null;

    var style = doc.createElement("style");
    style.setAttribute("data-picker", "highlight");
    style.textContent = ".picker-highlight { outline: 2px dashed #4A9FD8 !important; outline-offset: 2px !important; background: rgba(74,159,216,0.08) !important; }";
    doc.head.appendChild(style);
    return style;
  }

  function removeHighlight(iframe) {
    var doc = null;
    try { doc = iframe.contentDocument || iframe.contentWindow.document; } catch (_) {}
    if (!doc) return;
    var els = doc.querySelectorAll(".picker-highlight");
    for (var i = 0; i < els.length; i++) {
      try { els[i].classList.remove("picker-highlight"); } catch (_) {}
    }
  }

  // ── Internal: Modification dialog ──

  function ensureDialog() {
    if (dialogModal) return;

    var modal = document.createElement("div");
    modal.className = "element-modify-modal hidden";
    modal.id = "elementModifyModal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");
    modal.innerHTML =
      '<div class="element-modify-dialog">' +
        '<div class="element-modify-header">' +
          '<span id="elementModifyTagName"></span>' +
          '<strong>修改此元素</strong>' +
          '<button class="ghost-button" id="elementModifyClose" type="button">&times;</button>' +
        '</div>' +
        '<div class="element-modify-info" id="elementModifyInfo"></div>' +
        '<div class="element-modify-input-area">' +
          '<label for="elementModifyInput">描述你要修改什么</label>' +
          '<textarea id="elementModifyInput" rows="3" placeholder="例如：把这个按钮改成圆角蓝色背景、添加一个加载状态…"></textarea>' +
        '</div>' +
        '<div class="element-modify-stream hidden" id="elementModifyStream"></div>' +
        '<div class="element-modify-actions">' +
          '<button class="ghost-button" id="elementModifyCancel" type="button">取消</button>' +
          '<button class="primary-button" id="elementModifySubmit" type="button">提交修改</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(modal);

    dialogModal = modal;
    dialogTagName = modal.querySelector("#elementModifyTagName");
    dialogInfo = modal.querySelector("#elementModifyInfo");
    dialogInput = modal.querySelector("#elementModifyInput");
    dialogStream = modal.querySelector("#elementModifyStream");
    dialogSubmit = modal.querySelector("#elementModifySubmit");
    dialogClose = modal.querySelector("#elementModifyClose");
    dialogCancel = modal.querySelector("#elementModifyCancel");

    // Event bindings
    dialogClose.addEventListener("click", closeModificationDialog);
    dialogCancel.addEventListener("click", closeModificationDialog);
    dialogSubmit.addEventListener("click", submitModification);

    dialogInput.addEventListener("input", function () {
      dialogSubmit.disabled = !dialogInput.value.trim();
    });

    dialogInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!dialogSubmit.disabled) submitModification();
      }
      if (e.key === "Escape") {
        e.stopPropagation();
        closeModificationDialog();
      }
    });
  }

  function showModificationDialog() {
    if (!selectedInfo) return;
    ensureDialog();

    dialogTagName.textContent = selectedInfo.tagName.toUpperCase();
    dialogInfo.innerHTML =
      '<div class="info-row">' +
        '<span class="info-label">选择器：</span>' +
        '<span class="info-value">' + escapeHtml(selectedInfo.selector || "(unknown)") + '</span>' +
      '</div>' +
      '<div class="info-row">' +
        '<span class="info-label">来源：</span>' +
        '<span class="info-value">' + escapeHtml(selectedInfo.sourceFile) + ' (' + selectedInfo.iframeType + ')</span>' +
      '</div>' +
      '<div class="info-row">' +
        '<span class="info-label">HTML：</span>' +
        '<span class="info-value">' + escapeHtml(selectedInfo.html || "").substring(0, 300) + '</span>' +
      '</div>';

    dialogInput.value = "";
    dialogInput.disabled = false;
    dialogSubmit.disabled = true;
    dialogStream.classList.add("hidden");
    dialogStream.innerHTML = "";

    dialogModal.classList.remove("hidden");
    setTimeout(function () { dialogInput.focus(); }, 100);
  }

  function closeModificationDialog() {
    if (modificationEventSource) {
      modificationEventSource.close();
      modificationEventSource = null;
    }
    if (dialogModal) {
      dialogModal.classList.add("hidden");
    }
    selectedInfo = null;
  }

  function submitModification() {
    var changeRequest = dialogInput.value.trim();
    if (!changeRequest || !selectedInfo || !pipeline) return;

    // Show streaming area
    dialogStream.classList.remove("hidden");
    dialogStream.innerHTML = "";
    dialogSubmit.disabled = true;
    dialogInput.disabled = true;
    appendStreamSystem("正在调用 AI 模型修改代码…");

    if (modificationEventSource) {
      modificationEventSource.close();
    }

    var infoJson = encodeURIComponent(JSON.stringify(selectedInfo));
    var requestText = encodeURIComponent(changeRequest);
    var url = "http://127.0.0.1:8001/pipelines/" + pipeline.id +
      "/element-modify-stream?element_info=" + infoJson + "&change_request=" + requestText;

    var es = new EventSource(url);
    modificationEventSource = es;

    es.addEventListener("chunk", function (event) {
      appendStreamChunk(event.data);
    });

    es.addEventListener("system", function (event) {
      appendStreamSystem(event.data);
    });

    es.addEventListener("result", function (event) {
      try {
        es._resultData = JSON.parse(event.data);
      } catch (_) {
        es._resultData = event.data;
      }
    });

    es.addEventListener("done", function () {
      es.close();
      modificationEventSource = null;
      dialogSubmit.disabled = false;
      dialogInput.disabled = false;
      appendStreamSystem("修改完成！");

      // Refresh iframe(s)
      if (es._resultData) {
        refreshIframeAfterModification(es._resultData);
      }

      // Auto-close after short delay
      setTimeout(function () {
        closeModificationDialog();
      }, 1800);
    });

    es.addEventListener("fail", function (event) {
      appendStreamError(event.data || "修改失败");
      dialogSubmit.disabled = false;
      dialogInput.disabled = false;
      es.close();
      modificationEventSource = null;
    });

    es.onerror = function () {
      if (es.readyState === EventSource.CLOSED) {
        modificationEventSource = null;
        dialogSubmit.disabled = false;
        dialogInput.disabled = false;
      }
    };
  }

  function appendStreamChunk(text) {
    var span = document.createElement("span");
    span.className = "stream-chunk";
    span.textContent = text;
    dialogStream.appendChild(span);
    dialogStream.scrollTop = dialogStream.scrollHeight;
  }

  function appendStreamSystem(text) {
    var div = document.createElement("div");
    div.className = "stream-system";
    div.textContent = "⚙ " + text;
    dialogStream.appendChild(div);
    dialogStream.scrollTop = dialogStream.scrollHeight;
  }

  function appendStreamError(text) {
    var div = document.createElement("div");
    div.className = "stream-error";
    div.textContent = "✕ " + text;
    dialogStream.appendChild(div);
    dialogStream.scrollTop = dialogStream.scrollHeight;
  }

  function refreshIframeAfterModification(resultData) {
    // resultData: { file: "...", commit: "...", prototypeHtml: "..." }
    var iframeType = selectedInfo ? selectedInfo.iframeType : "product";

    if (iframeType === "prototype" && resultData.prototypeHtml) {
      // Refresh srcdoc iframes
      var srcdocIframes = document.querySelectorAll("#extras-requirement .prototype-inline iframe, #prototypeFrame");
      for (var i = 0; i < srcdocIframes.length; i++) {
        try {
          srcdocIframes[i].setAttribute("srcdoc", resultData.prototypeHtml);
        } catch (_) {}
      }
    } else {
      // Refresh product iframes (cache bust)
      var productIframes = document.querySelectorAll("#extras-code .product-preview-inline iframe, #productPreviewFrame");
      for (var j = 0; j < productIframes.length; j++) {
        try {
          var iframe = productIframes[j];
          if (iframe.src) {
            var base = iframe.src.replace(/\?t=\d+$/, "");
            iframe.src = base + "?t=" + Date.now();
          }
        } catch (_) {}
      }
    }
  }

  // ── Internal: Keyboard ──

  function onKeyDown(event) {
    if (event.key === "Escape") {
      // If dialog is open, close it first
      if (dialogModal && !dialogModal.classList.contains("hidden")) {
        closeModificationDialog();
        return;
      }
      // Otherwise exit edit mode (let script.js handle the toggle button state)
      disableEditMode();
      var toggleBtn = document.querySelector("#editModeToggle");
      if (toggleBtn) {
        toggleBtn.classList.remove("is-active");
        toggleBtn.textContent = "编辑模式";
      }
    }
  }

  // ── Utility ──

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ── Exports ──

  return {
    init: init,
    isEditMode: isEditMode,
    enableEditMode: enableEditMode,
    disableEditMode: disableEditMode,
  };
});
