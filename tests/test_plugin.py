"""Unit tests for LifeMemoryPlugin main logic and LLM tools."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

plugin_dir = Path(__file__).resolve().parent.parent
if str(plugin_dir) not in sys.path:
    sys.path.insert(0, str(plugin_dir))

from main import LifeMemoryPlugin


@pytest.fixture
def mock_context(tmp_path: Path):
    ctx = MagicMock()
    ctx.register_web_api = MagicMock()
    ctx.persona_manager = MagicMock()
    ctx.persona_manager.default_persona = "default"
    ctx.conversation_manager = None
    return ctx


@pytest.mark.asyncio
async def test_life_tools_workflow(mock_context, tmp_path: Path):
    config = {
        "enabled": True,
        "inject_guide": True,
        "storage_scope": "persona",
        "small_ttl_hours": 24,
        "ongoing_ttl_hours": 168,
        "max_events": 60,
    }
    plugin = LifeMemoryPlugin(mock_context, config)

    # 替换 store 为临时目录 store
    from store import LifeStore

    plugin.store = LifeStore(
        root_dir=tmp_path / "life_data", get_config_func=lambda: config
    )
    plugin.store.ensure_dir()

    event = MagicMock()
    event.unified_msg_origin = "test:user1"
    event.get_extra = MagicMock(return_value="default")
    event.set_extra = MagicMock()

    # 1. life_note 普通小事
    res1 = await plugin.life_note(event, content="中午吃了拉面", ongoing=False)
    assert "已记下" in res1
    assert "中午吃了拉面" in res1

    # 2. life_note 进行中的事
    res2 = await plugin.life_note(event, content="在等一个重要快递", ongoing=True)
    assert "已记下" in res2
    assert "进行中" in res2

    # 3. life_recall 回忆
    recall_res = await plugin.life_recall(event)
    assert "在等一个重要快递" in recall_res
    assert "中午吃了拉面" in recall_res

    # 4. life_plan 今日规划
    plan_res = await plugin.life_plan(
        event, day="今天写代码，晚上看电影", weather="晴天微风", mood="专注"
    )
    assert "已记下今天的规划" in plan_res
    assert "今天写代码，晚上看电影" in plan_res

    # 5. life_done 结束进行中的事
    done_res = await plugin.life_done(event, content="快递")
    assert "已结束" in done_res

    # 再次 recall，快递不再在进行中
    recall_res2 = await plugin.life_recall(event)
    assert "进行中的事" not in recall_res2 or "在等一个重要快递" not in recall_res2
