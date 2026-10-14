"""仿真实生活 (Life Memory) AstrBot 插件。

为 AI 角色提供拟真的生活记忆层：
- 每天第一次上线规划今日大致做什么；
- 记录当天小事（隔天自动淡忘）与进行中的大事（主动结束或长兜底淘汰）；
- 每轮动态注入生活上下文与规划提醒，让角色的生活线保持前后一致。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core.agent.message import TextPart
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

try:
    from .store import (
        LifeStore,
        extract_current_slot_schedule,
        get_natural_slot_name,
        get_today_holiday,
        is_same_event,
        is_today,
        minute_of_day,
        normalize_text,
        prune_events,
    )
except ImportError:
    from store import (  # type: ignore
        LifeStore,
        extract_current_slot_schedule,
        get_natural_slot_name,
        get_today_holiday,
        is_same_event,
        is_today,
        minute_of_day,
        normalize_text,
        prune_events,
    )

PLUGIN_NAME = "astrbot_plugin_life_memory"

USAGE_GUIDE = (
    "【生活事件记忆（你自己的日子）】\n"
    "· 每天第一次上线，先花一点时间用 life_plan 记下今天大致做什么"
    "（参考：今天天气、你手头进行中的事、你此刻的心绪；偶尔可以有一件突发的小事，不是每天都有）。\n"
    '· 遇到"正在进行、还没结束"的事（在等一个快递、东西写卡住了、跟谁还没和好），'
    "当场用 life_note 传 ongoing=true 记下 —— 记了才跨多轮跨天接得上；"
    "结束了用 life_done 收掉。\n"
    "· 当天的小事（吃了什么、去了哪、买了什么）可以顺手记一条（只记一天就淡忘），不必每件都记。\n"
    '· 想接上"我之前在做什么、在等什么"，用 life_recall 查，别凭空猜。\n'
    '· 别把机制当话题：不说"我刚记了生活事件"这类话。'
)


class LifeMemoryPlugin(Star):
    """仿真实生活插件主类。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        """初始化插件。

        Args:
            context: AstrBot 上下文。
            config: 插件配置字典。
        """
        super().__init__(context)
        self.config = config
        self.store: LifeStore | None = None

        # 注册 Dashboard 可视化视图后端 Web API
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/overview",
            self.api_dashboard_overview,
            ["GET"],
            "Get dashboard overview data",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/events",
            self.api_dashboard_events,
            ["GET"],
            "Get events list",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/event/add",
            self.api_dashboard_add_event,
            ["POST"],
            "Add a life event",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/event/done",
            self.api_dashboard_done_event,
            ["POST"],
            "Mark a life event as done",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/event/delete",
            self.api_dashboard_delete_event,
            ["POST"],
            "Delete a life event",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/plan/save",
            self.api_dashboard_save_plan,
            ["POST"],
            "Save today life plan",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/clear",
            self.api_dashboard_clear,
            ["POST"],
            "Clear all data for a scope",
        )
        context.register_web_api(
            f"/{PLUGIN_NAME}/dashboard/personas",
            self.api_dashboard_personas,
            ["GET"],
            "Get all personas list with life memory summary",
        )

    async def initialize(self) -> None:
        """异步初始化插件，准备存储目录与数据连接。"""
        plugin_data_path = (
            Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_life_memory"
        )
        self.store = LifeStore(
            root_dir=plugin_data_path,
            get_config_func=lambda: dict(self.config),
        )
        self.store.ensure_dir()
        logger.info(
            f"[life-memory] 仿真实生活插件已初始化，数据目录: {plugin_data_path}"
        )

    async def terminate(self) -> None:
        """插件销毁与清理。"""
        logger.info("[life-memory] 仿真实生活插件已卸载")

    def _get_default_persona_id(self) -> str:
        """获取系统默认人格 ID，安全校验类型并兜底 default。"""
        if hasattr(self.context, "persona_manager") and self.context.persona_manager:
            val = getattr(self.context.persona_manager, "default_persona", None)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return "default"

    async def get_event_persona_id(
        self, event: AstrMessageEvent, req: ProviderRequest | None = None
    ) -> str:
        """解析当前事件对应生效的人格唯一标识 (persona_id)。

        按优先级：
        1. 优先读取本轮已暂存到 event extra 中的 persona_id；
        2. 从 req.conversation 中读取 conversation_persona_id；
        3. 从 conversation_manager 中读取当前会话绑定的 persona_id；
        4. 通过 persona_manager.resolve_selected_persona 解析生效的人格；
        5. 兜底回退到系统默认人格 default。

        Args:
            event: AstrBot 消息事件。
            req: ProviderRequest 请求对象（可选）。

        Returns:
            生效的人格标识字符串。
        """
        # 1. 优先读取已暂存的人格标识
        if hasattr(event, "get_extra"):
            extra_pid = event.get_extra("life_memory_persona_id")
            if extra_pid and str(extra_pid).strip():
                return str(extra_pid).strip()

        # 2. 从 req.conversation 中获取
        conv_persona_id = None
        if req and getattr(req, "conversation", None):
            conv_persona_id = getattr(req.conversation, "persona_id", None)

        # 3. 从 conversation_manager 查询当前会话绑定的 persona_id
        umo = getattr(event, "unified_msg_origin", None) or ""
        if (
            not conv_persona_id
            and hasattr(self.context, "conversation_manager")
            and self.context.conversation_manager
            and umo
        ):
            try:
                curr_cid = (
                    await self.context.conversation_manager.get_curr_conversation_id(
                        umo
                    )
                )
                if curr_cid:
                    conv = await self.context.conversation_manager.get_conversation(
                        umo, curr_cid
                    )
                    if conv:
                        conv_persona_id = getattr(conv, "persona_id", None)
            except Exception as e:
                logger.debug(
                    f"[life-memory] 从 conversation_manager 获取 persona_id 失败: {e}"
                )

        # 4. 从 persona_manager 解析生效的人格
        resolved_pid = None
        if hasattr(self.context, "persona_manager") and self.context.persona_manager:
            try:
                platform_name = (
                    event.get_platform_name()
                    if hasattr(event, "get_platform_name")
                    else "unknown"
                )
                (
                    pid,
                    _,
                    _,
                    _,
                ) = await self.context.persona_manager.resolve_selected_persona(
                    umo=umo,
                    conversation_persona_id=conv_persona_id,
                    platform_name=platform_name,
                )
                if pid and isinstance(pid, str):
                    resolved_pid = pid.strip()
            except Exception as e:
                logger.debug(f"[life-memory] 从 persona_manager 解析 persona 失败: {e}")

        # 5. 兜底回退
        if not resolved_pid:
            resolved_pid = self._get_default_persona_id()

        if hasattr(event, "set_extra"):
            event.set_extra("life_memory_persona_id", resolved_pid)

        return resolved_pid

    async def _get_scope_key_async(
        self, event: AstrMessageEvent, req: ProviderRequest | None = None
    ) -> str:
        """异步获取当前事件对应的数据隔离键。

        根据 storage_scope 判断是全局共享还是按人格设定隔离。

        Args:
            event: 消息事件。
            req: LLM 请求对象（可选）。

        Returns:
            存储作用域标识字符串（全局为 __global__，否则为 persona_id）。
        """
        scope = str(self.config.get("storage_scope", "persona")).lower().strip()
        if scope == "global":
            return "__global__"
        # 默认按人格隔离（包含旧 session 配置平滑迁移）
        return await self.get_event_persona_id(event, req)

    def _get_scope_key(self, event: AstrMessageEvent) -> str:
        """获取当前事件对应的数据隔离键（同步降级）。

        Args:
            event: 消息事件。

        Returns:
            存储作用域标识字符串。
        """
        scope = str(self.config.get("storage_scope", "persona")).lower().strip()
        if scope == "global":
            return "__global__"
        if hasattr(event, "get_extra"):
            extra_pid = event.get_extra("life_memory_persona_id")
            if extra_pid and str(extra_pid).strip():
                return str(extra_pid).strip()
        return self._get_default_persona_id()

    async def get_all_personas_data(self) -> list[dict[str, Any]]:
        """获取系统中所有人格的元数据与其生活记忆概览。

        聚合 AstrBot 系统中的 Persona 定义与磁盘上已存在的生活数据。

        Returns:
            包含各人格 ID、设定预览、今日规划状态、事件统计的列表。
        """
        persona_map: dict[str, dict[str, Any]] = {}
        default_pid = self._get_default_persona_id()

        # 1. 从 persona_manager 读取系统已配置的人格
        if hasattr(self.context, "persona_manager") and self.context.persona_manager:
            pm = self.context.persona_manager

            # 优先从数据库查询
            try:
                if hasattr(pm, "get_all_personas"):
                    db_personas = await pm.get_all_personas()
                    for p in db_personas:
                        pid = str(getattr(p, "persona_id", "")).strip()
                        if not pid:
                            continue
                        prompt = str(getattr(p, "system_prompt", "") or "")
                        persona_map[pid] = {
                            "persona_id": pid,
                            "name": pid,
                            "system_prompt": prompt,
                            "system_prompt_preview": prompt[:160]
                            + ("..." if len(prompt) > 160 else ""),
                            "is_default": pid == default_pid,
                            "has_data": False,
                        }
            except Exception as e:
                logger.debug(f"[life-memory] get_all_personas 读取失败: {e}")

            # 补充从 personas_v3 读取
            if hasattr(pm, "personas_v3") and pm.personas_v3:
                for item in pm.personas_v3:
                    if isinstance(item, dict):
                        pid = str(item.get("name", "")).strip()
                        if pid and pid not in persona_map:
                            prompt = str(item.get("prompt", "") or "")
                            persona_map[pid] = {
                                "persona_id": pid,
                                "name": pid,
                                "system_prompt": prompt,
                                "system_prompt_preview": prompt[:160]
                                + ("..." if len(prompt) > 160 else ""),
                                "is_default": pid == default_pid,
                                "has_data": False,
                            }

        # 确保 default 人格存在
        if default_pid not in persona_map:
            persona_map[default_pid] = {
                "persona_id": default_pid,
                "name": default_pid,
                "system_prompt": "系统默认人格设定",
                "system_prompt_preview": "系统默认人格设定",
                "is_default": True,
                "has_data": False,
            }

        # 2. 结合磁盘上已有的生活数据 scopes
        if self.store:
            scopes = self.store.list_scopes()
            for s in scopes:
                if s not in persona_map:
                    persona_map[s] = {
                        "persona_id": s,
                        "name": s,
                        "system_prompt": "",
                        "system_prompt_preview": "（未在系统中配置的角色或历史数据）",
                        "is_default": s == default_pid,
                        "has_data": True,
                    }

        # 3. 统计每个人格的生活记忆数据
        results: list[dict[str, Any]] = []
        for pid, info in persona_map.items():
            if self.store:
                events = self.store.prune_and_get(pid)
                plan = self.store.read_plan(pid)
                ongoing = [e for e in events if e.get("ongoing")]
                today_events = [
                    e for e in events if not e.get("ongoing") and is_today(e.get("at"))
                ]
                has_today_plan = bool(plan and is_today(plan.get("date")))
                has_data = bool(events or plan)

                info["has_data"] = has_data
                info["is_today_planned"] = has_today_plan
                info["plan_summary"] = (
                    str(plan.get("day", "")) if has_today_plan and plan else ""
                )
                info["ongoing_count"] = len(ongoing)
                info["today_count"] = len(today_events)
                info["events_count"] = len(events)
            else:
                info["has_data"] = False
                info["is_today_planned"] = False
                info["plan_summary"] = ""
                info["ongoing_count"] = 0
                info["today_count"] = 0
                info["events_count"] = 0

            results.append(info)

        # 排序：默认人格放最前，其余按 persona_id 字母排序
        results.sort(
            key=lambda x: (not x.get("is_default", False), x.get("persona_id", ""))
        )
        return results

    def _is_session_enabled(self, unified_msg_origin: str) -> bool:
        """检查当前会话是否在允许的启用范围内。

        Args:
            unified_msg_origin: 统一消息来源标识。

        Returns:
            若当前会话允许启用返回 True，否则返回 False。
        """
        mode = str(self.config.get("session_list_mode", "all")).lower().strip()
        if mode == "all":
            return True
        session_list = [
            str(x).strip()
            for x in self.config.get("session_list", [])
            if str(x).strip()
        ]
        if mode == "whitelist":
            return unified_msg_origin in session_list
        if mode == "blacklist":
            return unified_msg_origin not in session_list
        return True

    # ==========================================
    # 大语言模型工具 (LLM Tools)
    # ==========================================

    @filter.llm_tool(name="life_note")
    async def life_note(
        self, event: AstrMessageEvent, content: str, ongoing: bool = False
    ) -> str:
        """记一条你自己的生活事件。

        Args:
            content(string): 事件内容，简短一点（60字以内）。
            ongoing(boolean): 是否正在进行中。进行中的事会一直记到结束；已过去的小事传 false。
        """
        try:
            if not self.config.get("enabled", True):
                return "仿真实生活功能已禁用，未记录。"
            if not self._is_session_enabled(event.unified_msg_origin or ""):
                return "当前会话未启用生活记忆。"
            text = str(content or "").strip()[:120]
            if not text:
                return "内容为空，未记录。"
            if not self.store:
                return "存储未就绪，记录失败。"

            scope_key = await self._get_scope_key_async(event)
            async with self.store.get_scope_lock(scope_key):
                events = self.store.prune_and_get(scope_key)
                now_ms = int(time.time() * 1000)

                # 检查去重与续期
                existing = None
                for e in events:
                    if is_same_event(e.get("text"), text):
                        existing = e
                        break

                if existing:
                    existing["touched_at"] = now_ms
                    existing["ongoing"] = bool(existing.get("ongoing")) or bool(ongoing)
                    if len(normalize_text(text)) > len(
                        normalize_text(str(existing.get("text", "")))
                    ):
                        existing["text"] = text
                    self.store.write_events(scope_key, events)
                    state = "（进行中）" if existing.get("ongoing") else ""
                    return f"这条之前记过，已续期：{existing['text']}{state}"

                new_event = {
                    "id": f"{now_ms}-{uuid.uuid4().hex[:5]}",
                    "at": now_ms,
                    "touched_at": now_ms,
                    "text": text,
                    "ongoing": bool(ongoing),
                }
                events.append(new_event)
                self.store.write_events(scope_key, events)
                state = "（进行中）" if ongoing else ""
                return f"已记下：{text}{state}"
        except Exception as e:
            logger.error(f"[life-memory] life_note 失败: {e}", exc_info=True)
            return f"记录失败：{e}"

    @filter.llm_tool(name="life_recall")
    async def life_recall(self, event: AstrMessageEvent) -> str:
        """回忆自己最近的生活事件：正在进行的事 + 近期的小事 + 近日规划脉络。当你想接上“我之前在做什么/在等什么”时用它，别凭空猜。"""
        try:
            if not self.config.get("enabled", True):
                return "仿真实生活功能已禁用。"
            if not self._is_session_enabled(event.unified_msg_origin or ""):
                return "当前会话未启用生活记忆。"
            if not self.store:
                return "存储未就绪。"

            scope_key = await self._get_scope_key_async(event)
            events = self.store.prune_and_get(scope_key)
            now_ms = int(time.time() * 1000)
            small_ttl_hours = float(self.config.get("small_ttl_hours", 24.0))
            small_ttl_ms = small_ttl_hours * 3600 * 1000

            ongoing = [e for e in events if e.get("ongoing")]
            recent = [
                e
                for e in events
                if not e.get("ongoing")
                and (now_ms - int(e.get("touched_at") or e.get("at") or 0))
                <= small_ttl_ms
            ]

            parts = []
            if ongoing:
                parts.append(
                    "进行中的事：" + "；".join(str(e.get("text")) for e in ongoing)
                )
            if recent:
                parts.append(
                    "今天的小事：" + "；".join(str(e.get("text")) for e in recent)
                )

            # 历史规划脉络参考
            hist_days = int(self.config.get("history_plan_days", 2))
            if hist_days > 0:
                hist_plans = self.store.get_recent_plan_history(
                    scope_key, limit=hist_days
                )
                if hist_plans:
                    hist_descs = [
                        f"{time.strftime('%m-%d', time.localtime(float(h.get('date', 0)) / 1000.0))} 做了「{h.get('day', '')}」"
                        for h in hist_plans
                        if h.get("day")
                    ]
                    if hist_descs:
                        parts.append("前几日生活：" + "；".join(hist_descs))

            if not parts:
                return "近期没记生活事件（或都已淡忘）。"

            return "\n".join(parts)
        except Exception as e:
            logger.error(f"[life-memory] life_recall 失败: {e}", exc_info=True)
            return f"回忆失败：{e}"

    @filter.llm_tool(name="life_done")
    async def life_done(self, event: AstrMessageEvent, content: str) -> str:
        """把一条“进行中”的生活事件标记为结束。传关键词匹配包含该词的进行中事件。

        Args:
            content(string): 要结束的事件关键词。
        """
        try:
            if not self.config.get("enabled", True):
                return "仿真实生活功能已禁用。"
            if not self._is_session_enabled(event.unified_msg_origin or ""):
                return "当前会话未启用生活记忆。"
            kw = str(content or "").strip()
            if not kw:
                return "没有提供关键词。"
            if not self.store:
                return "存储未就绪。"

            scope_key = await self._get_scope_key_async(event)
            async with self.store.get_scope_lock(scope_key):
                events = self.store.read_events(scope_key)
                done_count = 0
                now_ms = int(time.time() * 1000)

                for e in events:
                    if e.get("ongoing") and kw in str(e.get("text", "")):
                        e["ongoing"] = False
                        e["ended_at"] = now_ms
                        done_count += 1

                if done_count > 0:
                    cleaned = prune_events(
                        events,
                        small_ttl_hours=float(self.config.get("small_ttl_hours", 24.0)),
                        ongoing_ttl_hours=float(
                            self.config.get("ongoing_ttl_hours", 168.0)
                        ),
                        max_events=int(self.config.get("max_events", 60)),
                    )
                    self.store.write_events(scope_key, cleaned)
                    return f"已结束 {done_count} 条进行中的事。"
                return f"没找到包含「{kw}」的进行中的事。"
        except Exception as e:
            logger.error(f"[life-memory] life_done 失败: {e}", exc_info=True)
            return f"结束失败：{e}"

    @filter.llm_tool(name="life_plan")
    async def life_plan(
        self,
        event: AstrMessageEvent,
        day: str,
        twist: str = "",
        weather: str = "",
        outfit: str = "",
        mood: str = "",
        location: str = "",
    ) -> str:
        """规划今天的生活。每天第一次上线时记下今天大致做什么。

        Args:
            day(string): 今天大致做什么，一两行说清（如：上午写稿，下午去超市买菜）。
            twist(string): 今天有没有突发的小事（偶尔有，不是每天，没有就留空）。
            weather(string): 今天天气，可留空。
            outfit(string): 今天穿搭风格（选填，如：浅色宽松卫衣、舒适运动鞋）。
            mood(string): 今天心情或心境（选填，如：专注、平静、有些困意）。
            location(string): 当前主要所在地点（选填，如：家、书房、咖啡馆）。
        """
        try:
            if not self.config.get("enabled", True):
                return "仿真实生活功能已禁用。"
            if not self._is_session_enabled(event.unified_msg_origin or ""):
                return "当前会话未启用生活记忆。"
            day_text = str(day or "").strip()[:200]
            if not day_text:
                return "未填写规划内容，未记录。"
            if not self.store:
                return "存储未就绪。"

            scope_key = await self._get_scope_key_async(event)
            async with self.store.get_scope_lock(scope_key):
                now_ms = int(time.time() * 1000)
                holiday = "无"
                if bool(self.config.get("enable_holiday", True)):
                    holiday = get_today_holiday()

                plan_data = {
                    "date": now_ms,
                    "day": day_text,
                    "twist": str(twist or "").strip()[:80],
                    "weather": str(weather or "").strip()[:40],
                    "holiday": holiday,
                }
                if (
                    bool(self.config.get("enable_outfit", True))
                    and str(outfit or "").strip()
                ):
                    plan_data["outfit"] = str(outfit).strip()[:60]
                if str(mood or "").strip():
                    plan_data["mood"] = str(mood).strip()[:40]
                if str(location or "").strip():
                    plan_data["location"] = str(location).strip()[:60]

                self.store.write_plan(scope_key, plan_data)

                extras = []
                if plan_data.get("twist"):
                    extras.append(f"偶发：{plan_data['twist']}")
                if plan_data.get("weather"):
                    extras.append(f"天气：{plan_data['weather']}")
                if plan_data.get("outfit"):
                    extras.append(f"穿搭：{plan_data['outfit']}")
                if plan_data.get("mood"):
                    extras.append(f"心情：{plan_data['mood']}")
                if plan_data.get("holiday") and plan_data["holiday"] != "无":
                    extras.append(f"节日：🎉 {plan_data['holiday']}")

                extra_desc = f"（{'，'.join(extras)}）" if extras else ""
                return f"已记下今天的规划：{day_text}{extra_desc}"
        except Exception as e:
            logger.error(f"[life-memory] life_plan 失败: {e}", exc_info=True)
            return f"规划失败：{e}"

    # ==========================================
    # 动态提示词注入 (Prompt Injection)
    # ==========================================

    @filter.on_llm_request()
    async def inject_life_context(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """在请求 LLM 前动态注入生活事件上下文与使用引导。"""
        try:
            if not self.config.get("enabled", True):
                return
            if not self._is_session_enabled(event.unified_msg_origin or ""):
                return
            if not self.store:
                return

            scope_key = await self._get_scope_key_async(event, req)
            events = self.store.prune_and_get(scope_key)
            plan = self.store.read_plan(scope_key)

            ongoing = [e for e in events if e.get("ongoing")][:3]
            today_events = [
                e for e in events if not e.get("ongoing") and is_today(e.get("at"))
            ][:5]
            today_plan = plan if (plan and is_today(plan.get("date"))) else None

            guide_enabled = bool(self.config.get("inject_guide", True))
            if (
                not guide_enabled
                and not ongoing
                and not today_events
                and not today_plan
            ):
                return

            sections: list[str] = []

            # 1. 引导提示
            if guide_enabled:
                sections.append(USAGE_GUIDE)

            # 2. 进行中的事
            if ongoing:
                if guide_enabled:
                    lines = [
                        "【你正在进行中的生活事件（还没结束，聊到相关话题要接着它，别当成已经过去）】"
                    ]
                    lines.extend(f"· {e.get('text')}" for e in ongoing)
                    sections.append("\n".join(lines))
                else:
                    items = "；".join(str(e.get("text")) for e in ongoing)
                    sections.append(
                        f"你正在进行中的生活事件（还没结束，聊到相关话题要接着它，别当成已经过去）：{items}。"
                    )

            # 3. 今天做过的事
            if today_events:
                if guide_enabled:
                    lines = [
                        '【你今天做过的事（他问"今天干了什么""出门没""吃没吃"这类，一律以这里为准；这里没写的别编，就说没干或不确定）】'
                    ]
                    lines.extend(f"· {e.get('text')}" for e in today_events)
                    sections.append("\n".join(lines))
                else:
                    items = "；".join(str(e.get("text")) for e in today_events)
                    sections.append(
                        f"你今天做过的事（他问到就以此为准，没写的别编）：{items}。"
                    )

            # 4. 今日生活规划与当前时段状态
            if today_plan:
                current_slot, slot_schedule = extract_current_slot_schedule(today_plan)
                if guide_enabled:
                    plan_lines = [
                        f"【你今天的生活规划与基调（当前时段：{current_slot}，聊到相关话题以此为准）】",
                        f"· 今日规划：{today_plan.get('day', '')}",
                    ]
                    if slot_schedule and slot_schedule != today_plan.get("day"):
                        plan_lines.append(f"· 当前{current_slot}安排：{slot_schedule}")
                    if today_plan.get("weather"):
                        plan_lines.append(f"· 天气：{today_plan['weather']}")
                    if today_plan.get("twist"):
                        plan_lines.append(f"· 偶发：{today_plan['twist']}")
                    if bool(self.config.get("enable_outfit", True)) and today_plan.get(
                        "outfit"
                    ):
                        plan_lines.append(f"· 今日穿搭：{today_plan['outfit']}")
                    if today_plan.get("mood"):
                        plan_lines.append(f"· 当前心情：{today_plan['mood']}")
                    if today_plan.get("location"):
                        plan_lines.append(f"· 当前地点：{today_plan['location']}")
                    if (
                        bool(self.config.get("enable_holiday", True))
                        and today_plan.get("holiday")
                        and today_plan["holiday"] != "无"
                    ):
                        plan_lines.append(f"· 今日节日：🎉 {today_plan['holiday']}")
                    sections.append("\n".join(plan_lines))
                else:
                    parts_sub = [f"今日规划：{today_plan.get('day', '')}"]
                    if slot_schedule and slot_schedule != today_plan.get("day"):
                        parts_sub.append(f"当前{current_slot}正在做：{slot_schedule}")
                    if today_plan.get("twist"):
                        parts_sub.append(f"偶发：{today_plan['twist']}")
                    if bool(self.config.get("enable_outfit", True)) and today_plan.get(
                        "outfit"
                    ):
                        parts_sub.append(f"穿搭：{today_plan['outfit']}")
                    if today_plan.get("mood"):
                        parts_sub.append(f"心情：{today_plan['mood']}")
                    sections.append("；".join(parts_sub) + "。")
            else:
                # 今天还没规划，查询最近历史规划提供承接参考
                hist_days = int(self.config.get("history_plan_days", 2))
                hist_ref = ""
                if hist_days > 0:
                    hist_plans = self.store.get_recent_plan_history(
                        scope_key, limit=hist_days
                    )
                    if hist_plans and hist_plans[0].get("day"):
                        hist_ref = f"（参考：昨日规划为「{hist_plans[0]['day']}」）"

                current_slot = get_natural_slot_name(minute_of_day())
                if guide_enabled:
                    sections.append(
                        f"【今天还没规划】现在是{current_slot}，今天是新的一天，你还没规划今天{hist_ref}。"
                        "现在就用 life_plan 记下今天大致做什么"
                        "（参考：当前时段、今天天气、你手头进行中的事、你此刻的心绪与穿搭；偶发小事非每天有）。规划完再回他。"
                    )
                else:
                    sections.append(
                        f"现在是{current_slot}，今天还没规划{hist_ref}：先用 life_plan 记下今天大致做什么。"
                    )

            if sections:
                prompt_text = "\n\n".join(sections)
                # 使用 mark_as_temp()，只在本轮生效，不污染对话历史与服务端缓存
                req.extra_user_content_parts.append(
                    TextPart(
                        text=f"<life_memory>\n{prompt_text}\n</life_memory>"
                    ).mark_as_temp()
                )
        except Exception as e:
            logger.error(f"[life-memory] 动态提示词注入异常: {e}", exc_info=True)

    # ==========================================
    # 用户 / 管理员指令体系
    # ==========================================

    @filter.command_group("life")
    def life(self) -> None:
        """生活记忆指令组。"""

    @life.command("status")
    async def status(self, event: AstrMessageEvent, persona_id: str = ""):
        """查看当前生活记忆状态与今日规划。可选传入指定 persona_id。"""
        if not self.store:
            yield event.plain_result("存储未初始化。")
            return
        target_pid = str(persona_id or "").strip()
        if not target_pid:
            target_pid = await self._get_scope_key_async(event)
        scope_key = target_pid
        events = self.store.prune_and_get(scope_key)
        plan = self.store.read_plan(scope_key)

        ongoing = [e for e in events if e.get("ongoing")]
        today_events = [
            e for e in events if not e.get("ongoing") and is_today(e.get("at"))
        ]
        has_today_plan = plan and is_today(plan.get("date"))
        current_minute = minute_of_day()
        current_slot = get_natural_slot_name(current_minute)
        now_time_str = f"{current_minute // 60:02d}:{current_minute % 60:02d}"

        lines = [
            "【生活记忆状态】",
            f"· 当前人格: {scope_key}",
            f"· 当前时间/时段: {now_time_str}（{current_slot}）",
            f"· 事件总数: {len(events)} 条",
            f"· 进行中大事: {len(ongoing)} 条",
            f"· 今日小事: {len(today_events)} 条",
        ]
        if has_today_plan and plan:
            lines.append(f"· 今日规划: {plan.get('day', '')}")
            if plan.get("twist"):
                lines.append(f"  偶发事件: {plan.get('twist')}")
            if plan.get("weather"):
                lines.append(f"  今日天气: {plan.get('weather')}")
            if plan.get("outfit"):
                lines.append(f"  今日穿搭: {plan.get('outfit')}")
            if plan.get("mood"):
                lines.append(f"  当前心情: {plan.get('mood')}")
            if plan.get("location"):
                lines.append(f"  当前地点: {plan.get('location')}")
            if plan.get("holiday") and plan.get("holiday") != "无":
                lines.append(f"  今日节日: 🎉 {plan.get('holiday')}")
        else:
            lines.append("· 今日规划: 尚未规划")

        yield event.plain_result("\n".join(lines))

    @life.command("recall")
    async def cmd_recall(self, event: AstrMessageEvent, persona_id: str = ""):
        """手动回忆生活事件。可选传入指定 persona_id。"""
        target_pid = str(persona_id or "").strip()
        if target_pid and hasattr(event, "set_extra"):
            event.set_extra("life_memory_persona_id", target_pid)
        res = await self.life_recall(event)
        yield event.plain_result(res)

    @life.command("plan")
    async def cmd_plan(self, event: AstrMessageEvent, content: str):
        """手动设置今日生活规划。"""
        res = await self.life_plan(event, day=content)
        yield event.plain_result(res)

    @life.command("clear")
    async def cmd_clear(self, event: AstrMessageEvent, persona_id: str = ""):
        """清空指定人格的生活记忆数据。可选传入指定 persona_id。"""
        if not self.store:
            yield event.plain_result("存储未初始化。")
            return
        target_pid = str(persona_id or "").strip()
        if not target_pid:
            target_pid = await self._get_scope_key_async(event)
        scope_key = target_pid
        self.store.clear(scope_key)
        yield event.plain_result(
            f"已清空作用域（人格 [{scope_key}]）的所有生活事件与规划。"
        )

    # ==========================================
    # 可视化视图后端 Web API Handlers
    # ==========================================

    def _resolve_scope_key(self, raw_scope: str | None = None) -> str:
        """解析当前 Dashboard 请求的目标人格作用域标识。"""
        scope_setting = str(self.config.get("storage_scope", "persona")).lower().strip()
        if scope_setting == "global":
            return "__global__"
        if raw_scope and str(raw_scope).strip():
            safe = str(raw_scope).strip()
            return self.store.get_safe_key(safe) if self.store else safe
        return self._get_default_persona_id()

    async def api_dashboard_personas(self):
        """Dashboard 获取所有人格列表及其生活记忆概览接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        try:
            personas_data = await self.get_all_personas_data()
            default_pid = self._get_default_persona_id()
            return json_response(
                {
                    "personas": personas_data,
                    "default_persona_id": default_pid,
                    "total": len(personas_data),
                }
            )
        except Exception as e:
            logger.error(f"[life-memory] 获取 personas 列表失败: {e}", exc_info=True)
            return error_response(f"获取人格列表失败: {e}", status_code=500)

    async def api_dashboard_overview(self):
        """Dashboard 数据概览接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        raw_scope = request.query.get("persona_id") or request.query.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        all_personas = await self.get_all_personas_data()
        scopes = [p["persona_id"] for p in all_personas]
        if scope_key not in scopes and scope_key:
            scopes.insert(0, scope_key)

        current_persona = next(
            (p for p in all_personas if p["persona_id"] == scope_key), None
        )

        events = self.store.prune_and_get(scope_key)
        plan = self.store.read_plan(scope_key)
        ongoing = [e for e in events if e.get("ongoing")]
        today_events = [
            e for e in events if not e.get("ongoing") and is_today(e.get("at"))
        ]
        has_today_plan = bool(plan and is_today(plan.get("date")))
        current_minute = minute_of_day()
        current_slot = get_natural_slot_name(current_minute)
        today_holiday = get_today_holiday()
        history_plans = self.store.get_recent_plan_history(scope_key, limit=5)

        return json_response(
            {
                "storage_scope": str(self.config.get("storage_scope", "persona")),
                "current_scope_key": scope_key,
                "current_persona_id": scope_key,
                "current_persona_name": current_persona.get("name")
                if current_persona
                else scope_key,
                "current_persona_prompt": current_persona.get("system_prompt")
                if current_persona
                else "",
                "current_persona_preview": current_persona.get("system_prompt_preview")
                if current_persona
                else "",
                "is_default_persona": bool(current_persona.get("is_default"))
                if current_persona
                else (scope_key == "default"),
                "current_slot": current_slot,
                "current_time_str": f"{current_minute // 60:02d}:{current_minute % 60:02d}",
                "today_holiday": today_holiday,
                "history_plans": history_plans,
                "scopes": scopes,
                "personas": all_personas,
                "events_count": len(events),
                "ongoing_count": len(ongoing),
                "today_count": len(today_events),
                "max_events": int(self.config.get("max_events", 60)),
                "small_ttl_hours": float(self.config.get("small_ttl_hours", 24.0)),
                "ongoing_ttl_hours": float(self.config.get("ongoing_ttl_hours", 168.0)),
                "enabled": bool(self.config.get("enabled", True)),
                "inject_guide": bool(self.config.get("inject_guide", True)),
                "enable_holiday": bool(self.config.get("enable_holiday", True)),
                "enable_outfit": bool(self.config.get("enable_outfit", True)),
                "is_today_planned": has_today_plan,
                "plan": plan if has_today_plan else None,
            }
        )

    async def api_dashboard_events(self):
        """Dashboard 事件列表接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        raw_scope = request.query.get("persona_id") or request.query.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        events = self.store.prune_and_get(scope_key)
        result = []
        for e in reversed(events):
            item = dict(e)
            item["is_today"] = is_today(e.get("at"))
            result.append(item)
        return json_response(
            {
                "events": result,
                "scope_key": scope_key,
                "persona_id": scope_key,
            }
        )

    async def api_dashboard_add_event(self):
        """Dashboard 手动新增生活事件接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        content = str(payload.get("content", "")).strip()[:120]
        if not content:
            return error_response("事件内容不能为空", status_code=400)
        ongoing = bool(payload.get("ongoing", False))
        raw_scope = payload.get("persona_id") or payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        async with self.store.get_scope_lock(scope_key):
            events = self.store.prune_and_get(scope_key)
            now_ms = int(time.time() * 1000)

            existing = None
            for e in events:
                if is_same_event(e.get("text"), content):
                    existing = e
                    break

            if existing:
                existing["touched_at"] = now_ms
                existing["ongoing"] = bool(existing.get("ongoing")) or ongoing
                if len(normalize_text(content)) > len(
                    normalize_text(str(existing.get("text", "")))
                ):
                    existing["text"] = content
                self.store.write_events(scope_key, events)
                return json_response(
                    {
                        "status": "renewed",
                        "event": existing,
                        "message": "相似事件已存在，已自动续期触碰时间",
                    }
                )

            new_event = {
                "id": f"{now_ms}-{uuid.uuid4().hex[:5]}",
                "at": now_ms,
                "touched_at": now_ms,
                "text": content,
                "ongoing": ongoing,
            }
            events.append(new_event)
            self.store.write_events(scope_key, events)
            return json_response(
                {
                    "status": "created",
                    "event": new_event,
                    "message": "事件已成功记录",
                }
            )

    async def api_dashboard_done_event(self):
        """Dashboard 标记事件结束接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        event_id = str(payload.get("event_id", "")).strip()
        if not event_id:
            return error_response("缺少事件 ID", status_code=400)
        raw_scope = payload.get("persona_id") or payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        async with self.store.get_scope_lock(scope_key):
            ok = self.store.mark_event_done(scope_key, event_id)
            if ok:
                return json_response({"success": True, "message": "事件已标记结束"})
            return error_response("未找到该进行中事件或已结束", status_code=404)

    async def api_dashboard_delete_event(self):
        """Dashboard 删除指定事件接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        event_id = str(payload.get("event_id", "")).strip()
        if not event_id:
            return error_response("缺少事件 ID", status_code=400)
        raw_scope = payload.get("persona_id") or payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        async with self.store.get_scope_lock(scope_key):
            ok = self.store.delete_event(scope_key, event_id)
            if ok:
                return json_response({"success": True, "message": "事件已删除"})
            return error_response("未找到该事件", status_code=404)

    async def api_dashboard_save_plan(self):
        """Dashboard 保存今日规划接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        day = str(payload.get("day", "")).strip()[:200]
        if not day:
            return error_response("规划内容不能为空", status_code=400)
        twist = str(payload.get("twist", "")).strip()[:80]
        weather = str(payload.get("weather", "")).strip()[:40]
        outfit = str(payload.get("outfit", "")).strip()[:60]
        mood = str(payload.get("mood", "")).strip()[:40]
        location = str(payload.get("location", "")).strip()[:60]
        holiday = str(payload.get("holiday", "")).strip()[:40] or get_today_holiday()
        raw_scope = payload.get("persona_id") or payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        async with self.store.get_scope_lock(scope_key):
            now_ms = int(time.time() * 1000)
            plan_data = {
                "date": now_ms,
                "day": day,
                "twist": twist,
                "weather": weather,
                "holiday": holiday,
            }
            if outfit:
                plan_data["outfit"] = outfit
            if mood:
                plan_data["mood"] = mood
            if location:
                plan_data["location"] = location

            self.store.write_plan(scope_key, plan_data)
            return json_response(
                {
                    "success": True,
                    "plan": plan_data,
                    "message": f"人格 [{scope_key}] 今日规划已成功更新",
                }
            )

    async def api_dashboard_clear(self):
        """Dashboard 清空作用域数据接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        raw_scope = payload.get("persona_id") or payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        async with self.store.get_scope_lock(scope_key):
            self.store.clear(scope_key)
            return json_response(
                {
                    "success": True,
                    "message": f"已清空人格 [{scope_key}] 的所有生活数据",
                }
            )
