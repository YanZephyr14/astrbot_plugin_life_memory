"""Unit tests for LifeStore and core algorithms."""

from __future__ import annotations

import sys
import time
from pathlib import Path

# 将插件根目录加入 sys.path
plugin_dir = Path(__file__).resolve().parent.parent
if str(plugin_dir) not in sys.path:
    sys.path.insert(0, str(plugin_dir))

from store import (
    LifeStore,
    extract_current_slot_schedule,
    get_natural_slot_name,
    get_today_holiday,
    is_same_event,
    is_today,
    merge_events,
    minute_of_day,
    normalize_text,
    prune_events,
)


def test_normalize_text():
    assert normalize_text("  Hello, World! 吃了 牛肉面！！ ") == "helloworld吃了牛肉面"
    assert normalize_text("【生活事件】在等快递……") == "生活事件在等快递"
    assert normalize_text("") == ""


def test_is_same_event():
    assert is_same_event("中午吃了牛肉拉面", "中午吃了牛肉拉面！") is True
    assert is_same_event("中午吃了热腾腾的牛肉拉面", "吃了热腾腾的牛肉拉面") is True
    assert is_same_event("牛肉面", "今天中午去吃了牛肉面") is False
    assert is_same_event("中午去吃汉堡", "晚上散步") is False


def test_merge_events():
    now = int(time.time() * 1000)
    events = [
        {
            "text": "吃了热腾腾的牛肉拉面",
            "at": now - 10000,
            "touched_at": now - 10000,
            "ongoing": False,
        },
        {
            "text": "中午吃了热腾腾的牛肉拉面",
            "at": now - 5000,
            "touched_at": now,
            "ongoing": False,
        },
    ]
    merged = merge_events(events)
    assert len(merged) == 1
    assert merged[0]["text"] == "中午吃了热腾腾的牛肉拉面"
    assert merged[0]["at"] == now - 10000
    assert merged[0]["touched_at"] == now


def test_prune_events():
    now = int(time.time() * 1000)
    events = [
        # 过期的小事 (超过 24h)
        {
            "id": "1",
            "text": "昨天的小事",
            "at": now - 30 * 3600 * 1000,
            "touched_at": now - 30 * 3600 * 1000,
            "ongoing": False,
        },
        # 新鲜的小事 (1h 前)
        {
            "id": "2",
            "text": "刚才的小事",
            "at": now - 3600 * 1000,
            "touched_at": now - 3600 * 1000,
            "ongoing": False,
        },
        # 进行中的大事 (5天前，未超过 7 天)
        {
            "id": "3",
            "text": "正在等快递",
            "at": now - 5 * 24 * 3600 * 1000,
            "touched_at": now - 5 * 24 * 3600 * 1000,
            "ongoing": True,
        },
        # 进行中大事超时兜底 (超过 7 天)
        {
            "id": "4",
            "text": "超时的进行中事件",
            "at": now - 8 * 24 * 3600 * 1000,
            "touched_at": now - 8 * 24 * 3600 * 1000,
            "ongoing": True,
        },
    ]
    pruned = prune_events(
        events, small_ttl_hours=24.0, ongoing_ttl_hours=168.0, max_events=60
    )
    ids = [e["id"] for e in pruned]
    assert "2" in ids
    assert "3" in ids
    assert "1" not in ids
    assert "4" not in ids


def test_store_io(tmp_path: Path):
    store = LifeStore(
        root_dir=tmp_path,
        get_config_func=lambda: {"small_ttl_hours": 24, "ongoing_ttl_hours": 168},
    )
    store.ensure_dir()

    scope = "test_persona"
    events = [{"id": "e1", "text": "测试事件", "at": 1000, "ongoing": False}]
    store.write_events(scope, events)
    read_back = store.read_events(scope)
    assert len(read_back) == 1
    assert read_back[0]["text"] == "测试事件"

    now_ms = int(time.time() * 1000)
    plan = {"date": now_ms, "day": "今天去公园散步", "weather": "晴"}
    store.write_plan(scope, plan)
    plan_back = store.read_plan(scope)
    assert plan_back is not None
    assert plan_back["day"] == "今天去公园散步"
    assert is_today(plan_back["date"]) is True


def test_natural_slots_and_schedule():
    # 早上 08:30 (510 分钟)
    slot = get_natural_slot_name(8 * 60 + 30)
    assert slot == "早上"

    plan = {
        "day": "整日日程",
        "timeline": [
            {"time": "早上", "schedule": "享用美味早餐"},
            {"time": "上午", "schedule": "专注办公"},
        ],
    }
    # 提取早上
    cur_slot, schedule = extract_current_slot_schedule(plan)
    assert isinstance(cur_slot, str)
    assert isinstance(schedule, str)


def test_holiday_detection():
    holiday = get_today_holiday()
    assert isinstance(holiday, str)
