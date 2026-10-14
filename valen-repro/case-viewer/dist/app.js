const appState = {
  view: "benchmark",
  modality: "all",
  task: "all",
  result: "all",
  search: "",
  offset: 0,
  limit: 30,
  total: 0,
  selectedId: null,
  cases: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);
const formatPct = (value, digits = 1) => value == null ? "—" : `${(Number(value) * 100).toFixed(digits)}%`;
const formatNumber = (value) => Number(value).toLocaleString("zh-CN");
const formatBytes = (value) => value == null ? "—" : `${(Number(value) / 1024 ** 3).toFixed(1)} GB`;

async function api(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail || message; } catch {}
    throw new Error(message);
  }
  return response.json();
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 2400);
}

function verdict(caseItem) {
  if (caseItem.correct === true) return { cls: "correct", text: "预测正确" };
  if (caseItem.correct === false) return { cls: "wrong", text: "预测错误" };
  return { cls: "unscored", text: "软标签" };
}

function labelFor(item, key) {
  if (key == null) return "—";
  if (item.criteria?.[key] != null) return `${key} · ${item.criteria[key]}`;
  if (item.task === "noul") return key === "true" ? "True · 是" : "False · 否";
  return String(key);
}

async function loadSummary() {
  const data = await api("/api/summary");
  const b = data.benchmark;
  if (data.demo) {
    const notice = $("#demo-notice");
    notice.hidden = false;
    notice.textContent = "示例体验模式：以下 4 道题、概率与评分均为人工合成，仅演示界面功能，不代表 Valen 模型预测或真实 Benchmark 成绩。真实推理请按 README 安装完整版。";
    $(".hero h1").textContent = "先用 4 道合成示例，体验模型结果如何被查看。";
    $(".eyebrow").textContent = "SYNTHETIC UI DEMO";
    $(".orbit-core").textContent = "DEMO";
    $("#unload-model").disabled = true;
    document.querySelector('[data-view="benchmark"]').textContent = "示例案例";
    document.querySelectorAll('#infer-form input, #infer-form textarea, #infer-form select, #infer-form button').forEach((node) => { node.disabled = true; });
  }
  $("#metrics").innerHTML = `
    <article><span>全部问题</span><strong>${formatNumber(b.questions)}</strong><small>${formatNumber(b.records)} 条媒体记录</small></article>
    <article><span>图片问题</span><strong>${formatNumber(b.image)}</strong><small>Image</small></article>
    <article><span>视频问题</span><strong>${formatNumber(b.video)}</strong><small>Video</small></article>
    <article class="accent"><span>${data.demo ? "示例匹配率（合成）" : "硬标签准确率"}</span><strong>${formatPct(b.accuracy, 2)}</strong><small>${formatNumber(b.hard_correct)} / ${formatNumber(b.hard_scored)}</small></article>`;
  updateModelState(data.model);
}

function buildQuery() {
  const params = new URLSearchParams({
    offset: appState.offset,
    limit: appState.limit,
    modality: appState.modality,
    task: appState.task,
    result: appState.result,
    search: appState.search,
  });
  return params.toString();
}

async function loadCases({ preserveSelection = false } = {}) {
  const list = $("#case-list");
  list.innerHTML = '<div class="loading-card">正在筛选完整测试集…</div>';
  try {
    const data = await api(`/api/cases?${buildQuery()}`);
    appState.total = data.total;
    appState.cases = data.items;
    renderCaseList();
    renderPager();
    if (!preserveSelection || !data.items.some((item) => item.id === appState.selectedId)) {
      appState.selectedId = data.items[0]?.id || null;
    }
    if (appState.selectedId) await openCase(appState.selectedId, false);
    else $("#case-detail").innerHTML = '<div class="detail-empty"><span>∅</span><h3>没有匹配案例</h3><p>请放宽筛选条件后重试。</p></div>';
  } catch (error) {
    list.innerHTML = `<div class="empty-list">加载失败：${esc(error.message)}</div>`;
  }
}

