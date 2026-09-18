const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  currentRecord: null,
  history: [],
  toastTimer: null,
  searchTimer: null,
  placeTimer: null,
  lunarCache: new Map(),
  lunarRequest: 0,
};

const form = $("#birthForm");
const formView = $("#formView");
const reportView = $("#reportView");
const reportActions = $("#reportActions");
const historyList = $("#historyList");
const eventsList = $("#eventsList");
const eventsEmpty = $("#eventsEmpty");
const stageHeader = $(".stage-header");
const earthlyBranches = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"];
const enhancedSelects = new WeakMap();
let activeChoiceSelect = null;
let activeWheel = null;
const WHEEL_ITEM_HEIGHT = 44;

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

function appendOption(select, value, label) {
  const option = node("option", "", label);
  option.value = String(value);
  select.append(option);
}

function populateDateSelects() {
  const year = $("#year");
  const month = $("#month");
  const currentYear = new Date().getFullYear();
  for (let value = currentYear; value >= 1000; value -= 1) appendOption(year, value, `${value} 年`);
  for (let value = 1; value <= 12; value += 1) appendOption(month, value, `${value} 月`);
  updateDayOptions();
}

function populateTimeSelects() {
  for (let value = 0; value < 24; value += 1) {
    appendOption($("#exactHour"), String(value).padStart(2, "0"), `${String(value).padStart(2, "0")} 时`);
  }
  for (let value = 0; value < 60; value += 1) {
    appendOption($("#exactMinute"), String(value).padStart(2, "0"), `${String(value).padStart(2, "0")} 分`);
  }
}

async function loadLunarCalendar(year) {
  if (!year) return null;
  if (!state.lunarCache.has(year)) {
    state.lunarCache.set(year, api(`/api/calendar/lunar?year=${encodeURIComponent(year)}`));
  }
  try {
    return await state.lunarCache.get(year);
  } catch (error) {
    state.lunarCache.delete(year);
    throw error;
  }
}

async function updateDayOptions() {
  const day = $("#day");
  const previous = day.value;
  const year = Number($("#year").value);
  const month = Number($("#month").value);
  const calendar = $('input[name="calendarType"]:checked')?.value || "solar";
  const requestId = ++state.lunarRequest;
  let maxDay = year && month ? new Date(year, month, 0).getDate() : 31;
  if (calendar === "lunar") {
    maxDay = 30;
    if (year && month) {
      try {
        const metadata = await loadLunarCalendar(year);
        if (requestId !== state.lunarRequest) return;
        const leapMonth = Number(metadata?.leapMonth || 0);
        const leapAvailable = leapMonth === month;
        $("#leapMonthRow").hidden = !leapAvailable;
        if (!leapAvailable) $("#isLeapMonth").checked = false;
        const selected = metadata?.months?.find((item) => (
          Number(item.month) === month && Boolean(item.isLeap) === $("#isLeapMonth").checked
        ));
        if (selected) maxDay = Number(selected.days);
      } catch (error) {
        showToast(error.message, "error");
      }
    } else {
      $("#leapMonthRow").hidden = true;
    }
  }
  day.replaceChildren();
  appendOption(day, "", "日期");
  for (let value = 1; value <= maxDay; value += 1) appendOption(day, value, `${value} 日`);
  if (Number(previous) <= maxDay) day.value = previous;
  syncChoiceTrigger(day);
}

function syncChoiceTrigger(select) {
  const enhancement = enhancedSelects.get(select);
  if (!enhancement) return;
  const selected = select.options[select.selectedIndex];
  enhancement.label.textContent = selected?.textContent || select.getAttribute("aria-label") || "请选择";
  enhancement.trigger.classList.toggle("has-value", Boolean(select.value));
}

function enhanceSelect(select) {
  if (!select || enhancedSelects.has(select)) return;
  select.classList.add("choice-native-select");
  select.tabIndex = -1;
  const trigger = node("button", "choice-trigger");
  trigger.type = "button";
  trigger.setAttribute("aria-haspopup", "dialog");
  trigger.setAttribute("aria-label", select.dataset.choiceTitle || select.getAttribute("aria-label") || "打开选择页");
  const label = node("span");
  trigger.append(label, node("b", "", "⌄"));
  select.insertAdjacentElement("afterend", trigger);
  enhancedSelects.set(select, { trigger, label });
  select.addEventListener("change", () => syncChoiceTrigger(select));
  trigger.addEventListener("click", () => openChoiceDialog(select));
  syncChoiceTrigger(select);
}

function renderChoiceOptions(query = "") {
  const container = $("#choiceOptions");
  container.replaceChildren();
  if (!activeChoiceSelect) return;
  const normalizedQuery = query.trim().toLowerCase();
  [...activeChoiceSelect.options]
    .filter((option) => option.value && (!normalizedQuery || option.textContent.toLowerCase().includes(normalizedQuery)))
    .forEach((option) => {
      const button = node("button", "choice-option", option.textContent);
      button.type = "button";
      button.classList.toggle("selected", option.value === activeChoiceSelect.value);
      button.addEventListener("click", () => {
        activeChoiceSelect.value = option.value;
        activeChoiceSelect.dispatchEvent(new Event("change", { bubbles: true }));
        $("#choiceDialog").close();
      });
      container.append(button);
    });
}

function wheelOptions(select, override = null) {
  if (override) return override;
  return [...select.options]
    .filter((option) => option.value)
    .map((option) => ({ value: option.value, label: option.textContent }));
}

