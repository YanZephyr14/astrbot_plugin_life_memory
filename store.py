"""仿真实生活记忆存储与核心算法模块。

本模块实现：
1. 文本归一化与近似事件判定算法；
2. 事件去重、触碰续期与生命周期淘汰机制（TTL + 容量限制）；
3. 每日规划存储与当日有效性判断；
4. 基于本地 JSON 文件的原子写入与降级保护机制。
"""

from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import time
import unicodedata
import uuid
import zoneinfo
from collections.abc import Callable
from pathlib import Path
from typing import Any

CHINA_TIMEZONE = zoneinfo.ZoneInfo("Asia/Shanghai")

# 8 个自然时段映射（左闭右开，基于一天中 0~1440 的分钟数）
NATURAL_SLOTS: dict[str, tuple[int, int]] = {
    "凌晨": (0, 6 * 60),  # 00:00 - 06:00
    "早上": (6 * 60, 9 * 60),  # 06:00 - 09:00
    "上午": (9 * 60, 12 * 60),  # 09:00 - 12:00
    "中午": (12 * 60, 14 * 60),  # 12:00 - 14:00
    "下午": (14 * 60, 18 * 60),  # 14:00 - 18:00
    "傍晚": (18 * 60, 20 * 60),  # 18:00 - 20:00
    "晚上": (20 * 60, 23 * 60),  # 20:00 - 23:00
    "深夜": (23 * 60, 24 * 60),  # 23:00 - 24:00
}

NATURAL_SLOT_NAMES: tuple[str, ...] = tuple(NATURAL_SLOTS.keys())

_TIME_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–—~]\s*(\d{1,2}):(\d{2})")

# 可选生活状态多维属性注册表（注册表模式）
OPTIONAL_LIFE_FIELDS: dict[str, dict[str, str]] = {
    "outfit": {
        "label": "今日穿搭",
        "icon": "👔",
        "desc": "角色当天的外貌穿着或穿搭风格",
    },
    "mood": {
        "label": "当前心情",
        "icon": "🙂",
        "desc": "角色此刻的心绪与精神状态",
    },
    "location": {
        "label": "当前地点",
        "icon": "📍",
        "desc": "角色当前所处的位置或场所",
    },
    "holiday": {
        "label": "今日节日",
        "icon": "🎉",
        "desc": "当天对应的法定或传统节日",
    },
}


def minute_of_day(now_dt: datetime.datetime | None = None) -> int:
    """返回一天中的分钟数 (0~1439)。"""
    if now_dt is None:
        try:
            now_dt = datetime.datetime.now(CHINA_TIMEZONE)
        except Exception:
            now_dt = datetime.datetime.now()
    return now_dt.hour * 60 + now_dt.minute


def get_natural_slot_name(minute: int) -> str:
    """根据一天中的分钟数 (0~1439) 返回所属的自然时段名。"""
    clamped = max(0, min(1439, int(minute)))
    for slot_name, (start, end) in NATURAL_SLOTS.items():
        if start <= clamped < end:
            return slot_name
    return "上午"


def parse_time_slot(time_str: str) -> tuple[int, int] | None:
    """解析时间区间字符串或自然时段名，返回起止分钟数。"""
    val = str(time_str or "").strip()
    match = _TIME_RANGE_RE.fullmatch(val)
    if match:
        sh, sm, eh, em = map(int, match.groups())
        if 0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 24 and 0 <= em <= 59:
            start = sh * 60 + sm
            end = eh * 60 + em
            if start < end:
                return (start, min(1440, end))
    for keyword, interval in NATURAL_SLOTS.items():
        if keyword in val:
            return interval
    return None