function renderCaseList() {
  $("#result-count").textContent = formatNumber(appState.total);
  if (!appState.cases.length) {
    $("#case-list").innerHTML = '<div class="empty-list">没有匹配案例</div>';
    return;
  }
  $("#case-list").innerHTML = appState.cases.map((item) => {
    const v = verdict(item);
    return `<button class="case-row ${item.id === appState.selectedId ? "selected" : ""}" data-id="${esc(item.id)}">
      <div class="row-top"><div class="row-tags"><span class="tag ${esc(item.modality)}">${item.modality === "image" ? "图片" : "视频"}</span><span class="tag">${esc(item.task)}</span></div><i class="result-dot ${v.cls}" title="${v.text}"></i></div>
      <h3>${esc(item.question_short)}</h3>
      <div class="row-meta"><span>${esc(item.source)}</span><span>${esc(item.record_id)} · ${esc(item.qid)}</span></div>
    </button>`;
  }).join("");
  $$(".case-row").forEach((button) => button.addEventListener("click", () => openCase(button.dataset.id)));
}

function renderPager() {
  const page = appState.total ? Math.floor(appState.offset / appState.limit) + 1 : 0;
  const pages = Math.ceil(appState.total / appState.limit);
  $("#page-info").textContent = `${page} / ${pages || 0}`;
  $("#prev-page").disabled = appState.offset <= 0;
  $("#next-page").disabled = appState.offset + appState.limit >= appState.total;
}

async function openCase(id, scroll = true) {
  appState.selectedId = id;
  $$(".case-row").forEach((button) => button.classList.toggle("selected", button.dataset.id === id));
  const detail = $("#case-detail");
  detail.innerHTML = '<div class="detail-empty"><span>⌁</span><h3>加载案例…</h3></div>';
  try {
    const item = await api(`/api/cases/${encodeURIComponent(id)}`);
    renderCaseDetail(item);
    if (scroll && innerWidth < 821) detail.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    detail.innerHTML = `<div class="detail-empty"><h3>案例加载失败</h3><p>${esc(error.message)}</p></div>`;
  }
}

function renderProbabilities(item) {
  const keys = [...new Set([...Object.keys(item.criteria || {}), ...Object.keys(item.probabilities || {})])];
  if (item.task === "noul" && !keys.length) keys.push("true", "false");
  return keys.map((key) => {
    const probability = Number(item.probabilities?.[key] || 0);
    const classes = [key === item.predicted_key ? "predicted" : "", key === item.expected_key ? "target" : ""].filter(Boolean).join(" ");
    const label = item.criteria?.[key] ?? (key === "true" ? "是" : key === "false" ? "否" : key);
    return `<div class="prob-row ${classes}"><span class="prob-key">${esc(key)}</span><span class="prob-label">${esc(label)}</span><span class="bar"><i style="width:${Math.max(0, Math.min(100, probability * 100))}%"></i></span><span class="prob-value">${formatPct(probability, 2)}</span></div>`;
  }).join("");
}

