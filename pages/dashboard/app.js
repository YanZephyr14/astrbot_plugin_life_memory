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
const btnSettings = document.getElementById("btnSettings");
const btnRefresh = document.getElementById("btnRefresh");
const btnClear = document.getElementById("btnClear");

// DOM 元素 - 当前角色人设卡片
const personaTitle = document.getElementById("personaTitle");
const personaIdLabel = document.getElementById("personaIdLabel");
const badgeDefaultPersona = document.getElementById("badgeDefaultPersona");
const badgeWhitelistStatus = document.getElementById("badgeWhitelistStatus");
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

const btnAutoPlan = document.getElementById("btnAutoPlan");
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

// DOM 元素 - 确认清空模态框 (解决原生 confirm 在 iframe/webview 下被禁用的 Bug)
const modalConfirmClear = document.getElementById("modalConfirmClear");
const btnCloseConfirmClear = document.getElementById("btnCloseConfirmClear");
const btnCancelClearModal = document.getElementById("btnCancelClearModal");
const btnExecuteClear = document.getElementById("btnExecuteClear");
const confirmClearDesc = document.getElementById("confirmClearDesc");

// DOM 元素 - 插件设置模态框
const modalSettings = document.getElementById("modalSettings");
const btnCloseSettingsModal = document.getElementById("btnCloseSettingsModal");
const btnCancelSettings = document.getElementById("btnCancelSettings");
const formSettings = document.getElementById("formSettings");
const settingEnabled = document.getElementById("settingEnabled");
const settingStorageScope = document.getElementById("settingStorageScope");
const settingInjectGuide = document.getElementById("settingInjectGuide");
const settingEnableHoliday = document.getElementById("settingEnableHoliday");
const settingEnableOutfit = document.getElementById("settingEnableOutfit");
const settingEnablePersonaWhitelist = document.getElementById("settingEnablePersonaWhitelist");
const whitelistSelectArea = document.getElementById("whitelistSelectArea");
const personaCheckboxes = document.getElementById("personaCheckboxes");
const settingPersonaWhitelistManual = document.getElementById("settingPersonaWhitelistManual");
const settingSmallTtl = document.getElementById("settingSmallTtl");
const settingOngoingTtl = document.getElementById("settingOngoingTtl");
const settingMaxEvents = document.getElementById("settingMaxEvents");
const settingHistoryDays = document.getElementById("settingHistoryDays");

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

      if (btnAutoPlan) {
        btnAutoPlan.innerHTML = "<span>🔄</span> 重新规划";
        btnAutoPlan.title = "为当前角色重新生成今日拟真生活日程与规划";
      }

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
      statPlanDetail.textContent = `当前为 ${data.current_slot || "今天"}，点击「开始规划」即可一键制定`;
      planDay.innerHTML = `（今天尚未进行生活规划） <button id="btnQuickPlanInner" class="btn-quick-plan" style="margin-left: 8px;">✨ 立即规划</button>`;
      
      const btnInner = document.getElementById("btnQuickPlanInner");
      if (btnInner) {
        btnInner.addEventListener("click", () => triggerAutoPlan(currentScopeKey));
      }

      if (btnAutoPlan) {
        btnAutoPlan.innerHTML = "<span>✨</span> 开始规划";
        btnAutoPlan.title = "一键为当前角色生成今日拟真生活起居与日程规划";
      }

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

  if (data.enable_persona_whitelist && data.is_persona_enabled === false) {
    badgeWhitelistStatus.style.display = "inline-block";
    badgeWhitelistStatus.textContent = "未在白名单启用";
  } else {
    badgeWhitelistStatus.style.display = "none";
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
    scopeSelect.value = activeKey;
    return;
  }

  let hasMatched = false;
  for (const p of personasList) {
    const opt = document.createElement("option");
    opt.value = p.persona_id;
    const isDef = p.is_default ? "🌟 " : "🎭 ";
    const planTag = p.is_today_planned ? " [已规划]" : " [未规划]";
    opt.textContent = `${isDef}${p.name || p.persona_id}${planTag}`;
    if (p.persona_id === activeKey) {
      opt.selected = true;
      hasMatched = true;
    }
    scopeSelect.appendChild(opt);
  }

  // 若传入的 activeKey 不在列表内且非空，作为临时项补全，避免选中状态丢失
  if (!hasMatched && activeKey) {
    const opt = document.createElement("option");
    opt.value = activeKey;
    opt.textContent = `🎭 ${activeKey}`;
    opt.selected = true;
    scopeSelect.appendChild(opt);
  }

  scopeSelect.value = activeKey;
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

// 清空当前角色生活数据：唤起内置确认模态框（彻底解决 iframe/webview 下 window.confirm 被禁用的 Bug）
if (btnClear) {
  btnClear.addEventListener("click", () => {
    if (confirmClearDesc) {
      confirmClearDesc.textContent = `确认清空角色 [${currentScopeKey}] 下的所有生活事件与规划吗？此操作不可逆。`;
    }
    if (modalConfirmClear) {
      modalConfirmClear.style.display = "flex";
    }
  });
}

