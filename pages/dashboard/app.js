const bridge = window.AstrBotPluginPage || window.AstrBotPluginView;

// 状态管理
let currentScopeKey = "";
let allEvents = [];
let allPersonas = [];
let currentFilter = "all";
let currentOverview = null;

// DOM 元素 - 顶部导航与通用
const scopeSelect = document.getElementById("scopeSelect");
const btnAllPersonas = document.getElementById("btnAllPersonas");
const btnRefresh = document.getElementById("btnRefresh");
const btnClear = document.getElementById("btnClear");

// DOM 元素 - 当前角色人设卡片
const personaTitle = document.getElementById("personaTitle");
const personaIdLabel = document.getElementById("personaIdLabel");
const badgeDefaultPersona = document.getElementById("badgeDefaultPersona");
const btnTogglePrompt = document.getElementById("btnTogglePrompt");
const personaPromptBox = document.getElementById("personaPromptBox");
const personaPromptContent = document.getElementById("personaPromptContent");
const promptLengthTag = document.getElementById("promptLengthTag");

// DOM 元素 - 指标卡片
const badgePlanStatus = document.getElementById("badgePlanStatus");
const statPlanSummary = document.getElementById("statPlanSummary");
const statPlanDetail = document.getElementById("statPlanDetail");
const statOngoingCount = document.getElementById("statOngoingCount");
const statTodayCount = document.getElementById("statTodayCount");
const statEventsCount = document.getElementById("statEventsCount");
const statScopeDesc = document.getElementById("statScopeDesc");

// DOM 元素 - 规划展示与编辑
const planDisplay = document.getElementById("planDisplay");
const planDay = document.getElementById("planDay");
const planOutfitRow = document.getElementById("planOutfitRow");
const planOutfit = document.getElementById("planOutfit");
const planMoodRow = document.getElementById("planMoodRow");
const planMood = document.getElementById("planMood");
const planLocationRow = document.getElementById("planLocationRow");
const planLocation = document.getElementById("planLocation");
const planHolidayRow = document.getElementById("planHolidayRow");
const planHoliday = document.getElementById("planHoliday");
const planTwistRow = document.getElementById("planTwistRow");
const planTwist = document.getElementById("planTwist");
const planWeatherRow = document.getElementById("planWeatherRow");
const planWeather = document.getElementById("planWeather");

const btnTogglePlanEdit = document.getElementById("btnTogglePlanEdit");
const planEditForm = document.getElementById("planEditForm");
const inputPlanDay = document.getElementById("inputPlanDay");
const inputPlanOutfit = document.getElementById("inputPlanOutfit");
const inputPlanMood = document.getElementById("inputPlanMood");
const inputPlanLocation = document.getElementById("inputPlanLocation");
const inputPlanTwist = document.getElementById("inputPlanTwist");
const inputPlanWeather = document.getElementById("inputPlanWeather");
const btnCancelPlan = document.getElementById("btnCancelPlan");
const btnSavePlan = document.getElementById("btnSavePlan");

// DOM 元素 - 生活事件管理
const inputEventText = document.getElementById("inputEventText");
const checkOngoing = document.getElementById("checkOngoing");
const btnAddEvent = document.getElementById("btnAddEvent");

const eventsContainer = document.getElementById("eventsContainer");
const tabItems = document.querySelectorAll(".tab-item");
const countAll = document.getElementById("countAll");
const countOngoing = document.getElementById("countOngoing");
const countToday = document.getElementById("countToday");
const countDone = document.getElementById("countDone");

// DOM 元素 - 模态框与 Toast
const modalAllPersonas = document.getElementById("modalAllPersonas");
const btnCloseModal = document.getElementById("btnCloseModal");
const allPersonasGrid = document.getElementById("allPersonasGrid");
const toast = document.getElementById("toast");

// Toast 提示
function showToast(message, isError = false) {
  if (!toast) return;
  toast.textContent = message;
  toast.style.background = isError ? "var(--danger)" : "var(--text-primary)";
  toast.classList.add("show");
  setTimeout(() => {
    toast.classList.remove("show");
  }, 2400);
}