function renderCaseDetail(item) {
  const v = verdict(item);
  const media = item.media_url
    ? item.modality === "video"
      ? `<video src="${esc(item.media_url)}" controls preload="metadata"></video>`
      : `<img src="${esc(item.media_url)}" alt="测试输入图片" loading="eager">`
    : '<div class="detail-empty"><p>文本输入，无媒体文件</p></div>';
  const metrics = Object.entries(item.metrics || {}).map(([key, value]) => `<span class="metric-chip">${esc(key)} ${typeof value === "number" ? value.toFixed(4) : esc(value)}</span>`).join("");
  $("#case-detail").innerHTML = `
    <div class="detail-media">${media}<span class="media-badge">${item.modality === "video" ? "VIDEO INPUT" : "IMAGE INPUT"}</span></div>
    <div class="detail-body">
      <div class="detail-kicker"><span class="source-name">${esc(item.source)} · ${esc(item.record_id)} · ${esc(item.qid)}</span><span class="verdict ${v.cls}">${v.text}</span></div>
      <h2>${esc(item.question)}</h2>
      ${item.state_text ? `<div class="state-note">${esc(item.state_text)}</div>` : ""}
      <div class="answer-pair"><div class="answer-box pick"><span>模型预测</span><strong>${esc(labelFor(item, item.predicted_key))}</strong></div><div class="answer-box"><span>标准答案</span><strong>${esc(labelFor(item, item.expected_key))}</strong></div></div>
      <div class="probabilities"><h3>输出概率</h3>${renderProbabilities(item)}</div>
      <div class="metrics-line">${metrics}</div>
      <details class="raw-details"><summary>查看完整输入 / 输出 JSON</summary><div class="raw-grid"><div><h4>Input</h4><pre>${esc(JSON.stringify(item.raw_input, null, 2))}</pre></div><div><h4>Output</h4><pre>${esc(JSON.stringify(item.raw_output, null, 2))}</pre></div></div></details>
    </div>`;
}

function setView(view) {
  appState.view = view;
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === view));
  $$(".view").forEach((node) => node.classList.toggle("active", node.id === `${view}-view`));
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (view === "custom") refreshModelStatus();
}

function updateModelState(status) {
  const node = $("#model-state");
  node.className = `model-state ${status.phase || ""}`;
  node.querySelector("span").textContent = status.detail || status.phase;
  const profile = $("#profile-card");
  if (profile) {
    const gpu = status.gpu;
    profile.innerHTML = `<span>当前配置</span><strong>${esc(status.dtype.toUpperCase())}${status.quant !== "none" ? ` · ${esc(status.quant.toUpperCase())}` : ""} · ${esc(status.device)}</strong><small>${gpu ? `${esc(gpu.name)} · 空闲 ${formatBytes(gpu.free_bytes)}` : "未检测到 CUDA GPU"}${status.low_media ? " · 低媒体模式" : ""}</small>`;
  }
}

async function refreshModelStatus() {
  try { updateModelState(await api("/api/model/status")); } catch {}
}

function renderCustomProbabilities(answer) {
  const probabilities = answer.probabilities || (answer.type === "noul" ? { true: answer.noul, false: 1 - answer.noul } : {});
  return Object.entries(probabilities).sort((a, b) => b[1] - a[1]).map(([key, value], index) => `
    <div class="prob-row ${index === 0 ? "predicted" : ""}"><span class="prob-key">${esc(key)}</span><span class="prob-label">${esc(answer.legend?.[key] || key)}</span><span class="bar"><i style="width:${Math.max(0, Math.min(100, Number(value) * 100))}%"></i></span><span class="prob-value">${formatPct(value, 2)}</span></div>`).join("");
}

function customAnswerLabel(answer) {
  if (answer.choice != null) return answer.legend?.[answer.choice] ? `${answer.choice} · ${answer.legend[answer.choice]}` : answer.choice;
  if (answer.score != null) return `Score ${Number(answer.score).toFixed(3)}`;
  if (answer.noul != null) return Number(answer.noul) >= .5 ? "True · 是" : "False · 否";
  return "结构化输出";
}