// 模态框确认执行清空
if (btnExecuteClear) {
  btnExecuteClear.addEventListener("click", async () => {
    btnExecuteClear.disabled = true;
    btnExecuteClear.textContent = "正在清空...";
    try {
      const res = await bridge.apiPost("dashboard/clear", {
        persona_id: currentScopeKey,
        scope_key: currentScopeKey,
      });
      showToast(res.message || "已清空数据");
      if (modalConfirmClear) modalConfirmClear.style.display = "none";
      await refreshAll();
    } catch (err) {
      showToast(`清空失败: ${err.message}`, true);
    } finally {
      btnExecuteClear.disabled = false;
      btnExecuteClear.textContent = "确认清空";
    }
  });
}

// 关闭/取消清空模态框
if (btnCloseConfirmClear) {
  btnCloseConfirmClear.addEventListener("click", () => {
    if (modalConfirmClear) modalConfirmClear.style.display = "none";
  });
}

if (btnCancelClearModal) {
  btnCancelClearModal.addEventListener("click", () => {
    if (modalConfirmClear) modalConfirmClear.style.display = "none";
  });
}

if (modalConfirmClear) {
  modalConfirmClear.addEventListener("click", (e) => {
    if (e.target === modalConfirmClear) {
      modalConfirmClear.style.display = "none";
    }
  });
}

// 刷新按钮
btnRefresh.addEventListener("click", async () => {
  await refreshAll();
  showToast("数据已刷新");
});

