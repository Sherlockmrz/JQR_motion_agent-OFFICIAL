(() => {
  const config = window.DOC_CONFIG || {};
  const content = document.querySelector("#document-content");
  const raw = document.querySelector("#raw-content");
  const toc = document.querySelector("#toc");
  const status = document.querySelector("#load-status");
  let sourceText = "";

  const escapeHtml = (value) => value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

  const slugger = (() => {
    const used = new Map();
    return (text) => {
      const base = text.trim().toLowerCase()
        .replace(/[^\p{L}\p{N}]+/gu, "-")
        .replace(/^-|-$/g, "") || "section";
      const count = used.get(base) || 0;
      used.set(base, count + 1);
      return count ? `${base}-${count + 1}` : base;
    };
  })();

  function headingLevel(line) {
    if (/^(主线：|副线：|一、|二、|三、|四、|五、|六、|七、|八、|九、|十[一二三四五六七八九]?、)/.test(line)) return 2;
    if (/^\d+\.\s*\S/.test(line)) return 3;
    if (/^(目标|整体架构|任务分发规则|每个模块的功能总结|下一任务预判|输入|输出|Agent输入|Agent输出|结果说明)[：：]?/.test(line)) return 3;
    return 0;
  }

  function looksLikeCode(line, inBraceBlock) {
    if (inBraceBlock) return true;
    return /^\s*[{\[]\s*$/.test(line)
      || /^\s*(def |async def |class |import |from |await |return |if |elif |else:|try:|except |for |while )/.test(line)
      || /^\s*["'][\w\-]+["']\s*:/.test(line)
      || /^\s*(ws:\/\/|https?:\/\/|\[trace=|ROS_DOMAIN_ID=|scene=|command=|medicine:|light:)/.test(line);
  }

  function render(text) {
    const lines = text.replace(/\r\n?/g, "\n").split("\n");
    const fragment = document.createDocumentFragment();
    let index = 0;
    let inFence = false;
    let fenceLines = [];
    let braceDepth = 0;
    let codeLines = [];

    const flushCode = () => {
      if (!codeLines.length) return;
      const pre = document.createElement("pre");
      pre.className = "code-block";
      pre.textContent = codeLines.join("\n");
      fragment.appendChild(pre);
      codeLines = [];
      braceDepth = 0;
    };

    while (index < lines.length) {
      const line = lines[index];
      const trimmed = line.trim();

      if (trimmed.startsWith("```")) {
        if (inFence) {
          const pre = document.createElement("pre");
          pre.className = "code-block";
          pre.textContent = fenceLines.join("\n");
          fragment.appendChild(pre);
          fenceLines = [];
          inFence = false;
        } else {
          flushCode();
          inFence = true;
        }
        index += 1;
        continue;
      }

      if (inFence) {
        fenceLines.push(line);
        index += 1;
        continue;
      }

      const opening = (line.match(/{/g) || []).length + (line.match(/\[/g) || []).length;
      const closing = (line.match(/}/g) || []).length + (line.match(/\]/g) || []).length;
      if (looksLikeCode(line, braceDepth > 0)) {
        codeLines.push(line);
        braceDepth += opening - closing;
        if (braceDepth <= 0 && !/[,:({[]\s*$/.test(line)) flushCode();
        index += 1;
        continue;
      }
      flushCode();

      const level = headingLevel(trimmed);
      if (level) {
        const heading = document.createElement(`h${level}`);
        heading.textContent = trimmed;
        heading.id = slugger(trimmed);
        fragment.appendChild(heading);
      } else if (trimmed === "[图片]") {
        const note = document.createElement("div");
        note.className = "placeholder";
        note.textContent = "原文图片占位（仅保留本次随请求提供的原图，未提供的图片不作替换）";
        fragment.appendChild(note);
      } else if (/^[-*]\s+/.test(trimmed)) {
        const item = document.createElement("div");
        item.className = "bullet-line";
        item.textContent = `• ${trimmed.replace(/^[-*]\s+/, "")}`;
        fragment.appendChild(item);
      } else {
        const row = document.createElement("div");
        row.className = /^\d+[\.、]\s*/.test(trimmed) ? "number-line" : "prose-line";
        row.textContent = line || " ";
        fragment.appendChild(row);
      }
      index += 1;
    }
    flushCode();
    content.replaceChildren(fragment);
    buildToc();
  }

  function buildToc() {
    const headings = [...content.querySelectorAll("h2, h3")];
    toc.replaceChildren(...headings.map((heading) => {
      const link = document.createElement("a");
      link.href = `#${heading.id}`;
      link.textContent = heading.textContent;
      if (heading.tagName === "H3") link.style.paddingLeft = "18px";
      return link;
    }));
  }

  async function load() {
    try {
      const response = await fetch(config.source);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      sourceText = await response.text();
      raw.textContent = sourceText;
      render(sourceText);
      status.textContent = `原文已载入：${sourceText.split(/\r?\n/).length} 行`;
    } catch (error) {
      content.innerHTML = `<div class="error">无法载入原文：${escapeHtml(String(error))}。请通过HTTP静态服务器打开本目录，或点击“打开原始文本”。</div>`;
      status.textContent = "原文载入失败";
    }
  }

  document.querySelector("#toggle-view")?.addEventListener("click", () => {
    content.classList.toggle("hidden");
    raw.classList.toggle("hidden");
    document.querySelector("#toggle-view").textContent = raw.classList.contains("hidden") ? "查看完整原文" : "返回整理视图";
  });

  document.querySelector("#copy-source")?.addEventListener("click", async () => {
    if (!sourceText) return;
    await navigator.clipboard.writeText(sourceText);
    document.querySelector("#copy-source").textContent = "已复制";
    setTimeout(() => { document.querySelector("#copy-source").textContent = "复制原文"; }, 1500);
  });

  document.querySelector("#search-source")?.addEventListener("input", (event) => {
    const query = event.target.value.trim();
    if (!query) {
      render(sourceText);
      return;
    }
    const filtered = sourceText.split(/\r?\n/).filter((line) => line.toLowerCase().includes(query.toLowerCase())).join("\n");
    render(filtered || `没有找到：${query}`);
  });

  load();
})();
