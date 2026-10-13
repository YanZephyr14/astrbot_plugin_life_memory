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
        is_same_event,
        is_today,
        normalize_text,
        prune_events,
    )
except ImportError:
    from store import (  # type: ignore
        LifeStore,
        is_same_event,
        is_today,
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

    def _get_scope_key(self, event: AstrMessageEvent) -> str:
        """获取当前事件对应的数据隔离键。

        根据配置中的 storage_scope 判断是全局共享还是会话级独立隔离。

        Args:
            event: 消息事件。

        Returns:
            存储作用域标识字符串。
        """
        scope = str(self.config.get("storage_scope", "session")).lower()
        if scope == "global":
            return "__global__"
        return event.unified_msg_origin or event.get_session_id() or "__default__"

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
            text = str(content or "").strip()[:120]
            if not text:
                return "内容为空，未记录。"
            if not self.store:
                return "存储未就绪，记录失败。"

            scope_key = self._get_scope_key(event)
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

            import uuid

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
        """回忆自己最近的生活事件：正在进行的事 + 近期的小事。当你想接上“我之前在做什么/在等什么”时用它，别凭空猜。"""
        try:
            if not self.config.get("enabled", True):
                return "仿真实生活功能已禁用。"
            if not self.store:
                return "存储未就绪。"

            scope_key = self._get_scope_key(event)
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

            if not ongoing and not recent:
                return "近期没记生活事件（或都已淡忘）。"

            parts = []
            if ongoing:
                parts.append(
                    "进行中的事：" + "；".join(str(e.get("text")) for e in ongoing)
                )
            if recent:
                parts.append(
                    "今天的小事：" + "；".join(str(e.get("text")) for e in recent)
                )
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
            kw = str(content or "").strip()
            if not kw:
                return "没有提供关键词。"
            if not self.store:
                return "存储未就绪。"

            scope_key = self._get_scope_key(event)
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
    ) -> str:
        """规划今天的生活。每天第一次上线时记下今天大致做什么。

        Args:
            day(string): 今天大致做什么，一两行说清。
            twist(string): 今天有没有突发的小事（偶尔有，不是每天，没有就留空）。
            weather(string): 今天天气，可留空。
        """
        try:
            if not self.config.get("enabled", True):
                return "仿真实生活功能已禁用。"
            day_text = str(day or "").strip()[:200]
            if not day_text:
                return "未填写规划内容，未记录。"
            if not self.store:
                return "存储未就绪。"

            scope_key = self._get_scope_key(event)
            now_ms = int(time.time() * 1000)
            plan_data = {
                "date": now_ms,
                "day": day_text,
                "twist": str(twist or "").strip()[:80],
                "weather": str(weather or "").strip()[:40],
            }
            self.store.write_plan(scope_key, plan_data)
            twist_desc = f"（偶发：{plan_data['twist']}）" if plan_data["twist"] else ""
            weather_desc = (
                f"（天气：{plan_data['weather']}）" if plan_data["weather"] else ""
            )
            return f"已记下今天的规划：{day_text}{twist_desc}{weather_desc}"
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
            if not self.store:
                return

            scope_key = self._get_scope_key(event)
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

            # 4. 今日生活规划
            if today_plan:
                if guide_enabled:
                    plan_lines = [
                        '【你今天的生活规划（他问"今天打算做什么""今天怎么样"时以这个为底；实际做没做、有没有变化，用 life_note 记实际发生的）】',
                        f"· {today_plan.get('day', '')}",
                    ]
                    if today_plan.get("weather"):
                        plan_lines.append(f"· 天气：{today_plan['weather']}")
                    if today_plan.get("twist"):
                        plan_lines.append(f"· 偶发：{today_plan['twist']}")
                    sections.append("\n".join(plan_lines))
                else:
                    twist_part = (
                        f"；偶发：{today_plan['twist']}"
                        if today_plan.get("twist")
                        else ""
                    )
                    sections.append(
                        f"你今天的生活规划：{today_plan.get('day', '')}{twist_part}。"
                    )
            else:
                # 今天还没规划，注入提醒
                if guide_enabled:
                    sections.append(
                        "【今天还没规划】今天是新的一天，你还没规划今天。现在就用 life_plan 记下今天大致做什么"
                        "（参考：今天天气、你手头进行中的事、你此刻的心绪；偶尔可以有一件突发的小事，不是每天都有）。规划完再回他。"
                    )
                else:
                    sections.append("今天还没规划：先用 life_plan 记下今天大致做什么。")

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
    async def status(self, event: AstrMessageEvent):
        """查看当前生活记忆状态与今日规划。"""
        if not self.store:
            yield event.plain_result("存储未初始化。")
            return
        scope_key = self._get_scope_key(event)
        events = self.store.prune_and_get(scope_key)
        plan = self.store.read_plan(scope_key)

        ongoing = [e for e in events if e.get("ongoing")]
        today_events = [
            e for e in events if not e.get("ongoing") and is_today(e.get("at"))
        ]
        has_today_plan = plan and is_today(plan.get("date"))

        lines = [
            "【生活记忆状态】",
            f"· 当前作用域: {scope_key}",
            f"· 事件总数: {len(events)} 条",
            f"· 进行中大事: {len(ongoing)} 条",
            f"· 今日小事: {len(today_events)} 条",
        ]
        if has_today_plan and plan:
            lines.append(f"· 今日规划: {plan.get('day', '')}")
            if plan.get("twist"):
                lines.append(f"  偶发事件: {plan.get('twist')}")
            if plan.get("weather"):
                lines.append(f"  天气: {plan.get('weather')}")
        else:
            lines.append("· 今日规划: 尚未规划")

        yield event.plain_result("\n".join(lines))

    @life.command("recall")
    async def cmd_recall(self, event: AstrMessageEvent):
        """手动回忆生活事件。"""
        res = await self.life_recall(event)
        yield event.plain_result(res)

    @life.command("plan")
    async def cmd_plan(self, event: AstrMessageEvent, content: str):
        """手动设置今日生活规划。"""
        res = await self.life_plan(event, day=content)
        yield event.plain_result(res)

    @life.command("clear")
    async def cmd_clear(self, event: AstrMessageEvent):
        """清空当前会话的生活记忆数据。"""
        if not self.store:
            yield event.plain_result("存储未初始化。")
            return
        scope_key = self._get_scope_key(event)
        self.store.clear(scope_key)
        yield event.plain_result(f"已清空作用域 [{scope_key}] 的所有生活事件与规划。")

    # ==========================================
    # 可视化视图后端 Web API Handlers
    # ==========================================

    def _resolve_scope_key(self, raw_scope: str | None = None) -> str:
        """解析当前 Dashboard 请求的目标作用域标识。"""
        scope_setting = str(self.config.get("storage_scope", "session")).lower()
        if scope_setting == "global":
            return "__global__"
        if raw_scope and str(raw_scope).strip():
            safe = str(raw_scope).strip()
            return self.store.get_safe_key(safe) if self.store else safe
        return "__default__"

    async def api_dashboard_overview(self):
        """Dashboard 数据概览接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        raw_scope = request.query.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        scopes = self.store.list_scopes()
        if scope_key not in scopes and scope_key:
            scopes.insert(0, scope_key)
        events = self.store.prune_and_get(scope_key)
        plan = self.store.read_plan(scope_key)
        ongoing = [e for e in events if e.get("ongoing")]
        today_events = [
            e for e in events if not e.get("ongoing") and is_today(e.get("at"))
        ]
        has_today_plan = bool(plan and is_today(plan.get("date")))

        return json_response(
            {
                "storage_scope": str(self.config.get("storage_scope", "session")),
                "current_scope_key": scope_key,
                "scopes": scopes,
                "events_count": len(events),
                "ongoing_count": len(ongoing),
                "today_count": len(today_events),
                "max_events": int(self.config.get("max_events", 60)),
                "small_ttl_hours": float(self.config.get("small_ttl_hours", 24.0)),
                "ongoing_ttl_hours": float(self.config.get("ongoing_ttl_hours", 168.0)),
                "enabled": bool(self.config.get("enabled", True)),
                "inject_guide": bool(self.config.get("inject_guide", True)),
                "is_today_planned": has_today_plan,
                "plan": plan if has_today_plan else None,
            }
        )

    async def api_dashboard_events(self):
        """Dashboard 事件列表接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        raw_scope = request.query.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        events = self.store.prune_and_get(scope_key)
        result = []
        for e in reversed(events):
            item = dict(e)
            item["is_today"] = is_today(e.get("at"))
            result.append(item)
        return json_response({"events": result, "scope_key": scope_key})

    async def api_dashboard_add_event(self):
        """Dashboard 手动新增生活事件接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        content = str(payload.get("content", "")).strip()[:120]
        if not content:
            return error_response("事件内容不能为空", status_code=400)
        ongoing = bool(payload.get("ongoing", False))
        raw_scope = payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
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
        raw_scope = payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
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
        raw_scope = payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
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
        raw_scope = payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        now_ms = int(time.time() * 1000)
        plan_data = {
            "date": now_ms,
            "day": day,
            "twist": twist,
            "weather": weather,
        }
        self.store.write_plan(scope_key, plan_data)
        return json_response(
            {
                "success": True,
                "plan": plan_data,
                "message": "今日规划已成功更新",
            }
        )

    async def api_dashboard_clear(self):
        """Dashboard 清空作用域数据接口。"""
        if not self.store:
            return error_response("存储未初始化", status_code=500)
        payload = await request.json(default={})
        raw_scope = payload.get("scope_key")
        scope_key = self._resolve_scope_key(raw_scope)
        self.store.clear(scope_key)
        return json_response(
            {
                "success": True,
                "message": f"已清空作用域 [{scope_key}] 的所有生活数据",
            }
        )
