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
  $("#pageEyebrow").textContent = keepValues ? "编辑资料" : "新建研判";
  $("#pageTitle").textContent = "录入出生信息";
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
  summaryInput.placeholder = "只写可核验的事实";
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
  heroInner.append(node("p", "", "依据已核验资料生成；资料缺口与结论边界在报告中单独标注。"));
  appendPillars(heroInner, record.chart.pillars || []);
  appendReportFacts(heroInner, record);
  hero.append(heroInner);

  const index = $("#reportIndex");
  const content = $("#reportContent");
  index.replaceChildren();
  content.replaceChildren();

  if (record.quality.reasonText?.length) {
    const notice = node("div", "quality-notice");
    notice.append(node("strong", "", "资料质量提示"));
    notice.append(node("span", "", record.quality.reasonText.join(" ")));
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

  record.report.sections.forEach((section, sectionIndex) => {
    const anchor = node("a", "", section.title);
    anchor.href = `#report-${section.id}`;
    index.append(anchor);

    const sectionNode = node("section", "report-section");
    sectionNode.id = `report-${section.id}`;
    sectionNode.append(node("span", "report-section-number", String(sectionIndex + 1).padStart(2, "0")));
    sectionNode.append(node("h3", "", section.title));
    sectionNode.append(node("p", "report-summary", section.summary));
    const list = node("ul");
    section.items.forEach((item) => list.append(node("li", "", item)));
    sectionNode.append(list);
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
    label.textContent = "生成命理报告";
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
