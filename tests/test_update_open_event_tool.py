import sys
import json
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pytest
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
from tools.update_open_event_tool import update_open_event_tool


def test_update_open_event_tool_undo_no_snapshot_returns_noop():
    mock_ddb = Mock()
    mock_lambda = Mock()

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"action": "undo"}),
        "UTC",
        open_event_id="evt-1",
        last_open_event_update=None,
    )

    assert result["action"] == "undo_noop"
    assert "no prior open event update" in result["result"].lower()
    assert not mock_ddb.put_item.called


def test_update_open_event_tool_undo_restores_snapshot():
    mock_ddb = Mock()
    mock_lambda = Mock()
    snapshot = {
        "userId": "user-1",
        "id": "evt-1",
        "description": "before update",
        "startDate": "2026-01-01T10:00:00+00:00",
        "endDate": "2026-01-01T11:00:00+00:00",
    }

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"action": "undo"}),
        "UTC",
        open_event_id="evt-1",
        last_open_event_update={"event_id": "evt-1", "event_data": json.dumps(snapshot)},
    )

    assert result["action"] == "undo"
    assert result["tool_name"] == "update_open_event_tool"
    assert mock_ddb.put_item.called


def test_update_open_event_tool_undo_noop_when_event_changed():
    mock_ddb = Mock()
    mock_lambda = Mock()

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"action": "undo"}),
        "UTC",
        open_event_id="evt-2",
        last_open_event_update={"event_id": "evt-1", "event_data": "{}"},
    )

    assert result["action"] == "undo_noop"
    assert "open event changed" in result["result"].lower()
    assert not mock_ddb.put_item.called


@pytest.mark.asyncio
async def test_update_open_event_sets_last_open_event_update(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="u", timezone="UTC")
    s.open_event_id = "evt-1"

    def fake_update_open_event_tool(*args, **kwargs):
        return {
            "result": "Updated the event.",
            "tool_name": "update_open_event_tool",
            "action": "update",
            "event_data": json.dumps({"userId": "u", "id": "evt-1", "description": "before"}),
            "updated_fields": json.dumps({"description": "after"}),
        }

    monkeypatch.setattr(s2s_session_manager, "update_open_event_tool", fake_update_open_event_tool)

    await s.processToolUse("update_event_content", {"content": "{}"})

    assert s.last_open_event_update is not None
    assert s.last_open_event_update["event_id"] == "evt-1"


@pytest.mark.asyncio
async def test_close_event_clears_last_open_event_update():
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="u", timezone="UTC")
    s.open_event_id = "evt-1"
    s.last_open_event_update = {"event_id": "evt-1", "event_data": "{}"}

    result = await s.processToolUse("close_event", {"content": "{}"})

    assert result["tool_name"] == "close_event"
    assert s.open_event_id is None
    assert s.last_open_event_update is None


def test_reset_session_state_clears_open_event_and_last_update():
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="u", timezone="UTC")
    s.open_event_id = "evt-1"
    s.last_open_event_update = {"event_id": "evt-1", "event_data": "{}"}

    s.reset_session_state()

    assert s.open_event_id is None
    assert s.last_open_event_update is None
