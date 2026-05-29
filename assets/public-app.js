const DATA_URL = "dist/latest.json";

const state = {
  articles: [],
  region: "all",
  query: "",
  sort: "score",
  generatedAt: "",
  errors: [],
};

const els = {
  updateStatus: document.querySelector("#updateStatus"),
  updatedAt: document.querySelector("#updatedAt"),
  totalCount: document.querySelector("#totalCount"),
  topScore: document.querySelector("#topScore"),
  sourceCount: document.querySelector("#sourceCount"),
  regionCount: document.querySelector("#regionCount"),
  searchInput: document.querySelector("#searchInput"),
  sortSelect: document.querySelector("#sortSelect"),
  regionFilters: document.querySelector("#regionFilters"),
  keywordList: document.querySelector("#keywordList"),
  sourceList: document.querySelector("#sourceList"),
  resultCount: document.querySelector("#resultCount"),
  notice: document.querySelector("#notice"),
  news: document.querySelector("#news"),
  reloadButton: document.querySelector("#reloadButton"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDate(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function normalizePayload(payload) {
  if (Array.isArray(payload)) {
    return { articles: payload, generated_at: "", errors: [] };
  }
  return {
    articles: Array.isArray(payload.articles) ? payload.articles : [],
    generated_at: payload.generated_at || payload.generatedAt || "",
    errors: Array.isArray(payload.errors) ? payload.errors : [],
  };
}

function countBy(items, key) {
  return items.reduce((acc, item) => {
    const value = item[key] || "Unknown";
    acc.set(value, (acc.get(value) || 0) + 1);
    return acc;
  }, new Map());
}

function getKeywords(articles) {
  const counts = new Map();
  articles.forEach((article) => {
    (article.keywords || []).forEach((keyword) => {
      counts.set(keyword, (counts.get(keyword) || 0) + 1);
    });
  });
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 14);
}

function getFilteredArticles() {
  const query = state.query.trim().toLowerCase();
  let items = state.articles.filter((article) => {
    const matchesRegion = state.region === "all" || article.region === state.region;
    const text = [
      article.title,
      article.summary,
      article.ai_summary,
      article.source,
      article.region,
      ...(article.keywords || []),
    ]
      .join(" ")
      .toLowerCase();
    return matchesRegion && (!query || text.includes(query));
  });

  items = [...items].sort((a, b) => {
    if (state.sort === "time") {
      return String(b.published_iso || "").localeCompare(String(a.published_iso || ""));
    }
    if (state.sort === "source") {
      return String(a.source || "").localeCompare(String(b.source || "")) || (b.score || 0) - (a.score || 0);
    }
    return (b.score || 0) - (a.score || 0) || String(b.published_iso || "").localeCompare(String(a.published_iso || ""));
  });

  return items;
}

function renderStats() {
  const articles = state.articles;
  const sources = countBy(articles, "source");
  const regions = countBy(articles, "region");
  const topScore = articles.reduce((max, item) => Math.max(max, Number(item.score || 0)), 0);

  els.updatedAt.textContent = state.generatedAt ? formatDate(state.generatedAt) : "等待更新";
  els.totalCount.textContent = String(articles.length);
  els.topScore.textContent = String(topScore || "--");
  els.sourceCount.textContent = String(sources.size || "--");
  els.regionCount.textContent = String(regions.size || "--");
}

function renderRegions() {
  const regions = [["all", state.articles.length], ...countBy(state.articles, "region").entries()];
  els.regionFilters.innerHTML = regions
    .map(([region, count]) => {
      const label = region === "all" ? "全部" : region;
      const active = region === state.region ? " is-active" : "";
      return `<button class="chip${active}" type="button" data-region="${escapeHtml(region)}">${escapeHtml(label)} ${count}</button>`;
    })
    .join("");
}

function renderSidebar() {
  const sources = [...countBy(state.articles, "source").entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  els.sourceList.innerHTML = sources.map(([source, count]) => `<li><span>${escapeHtml(source)}</span><strong>${count}</strong></li>`).join("");

  const keywords = getKeywords(state.articles);
  els.keywordList.innerHTML = keywords.length
    ? keywords.map(([keyword, count]) => `<span class="keyword">${escapeHtml(keyword)} · ${count}</span>`).join("")
    : `<span class="keyword">等待新闻数据</span>`;
}

function renderArticles() {
  const articles = getFilteredArticles();
  els.resultCount.textContent = `显示 ${articles.length} 条`;

  if (!articles.length) {
    els.news.innerHTML = `<div class="empty">没有匹配的新闻，换个关键词试试。</div>`;
    return;
  }

  els.news.innerHTML = articles
    .map((article) => {
      const tags = (article.keywords || []).slice(0, 5).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
      const aiSummary = article.ai_summary ? `<p class="ai-summary">${escapeHtml(article.ai_summary)}</p>` : "";
      return `
        <article class="news-card">
          <div class="card-top">
            <span class="pill source-pill">${escapeHtml(article.source || "Unknown")}</span>
            <span class="pill region-pill">${escapeHtml(article.region || "World")}</span>
            <span class="pill score-pill">热度 ${escapeHtml(article.score || 0)}</span>
          </div>
          <h3><a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">${escapeHtml(article.title || "Untitled")}</a></h3>
          ${aiSummary}
          <p class="card-summary">${escapeHtml(article.summary || "暂无摘要。")}</p>
          ${tags ? `<div class="card-tags">${tags}</div>` : ""}
          <div class="news-meta">
            <time>${escapeHtml(article.published || formatDate(article.published_iso))}</time>
            <a href="${escapeHtml(article.link || "#")}" target="_blank" rel="noreferrer">阅读原文</a>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderNotice() {
  if (!state.errors.length) {
    els.notice.hidden = true;
    els.notice.textContent = "";
    return;
  }
  els.notice.hidden = false;
  els.notice.textContent = `有 ${state.errors.length} 个新闻源暂时读取失败，其他新闻已正常显示。`;
}

function render() {
  renderStats();
  renderRegions();
  renderSidebar();
  renderNotice();
  renderArticles();
}

async function loadNews() {
  els.updateStatus.textContent = "读取中";
  els.reloadButton.disabled = true;
  try {
    const response = await fetch(`${DATA_URL}?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = normalizePayload(await response.json());
    state.articles = payload.articles;
    state.generatedAt = payload.generated_at;
    state.errors = payload.errors;
    els.updateStatus.textContent = state.articles.length ? "已更新" : "暂无数据";
    render();
  } catch (error) {
    els.updateStatus.textContent = "读取失败";
    els.notice.hidden = false;
    els.notice.textContent = "暂时无法读取新闻数据。GitHub Pages 刚开启时可能需要等 1-2 分钟。";
    els.news.innerHTML = `<div class="empty">没有加载到 dist/latest.json。请稍后刷新，或到 GitHub Actions 查看自动更新是否成功。</div>`;
  } finally {
    els.reloadButton.disabled = false;
  }
}

els.searchInput.addEventListener("input", (event) => {
  state.query = event.target.value;
  renderArticles();
});

els.sortSelect.addEventListener("change", (event) => {
  state.sort = event.target.value;
  renderArticles();
});

els.regionFilters.addEventListener("click", (event) => {
  const button = event.target.closest("[data-region]");
  if (!button) return;
  state.region = button.dataset.region;
  renderRegions();
  renderArticles();
});

els.reloadButton.addEventListener("click", loadNews);

loadNews();
