const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  currentRecord: null,
  history: [],
  toastTimer: null,
  searchTimer: null,
};

const form = $("#birthForm");
const formView = $("#formView");
const reportView = $("#reportView");
const reportActions = $("#reportActions");
const historyList = $("#historyList");
const eventsList = $("#eventsList");
const eventsEmpty = $("#eventsEmpty");

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error("服务返回了无法识别的数据");
  }
  if (!response.ok) {
    throw new Error(payload.error || `请求失败（${response.status}）`);
  }
  return payload;
}

function showToast(message, type = "info") {
  const toast = $("#toast");
  window.clearTimeout(state.toastTimer);
  toast.textContent = message;
  toast.classList.toggle("error", type === "error");
  toast.hidden = false;
  state.toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3600);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatBirthDate(value) {
  const [calendar, date] = String(value || "").split(" ");
  const label = calendar === "lunar" ? "农历" : "阳历";
  return `${label} ${date || ""}`;
}

function genderLabel(value) {
  return { male: "男", female: "女", unknown: "未知" }[value] || "未知";
}

function closeSidebar() {
  $("#historySidebar").classList.remove("open");
  $("#sidebarScrim").hidden = true;
}

async function loadHistory(query = "") {
  try {
    const data = await api(`/api/reports?q=${encodeURIComponent(query)}`);
    state.history = data.records || [];
    renderHistory();
  } catch (error) {
    historyList.replaceChildren(node("p", "history-empty", "无法读取记录，请确认本地服务正在运行。"));
    showToast(error.message, "error");
  }
}

function renderHistory() {
  historyList.replaceChildren();
  $("#recordCount").textContent = String(state.history.length);
  if (!state.history.length) {
    historyList.append(node("p", "history-empty", "暂无查询记录\n生成第一份报告后会显示在这里。"));
    return;
  }
  state.history.forEach((record) => {
    const button = node("button", "history-item");
    button.type = "button";
    button.dataset.recordId = record.recordId;
    button.classList.toggle("active", state.currentRecord?.recordId === record.recordId);

    const head = node("div", "history-item-head");
    head.append(node("strong", "", record.name));
    head.append(node("span", "quality-mini", record.qualityLevel));

    const meta = node("div", "history-item-meta");
    meta.append(node("span", "", formatBirthDate(record.birthDateText)));
    meta.append(node("span", "", formatDateTime(record.createdAt)));
    button.append(head, meta);
    button.addEventListener("click", () => openRecord(record.recordId));
    historyList.append(button);
  });
}

