"""仿真实生活记忆存储与核心算法模块。

本模块实现：
1. 文本归一化与近似事件判定算法；
2. 事件去重、触碰续期与生命周期淘汰机制（TTL + 容量限制）；
3. 每日规划存储与当日有效性判断；
4. 基于本地 JSON 文件的原子写入与降级保护机制。
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any


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

    def ensure_dir(self) -> None:
        """确保存储根目录存在。"""
        try:
            self.root_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def get_safe_key(self, scope_key: str | None) -> str:
        """根据会话或标识生成安全文件名键名。

        Args:
            scope_key: 原始会话标识或统一消息来源（UMO）。

        Returns:
            经过安全过滤的标识字符串。
        """
        raw = str(scope_key or "").strip()
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", raw)
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

    def write_plan(self, scope_key: str | None, plan: dict[str, Any]) -> bool:
        """原子写入生活规划。

        Args:
            scope_key: 作用域标识。
            plan: 规划数据字典。

        Returns:
            写入成功返回 True，失败返回 False。
        """
        try:
            self.ensure_dir()
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
                    scopes.add(key)
                elif not name.startswith(".") and ".tmp" not in name:
                    key = name[:-5]
                    scopes.add(key)
            return sorted(scopes)
        except Exception:
            return []

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