def extract_current_slot_schedule(
    plan: dict[str, Any] | None,
    now_dt: datetime.datetime | None = None,
) -> tuple[str, str]:
    """从今日规划中提取当前时段及其具体安排。

    Args:
        plan: 规划数据字典。
        now_dt: 当前日期时间，缺省为当前北京时间。

    Returns:
        (当前时段名称, 当前时段具体安排)。
    """
    minute = minute_of_day(now_dt)
    current_slot = get_natural_slot_name(minute)
    if not plan or not isinstance(plan, dict):
        return current_slot, ""

    timeline = plan.get("timeline")
    if isinstance(timeline, list) and timeline:
        # 1. 优先匹配具体精确时间区间
        for item in timeline:
            if not isinstance(item, dict):
                continue
            time_label = str(item.get("time") or "").strip()
            interval = parse_time_slot(time_label)
            if interval and interval[0] <= minute < interval[1]:
                desc = str(item.get("schedule") or item.get("desc") or "").strip()
                if desc:
                    return time_label, desc
        # 2. 匹配自然时段关键字
        for item in timeline:
            if not isinstance(item, dict):
                continue
            time_label = str(item.get("time") or "").strip()
            if current_slot in time_label:
                desc = str(item.get("schedule") or item.get("desc") or "").strip()
                if desc:
                    return current_slot, desc

    # 3. 若无 timeline 条目，回退返回当前时段及整日概要
    return current_slot, str(plan.get("day") or "").strip()


def get_today_holiday(target_date: datetime.date | None = None) -> str:
    """获取指定日期的中国传统/法定节日名称。

    优先使用 holidays 库；未安装或查询失败时使用内置常用节日映射表安全降级。

    Args:
        target_date: 目标公历日期，缺省为今日。

    Returns:
        节日名称，非节日时返回 "无"。
    """
    if target_date is None:
        try:
            target_date = datetime.datetime.now(CHINA_TIMEZONE).date()
        except Exception:
            target_date = datetime.date.today()

    # 1. 尝试使用 holidays 库
    try:
        import holidays

        cn_holidays = holidays.country_holidays(
            "CN",
            years=target_date.year,
            observed=False,
            language="zh_CN",
        )
        holiday_name = cn_holidays.get(target_date)
        if holiday_name:
            return str(holiday_name).strip()
    except Exception:
        pass

    # 2. 内置公历常用节日表安全降级
    month_day = f"{target_date.month:02d}-{target_date.day:02d}"
    fixed_holidays = {
        "01-01": "元旦",
        "03-08": "妇女节",
        "05-01": "劳动节",
        "05-04": "青年节",
        "06-01": "儿童节",
        "09-10": "教师节",
        "10-01": "国庆节",
        "12-25": "圣诞节",
    }
    return fixed_holidays.get(month_day, "无")


def normalize_text(text: str | None) -> str:
    """对文本进行归一化处理。

    去除所有空白、Unicode 标点符号与特殊符号，并折叠为小写。

    Args:
        text: 待归一化的原始字符串。

    Returns:
        归一化后的纯净字符串。
    """
    if not text:
        return ""
    # 去除空白
    cleaned = re.sub(r"\s+", "", str(text))
    # 过滤 Unicode 标点符号 (P*) 与特殊符号 (S*)
    result = []
    for char in cleaned:
        cat = unicodedata.category(char)
        if not (cat.startswith("P") or cat.startswith("S")):
            result.append(char)
    return "".join(result).lower()


def is_same_event(a: str | None, b: str | None) -> bool:
    """判定两条事件是否为同一事件或高度近似事件。

    匹配规则：
    1. 归一化后完全相等；
    2. 一方包含另一方，且较短句子长度 >= 6 个字符，且短句占长句长度 >= 50%。

    Args:
        a: 第一条事件文本。
        b: 第二条事件文本。

    Returns:
        若属于同一事件则返回 True，否则返回 False。
    """
    x = normalize_text(a)
    y = normalize_text(b)
    if not x or not y:
        return False
    if x == y:
        return True
    short, long = (x, y) if len(x) <= len(y) else (y, x)
    if len(short) < 6:
        return False
    return (short in long) and (len(short) / len(long) >= 0.5)