async function openRecord(recordId) {
  try {
    const record = await api(`/api/reports/${encodeURIComponent(recordId)}`);
    state.currentRecord = record;
    renderReport(record);
    renderHistory();
    closeSidebar();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function setRadio(name, value) {
  const target = $(`input[name="${name}"][value="${value}"]`);
  if (target) target.checked = true;
}

function setField(id, value) {
  const field = $(`#${id}`);
  if (field) field.value = value ?? "";
}

function fillForm(input) {
  setField("name", input.name);
  setRadio("gender", input.gender);
  setRadio("calendarType", input.calendarType);
  setField("year", input.year);
  setField("month", input.month);
  setField("day", input.day);
  $("#isLeapMonth").checked = Boolean(input.isLeapMonth);
  setField("timeText", input.timeText);
  setField("birthplace", input.birthplace);
  setField("longitude", input.longitude);
  setField("latitude", input.latitude);
  setField("timezone", input.timezone || "Asia/Shanghai");
  $("#calendarVerified").checked = Boolean(input.calendarVerified);
  $("#timeStandardVerified").checked = Boolean(input.timeStandardVerified);
  eventsList.replaceChildren();
  (input.events || []).forEach(addEventRow);
  updateEventsEmpty();
  updateCalendarControls();
  $("#precisionPanel").open = Boolean(
    input.longitude !== null || input.latitude !== null || input.calendarVerified || input.timeStandardVerified
  );
}

function showForm({ keepValues = false } = {}) {
  if (!keepValues) {
    form.reset();
    setField("timezone", "Asia/Shanghai");
    eventsList.replaceChildren();
    state.currentRecord = null;
  }
  updateEventsEmpty();
  updateCalendarControls();
  formView.hidden = false;
  reportView.hidden = true;
  reportActions.hidden = true;
  $("#pageEyebrow").textContent = keepValues ? "回来补充资料" : "新建报告";
  $("#pageTitle").textContent = keepValues ? "再核对一下出生信息" : "把出生信息告诉我们";
  renderHistory();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function addEventRow(eventData = {}) {
  const row = node("div", "event-row");

  const dateLabel = node("label", "field");
  dateLabel.append(node("span", "", "日期"));
  const dateInput = node("input", "event-date");
  dateInput.placeholder = "例如 2016-05";
  dateInput.inputMode = "numeric";
  dateInput.value = eventData.date || "";
  dateLabel.append(dateInput);

  const typeLabel = node("label", "field");
  typeLabel.append(node("span", "", "类型"));
  const typeSelect = node("select", "event-type");
  ["事业", "迁移", "关系", "子女", "财务", "健康", "亲属", "教育", "其他"].forEach((item) => {
    const option = node("option", "", item);
    option.value = item;
    option.selected = item === eventData.type;
    typeSelect.append(option);
  });
  typeLabel.append(typeSelect);

  const summaryLabel = node("label", "field event-summary");
  summaryLabel.append(node("span", "", "事件说明"));
  const summaryInput = node("input", "event-summary-input");
  summaryInput.placeholder = "例如结婚、换工作、搬到西安";
  summaryInput.maxLength = 180;
  summaryInput.value = eventData.summary || "";
  summaryLabel.append(summaryInput);

  const removeButton = node("button", "remove-event", "×");
  removeButton.type = "button";
  removeButton.title = "删除事件";
  removeButton.setAttribute("aria-label", "删除此事件");
  removeButton.addEventListener("click", () => {
    row.remove();
    updateEventsEmpty();
  });

  row.append(dateLabel, typeLabel, summaryLabel, removeButton);
  eventsList.append(row);
  updateEventsEmpty();
  if (!eventData.date) dateInput.focus();
}

function updateEventsEmpty() {
  eventsEmpty.hidden = eventsList.children.length > 0;
}

function updateCalendarControls() {
  const calendar = $('input[name="calendarType"]:checked')?.value || "solar";
  $("#leapMonthRow").hidden = calendar !== "lunar";
  if (calendar !== "lunar") $("#isLeapMonth").checked = false;
}

function collectEvents() {
  return $$(".event-row", eventsList).map((row) => ({
    date: $(".event-date", row).value.trim(),
    type: $(".event-type", row).value,
    summary: $(".event-summary-input", row).value.trim(),
  }));
}

function optionalNumber(id) {
  const value = $(`#${id}`).value.trim();
  return value === "" ? null : Number(value);
}

function collectFormData() {
  return {
    name: $("#name").value.trim(),
    gender: $('input[name="gender"]:checked').value,
    calendarType: $('input[name="calendarType"]:checked').value,
    year: Number($("#year").value),
    month: Number($("#month").value),
    day: Number($("#day").value),
    isLeapMonth: $("#isLeapMonth").checked,
    timeText: $("#timeText").value.trim(),
    birthplace: $("#birthplace").value.trim(),
    longitude: optionalNumber("longitude"),
    latitude: optionalNumber("latitude"),
    timezone: $("#timezone").value.trim(),
    calendarVerified: $("#calendarVerified").checked,
    timeStandardVerified: $("#timeStandardVerified").checked,
    events: collectEvents(),
  };
}

function appendPillars(container, pillars) {
  const labels = ["年柱", "月柱", "日柱", "时柱"];
  const strip = node("div", "pillar-strip");
  labels.forEach((label, index) => {
    const cell = node("div", "pillar-cell");
    cell.append(node("span", "", label), node("strong", "", pillars[index] || "待定"));
    strip.append(cell);
  });
  container.append(strip);
}

function appendReportFacts(container, record) {
  const input = record.input;
  const facts = node("div", "report-facts");
  const calendar = input.calendarType === "lunar" ? "农历" : "阳历";
  const values = [
    `${genderLabel(input.gender)} · ${calendar}${input.year}年${input.month}月${input.day}日`,
    input.timeText || "时辰不详",
    input.birthplace || "出生地未提供",
    `换算阳历 ${input.solarDate}`,
  ];
  values.forEach((value) => facts.append(node("span", "", value)));
  container.append(facts);
}

function renderReport(record) {
  formView.hidden = true;
  reportView.hidden = false;
  reportActions.hidden = false;
  $("#pageEyebrow").textContent = "命理综合研判";
  $("#pageTitle").textContent = record.report.title;

  const hero = $("#reportHero");
  hero.replaceChildren();
  const heroInner = node("div", "report-hero-inner");
  const status = node("div", "report-status-row");
  status.append(
    node("span", "quality-badge", record.quality.level),
    node("span", "", `${record.quality.maxReportLevel} · ${formatDateTime(record.report.generatedAt)}`)
  );
  heroInner.append(status, node("h2", "", record.report.title));
  heroInner.append(node("p", "", "这不是给人生下定义，而是借一张传统命盘，陪你重新看看自己的性情、关系与选择。"));
  appendPillars(heroInner, record.chart.pillars || []);
  appendReportFacts(heroInner, record);
  hero.append(heroInner);

  const index = $("#reportIndex");
  const content = $("#reportContent");
  index.replaceChildren();
  content.replaceChildren();

  if (record.report.highlights?.length) {
    const highlights = node("section", "report-highlights");
    const heading = node("div", "highlights-heading");
    heading.append(node("span", "", "先看这四点"), node("small", "", "整份报告的核心提要"));
    highlights.append(heading);
    const grid = node("div", "highlights-grid");
    record.report.highlights.forEach((highlight, index) => {
      const item = node("div", `highlight-item tone-${index + 1}`);
      item.append(node("span", "", highlight.label), node("strong", "", highlight.value));
      grid.append(item);
    });
    highlights.append(grid);
    content.append(highlights);
  }

  if (record.quality.reasonText?.length) {
    const notice = node("div", "quality-notice");
    notice.append(node("strong", "", "有几处信息还可以慢慢补全"));
    notice.append(node("span", "", `${record.quality.reasonText.join(" ")} 这不妨碍阅读整份报告，只会让相应细节保留一些弹性。`));
    content.append(notice);
  }

  if (record.rectification.status === "candidate_only") {
    const block = node("section", "rectification-block");
    block.append(node("strong", "", "时辰反推：候选阶段"));
    block.append(node("span", "", record.rectification.disclosure));
    const candidates = node("div", "candidate-grid");
    record.rectification.candidates.forEach((candidate) => {
      const item = node("div");
      item.append(node("span", "", `${candidate.branch}时`), node("small", "", candidate.hourPillar || "待算"));
      candidates.append(item);
    });
    block.append(candidates);
    content.append(block);
  }

  if (record.report.foundation) {
    const foundation = record.report.foundation;
    const details = node("details", "foundation-panel");
    const summary = node("summary");
    const summaryCopy = node("span");
    summaryCopy.append(node("strong", "", "本次研判底稿"));
    summaryCopy.append(node("small", "", `${foundation.knowledgeRuleCount} 条规则 · ${foundation.theorySourceCount} 类理论来源 · ${foundation.appliedRules.length} 条本次采用`));
    summary.append(summaryCopy, node("em", "", "查看依据"));
    details.append(summary);
    const body = node("div", "foundation-body");
    const stats = node("div", "foundation-stats");
    [
      ["公开人物", foundation.stats.publicPeople],
      ["事件资料", foundation.stats.publicEvents],
      ["排盘快照", foundation.stats.chartSnapshots],
      ["纠偏记录", foundation.stats.correctionRecords],
    ].forEach(([label, value]) => {
      const item = node("div");
      item.append(node("strong", "", Number(value).toLocaleString("zh-CN")), node("span", "", label));
      stats.append(item);
    });
    body.append(stats);
    if (foundation.appliedRules.length) {
      const rules = node("div", "foundation-rules");
      foundation.appliedRules.forEach((rule) => {
        const item = node("p");
        item.append(node("strong", "", rule.topic), document.createTextNode(rule.summary));
        rules.append(item);
      });
      body.append(rules);
    }
    body.append(node("p", "foundation-note", foundation.note));
    details.append(body);
    content.append(details);
  }

  record.report.sections.forEach((section, sectionIndex) => {
    const anchor = node("a", "", section.title);
    anchor.href = `#report-${section.id}`;
    index.append(anchor);

    const sectionNode = node("section", "report-section");
    sectionNode.id = `report-${section.id}`;
    sectionNode.append(node("span", "report-section-number", String(sectionIndex + 1).padStart(2, "0")));
    sectionNode.append(node("h3", "", section.title));
    sectionNode.append(node("p", "report-summary", section.summary));
    if (section.technical) {
      const technical = node("p", "technical-cue");
      technical.append(node("strong", "", "专业线索"), document.createTextNode(section.technical));
      sectionNode.append(technical);
    }
    if (section.scenes?.length) {
      const story = node("div", "report-story");
      section.scenes.forEach((paragraph) => story.append(node("p", "", paragraph)));
      sectionNode.append(story);
    }
    if (section.insight) {
      const insight = node("aside", "deep-insight");
      insight.append(node("span", "", "深层洞见"), node("p", "", section.insight));
      sectionNode.append(insight);
    }
    if (section.items?.length) {
      if (section.listTitle) sectionNode.append(node("p", "report-list-title", section.listTitle));
      const list = node("ul");
      section.items.forEach((item) => list.append(node("li", "", item)));
      sectionNode.append(list);
    }
    if (section.note) {
      const note = node("p", "section-note");
      note.append(node("strong", "", "简要注释："), document.createTextNode(section.note));
      sectionNode.append(note);
    }
    content.append(sectionNode);
  });

  content.append(node("p", "disclosure", record.report.disclosure));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function submitReport(event) {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = $("#generateButton");
  const label = $(".button-label", button);
  button.disabled = true;
  label.textContent = "正在排盘…";
  try {
    const record = await api("/api/reports", {
      method: "POST",
      body: JSON.stringify(collectFormData()),
    });
    state.currentRecord = record;
    renderReport(record);
    await loadHistory($("#historySearch").value.trim());
    showToast("报告已生成并保存到查询记录");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    label.textContent = "看看我的命理报告";
  }
}

async function deleteCurrentRecord() {
  if (!state.currentRecord) return;
  const { recordId, input } = state.currentRecord;
  if (!window.confirm(`确认删除“${input.name}”的这份查询记录？`)) return;
  try {
    await api(`/api/reports/${encodeURIComponent(recordId)}`, { method: "DELETE" });
    showForm();
    await loadHistory($("#historySearch").value.trim());
    showToast("记录已删除");
  } catch (error) {
    showToast(error.message, "error");
  }
}

$("#newReportButton").addEventListener("click", () => {
  showForm();
  closeSidebar();
});

$("#editReportButton").addEventListener("click", () => {
  if (!state.currentRecord) return;
  fillForm(state.currentRecord.input);
  showForm({ keepValues: true });
});

$("#addEventButton").addEventListener("click", () => addEventRow());
$("#printButton").addEventListener("click", () => window.print());
$("#deleteButton").addEventListener("click", deleteCurrentRecord);
form.addEventListener("submit", submitReport);

$$('input[name="calendarType"]').forEach((input) => input.addEventListener("change", updateCalendarControls));

$("#historySearch").addEventListener("input", (event) => {
  window.clearTimeout(state.searchTimer);
  state.searchTimer = window.setTimeout(() => loadHistory(event.target.value.trim()), 220);
});

$("#historyToggle").addEventListener("click", () => {
  $("#historySidebar").classList.add("open");
  $("#sidebarScrim").hidden = false;
});
$("#sidebarScrim").addEventListener("click", closeSidebar);

updateCalendarControls();
updateEventsEmpty();
loadHistory();