// 格式化时间
function formatTime(ts) {
  if (!ts) return "-";
  const d = new Date(Number(ts));
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 转义 HTML
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// 加载概览统计与当前角色数据
async function loadOverview() {
  try {
    const params = currentScopeKey
      ? { persona_id: currentScopeKey, scope_key: currentScopeKey }
      : {};
    const data = await bridge.apiGet("dashboard/overview", params);
    currentOverview = data;
    currentScopeKey = data.current_persona_id || data.current_scope_key || "default";
    allPersonas = data.personas || [];

    // 1. 渲染当前角色人设卡片
    renderCurrentPersonaCard(data);

    // 2. 渲染角色下拉列表
    renderScopeOptions(allPersonas, currentScopeKey);

    const slotTag = data.current_slot ? ` · ${data.current_slot}` : "";

    // 3. 统计卡片渲染
    if (data.is_today_planned && data.plan) {
      badgePlanStatus.textContent = `今日已规划${slotTag}`;
      badgePlanStatus.className = "badge badge-ongoing";
      statPlanSummary.textContent = "已就绪";
      statPlanDetail.textContent = data.plan.day || "-";
      planDay.textContent = data.plan.day || "-";

      if (data.plan.outfit) {
        planOutfit.textContent = data.plan.outfit;
        planOutfitRow.style.display = "flex";
      } else {
        planOutfitRow.style.display = "none";
      }

      if (data.plan.mood) {
        planMood.textContent = data.plan.mood;
        planMoodRow.style.display = "flex";
      } else {
        planMoodRow.style.display = "none";
      }

      if (data.plan.location) {
        planLocation.textContent = data.plan.location;
        planLocationRow.style.display = "flex";
      } else {
        planLocationRow.style.display = "none";
      }

      if (data.plan.holiday && data.plan.holiday !== "无") {
        planHoliday.textContent = `🎉 ${data.plan.holiday}`;
        planHolidayRow.style.display = "flex";
      } else {
        planHolidayRow.style.display = "none";
      }

      if (data.plan.twist) {
        planTwist.textContent = data.plan.twist;
        planTwistRow.style.display = "flex";
      } else {
        planTwistRow.style.display = "none";
      }
      if (data.plan.weather) {
        planWeather.textContent = data.plan.weather;
        planWeatherRow.style.display = "flex";
      } else {
        planWeatherRow.style.display = "none";
      }
    } else {
      badgePlanStatus.textContent = `今日未规划${slotTag}`;
      badgePlanStatus.className = "badge badge-done";
      statPlanSummary.textContent = "待规划";
      statPlanDetail.textContent = `当前为 ${data.current_slot || "今天"}，AI 角色将在首轮对话中自动规划`;
      planDay.textContent = "（今天尚未进行生活规划）";
      planOutfitRow.style.display = "none";
      planMoodRow.style.display = "none";
      planLocationRow.style.display = "none";
      planHolidayRow.style.display = "none";
      planTwistRow.style.display = "none";
      planWeatherRow.style.display = "none";
    }

    statOngoingCount.textContent = data.ongoing_count;
    statTodayCount.textContent = data.today_count;
    statEventsCount.textContent = `${data.events_count} / ${data.max_events}`;
    statScopeDesc.textContent = `当前角色生活线: ${currentScopeKey}`;
  } catch (err) {
    showToast(`获取概览失败: ${err.message}`, true);
  }
}

// 渲染当前角色人设卡片
function renderCurrentPersonaCard(data) {
  const name = data.current_persona_name || data.current_persona_id || "default";
  personaTitle.textContent = name;
  personaIdLabel.textContent = data.current_persona_id || "default";

  if (data.is_default_persona) {
    badgeDefaultPersona.style.display = "inline-block";
  } else {
    badgeDefaultPersona.style.display = "none";
  }

  const prompt = data.current_persona_prompt || "";
  personaPromptContent.textContent = prompt || "（该人格暂未设置独立的 System Prompt 系统提示词）";
  promptLengthTag.textContent = `${prompt.length} 字`;
}

// 渲染角色下拉列表
function renderScopeOptions(personasList, activeKey) {
  scopeSelect.innerHTML = "";

  if (!personasList || !personasList.length) {
    const opt = document.createElement("option");
    opt.value = activeKey;
    opt.textContent = activeKey;
    scopeSelect.appendChild(opt);
    return;
  }

  for (const p of personasList) {
    const opt = document.createElement("option");
    opt.value = p.persona_id;
    const isDef = p.is_default ? "🌟 " : "🎭 ";
    const planTag = p.is_today_planned ? " [已规划]" : " [未规划]";
    opt.textContent = `${isDef}${p.name || p.persona_id}${planTag}`;
    if (p.persona_id === activeKey) opt.selected = true;
    scopeSelect.appendChild(opt);
  }
}

// 加载当前角色事件列表
async function loadEvents() {
  try {
    const params = currentScopeKey
      ? { persona_id: currentScopeKey, scope_key: currentScopeKey }
      : {};
    const res = await bridge.apiGet("dashboard/events", params);
    allEvents = res.events || [];
    renderEvents();
  } catch (err) {
    showToast(`获取事件列表失败: ${err.message}`, true);
  }
}

// 渲染事件列表
function renderEvents() {
  const ongoingList = allEvents.filter((e) => e.ongoing);
  const todayList = allEvents.filter((e) => !e.ongoing && e.is_today);
  const doneList = allEvents.filter((e) => !e.ongoing && !e.is_today);

  countAll.textContent = allEvents.length;
  countOngoing.textContent = ongoingList.length;
  countToday.textContent = todayList.length;
  countDone.textContent = doneList.length;

  let displayList = allEvents;
  if (currentFilter === "ongoing") displayList = ongoingList;
  else if (currentFilter === "today") displayList = todayList;
  else if (currentFilter === "done") displayList = doneList;

  eventsContainer.innerHTML = "";
  if (!displayList.length) {
    eventsContainer.innerHTML = '<div class="empty-state">当前分类下暂无生活事件</div>';
    return;
  }

  for (const ev of displayList) {
    const card = document.createElement("div");
    card.className = "event-item";

    const isOngoing = Boolean(ev.ongoing);
    const badgeHtml = isOngoing
      ? '<span class="badge badge-ongoing">进行中</span>'
      : ev.is_today
        ? '<span class="badge badge-today">今日小事</span>'
        : '<span class="badge badge-done">已过去</span>';

    card.innerHTML = `
      <div class="event-main">
        <div class="event-badges">
          ${badgeHtml}
          <span class="event-text">${escapeHtml(ev.text)}</span>
        </div>
        <div class="event-meta">
          <span>创建: ${formatTime(ev.at)}</span>
          <span>最近触碰: ${formatTime(ev.touched_at)}</span>
          ${ev.ended_at ? `<span>结束: ${formatTime(ev.ended_at)}</span>` : ""}
        </div>
      </div>
      <div class="event-actions">
        ${isOngoing ? `<button class="btn btn-outline btn-sm btn-done" data-id="${ev.id}">结束</button>` : ""}
        <button class="btn btn-outline btn-sm btn-delete" data-id="${ev.id}" title="删除此事件">✕</button>
      </div>
    `;

    const btnDone = card.querySelector(".btn-done");
    if (btnDone) {
      btnDone.addEventListener("click", async () => {
        await handleDoneEvent(ev.id);
      });
    }

    const btnDelete = card.querySelector(".btn-delete");
    if (btnDelete) {
      btnDelete.addEventListener("click", async () => {
        await handleDeleteEvent(ev.id);
      });
    }

    eventsContainer.appendChild(card);
  }
}

// 结束事件
async function handleDoneEvent(eventId) {
  try {
    const res = await bridge.apiPost("dashboard/event/done", {
      event_id: eventId,
      persona_id: currentScopeKey,
      scope_key: currentScopeKey,
    });
    showToast(res.message || "已结束事件");
    await refreshAll();
  } catch (err) {
    showToast(`操作失败: ${err.message}`, true);
  }
}

// 删除事件
async function handleDeleteEvent(eventId) {
  if (!confirm(`确认删除此事件吗？（当前角色: ${currentScopeKey}）`)) return;
  try {
    const res = await bridge.apiPost("dashboard/event/delete", {
      event_id: eventId,
      persona_id: currentScopeKey,
      scope_key: currentScopeKey,
    });
    showToast(res.message || "已删除事件");
    await refreshAll();
  } catch (err) {
    showToast(`删除失败: ${err.message}`, true);
  }
}

// 添加新事件
btnAddEvent.addEventListener("click", async () => {
  const content = inputEventText.value.trim();
  if (!content) {
    showToast("请输入事件内容", true);
    return;
  }
  const ongoing = checkOngoing.checked;
  try {
    const res = await bridge.apiPost("dashboard/event/add", {
      content,
      ongoing,
      persona_id: currentScopeKey,
      scope_key: currentScopeKey,
    });
    showToast(res.message || "记录成功");
    inputEventText.value = "";
    checkOngoing.checked = false;
    await refreshAll();
  } catch (err) {
    showToast(`记录失败: ${err.message}`, true);
  }
});

// 保存规划
btnSavePlan.addEventListener("click", async () => {
  const day = inputPlanDay.value.trim();
  if (!day) {
    showToast("请填写规划内容", true);
    return;
  }
  const outfit = inputPlanOutfit.value.trim();
  const mood = inputPlanMood.value.trim();
  const location = inputPlanLocation.value.trim();
  const twist = inputPlanTwist.value.trim();
  const weather = inputPlanWeather.value.trim();

  try {
    const res = await bridge.apiPost("dashboard/plan/save", {
      day,
      outfit,
      mood,
      location,
      twist,
      weather,
      persona_id: currentScopeKey,
      scope_key: currentScopeKey,
    });
    showToast(res.message || "今日规划已保存");
    planEditForm.style.display = "none";
    planDisplay.style.display = "block";
    btnTogglePlanEdit.textContent = "编辑规划";
    await refreshAll();
  } catch (err) {
    showToast(`保存失败: ${err.message}`, true);
  }
});

// 编辑规划表单切换
btnTogglePlanEdit.addEventListener("click", () => {
  const isEditing = planEditForm.style.display !== "none";
  if (isEditing) {
    planEditForm.style.display = "none";
    planDisplay.style.display = "block";
    btnTogglePlanEdit.textContent = "编辑规划";
  } else {
    if (currentOverview && currentOverview.plan) {
      inputPlanDay.value = currentOverview.plan.day || "";
      inputPlanOutfit.value = currentOverview.plan.outfit || "";
      inputPlanMood.value = currentOverview.plan.mood || "";
      inputPlanLocation.value = currentOverview.plan.location || "";
      inputPlanTwist.value = currentOverview.plan.twist || "";
      inputPlanWeather.value = currentOverview.plan.weather || "";
    } else {
      inputPlanDay.value = "";
      inputPlanOutfit.value = "";
      inputPlanMood.value = "";
      inputPlanLocation.value = "";
      inputPlanTwist.value = "";
      inputPlanWeather.value = "";
    }
    planDisplay.style.display = "none";
    planEditForm.style.display = "block";
    btnTogglePlanEdit.textContent = "收起表单";
  }
});

btnCancelPlan.addEventListener("click", () => {
  planEditForm.style.display = "none";
  planDisplay.style.display = "block";
  btnTogglePlanEdit.textContent = "编辑规划";
});

// 人设 Prompt 折叠切换
btnTogglePrompt.addEventListener("click", () => {
  const isVisible = personaPromptBox.style.display !== "none";
  if (isVisible) {
    personaPromptBox.style.display = "none";
    btnTogglePrompt.textContent = "查看人设 Prompt";
  } else {
    personaPromptBox.style.display = "block";
    btnTogglePrompt.textContent = "收起人设 Prompt";
  }
});

// 清空当前角色生活数据
btnClear.addEventListener("click", async () => {
  if (
    !confirm(
      `确认清空角色 [${currentScopeKey}] 下的所有生活事件与规划吗？此操作不可逆。`
    )
  ) {
    return;
  }
  try {
    const res = await bridge.apiPost("dashboard/clear", {
      persona_id: currentScopeKey,
      scope_key: currentScopeKey,
    });
    showToast(res.message || "已清空数据");
    await refreshAll();
  } catch (err) {
    showToast(`清空失败: ${err.message}`, true);
  }
});

// 刷新按钮
btnRefresh.addEventListener("click", async () => {
  await refreshAll();
  showToast("数据已刷新");
});

// 角色下拉切换
scopeSelect.addEventListener("change", async (e) => {
  currentScopeKey = e.target.value;
  await refreshAll();
});

// 渲染所有人格全景模态框
function renderAllPersonasModal() {
  allPersonasGrid.innerHTML = "";
  if (!allPersonas.length) {
    allPersonasGrid.innerHTML = '<div class="empty-state">暂无角色数据</div>';
    return;
  }

  for (const p of allPersonas) {
    const item = document.createElement("div");
    item.className = `persona-grid-item ${p.persona_id === currentScopeKey ? "active" : ""}`;

    const defBadge = p.is_default
      ? '<span class="badge badge-default">默认</span>'
      : "";
    const planBadge = p.is_today_planned
      ? '<span class="badge badge-ongoing">已规划</span>'
      : '<span class="badge badge-done">待规划</span>';

    item.innerHTML = `
      <div>
        <div class="p-item-header">
          <span class="p-item-name">🎭 ${escapeHtml(p.name || p.persona_id)}</span>
          <div>${defBadge} ${planBadge}</div>
        </div>
        <div class="p-item-preview" style="margin-top: 8px;">
          ${escapeHtml(p.system_prompt_preview || p.system_prompt || "暂无系统设定")}
        </div>
      </div>
      <div class="p-item-footer">
        <span>进行中: <b>${p.ongoing_count || 0}</b></span>
        <span>今日做过: <b>${p.today_count || 0}</b></span>
        <span>总事件: <b>${p.events_count || 0}</b></span>
      </div>
    `;

    item.addEventListener("click", async () => {
      currentScopeKey = p.persona_id;
      modalAllPersonas.style.display = "none";
      await refreshAll();
      showToast(`已切换至角色: ${p.name || p.persona_id}`);
    });

    allPersonasGrid.appendChild(item);
  }
}

// 打开所有人格模态框
btnAllPersonas.addEventListener("click", async () => {
  try {
    const res = await bridge.apiGet("dashboard/personas");
    if (res && res.personas) {
      allPersonas = res.personas;
    }
  } catch (err) {
    console.warn("加载 personas 列表失败，回退至缓存:", err);
  }
  renderAllPersonasModal();
  modalAllPersonas.style.display = "flex";
});

// 关闭模态框
btnCloseModal.addEventListener("click", () => {
  modalAllPersonas.style.display = "none";
});

modalAllPersonas.addEventListener("click", (e) => {
  if (e.target === modalAllPersonas) {
    modalAllPersonas.style.display = "none";
  }
});

// Tab 切换
tabItems.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabItems.forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    currentFilter = tab.getAttribute("data-filter");
    renderEvents();
  });
});

async function refreshAll() {
  await loadOverview();
  await loadEvents();
}

// 初始化 bridge 与页面
async function init() {
  try {
    if (bridge && typeof bridge.ready === "function") {
      await bridge.ready();
    }
    await refreshAll();
  } catch (e) {
    console.error("Bridge ready failed:", e);
    await refreshAll();
  }
}

init();