function defaultWheelValue(select, options) {
  if (select.value) return select.value;
  const now = new Date();
  const defaults = {
    year: String(now.getFullYear() - 30),
    month: String(now.getMonth() + 1),
    day: String(now.getDate()),
    exactHour: "12",
    exactMinute: "00",
  };
  const candidate = defaults[select.id];
  return options.some((option) => option.value === candidate) ? candidate : options[0]?.value || "";
}

function setWheelSelection(scroller, value) {
  const buttons = $$(".wheel-option", scroller);
  buttons.forEach((button) => {
    const selected = button.dataset.value === String(value);
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-selected", String(selected));
  });
}

function buildWheelColumn(select, label, override = null) {
  const options = wheelOptions(select, override);
  const column = node("section", "wheel-column");
  column.dataset.selectId = select.id;
  column.append(node("span", "wheel-column-label", label));
  const frame = node("div", "wheel-frame");
  const scroller = node("div", "wheel-scroller");
  scroller.setAttribute("role", "listbox");
  scroller.setAttribute("aria-label", select.getAttribute("aria-label") || label);
  const value = activeWheel.values[select.id] || defaultWheelValue(select, options);
  activeWheel.values[select.id] = value;
  options.forEach((option) => {
    const button = node("button", "wheel-option", option.label);
    button.type = "button";
    button.dataset.value = option.value;
    button.setAttribute("role", "option");
    button.addEventListener("click", () => {
      const index = options.findIndex((item) => item.value === option.value);
      activeWheel.values[select.id] = option.value;
      setWheelSelection(scroller, option.value);
      if (select.id === "year" || select.id === "month") refreshWheelDayColumn();
      scroller.scrollTo({ top: index * WHEEL_ITEM_HEIGHT, behavior: "smooth" });
    });
    scroller.append(button);
  });
  frame.append(node("div", "wheel-focus-line"), scroller);
  column.append(frame);
  activeWheel.columns.set(select.id, { select, label, column, scroller, options });
  setWheelSelection(scroller, value);
  let scrollTimer;
  scroller.addEventListener("scroll", () => {
    if (scroller.dataset.ready !== "true" || !activeWheel) return;
    const index = Math.max(0, Math.min(options.length - 1, Math.round(scroller.scrollTop / WHEEL_ITEM_HEIGHT)));
    const selected = options[index];
    if (!selected) return;
    activeWheel.values[select.id] = selected.value;
    setWheelSelection(scroller, selected.value);
    window.clearTimeout(scrollTimer);
    scrollTimer = window.setTimeout(() => {
      if (!activeWheel) return;
      scroller.scrollTo({ top: index * WHEEL_ITEM_HEIGHT, behavior: "smooth" });
      if (select.id === "year" || select.id === "month") refreshWheelDayColumn();
    }, 90);
  });
  window.requestAnimationFrame(() => {
    const index = Math.max(0, options.findIndex((option) => option.value === value));
    scroller.style.scrollBehavior = "auto";
    scroller.scrollTop = index * WHEEL_ITEM_HEIGHT;
    window.requestAnimationFrame(() => {
      scroller.style.removeProperty("scroll-behavior");
      scroller.dataset.ready = "true";
    });
  });
  return column;
}

async function wheelDayOptions() {
  const year = Number(activeWheel?.values.year);
  const month = Number(activeWheel?.values.month);
  const calendar = $('input[name="calendarType"]:checked')?.value || "solar";
  let maxDay = year && month ? new Date(year, month, 0).getDate() : 31;
  if (calendar === "lunar" && year && month) {
    try {
      const metadata = await loadLunarCalendar(year);
      const selected = metadata?.months?.find((item) => (
        Number(item.month) === month && Boolean(item.isLeap) === $("#isLeapMonth").checked
      ));
      if (selected) maxDay = Number(selected.days);
    } catch (error) {
      showToast(error.message, "error");
    }
  }
  return Array.from({ length: maxDay }, (_, index) => ({ value: String(index + 1), label: `${index + 1} 日` }));
}

async function refreshWheelDayColumn() {
  if (activeWheel?.type !== "date") return;
  const current = activeWheel.columns.get("day");
  if (!current) return;
  const options = await wheelDayOptions();
  if (activeWheel?.type !== "date") return;
  if (!options.some((option) => option.value === activeWheel.values.day)) {
    activeWheel.values.day = options.at(-1)?.value || "1";
  }
  const replacement = buildWheelColumn($("#day"), "日", options);
  current.column.replaceWith(replacement);
}

async function applyWheelSelection() {
  if (!activeWheel) return;
  if (activeWheel.type === "date") {
    $("#year").value = activeWheel.values.year;
    $("#month").value = activeWheel.values.month;
    await updateDayOptions();
    $("#day").value = activeWheel.values.day;
    [$("#year"), $("#month"), $("#day")].forEach(syncChoiceTrigger);
  } else {
    $("#exactHour").value = activeWheel.values.exactHour;
    $("#exactMinute").value = activeWheel.values.exactMinute;
    [$("#exactHour"), $("#exactMinute")].forEach(syncChoiceTrigger);
    updateTimeControls();
  }
  $("#choiceDialog").close();
}

async function openWheelDialog(type) {
  activeChoiceSelect = null;
  activeWheel = { type, values: {}, columns: new Map() };
  const dialog = $("#choiceDialog");
  dialog.classList.add("wheel-mode");
  $("#choiceDialogSearch").hidden = true;
  $("#choiceDialogFooter").hidden = false;
  $("#choiceDialogTitle").textContent = type === "date" ? "滑动选择出生日期" : "滑动选择出生时刻";
  const container = $("#choiceOptions");
  container.className = "choice-options wheel-picker";
  container.replaceChildren();
  const definitions = type === "date"
    ? [[$("#year"), "年"], [$("#month"), "月"], [$("#day"), "日"]]
    : [[$("#exactHour"), "时"], [$("#exactMinute"), "分"]];
  definitions.forEach(([select, label]) => container.append(buildWheelColumn(select, label)));
  dialog.showModal();
  if (type === "date") await refreshWheelDayColumn();
}