function renderCustomOutput(data) {
  const answers = data.result?.answers || {};
  const answer = answers.custom || Object.values(answers)[0] || {};
  const confidence = answer.confidence != null ? formatPct(answer.confidence, 2) : answer.noul != null ? formatPct(Math.max(answer.noul, 1 - answer.noul), 2) : "—";
  $("#custom-output").className = "output-result";
  $("#custom-output").innerHTML = `
    <div class="answer-hero"><span>Valen structured decision</span><strong>${esc(customAnswerLabel(answer))}</strong><small>置信度 ${confidence}</small></div>
    <div class="probabilities"><h3>概率分布</h3>${renderCustomProbabilities(answer)}</div>
    <div class="output-meta"><span class="metric-chip">推理 ${Number(data.elapsed_seconds).toFixed(2)} 秒</span><span class="metric-chip">${esc(data.profile.dtype.toUpperCase())}</span><span class="metric-chip">${esc(data.profile.device)}</span><span class="metric-chip">显存占用 ${formatBytes(data.profile.gpu?.allocated_bytes)}</span></div>
    <details class="output-json"><summary>查看完整请求与响应 JSON</summary><pre>${esc(JSON.stringify({ request: data.request, response: data.result }, null, 2))}</pre></details>`;
}

function setupEvents() {
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
  $$("#modality-filter button").forEach((button) => button.addEventListener("click", () => {
    $$("#modality-filter button").forEach((node) => node.classList.remove("selected"));
    button.classList.add("selected"); appState.modality = button.dataset.value; appState.offset = 0; loadCases();
  }));
  $("#task-filter").addEventListener("change", (event) => { appState.task = event.target.value; appState.offset = 0; loadCases(); });
  $("#result-filter").addEventListener("change", (event) => { appState.result = event.target.value; appState.offset = 0; loadCases(); });
  let searchTimer;
  $("#search").addEventListener("input", (event) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { appState.search = event.target.value; appState.offset = 0; loadCases(); }, 280); });
  $("#reset-filters").addEventListener("click", () => {
    Object.assign(appState, { modality: "all", task: "all", result: "all", search: "", offset: 0 });
    $("#search").value = ""; $("#task-filter").value = "all"; $("#result-filter").value = "all";
    $$("#modality-filter button").forEach((node) => node.classList.toggle("selected", node.dataset.value === "all")); loadCases();
  });
  $("#prev-page").addEventListener("click", () => { appState.offset = Math.max(0, appState.offset - appState.limit); loadCases(); });
  $("#next-page").addEventListener("click", () => { appState.offset += appState.limit; loadCases(); });
  $("#question-type").addEventListener("change", (event) => {
    const field = $("#criteria-field"); const area = $("#criteria"); const type = event.target.value;
    field.hidden = type === "noul";
    if (type === "score") { field.childNodes[0].nodeValue = "评分标准 "; area.value = "0: 完全不符合\n1: 少量符合\n2: 部分符合\n3: 大部分符合\n4: 完全符合"; }
    if (type === "choice") { field.childNodes[0].nodeValue = "候选选项 "; area.value = "A | 第一个选项\nB | 第二个选项\nC | 第三个选项\nD | 第四个选项"; }
  });
  $("#media-file").addEventListener("change", (event) => {
    const file = event.target.files[0]; const preview = $("#media-preview"); const prompt = $("#upload-prompt");
    if (!file) { preview.hidden = true; prompt.hidden = false; preview.innerHTML = ""; return; }
    if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
    const url = URL.createObjectURL(file); preview.dataset.url = url; prompt.hidden = true; preview.hidden = false;
    preview.innerHTML = file.type.startsWith("video/") ? `<video src="${url}" controls></video>` : `<img src="${url}" alt="上传预览">`;
  });
  $("#fill-example").addEventListener("click", () => {
    const form = $("#infer-form");
    form.elements.state_text.value = "A cat is sitting on a blue sofa near the window.";
    form.elements.instructions.value = "Which animal is sitting on the sofa?";
    $("#question-type").value = "choice";
    $("#criteria-field").hidden = false;
    $("#criteria-field").childNodes[0].nodeValue = "候选选项 ";
    $("#criteria").value = "cat | A cat\ndog | A dog\nrabbit | A rabbit\nbird | A bird";
    const mediaInput = $("#media-file");
    const preview = $("#media-preview");
    if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
    mediaInput.value = "";
    preview.dataset.url = "";
    preview.innerHTML = "";
    preview.hidden = true;
    $("#upload-prompt").hidden = false;
    toast("示例已填入，可以直接运行推理");
  });
  $("#infer-form").addEventListener("submit", runInference);
  $("#unload-model").addEventListener("click", async () => {
    try { updateModelState(await api("/api/model/unload", { method: "POST" })); toast("模型已卸载，显存已释放"); } catch (error) { toast(error.message); }
  });
}