// 角色下拉切换
scopeSelect.addEventListener("change", async (e) => {
  const selectedId = e.target.value;
  await refreshAll(selectedId);
  showToast(`已切换至角色: ${selectedId}`);
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
    const wlBadge = p.is_enabled === false
      ? '<span class="badge badge-warning" style="font-size: 11px;" title="该角色未加入生效白名单">未在白名单</span>'
      : "";
    const planBadge = p.is_today_planned
      ? '<span class="badge badge-ongoing">已规划</span>'
      : `<span class="badge badge-done">待规划</span> <button class="btn-quick-plan btn-plan-single" data-pid="${p.persona_id}" title="立即为该角色制定今日规划">✨ 开始规划</button>`;

    item.innerHTML = `
      <div>
        <div class="p-item-header">
          <span class="p-item-name">🎭 ${escapeHtml(p.name || p.persona_id)}</span>
          <div style="display: flex; align-items: center; gap: 4px;">${defBadge} ${wlBadge} ${planBadge}</div>
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

    // 绑定卡片头部的开始规划按钮
    const btnPlanSingle = item.querySelector(".btn-plan-single");
    if (btnPlanSingle) {
      btnPlanSingle.addEventListener("click", async (e) => {
        e.stopPropagation();
        btnPlanSingle.disabled = true;
        btnPlanSingle.textContent = "⏳ 规划中...";
        try {
          const res = await bridge.apiPost("dashboard/plan/auto_generate", {
            persona_id: p.persona_id,
          });
          showToast(res.message || "已制定规划");
          const pres = await bridge.apiGet("dashboard/personas");
          if (pres && pres.personas) allPersonas = pres.personas;
          renderAllPersonasModal();
          if (p.persona_id === currentScopeKey) {
            await refreshAll();
          }
        } catch (err) {
          showToast(`规划失败: ${err.message}`, true);
          btnPlanSingle.disabled = false;
          btnPlanSingle.textContent = "✨ 开始规划";
        }
      });
    }

    item.addEventListener("click", async () => {
      const selectedId = p.persona_id;
      modalAllPersonas.style.display = "none";
      await refreshAll(selectedId);
      showToast(`已切换至角色: ${p.name || selectedId}`);
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

// 一键自动开始规划今日生活
async function triggerAutoPlan(targetPid) {
  const pid = targetPid || currentScopeKey;
  if (!pid) return;

  const isPlanned = currentOverview && currentOverview.is_today_planned;
  if (
    isPlanned &&
    !confirm(`当前角色 [${pid}] 今天已制定过生活规划，是否重新生成覆盖？`)
  ) {
    return;
  }

  if (btnAutoPlan) {
    btnAutoPlan.disabled = true;
    btnAutoPlan.innerHTML = "<span>⏳</span> 正在生成...";
  }

  try {
    const res = await bridge.apiPost("dashboard/plan/auto_generate", {
      persona_id: pid,
    });
    showToast(res.message || "今日生活规划已制定！");
    await refreshAll();
  } catch (err) {
    showToast(`生成规划失败: ${err.message}`, true);
  } finally {
    if (btnAutoPlan) {
      btnAutoPlan.disabled = false;
    }
  }
}

// 绑定规划按钮
if (btnAutoPlan) {
  btnAutoPlan.addEventListener("click", () => triggerAutoPlan(currentScopeKey));
}

// 打开插件配置模态框
if (btnSettings) {
  btnSettings.addEventListener("click", async () => {
    try {
      const res = await bridge.apiGet("dashboard/config");
      const conf = (res && res.config) || {};

      settingEnabled.checked = conf.enabled !== false;
      settingStorageScope.value = conf.storage_scope || "persona";
      settingInjectGuide.checked = conf.inject_guide !== false;
      settingEnableHoliday.checked = conf.enable_holiday !== false;
      settingEnableOutfit.checked = conf.enable_outfit !== false;

      // 白名单设置回显
      const isWlEnabled = Boolean(conf.enable_persona_whitelist);
      if (settingEnablePersonaWhitelist) {
        settingEnablePersonaWhitelist.checked = isWlEnabled;
      }
      const curWl = conf.persona_whitelist || [];
      if (settingPersonaWhitelistManual) {
        settingPersonaWhitelistManual.value = curWl.join(", ");
      }

      // 动态生成角色复选框
      if (personaCheckboxes) {
        personaCheckboxes.innerHTML = "";
        const pList = allPersonas.length
          ? allPersonas
          : [{ persona_id: "default", name: "default" }];
        pList.forEach((p) => {
          const lbl = document.createElement("label");
          lbl.className = "checkbox-label";
          lbl.style.padding = "4px 8px";
          lbl.style.border = "1px solid var(--border-color)";
          lbl.style.borderRadius = "var(--radius-sm)";
          lbl.style.background = "var(--bg-secondary)";
          lbl.style.fontSize = "13px";
          const isChecked = curWl.includes(p.persona_id);
          lbl.innerHTML = `<input type="checkbox" class="cb-persona-wl" value="${escapeHtml(p.persona_id)}" ${isChecked ? "checked" : ""} /> <span>🎭 ${escapeHtml(p.name || p.persona_id)}</span>`;
          personaCheckboxes.appendChild(lbl);
        });
      }

      const updateWlArea = () => {
        if (whitelistSelectArea && settingEnablePersonaWhitelist) {
          whitelistSelectArea.style.opacity = settingEnablePersonaWhitelist.checked
            ? "1"
            : "0.5";
        }
      };
      updateWlArea();
      if (settingEnablePersonaWhitelist) {
        settingEnablePersonaWhitelist.onchange = updateWlArea;
      }

      settingSmallTtl.value = conf.small_ttl_hours || 24;
      settingOngoingTtl.value = conf.ongoing_ttl_hours || 168;
      settingMaxEvents.value = conf.max_events || 60;
      settingHistoryDays.value =
        conf.history_plan_days !== undefined ? conf.history_plan_days : 2;

      modalSettings.style.display = "flex";
    } catch (err) {
      showToast(`获取插件配置失败: ${err.message}`, true);
    }
  });
}

// 关闭设置模态框
if (btnCloseSettingsModal) {
  btnCloseSettingsModal.addEventListener("click", () => {
    modalSettings.style.display = "none";
  });
}

if (btnCancelSettings) {
  btnCancelSettings.addEventListener("click", () => {
    modalSettings.style.display = "none";
  });
}

if (modalSettings) {
  modalSettings.addEventListener("click", (e) => {
    if (e.target === modalSettings) {
      modalSettings.style.display = "none";
    }
  });
}

// 保存插件配置
if (formSettings) {
  formSettings.addEventListener("submit", async (e) => {
    e.preventDefault();

    // 收集已勾选及自定义添加的 Persona ID
    const selectedPids = new Set();
    document.querySelectorAll(".cb-persona-wl:checked").forEach((cb) => {
      if (cb.value && cb.value.trim()) selectedPids.add(cb.value.trim());
    });
    if (settingPersonaWhitelistManual && settingPersonaWhitelistManual.value) {
      settingPersonaWhitelistManual.value
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .forEach((pid) => selectedPids.add(pid));
    }

    const payload = {
      enabled: settingEnabled.checked,
      storage_scope: settingStorageScope.value,
      inject_guide: settingInjectGuide.checked,
      enable_holiday: settingEnableHoliday.checked,
      enable_outfit: settingEnableOutfit.checked,
      enable_persona_whitelist: settingEnablePersonaWhitelist
        ? settingEnablePersonaWhitelist.checked
        : false,
      persona_whitelist: Array.from(selectedPids),
      small_ttl_hours: Number(settingSmallTtl.value) || 24,
      ongoing_ttl_hours: Number(settingOngoingTtl.value) || 168,
      max_events: Number(settingMaxEvents.value) || 60,
      history_plan_days: Number(settingHistoryDays.value) || 2,
    };

    try {
      const res = await bridge.apiPost("dashboard/config/save", payload);
      showToast(res.message || "插件配置已成功保存！");
      modalSettings.style.display = "none";
      await refreshAll();
    } catch (err) {
      showToast(`保存配置失败: ${err.message}`, true);
    }
  });
}

async function refreshAll(targetKey) {
  if (targetKey) {
    currentScopeKey = targetKey;
  }
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