function openChoiceDialog(select) {
  if (["year", "month", "day"].includes(select.id)) {
    openWheelDialog("date");
    return;
  }
  if (["exactHour", "exactMinute"].includes(select.id)) {
    openWheelDialog("time");
    return;
  }
  activeChoiceSelect = select;
  activeWheel = null;
  const search = $("#choiceDialogSearch");
  const searchInput = $("#choiceSearchInput");
  const dialog = $("#choiceDialog");
  dialog.classList.remove("wheel-mode");
  $("#choiceDialogFooter").hidden = true;
  $("#choiceOptions").className = "choice-options";
  $("#choiceDialogTitle").textContent = select.dataset.choiceTitle || select.getAttribute("aria-label") || "请选择";
  search.hidden = select.options.length <= 40;
  searchInput.value = "";
  renderChoiceOptions();
  dialog.showModal();
  window.setTimeout(() => {
    const selected = $(".choice-option.selected", dialog);
    if (selected) selected.scrollIntoView({ block: "center" });
    if (!search.hidden) searchInput.focus();
  }, 0);
}

function syncAllChoiceTriggers() {
  $$("select.choice-native-select").forEach(syncChoiceTrigger);
}

function genderLabel(value) {
  return { male: "男", female: "女", unknown: "未知" }[value] || "未知";
}

function reportDisplayText(value) {
  return String(value || "")
    .replaceAll("校准四柱报告", "四柱精研报告")
    .replaceAll("暂定四柱报告", "四柱综合报告")
    .replaceAll("三柱情境报告", "三柱综合报告")
    .replaceAll("基础三柱报告", "基础研判报告")
    .replace(/当前资料等级为 L[1-4][，,]?/g, "")
    .replace(/资料等级 L[1-4][；;,]?/g, "");
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
    renderQuickPlaces();
  } catch (error) {
    historyList.replaceChildren(node("p", "history-empty", "无法读取记录，请确认本地服务正在运行。"));
    showToast(error.message, "error");
  }
}

function renderQuickPlaces() {
  const datalist = $("#birthplaceOptions");
  const container = $("#quickPlaceOptions");
  const label = $("#quickPlaceLabel");
  const places = [...new Set(state.history.map((record) => record.birthplace).filter(Boolean))];
  datalist.replaceChildren();
  container.replaceChildren();
  places.forEach((place) => appendOption(datalist, place, place));
  places.slice(0, 3).forEach((place) => {
    const button = node("button", "quick-place-button", place);
    button.type = "button";
    button.title = place;
    button.addEventListener("click", () => {
      setField("birthplace", place);
      resolvePlace();
    });
    container.append(button);
  });
  label.hidden = places.length === 0;
}

