// src/rules.ts
var DEFAULTS = {
  minWords: 4,
  maxFontSize: "",
  minFontSize: "",
  minLastLineWords: 2,
  maxProtectedChars: 25,
  onlyMultiLine: false
};
function resolveRule(rule) {
  return { ...DEFAULTS, ...rule };
}
function parsePx(value) {
  if (!value)
    return null;
  const match = value.match(/^([\d.]+)\s*(px|rem)?$/i);
  if (!match)
    return null;
  const num = parseFloat(match[1]);
  if (!Number.isFinite(num))
    return null;
  const unit = (match[2] || "px").toLowerCase();
  if (unit === "px")
    return num;
  if (unit === "rem") {
    const root = parseFloat(getComputedStyle(document.documentElement).fontSize);
    return num * root;
  }
  return null;
}
function isMultiLine(el) {
  const style = getComputedStyle(el);
  const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
  return el.clientHeight > lineHeight * 1.5;
}
function shouldApply(el, words, rule) {
  if (words.length < rule.minWords)
    return false;
  const fontSize = parsePx(getComputedStyle(el).fontSize);
  if (fontSize !== null) {
    const max = parsePx(rule.maxFontSize);
    if (max !== null && fontSize > max)
      return false;
    const min = parsePx(rule.minFontSize);
    if (min !== null && fontSize < min)
      return false;
  }
  if (rule.onlyMultiLine && !isMultiLine(el))
    return false;
  const lastWords = words.slice(-rule.minLastLineWords);
  if (lastWords.join(" ").length > rule.maxProtectedChars)
    return false;
  return true;
}

// src/core.ts
var NBSP = " ";
var DEMO_ATTR = "data-orphan-demo";
var STYLE_ID = "orphan-obliterator-demo";
var originals = new WeakMap;
function normalizeConfigs(input) {
  if (typeof input === "string") {
    return [{ selectors: input.split(",").map((s) => s.trim()) }];
  }
  return Array.isArray(input) ? input : [input];
}
function lastTextNode(el) {
  for (let i = el.childNodes.length - 1;i >= 0; i--) {
    const child = el.childNodes[i];
    if (child.nodeType === Node.TEXT_NODE && child.textContent?.includes(" ")) {
      return child;
    }
    if (child.nodeType === Node.ELEMENT_NODE) {
      const found = lastTextNode(child);
      if (found)
        return found;
    }
  }
  return null;
}
function injectDemoStyles() {
  if (document.getElementById(STYLE_ID))
    return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = [
    `[${DEMO_ATTR}]{outline:1px dotted #ccc;outline-offset:2px;border-radius:2px;cursor:pointer;position:relative}`,
    `[${DEMO_ATTR}]:hover{outline-color:#999}`,
    `[${DEMO_ATTR}]::after{content:attr(data-orphan-tip);position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);padding:4px 8px;background:#333;color:#fff;font-size:12px;line-height:1.4;white-space:nowrap;border-radius:4px;opacity:0;pointer-events:none;transition:opacity .15s}`,
    `[${DEMO_ATTR}]:hover::after{opacity:1;pointer-events:auto}`
  ].join(`
`);
  document.head.appendChild(style);
}
function hasOrphan(node) {
  const text = node.textContent || "";
  const lastSpace = text.lastIndexOf(" ");
  if (lastSpace === -1)
    return false;
  const range = document.createRange();
  range.setStart(node, lastSpace + 1);
  range.setEnd(node, text.length);
  const lastRect = range.getBoundingClientRect();
  range.setStart(node, 0);
  range.setEnd(node, lastSpace);
  const rects = range.getClientRects();
  if (rects.length === 0)
    return false;
  const prevRect = rects[rects.length - 1];
  return Math.abs(lastRect.top - prevRect.top) > 2;
}
function wrapDemoSpan(node, splitIndex, protectedText) {
  const parent = node.parentNode;
  const span = document.createElement("span");
  span.setAttribute(DEMO_ATTR, "");
  span.setAttribute("data-orphan-tip", "corrected using orphan-obliterator");
  span.addEventListener("click", () => window.open("https://github.com/doublej/orphan-obliterator", "_blank"));
  span.textContent = protectedText;
  const before = node.textContent.slice(0, splitIndex);
  if (before) {
    node.textContent = before;
    parent.insertBefore(span, node.nextSibling);
  } else {
    parent.replaceChild(span, node);
  }
}
function processElement(el, config) {
  const node = lastTextNode(el);
  if (!node?.textContent)
    return;
  const rule = resolveRule(config.rules);
  const allWords = (el.textContent || "").trim().split(/\s+/).filter(Boolean);
  if (!shouldApply(el, allWords, rule))
    return;
  if (!originals.has(node))
    originals.set(node, node.textContent);
  const parts = node.textContent.split(/( +)/);
  let replaced = 0;
  let firstReplacedIndex = -1;
  const needed = rule.minLastLineWords - 1;
  for (let i = parts.length - 1;i >= 0 && replaced < needed; i--) {
    if (/^ +$/.test(parts[i])) {
      parts[i] = NBSP;
      firstReplacedIndex = i;
      replaced++;
    }
  }
  if (replaced === 0)
    return;
  if (config.demo && (!isMultiLine(el) || !hasOrphan(node))) {
    node.textContent = parts.join("");
    return;
  }
  if (config.demo) {
    injectDemoStyles();
    const splitPos = parts.slice(0, firstReplacedIndex).join("").length;
    const protectedText = parts.slice(firstReplacedIndex).join("");
    wrapDemoSpan(node, splitPos, protectedText);
  } else {
    node.textContent = parts.join("");
  }
}
function restoreElement(el) {
  for (const span of el.querySelectorAll(`[${DEMO_ATTR}]`)) {
    const parent = span.parentNode;
    while (span.firstChild)
      parent.insertBefore(span.firstChild, span);
    parent.removeChild(span);
    parent.normalize();
  }
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let node;
  while (node = walker.nextNode()) {
    const original = originals.get(node);
    if (original !== undefined) {
      node.textContent = original;
      originals.delete(node);
    }
  }
}
function debounce(fn, ms) {
  let timer;
  return () => {
    clearTimeout(timer);
    timer = setTimeout(fn, ms);
  };
}
function obliterate(input) {
  const configs = normalizeConfigs(input);
  const observers = [];
  let processing = false;
  function update() {
    if (processing)
      return;
    processing = true;
    for (const config of configs) {
      const selector = config.selectors.join(", ");
      for (const el of document.querySelectorAll(selector)) {
        restoreElement(el);
        processElement(el, config);
      }
    }
    processing = false;
  }
  update();
  if (configs.some((c) => c.observe)) {
    const mo = new MutationObserver(debounce(update, 100));
    mo.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true
    });
    observers.push(mo);
  }
  if (configs.some((c) => c.responsive ?? c.demo)) {
    const ro = new ResizeObserver(debounce(update, 150));
    ro.observe(document.documentElement);
    observers.push(ro);
  }
  return {
    update,
    destroy() {
      observers.forEach((o) => o.disconnect());
      observers.length = 0;
      for (const config of configs) {
        const selector = config.selectors.join(", ");
        for (const el of document.querySelectorAll(selector)) {
          restoreElement(el);
        }
      }
      document.getElementById(STYLE_ID)?.remove();
    }
  };
}
export {
  obliterate
};