def merge_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并去重事件列表。

    对于近似重复的事件：
    - 保留包含信息更多（归一化长度更长）的文本；
    - 记录时间 `at` 保留最早创建时间；
    - 触碰时间 `touched_at` 刷新为最新时间（触碰即续期）；
    - `ongoing` 取逻辑或（只要有一条标记为进行中即为进行中）。

    Args:
        events: 原始事件列表。

    Returns:
        按创建时间升序排列的合并后事件列表。
    """
    out: list[dict[str, Any]] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        text = str(e.get("text", "")).strip()
        if not text:
            continue
        at = int(e.get("at") or 0)
        touched_at = int(e.get("touched_at") or at or int(time.time() * 1000))
        ongoing = bool(e.get("ongoing", False))
        event_id = str(e.get("id") or f"{at}-{uuid.uuid4().hex[:6]}")
        ended_at = e.get("ended_at")

        hit = None
        for item in out:
            if is_same_event(item.get("text"), text):
                hit = item
                break

        if not hit:
            out.append(
                {
                    "id": event_id,
                    "text": text,
                    "at": at,
                    "touched_at": touched_at,
                    "ongoing": ongoing,
                    "ended_at": ended_at,
                }
            )
            continue

        # 命中已有事件，进行合并与信息增强
        if len(normalize_text(text)) > len(normalize_text(str(hit.get("text", "")))):
            hit["text"] = text
        hit_at = int(hit.get("at") or 0)
        hit["at"] = min(hit_at, at) if hit_at and at else (hit_at or at)
        hit["touched_at"] = max(int(hit.get("touched_at") or 0), touched_at)
        hit["ongoing"] = bool(hit.get("ongoing")) or ongoing
        if ended_at and not hit.get("ended_at"):
            hit["ended_at"] = ended_at

    return sorted(out, key=lambda x: int(x.get("at") or 0))


def prune_events(
    events: list[dict[str, Any]],
    small_ttl_hours: float = 24.0,
    ongoing_ttl_hours: float = 168.0,
    max_events: int = 60,
    now_ms: int | None = None,
) -> list[dict[str, Any]]:
    """清理过期事件并限制容量上限。

    - 已经过去的小事（非 ongoing）：按最近触碰时间 `touched_at` 淘汰（默认 24h）；
    - 进行中的大事（ongoing）：按长兜底时间 `ongoing_ttl_hours` 淘汰（默认 7 天 / 168h）；
    - 裁剪保留最后 `max_events` 条事件。

    Args:
        events: 待清理的事件列表。
        small_ttl_hours: 小事保留时长（小时）。
        ongoing_ttl_hours: 进行中大事兜底保留时长（小时）。
        max_events: 最多保留事件数。
        now_ms: 当前时间戳（毫秒），为 None 时自动获取当前时间。

    Returns:
        清理并裁剪后的事件列表。
    """
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    small_ttl_ms = max(1.0, float(small_ttl_hours)) * 3600 * 1000
    ongoing_ttl_ms = max(1.0, float(ongoing_ttl_hours)) * 3600 * 1000
    limit = max(1, int(max_events))

    merged = merge_events(events)
    kept: list[dict[str, Any]] = []

    for e in merged:
        touched = int(e.get("touched_at") or e.get("at") or 0)
        diff = now_ms - touched
        if bool(e.get("ongoing")):
            if diff <= ongoing_ttl_ms:
                kept.append(e)
        else:
            if diff <= small_ttl_ms:
                kept.append(e)

    return kept[-limit:]


def is_today(ts_ms: int | float | None) -> bool:
    """判断给定的毫秒时间戳是否属于本地日期的“今天”。

    Args:
        ts_ms: 毫秒时间戳。

    Returns:
        若是当天日期则返回 True，否则返回 False。
    """
    if not ts_ms:
        return False
    try:
        event_time = time.localtime(float(ts_ms) / 1000.0)
        now_time = time.localtime()
        return (
            event_time.tm_year == now_time.tm_year
            and event_time.tm_mon == now_time.tm_mon
            and event_time.tm_mday == now_time.tm_mday
        )
    except Exception:
        return False


class LifeStore:
    """生活事件与每日规划本地持久化存储器。

    支持会话隔离或全局共享、原子写入及损坏降级。
    """

    def __init__(
        self,
        root_dir: Path | str,
        get_config_func: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        """初始化存储器。

        Args:
            root_dir: 数据持久化根目录。
            get_config_func: 获取实时配置的回调函数。
        """
        self.root_dir = Path(root_dir).resolve()
        self._get_config = get_config_func or (lambda: {})
        self._locks: dict[str, asyncio.Lock] = {}
        self._failure_counts: dict[str, int] = {}

    def get_scope_lock(self, scope_key: str | None) -> asyncio.Lock:
        """获取指定作用域的异步互斥锁。

        Args:
            scope_key: 作用域标识。

        Returns:
            asyncio.Lock 实例。
        """
        safe = self.get_safe_key(scope_key)
        if safe not in self._locks:
            self._locks[safe] = asyncio.Lock()
        return self._locks[safe]

    def record_failure(self, scope_key: str | None) -> int:
        """记录一次生成失败，并返回当前失败累计次数。

        Args:
            scope_key: 作用域标识。

        Returns:
            累计失败次数。
        """
        safe = self.get_safe_key(scope_key)
        self._failure_counts[safe] = self._failure_counts.get(safe, 0) + 1
        return self._failure_counts[safe]

    def reset_failure(self, scope_key: str | None) -> None:
        """重置指定作用域的失败计数。

        Args:
            scope_key: 作用域标识。
        """
        safe = self.get_safe_key(scope_key)
        self._failure_counts[safe] = 0

    def is_circuit_broken(self, scope_key: str | None, max_failures: int = 3) -> bool:
        """检查指定作用域是否已达到失败熔断阈值。

        Args:
            scope_key: 作用域标识。
            max_failures: 最大允许连续失败次数。

        Returns:
            若已熔断返回 True，否则返回 False。
        """
        safe = self.get_safe_key(scope_key)
        return self._failure_counts.get(safe, 0) >= max(1, int(max_failures))

    def get_history_dir(self) -> Path:
        """获取历史规划归档目录。"""
        return self.root_dir / "history"

    def ensure_dir(self) -> None:
        """确保存储根目录与历史归档目录存在。"""
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            self.get_history_dir().mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def get_safe_key(self, scope_key: str | None) -> str:
        """根据会话或人格标识生成安全文件名键名。

        仅过滤操作系统底层保留的非法路径字符，完整保留中文及各语言合法 Unicode 字符。

        Args:
            scope_key: 原始会话标识或人格 ID。

        Returns:
            经过安全过滤的合法文件名标识字符串。
        """
        raw = str(scope_key or "").strip()
        if not raw:
            return "_default"
        # 仅过滤跨平台非法文件名字符: < > : " / \ | ? * 以及 ASCII 控制字符
        safe = re.sub(r"[\<\>\:\"\/\\\|\?\*\x00-\x1f]", "_", raw).strip(". ")
        # 处理 Windows 保留设备名称
        if safe.upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }:
            safe = f"_{safe}"
        if re.fullmatch(r"_+", safe):
            safe = "_default"
        return safe or "_default"

    def get_events_file(self, scope_key: str | None) -> Path:
        """获取指定作用域的事件存储文件路径。"""
        safe = self.get_safe_key(scope_key)
        return self.root_dir / f"{safe}.json"

    def get_plan_file(self, scope_key: str | None) -> Path:
        """获取指定作用域的每日规划存储文件路径。"""
        safe = self.get_safe_key(scope_key)
        return self.root_dir / f"{safe}.plan.json"

    def read_events(self, scope_key: str | None) -> list[dict[str, Any]]:
        """读取指定作用域的事件列表。

        Args:
            scope_key: 作用域标识。

        Returns:
            事件列表，读取失败或文件不存在时返回空列表。
        """
        try:
            file_path = self.get_events_file(scope_key)
            if not file_path.exists():
                return []
            content = file_path.read_text(encoding="utf-8").lstrip("\ufeff")
            data = json.loads(content)
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                return data["events"]
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def write_events(self, scope_key: str | None, events: list[dict[str, Any]]) -> bool:
        """原子写入事件列表。

        Args:
            scope_key: 作用域标识。
            events: 事件列表。

        Returns:
            写入成功返回 True，失败返回 False。
        """
        try:
            self.ensure_dir()
            target_path = self.get_events_file(scope_key)
            tmp_path = target_path.with_suffix(
                f".tmp.{os.getpid()}_{uuid.uuid4().hex[:6]}"
            )
            payload = {"events": events}
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(target_path)
            return True
        except Exception:
            return False

    def read_plan(self, scope_key: str | None) -> dict[str, Any] | None:
        """读取指定作用域的今日生活规划。

        Args:
            scope_key: 作用域标识。

        Returns:
            规划字典，若无或读取失败则返回 None。
        """
        try:
            file_path = self.get_plan_file(scope_key)
            if not file_path.exists():
                return None
            content = file_path.read_text(encoding="utf-8").lstrip("\ufeff")
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            return None
        except Exception:
            return None

    def _archive_old_plan(
        self, scope_key: str | None, old_plan: dict[str, Any]
    ) -> None:
        """将旧规划归档到历史目录中并保留最近 7 天。

        Args:
            scope_key: 作用域标识。
            old_plan: 历史规划字典。
        """
        try:
            ts = float(old_plan.get("date") or 0)
            if ts <= 0:
                return
            old_dt_str = time.strftime("%Y%m%d", time.localtime(ts / 1000.0))
            safe = self.get_safe_key(scope_key)
            hist_dir = self.get_history_dir()
            hist_dir.mkdir(parents=True, exist_ok=True)
            hist_file = hist_dir / f"{safe}_{old_dt_str}.json"
            hist_file.write_text(
                json.dumps(old_plan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 清理超出 7 天的旧归档
            prefix = f"{safe}_"
            matched_files: list[tuple[str, Path]] = []
            for item in hist_dir.iterdir():
                if item.name.startswith(prefix) and item.name.endswith(".json"):
                    matched_files.append((item.name, item))
            matched_files.sort(key=lambda x: x[0], reverse=True)
            for _, expired in matched_files[7:]:
                try:
                    expired.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def get_recent_plan_history(
        self, scope_key: str | None, limit: int = 2
    ) -> list[dict[str, Any]]:
        """读取指定作用域最近的历史规划归档。

        Args:
            scope_key: 作用域标识。
            limit: 最多返回的历史规划天数。

        Returns:
            历史规划列表，按日期从新到旧排列。
        """
        try:
            hist_dir = self.get_history_dir()
            if not hist_dir.exists():
                return []
            safe = self.get_safe_key(scope_key)
            prefix = f"{safe}_"
            matched_files: list[tuple[str, Path]] = []
            for item in hist_dir.iterdir():
                if item.name.startswith(prefix) and item.name.endswith(".json"):
                    matched_files.append((item.name, item))
            matched_files.sort(key=lambda x: x[0], reverse=True)
            result: list[dict[str, Any]] = []
            for _, path in matched_files[: max(1, limit)]:
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        result.append(raw)
                except Exception:
                    pass
            return result
        except Exception:
            return []

    def write_plan(self, scope_key: str | None, plan: dict[str, Any]) -> bool:
        """原子写入生活规划，并在跨天时自动归档旧规划。

        Args:
            scope_key: 作用域标识。
            plan: 规划数据字典。

        Returns:
            写入成功返回 True，失败返回 False。
        """
        try:
            self.ensure_dir()
            # 检查是否有昨天的旧规划，若有则自动归档
            old_plan = self.read_plan(scope_key)
            if old_plan and not is_today(old_plan.get("date")):
                self._archive_old_plan(scope_key, old_plan)

            target_path = self.get_plan_file(scope_key)
            tmp_path = target_path.with_suffix(
                f".tmp.{os.getpid()}_{uuid.uuid4().hex[:6]}"
            )
            tmp_path.write_text(
                json.dumps(plan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(target_path)
            return True
        except Exception:
            return False

    def prune_and_get(self, scope_key: str | None) -> list[dict[str, Any]]:
        """读取并自动清理指定作用域的事件列表。

        Args:
            scope_key: 作用域标识。

        Returns:
            清理后的事件列表。
        """
        raw_events = self.read_events(scope_key)
        cfg = self._get_config()
        small_ttl = float(cfg.get("small_ttl_hours", 24.0))
        ongoing_ttl = float(cfg.get("ongoing_ttl_hours", 168.0))
        max_events = int(cfg.get("max_events", 60))
        return prune_events(
            raw_events,
            small_ttl_hours=small_ttl,
            ongoing_ttl_hours=ongoing_ttl,
            max_events=max_events,
        )

    def clear(self, scope_key: str | None) -> bool:
        """清空指定作用域的所有生活数据（事件与规划）。

        Args:
            scope_key: 作用域标识。

        Returns:
            是否清空成功。
        """
        try:
            ev_file = self.get_events_file(scope_key)
            if ev_file.exists():
                ev_file.unlink()
            plan_file = self.get_plan_file(scope_key)
            if plan_file.exists():
                plan_file.unlink()
            return True
        except Exception:
            return False

    def list_scopes(self) -> list[str]:
        """列出当前存在数据的所有作用域标识列表。

        Returns:
            作用域 safe_key 列表。
        """
        try:
            if not self.root_dir.exists():
                return []
            scopes: set[str] = set()
            for item in self.root_dir.glob("*.json"):
                name = item.name
                if name.endswith(".plan.json"):
                    key = name[:-10]
                elif not name.startswith(".") and ".tmp" not in name:
                    key = name[:-5]
                else:
                    continue
                # 过滤由纯下划线构成的历史遗留脏文件名，不作为独立作用域暴露
                if key and not re.fullmatch(r"_+", key):
                    scopes.add(key)
            return sorted(scopes)
        except Exception:
            return []

    def migrate_legacy_underscore_files(
        self, candidate_personas: list[str]
    ) -> list[tuple[str, str]]:
        """迁移因旧版 safe_key 过滤导致转义为纯下划线的历史文件。

        Args:
            candidate_personas: 系统已知的人格 ID 列表。

        Returns:
            成功迁移的文件名映射列表 [(old_name, new_name), ...]。
        """
        migrated: list[tuple[str, str]] = []
        try:
            if not self.root_dir.exists():
                return migrated
            for item in list(self.root_dir.glob("*.json")):
                stem = ""
                is_plan = False
                if item.name.endswith(".plan.json"):
                    stem = item.name[:-10]
                    is_plan = True
                elif not item.name.startswith(".") and ".tmp" not in item.name:
                    stem = item.name[:-5]
                    is_plan = False
                else:
                    continue

                if not re.fullmatch(r"_+", stem):
                    continue

                # 寻找字符长度匹配且尚未有对应文件的候选人格
                matched_pid = None
                matches = [p for p in candidate_personas if len(p) == len(stem)]
                for cand in matches:
                    cand_safe = self.get_safe_key(cand)
                    target_file = (
                        self.get_plan_file(cand_safe)
                        if is_plan
                        else self.get_events_file(cand_safe)
                    )
                    if not target_file.exists():
                        matched_pid = cand
                        break

                if matched_pid:
                    target_file = (
                        self.get_plan_file(matched_pid)
                        if is_plan
                        else self.get_events_file(matched_pid)
                    )
                    item.replace(target_file)
                    migrated.append((item.name, target_file.name))
                else:
                    # 无法匹配的孤立纯下划线脏文件，安全删除以防污染作用域
                    try:
                        item.unlink()
                    except Exception:
                        pass
        except Exception:
            pass
        return migrated

    def delete_event(self, scope_key: str | None, event_id: str) -> bool:
        """按 ID 删除指定作用域中的某条事件。

        Args:
            scope_key: 作用域标识。
            event_id: 事件唯一标识。

        Returns:
            是否成功找到并删除。
        """
        try:
            events = self.read_events(scope_key)
            new_events = [e for e in events if str(e.get("id")) != str(event_id)]
            if len(new_events) != len(events):
                self.write_events(scope_key, new_events)
                return True
            return False
        except Exception:
            return False

    def mark_event_done(self, scope_key: str | None, event_id: str) -> bool:
        """按 ID 将指定作用域中的某条事件标记为结束。

        Args:
            scope_key: 作用域标识。
            event_id: 事件唯一标识。

        Returns:
            是否成功标记结束。
        """
        try:
            events = self.read_events(scope_key)
            modified = False
            now_ms = int(time.time() * 1000)
            for e in events:
                if str(e.get("id")) == str(event_id) and e.get("ongoing"):
                    e["ongoing"] = False
                    e["ended_at"] = now_ms
                    modified = True
                    break
            if modified:
                self.write_events(scope_key, events)
                return True
            return False
        except Exception:
            return False