async function runInference(event) {
  event.preventDefault();
  const button = $("#run-inference");
  button.disabled = true; button.querySelector("span").textContent = "正在推理…";
  $("#custom-output").className = "running-view";
  $("#custom-output").innerHTML = '<div class="spinner"></div><h3>模型正在思考</h3><p>首次运行包含模型加载时间，请稍候。</p>';
  try {
    const data = await api("/api/infer", { method: "POST", body: new FormData(event.currentTarget) });
    renderCustomOutput(data); updateModelState(data.profile);
  } catch (error) {
    $("#custom-output").className = "output-result";
    $("#custom-output").innerHTML = `<div class="error-card"><h3>推理失败</h3><p>${esc(error.message)}</p></div>`;
    refreshModelStatus();
  } finally {
    button.disabled = false; button.querySelector("span").textContent = "运行本地推理";
  }
}

async function loadLatency() {
  try {
    const data = await api("/api/latency");
    let html = `<h2>不同模态的平均推理耗时</h2><p>${esc(data.reason || "暂无实测结果")}</p>`;
    if (data.available) {
      const report = data.report;
      const profile = report.profile;
      const labels = { text: "文本", image: "图片", video: "视频" };
      const rows = Object.entries(report.modalities).map(([key, value]) => `<tr><th scope="row">${esc(labels[key] || key)}</th><td><strong>${Number(value.mean_seconds).toFixed(3)} 秒</strong></td><td>${Number(value.median_seconds).toFixed(3)} 秒</td><td>${Number(value.min_seconds).toFixed(3)}–${Number(value.max_seconds).toFixed(3)} 秒</td><td>${value.distinct_inputs} 个输入 × ${value.sample_count / value.distinct_inputs} 轮</td><td>${Number(value.warmup_inference_seconds).toFixed(3)} 秒</td></tr>`).join("");
      html = `<h2>不同模态的平均推理耗时 <small>本机小范围实测</small></h2><p>${esc(profile.gpu)} · ${esc(profile.dtype.toUpperCase())} / ${esc(profile.quant)} · ${esc(report.measured_at.replace("T", " "))}</p><div class="latency-scroll"><table><thead><tr><th>模态</th><th>预热后平均</th><th>中位数</th><th>最小–最大</th><th>采样次数</th><th>首次 / 预热请求</th></tr></thead><tbody>${rows}</tbody></table></div><p>单次请求只包含一道 Choice 问题；每种模态先预热 1 次，不计入平均值。包含媒体预处理与 GPU 推理，不包含模型加载、排队、上传和网络耗时。模型加载 ${Number(profile.load_seconds || 0).toFixed(2)} 秒，单独统计。</p><p>文本、图片和视频的输入长度与复杂度不同；小样本结果仅供当前机器参考，不代表完整 Benchmark 平均速度。${data.matches_current_profile ? "" : "当前启动配置与测试配置不同，请以报告中的配置为准。"} <a href="/api/latency" target="_blank" rel="noopener">查看逐次原始记录</a></p>`;
    }
    $$(".latency-panel").forEach((node) => { node.innerHTML = html; });
  } catch (error) {
    $$(".latency-panel").forEach((node) => { node.textContent = `耗时报告读取失败：${error.message}`; });
  }
}

async function init() {
  setupEvents();
  try { await Promise.all([loadSummary(), loadCases(), loadLatency()]); }
  catch (error) { toast(`初始化失败：${error.message}`); }
  setInterval(refreshModelStatus, 3500);
}

init();