async function resolvePlace({ quiet = false } = {}) {
  const query = $("#birthplace").value.trim();
  const status = $("#placeResolution");
  if (!query) {
    status.hidden = true;
    status.textContent = "";
    return null;
  }
  try {
    const data = await api(`/api/places?q=${encodeURIComponent(query)}`);
    if (!data.match) {
      status.textContent = "地点已记录；如需真太阳时，可在精度设置中补充坐标。";
      status.classList.remove("resolved");
      status.hidden = false;
      return null;
    }
    setField("longitude", data.match.longitude);
    setField("latitude", data.match.latitude);
    setField("timezone", data.match.timezone);
    status.textContent = `已识别 ${data.match.label}，将自动校正经度与时区`;
    status.classList.add("resolved");
    status.hidden = false;
    return data.match;
  } catch (error) {
    if (!quiet) showToast(error.message, "error");
    return null;
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
    const item = node("div", "history-item");
    item.dataset.recordId = record.recordId;
    item.classList.toggle("active", state.currentRecord?.recordId === record.recordId);

    const openButton = node("button", "history-item-open");
    openButton.type = "button";

    const head = node("div", "history-item-head");
    head.append(node("strong", "", record.name));

    const meta = node("div", "history-item-meta");
    meta.append(node("span", "", formatBirthDate(record.birthDateText)));
    meta.append(node("span", "", formatDateTime(record.createdAt)));
    openButton.append(head, meta);
    openButton.addEventListener("click", () => openRecord(record.recordId));

    const deleteButton = node("button", "history-item-delete", "删");
    deleteButton.type = "button";
    deleteButton.setAttribute("aria-label", `删除${record.name}的查询记录`);
    deleteButton.title = "删除这条记录";
    deleteButton.addEventListener("click", () => deleteHistoryRecord(record));
    item.append(openButton, deleteButton);
    historyList.append(item);
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
  if (field) {
    field.value = value ?? "";
    if (field.matches("select")) syncChoiceTrigger(field);
  }
}

function branchFromHour(hour) {
  return earthlyBranches[Math.floor(((hour + 1) % 24) / 2)];
}

function updateTimeControls() {
  const mode = $('input[name="timeMode"]:checked')?.value || "exact";
  $("#exactTimeField").hidden = mode !== "exact";
  $("#branchTimeField").hidden = mode !== "branch";
  $("#unknownTimeHint").hidden = mode !== "unknown";
  const exactTime = $("#exactHour").value && $("#exactMinute").value
    ? `${$("#exactHour").value}:${$("#exactMinute").value}`
    : "";
  $("#exactTime").value = exactTime;
  $("#timeText").value = mode === "exact"
    ? exactTime
    : mode === "branch"
      ? $("#timeBranch").value
      : "";
}

function fillTimeControls(value) {
  const text = String(value || "").trim();
  const exact = text.match(/(?:^|\D)([01]?\d|2[0-3]):([0-5]\d)(?:\D|$)/);
  const branch = earthlyBranches.find((item) => text.includes(`${item}时`));
  const approximateHour = text.match(/(?:^|\D)([01]?\d|2[0-3])(?:点|时)/);
  $("#exactHour").value = "";
  $("#exactMinute").value = "";
  $("#timeBranch").value = "";
  if (exact) {
    setRadio("timeMode", "exact");
    $("#exactHour").value = exact[1].padStart(2, "0");
    $("#exactMinute").value = exact[2];
  } else if (branch || approximateHour) {
    setRadio("timeMode", "branch");
    $("#timeBranch").value = `${branch || branchFromHour(Number(approximateHour[1]))}时`;
  } else {
    setRadio("timeMode", "unknown");
  }
  syncAllChoiceTriggers();
  updateTimeControls();
}

function fillForm(input) {
  setField("name", input.name);
  setRadio("gender", input.gender);
  setRadio("calendarType", input.calendarType);
  setField("year", input.year);
  setField("month", input.month);
  setField("day", input.day);
  $("#isLeapMonth").checked = Boolean(input.isLeapMonth);
  fillTimeControls(input.timeText);
  setField("birthplace", input.birthplace);
  setField("longitude", input.longitude);
  setField("latitude", input.latitude);
  setField("timezone", input.timezone || "Asia/Shanghai");
  const placeStatus = $("#placeResolution");
  if (input.geoSource) {
    placeStatus.textContent = `已识别 ${input.resolvedPlace || input.birthplace}，经纬度与时区已带入`;
    placeStatus.classList.add("resolved");
    placeStatus.hidden = false;
  }
  $("#calendarVerified").checked = Boolean(input.calendarVerified);
  $("#timeStandardVerified").checked = Boolean(input.timeStandardVerified);
  eventsList.replaceChildren();
  $("#eventPanel").open = false;
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
    $("#eventPanel").open = false;
    $("#precisionPanel").open = false;
    state.currentRecord = null;
    $("#placeResolution").hidden = true;
    $("#formErrorSummary").hidden = true;
  }
  updateEventsEmpty();
  updateCalendarControls();
  updateTimeControls();
  syncAllChoiceTriggers();
  formView.hidden = false;
  reportView.hidden = true;
  reportActions.hidden = true;
  $("#pageEyebrow").textContent = "参天·东方智慧命理研判";
  $("#pageTitle").textContent = "建立命盘，信息越准，研判越稳";
  stageHeader.classList.add("form-mode");
  stageHeader.classList.remove("report-mode");
  renderHistory();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function addEventRow(eventData = {}) {
  $("#eventPanel").open = true;
  const row = node("div", "event-row");

  const dateLabel = node("label", "field");
  dateLabel.append(node("span", "", "日期"));
  const dateInput = node("input", "event-date");
  dateInput.type = "month";
  dateInput.value = eventData.date || "";
  dateLabel.append(dateInput);

  const typeLabel = node("label", "field");
  typeLabel.append(node("span", "", "类型"));
  const typeSelect = node("select", "event-type");
  typeSelect.dataset.choiceTitle = "选择经历类型";
  typeSelect.setAttribute("aria-label", "经历类型");
  ["事业", "迁移", "关系", "子女", "财务", "健康", "亲属", "教育", "其他"].forEach((item) => {
    const option = node("option", "", item);
    option.value = item;
    option.selected = item === eventData.type;
    typeSelect.append(option);
  });
  typeLabel.append(typeSelect);
  enhanceSelect(typeSelect);

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
  const count = eventsList.children.length;
  eventsEmpty.hidden = count > 0;
  $("#eventCount").textContent = `${count} 条`;
}

function updateCalendarControls() {
  const calendar = $('input[name="calendarType"]:checked')?.value || "solar";
  $("#leapMonthRow").hidden = true;
  if (calendar !== "lunar") $("#isLeapMonth").checked = false;
  updateDayOptions();
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

function appendPillars(container, pillars, trueSolarVariant = null) {
  const labels = ["年柱", "月柱", "日柱", "时柱"];
  const strip = node("div", "pillar-strip");
  labels.forEach((label, index) => {
    const cell = node("div", "pillar-cell");
    cell.append(node("span", "", label), node("strong", "", pillars[index] || "待定"));
    if (index === 3 && trueSolarVariant?.changesHourPillar) {
      cell.append(node("small", "", `真太阳 ${trueSolarVariant.hourPillar}`));
      cell.classList.add("has-variant");
    }
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
  if (input.geoSource) values.push(`${input.resolvedPlace || "出生地"}坐标已解析`);
  if (record.chart.trueSolarVariant) {
    values.push(`真太阳时校正 ${record.chart.trueSolarVariant.correctionMinutes} 分钟`);
  }
  values.forEach((value) => facts.append(node("span", "", value)));
  container.append(facts);
}

function pickUniqueVisual(library, categoryNames, seed, usedSources) {
  const categories = Array.isArray(categoryNames) ? categoryNames : [categoryNames];
  for (let attempt = 0; attempt < library.entries.length; attempt += 1) {
    const attemptSeed = `${seed}:unique:${attempt}`;
    const visual = categories.length === 1
      ? library.pick(categories[0], attemptSeed)
      : library.pickAny(categories, attemptSeed);
    if (!usedSources.has(visual.src)) {
      usedSources.add(visual.src);
      return visual;
    }
  }
  const fallback = library.entries.find((entry) => categories.includes(entry.category) && !usedSources.has(entry.src));
  if (fallback) usedSources.add(fallback.src);
  return fallback || library.pick(categories[0], seed);
}

function setReadMode(mode) {
  const content = $("#reportContent");
  const layout = $(".report-layout");
  content.dataset.readMode = mode;
  layout.dataset.readMode = mode;
  $$(".reading-mode-button", content).forEach((button) => {
    const active = button.dataset.mode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  window.localStorage.setItem("mingliReadMode", mode);
  updateReadingProgress();
}

function appendReadingModes(container) {
  const modes = node("div", "reading-modes");
  modes.setAttribute("role", "tablist");
  [["summary", "纲要"], ["focused", "精读"], ["full", "全文"]].forEach(([mode, label]) => {
    const button = node("button", "reading-mode-button", label);
    button.type = "button";
    button.dataset.mode = mode;
    button.setAttribute("role", "tab");
    button.addEventListener("click", () => setReadMode(mode));
    modes.append(button);
  });
  container.append(modes);
}

function appendClaims(container, claims) {
  if (!claims?.length) return;
  const panel = node("section", "report-claims");
  const heading = node("div", "report-claims-heading");
  heading.append(node("span", "", "核心判断与依据"), node("small", "", "结论、证据、反证与行动放在一起看"));
  panel.append(heading);
  const list = node("div", "report-claims-list");
  claims.forEach((claim, index) => {
    const item = node("details", "report-claim");
    if (index === 0) item.open = true;
    const summary = node("summary");
    const copy = node("span");
    copy.append(node("small", "", claim.category), node("strong", "", claim.claim));
    summary.append(copy, node("em", "", claim.confidence));
    item.append(summary);
    const body = node("div", "report-claim-body");
    const evidence = node("p");
    evidence.append(node("b", "", "支持依据"), document.createTextNode(claim.evidence.join("；")));
    const counter = node("p");
    counter.append(node("b", "", "保留条件"), document.createTextNode(claim.counterEvidence.join("；")));
    const action = node("p");
    action.append(node("b", "", "行动建议"), document.createTextNode(claim.action));
    body.append(evidence, counter, action);
    item.append(body);
    list.append(item);
  });
  panel.append(list);
  container.append(panel);
}

function appendLuckCycles(container, luckCycles) {
  if (!luckCycles?.cycles?.length) return;
  const panel = node("details", "luck-cycle-panel");
  const age = luckCycles.startAge;
  const summary = node("summary");
  summary.append(
    node("strong", "", "大运时间轴"),
    node("span", "", `${luckCycles.direction} · 约 ${age.years} 岁 ${age.months} 个月起运`)
  );
  panel.append(summary);
  const track = node("div", "luck-cycle-track");
  luckCycles.cycles.forEach((cycle) => {
    const item = node("div", cycle === luckCycles.current ? "current" : "");
    item.append(node("strong", "", cycle.ganZhi), node("span", "", `${cycle.startYear}—${cycle.endYear}`));
    track.append(item);
  });
  panel.append(track, node("p", "", `${luckCycles.method}。时间轴用于观察阶段背景，不把单一干支解释为必然事件。`));
  container.append(panel);
}

function appendTechnicalSnapshot(container, record) {
  const details = record.chart.details || {};
  const hidden = details.hidden_stems || {};
  const naYin = details.na_yin || {};
  const labels = { year: "年柱", month: "月柱", day: "日柱", hour: "时柱" };
  const panel = node("details", "technical-snapshot-panel");
  const summary = node("summary");
  summary.append(node("strong", "", "专业计算底稿"), node("span", "", `模型 ${record.report.modelVersion || record.modelVersion || "legacy"}`));
  panel.append(summary);
  const grid = node("div", "technical-snapshot-grid");
  const rows = [
    ["四柱", (record.chart.pillars || []).join(" · ")],
    ["月令与节气", `${record.chart.month_command || "待定"} · ${(record.chart.climate_tags || []).join("、") || "待复核"}`],
    ["藏干", Object.entries(hidden).map(([key, value]) => `${labels[key] || key} ${Array.isArray(value) ? value.join("/") : value}`).join("；") || "时柱待补"],
    ["纳音", Object.entries(naYin).map(([key, value]) => `${labels[key] || key} ${value}`).join("；") || "待补"],
    ["命宫 / 身宫", `${details.ming_gong || "待时柱"} / ${details.shen_gong || "待时柱"}`],
    ["地理校正", record.chart.trueSolarVariant
      ? `校正 ${record.chart.trueSolarVariant.correctionMinutes} 分钟，时柱 ${record.chart.trueSolarVariant.hourPillar}`
      : "当前未形成真太阳时备选"],
  ];
  rows.forEach(([label, value]) => {
    const item = node("div");
    item.append(node("span", "", label), node("strong", "", value));
    grid.append(item);
  });
  panel.append(grid);
  container.append(panel);
}

function updateReadingProgress() {
  if (reportView.hidden) return;
  const top = reportView.offsetTop;
  const height = Math.max(reportView.offsetHeight - window.innerHeight, 1);
  const progress = Math.max(0, Math.min(1, (window.scrollY - top) / height));
  $("#readingProgress").style.width = `${Math.round(progress * 100)}%`;
  const sections = $$(".report-section:not([hidden])");
  let activeId = "";
  sections.forEach((section) => {
    if (section.getBoundingClientRect().top <= 150) activeId = section.id;
  });
  $$("#reportIndex a").forEach((anchor) => anchor.classList.toggle("active", anchor.hash === `#${activeId}`));
}

function renderReport(record) {
  formView.hidden = true;
  reportView.hidden = false;
  reportActions.hidden = false;
  stageHeader.classList.remove("form-mode");
  stageHeader.classList.add("report-mode");
  $("#pageEyebrow").textContent = "";
  $("#pageTitle").textContent = "参天·东方智慧命理研判";
  const imageSeed = record.recordId || `${record.input.name}:${record.input.solarDate}:${record.report.generatedAt}`;
  const imageLibrary = globalThis.MingliImages;
  const usedImageSources = new Set();

  const hero = $("#reportHero");
  hero.replaceChildren();
  if (imageLibrary) {
    const heroVisual = pickUniqueVisual(imageLibrary, ["palace", "cosmos", "mountains", "elements"], `${imageSeed}:hero`, usedImageSources);
    hero.style.setProperty("--report-hero-image", `url("${heroVisual.src}")`);
    hero.style.setProperty("--report-hero-position", heroVisual.position);
    hero.dataset.imageId = heroVisual.id;
  }
  const heroInner = node("div", "report-hero-inner");
  const status = node("div", "report-status-row");
  status.append(node("span", "", `${reportDisplayText(record.quality.maxReportLevel) || "命理综合报告"} · ${formatDateTime(record.report.generatedAt)}`));
  heroInner.append(status, node("h2", "", record.report.title));
  heroInner.append(node("p", "", "这不是给人生下定义，而是借一张传统命盘，陪你重新看看自己的性情、关系与选择。"));
  appendPillars(heroInner, record.chart.pillars || [], record.chart.trueSolarVariant);
  appendReportFacts(heroInner, record);
  hero.append(heroInner);

  const index = $("#reportIndex");
  const content = $("#reportContent");
  let foundationPanel = null;
  index.replaceChildren();
  content.replaceChildren();
  appendReadingModes(content);

  if (record.report.highlights?.length) {
    const highlights = node("section", "report-highlights");
    const heading = node("div", "highlights-heading");
    heading.append(node("span", "", "命盘四纲"), node("small", "", "全篇研判的核心纲领"));
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

  appendClaims(content, record.report.claims);
  appendLuckCycles(content, record.report.luckCycles || record.chart.luckCycles);
  appendTechnicalSnapshot(content, record);

  if (record.quality.reasonText?.length) {
    const notice = node("div", "quality-notice");
    notice.append(node("strong", "", "有几处信息还可以慢慢补全"));
    notice.append(node("span", "", `${record.quality.reasonText.join(" ")} 这不妨碍阅读整份报告，只会让相应细节保留一些弹性。`));
    content.append(notice);
  }

  if (record.rectification.status === "candidate_only") {
    const block = node("section", "rectification-block");
    block.append(node("strong", "", "时辰反推：实验性候选排序"));
    block.append(node("span", "", record.rectification.disclosure));
    const candidates = node("div", "candidate-grid");
    record.rectification.candidates.forEach((candidate) => {
      const item = node("div");
      const score = candidate.matchScore === undefined ? "未评分" : `匹配 ${candidate.matchScore}`;
      item.append(
        node("span", "", `${String(candidate.rank || "").padStart(2, "0")} · ${candidate.branch}时`),
        node("small", "", `${candidate.hourPillar || "待算"} · ${score}`)
      );
      if (candidate.supportingEvents?.length) {
        item.title = candidate.supportingEvents
          .map((event) => `${event.date} ${event.type}：${event.reasons.join("、")}`)
          .join("\n");
      }
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
    const coverage = foundation.coverage || {};
    const validation = foundation.validation || {};
    const birthRange = coverage.birthStartYear && coverage.birthEndYear
      ? `${coverage.birthStartYear}—${coverage.birthEndYear} 年`
      : "年代持续扩充";
    summaryCopy.append(node("strong", "", "研判模型"));
    summaryCopy.append(node("small", "", `${Number(foundation.stats.publicPeople).toLocaleString("zh-CN")} 位公开人物 · ${Number(coverage.timedBirthRecords || 0).toLocaleString("zh-CN")} 条含时刻 · 研究验证中`));
    summary.append(summaryCopy, node("em", "", "查看模型"));
    details.append(summary);
    const body = node("div", "foundation-body");

    const intro = node("section", "model-intro");
    intro.append(node("span", "", "MODEL / 研判框架"));
    intro.append(node("strong", "", foundation.modelName || "多源命理结构研判模型"));
    intro.append(node("p", "", "把传统结构规则、公开人物样本与本人真实经历放在同一条证据链中。规则负责提出判断，案例负责寻找偏差，人生事件负责验证这份判断是否真的贴近本人。"));
    body.append(intro);

    const stats = node("div", "foundation-stats");
    [
      ["公开人物", foundation.stats.publicPeople],
      ["事件资料", foundation.stats.publicEvents],
      ["排盘快照", foundation.stats.chartSnapshots],
      ["精确日期", coverage.exactDateRecords || 0],
      ["校时运行", validation.rectificationRuns || 0],
      ["留出事件", validation.holdoutEvents || 0],
    ].forEach(([label, value]) => {
      const item = node("div");
      item.append(node("strong", "", Number(value).toLocaleString("zh-CN")), node("span", "", label));
      stats.append(item);
    });
    body.append(stats);

    const coverageBlock = node("section", "model-evidence");
    coverageBlock.append(node("h4", "", "数据覆盖与边界"));
    coverageBlock.append(node("p", "", `出生资料覆盖 ${birthRange}，约 ${Number(coverage.birthSpanYears || 0).toLocaleString("zh-CN")} 年；事件记录覆盖 ${coverage.eventStartYear || "待补"}—${coverage.eventEndYear || "待补"} 年，共 ${coverage.eventTypeCount || 0} 类。当前仅 ${Number(coverage.timedBirthRecords || 0).toLocaleString("zh-CN")} 条公开资料带出生时刻，因此无时辰样本不会被用于证明精确时柱。`));
    const coverageMeta = node("div", "model-meta-row");
    coverageMeta.append(
      node("span", "", `${Number(validation.calibrationEvents || 0).toLocaleString("zh-CN")} 条校时事件`),
      node("span", "", `${Number(validation.holdoutEvents || 0).toLocaleString("zh-CN")} 条留出事件`),
      node("span", "", `${Number(foundation.stats.correctionRecords || 0).toLocaleString("zh-CN")} 条人工纠偏`),
      node("span", "", `${Number(validation.metricRecords || 0).toLocaleString("zh-CN")} 项验证指标`),
      node("span", "", `${foundation.knowledgeRuleCount} 条结构规则`),
      node("span", "", `${foundation.theorySourceCount} 类理论来源`),
      node("span", "", "候选校时：尚未校准为概率")
    );
    coverageBlock.append(coverageMeta);
    body.append(coverageBlock);

    if (foundation.representativePeople?.length) {
      const peopleBlock = node("section", "model-evidence");
      peopleBlock.append(node("h4", "", "已收录公开人物举例"));
      const people = node("div", "people-chips");
      foundation.representativePeople.forEach((name) => people.append(node("span", "", name)));
      peopleBlock.append(people);
      peopleBlock.append(node("small", "", "人物仅用于验证数据管线与结构规则，列入数据库不代表对其人生作价值评价。"));
      body.append(peopleBlock);
    }

    if (foundation.similarFigures?.length) {
      const similarBlock = node("section", "model-evidence");
      similarBlock.append(node("h4", "", "知名样本的结构距离"));
      similarBlock.append(node("p", "", "从已收录的知名公开人物中，按日主、月令与三柱结构计算模型内距离；数值越小，只表示结构字段越接近。"));
      const similarGrid = node("div", "similar-figures");
      foundation.similarFigures.forEach((figure) => {
        const item = node("div");
        const top = node("span");
        top.append(node("strong", "", figure.name), node("em", "", `距离 ${figure.distance}/100`));
        item.append(top, node("small", "", figure.matches.join(" · ")));
        similarGrid.append(item);
      });
      similarBlock.append(similarGrid);
      body.append(similarBlock);
    }

    if (foundation.correctionPaths?.length) {
      const correctionBlock = node("section", "model-evidence correction-model");
      correctionBlock.append(node("h4", "", "双向纠偏如何工作"));
      const pathGrid = node("div", "correction-paths");
      foundation.correctionPaths.forEach((path) => {
        const item = node("div");
        item.append(node("strong", "", path.label));
        const steps = node("div", "correction-steps");
        path.steps.forEach((step, index) => {
          steps.append(node("span", "", step));
          if (index < path.steps.length - 1) steps.append(node("b", "", "→"));
        });
        item.append(steps, node("p", "", path.description));
        pathGrid.append(item);
      });
      correctionBlock.append(pathGrid);
      body.append(correctionBlock);
    }

    if (foundation.appliedRules.length) {
      const rules = node("section", "foundation-rules");
      rules.append(node("h4", "", "本次采用的专业规则"));
      foundation.appliedRules.forEach((rule) => {
        const item = node("p");
        item.append(node("strong", "", rule.topic), document.createTextNode(rule.summary));
        rules.append(item);
      });
      body.append(rules);
    }
    body.append(node("p", "foundation-note", foundation.note));
    details.append(body);
    foundationPanel = details;
  }

  const sectionIllustrationCategories = {
    structure: "elements",
    career: "steps",
    relationships: "pools",
    "turning-points": "cosmos",
    wellbeing: "mountains",
  };

  record.report.sections.forEach((section, sectionIndex) => {
    const anchor = node("a", "", section.title);
    anchor.href = `#report-${section.id}`;
    anchor.addEventListener("click", () => setReadMode("focused"));
    index.append(anchor);

    const sectionNode = node("section", "report-section");
    sectionNode.id = `report-${section.id}`;
    sectionNode.append(node("span", "report-section-number", String(sectionIndex + 1).padStart(2, "0")));
    sectionNode.append(node("h3", "", section.title));
    sectionNode.append(node("p", "report-summary", section.summary));
    const illustrationCategory = sectionIllustrationCategories[section.id];
    if (illustrationCategory && imageLibrary) {
      const illustrationData = pickUniqueVisual(imageLibrary, illustrationCategory, `${imageSeed}:${section.id}`, usedImageSources);
      const figure = node("figure", "section-illustration");
      figure.dataset.imageId = illustrationData.id;
      figure.style.setProperty("--illustration-scale", illustrationData.scale);
      const image = document.createElement("img");
      image.src = illustrationData.src;
      image.alt = illustrationData.alt;
      image.loading = "lazy";
      image.style.objectPosition = illustrationData.position;
      image.style.filter = `saturate(${illustrationData.saturation}) brightness(${illustrationData.brightness})`;
      figure.append(image, node("figcaption", "", illustrationData.caption));
      sectionNode.append(figure);
    }
    if (section.technical) {
      const technical = node("p", "technical-cue");
      technical.append(node("strong", "", "专业线索"), document.createTextNode(reportDisplayText(section.technical)));
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
      note.append(node("strong", "", "简要注释："), document.createTextNode(reportDisplayText(section.note)));
      sectionNode.append(note);
    }
    content.append(sectionNode);
  });

  if (foundationPanel) {
    const footer = node("section", "foundation-footer");
    const heading = node("div", "foundation-footer-heading");
    heading.append(node("span", "", "研判依据"), node("strong", "", "模型、数据与双向纠偏"));
    footer.append(heading, foundationPanel);
    content.append(footer);
  }
  content.append(node("p", "disclosure", record.report.disclosure));
  const preferredMode = window.localStorage.getItem("mingliReadMode");
  setReadMode(["summary", "focused", "full"].includes(preferredMode) ? preferredMode : "focused");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function clearFormErrors() {
  $("#formErrorSummary").hidden = true;
  $$(".invalid-field").forEach((element) => element.classList.remove("invalid-field"));
  $$('[aria-invalid="true"]').forEach((element) => element.removeAttribute("aria-invalid"));
}

function validationTarget(id) {
  const field = $(`#${id}`);
  if (!field) return null;
  return enhancedSelects.get(field)?.trigger || field;
}

function validateForm() {
  clearFormErrors();
  const issues = [];
  const requireValue = (id, message) => {
    const field = $(`#${id}`);
    if (!String(field?.value || "").trim()) issues.push({ id, message });
  };
  requireValue("name", "请填写姓名");
  requireValue("year", "请选择出生年份");
  requireValue("month", "请选择出生月份");
  requireValue("day", "请选择出生日期");
  requireValue("birthplace", "请填写出生地点");
  const timeMode = $('input[name="timeMode"]:checked')?.value;
  if (timeMode === "exact") {
    requireValue("exactHour", "请选择出生小时");
    requireValue("exactMinute", "请选择出生分钟");
  } else if (timeMode === "branch") {
    requireValue("timeBranch", "请选择传统时辰");
  }
  $$(".event-row", eventsList).forEach((row, index) => {
    const date = $(".event-date", row);
    const summary = $(".event-summary-input", row);
    if (!date.value || !summary.value.trim()) {
      const target = !date.value ? date : summary;
      issues.push({ element: target, message: `请补全第 ${index + 1} 条关键经历，或将它删除` });
    }
  });
  if (!issues.length) return true;
  issues.forEach((issue) => {
    const target = issue.element || validationTarget(issue.id);
    target?.classList.add("invalid-field");
    target?.setAttribute("aria-invalid", "true");
  });
  const summary = $("#formErrorSummary");
  summary.textContent = issues[0].message;
  summary.hidden = false;
  const firstTarget = issues[0].element || validationTarget(issues[0].id);
  firstTarget?.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => firstTarget?.focus(), 250);
  return false;
}

async function submitReport(event) {
  event.preventDefault();
  if (!validateForm()) return;
  await resolvePlace({ quiet: true });
  const button = $("#generateButton");
  const label = $(".button-label", button);
  button.disabled = true;
  label.textContent = "命盘推演中…";
  try {
    const record = await api("/api/reports", {
      method: "POST",
      body: JSON.stringify(collectFormData()),
    });
    state.currentRecord = record;
    renderReport(record);
    await loadHistory($("#historySearch").value.trim());
    showToast(record.reused ? "资料与模型版本一致，已打开原报告" : "报告已生成并保存到查询记录");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    label.textContent = "开启研判";
  }
}

async function deleteHistoryRecord(record) {
  if (!window.confirm(`确认删除“${record.name}”的这份查询记录？`)) return;
  try {
    await api(`/api/reports/${encodeURIComponent(record.recordId)}`, { method: "DELETE" });
    if (state.currentRecord?.recordId === record.recordId) showForm();
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
form.addEventListener("submit", submitReport);

$$('input[name="calendarType"]').forEach((input) => input.addEventListener("change", updateCalendarControls));
$$('input[name="timeMode"]').forEach((input) => input.addEventListener("change", updateTimeControls));
$("#exactHour").addEventListener("change", updateTimeControls);
$("#exactMinute").addEventListener("change", updateTimeControls);
$("#timeBranch").addEventListener("change", updateTimeControls);
$("#year").addEventListener("change", updateDayOptions);
$("#month").addEventListener("change", updateDayOptions);
$("#isLeapMonth").addEventListener("change", updateDayOptions);
$("#birthplace").addEventListener("input", () => {
  window.clearTimeout(state.placeTimer);
  state.placeTimer = window.setTimeout(() => resolvePlace({ quiet: true }), 450);
});
form.addEventListener("input", clearFormErrors);
form.addEventListener("change", clearFormErrors);
window.addEventListener("scroll", updateReadingProgress, { passive: true });
window.addEventListener("resize", updateReadingProgress);

$("#historySearch").addEventListener("input", (event) => {
  window.clearTimeout(state.searchTimer);
  state.searchTimer = window.setTimeout(() => loadHistory(event.target.value.trim()), 220);
});

$("#historyToggle").addEventListener("click", () => {
  $("#historySidebar").classList.add("open");
  $("#sidebarScrim").hidden = false;
});
$("#sidebarScrim").addEventListener("click", closeSidebar);
$("#choiceDialogClose").addEventListener("click", () => $("#choiceDialog").close());
$("#choiceSearchInput").addEventListener("input", (event) => renderChoiceOptions(event.target.value));
$("#wheelConfirmButton").addEventListener("click", applyWheelSelection);
$("#choiceDialog").addEventListener("close", () => {
  activeWheel = null;
  activeChoiceSelect = null;
});
$("#choiceDialog").addEventListener("click", (event) => {
  if (event.target === $("#choiceDialog")) $("#choiceDialog").close();
});

populateDateSelects();
populateTimeSelects();
updateCalendarControls();
updateTimeControls();
[$("#year"), $("#month"), $("#day"), $("#exactHour"), $("#exactMinute"), $("#timeBranch")].forEach(enhanceSelect);
updateEventsEmpty();
loadHistory();
