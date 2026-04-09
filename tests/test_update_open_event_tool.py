import sys
import json
from pathlib import Path
from unittest.mock import Mock
from boto3.dynamodb.types import TypeDeserializer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pytest
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
from tools.update_open_event_tool import update_open_event_tool


deserializer = TypeDeserializer()


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


def test_update_open_event_tool_update_serializes_decimal_and_normalizes_utc_z():
    mock_ddb = Mock()
    mock_lambda = Mock()
    mock_ddb.get_item.return_value = {
        "Item": {
            "userId": {"S": "user-1"},
            "id": {"S": "evt-1"},
            "description": {"S": "before update"},
            "startDate": {"S": "2026-01-01T10:00:00+00:00"},
            "endDate": {"S": "2026-01-01T11:00:00+00:00"},
            "done": {"N": "1"},
            "allDay": {"BOOL": False},
        }
    }

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"title": "after update"}),
        "UTC",
        open_event_id="evt-1",
    )

    assert result["action"] == "update"
    payload = json.loads(result["event_data"])
    assert payload["done"] == 1
    assert payload["startDate"].endswith("Z")
    assert payload["endDate"].endswith("Z")


def test_update_open_event_tool_undo_serializes_decimal_snapshot():
    mock_ddb = Mock()
    mock_lambda = Mock()
    snapshot = {
        "userId": "user-1",
        "id": "evt-1",
        "description": "before update",
        "startDate": "2026-01-01T10:00:00.000Z",
        "endDate": "2026-01-01T11:00:00.000Z",
        "done": Decimal("1"),
    }

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"action": "undo"}),
        "UTC",
        open_event_id="evt-1",
        last_open_event_update={"event_id": "evt-1", "event_data": snapshot},
    )

    assert result["action"] == "undo"
    payload = json.loads(result["event_data"])
    assert payload["done"] == 1


def test_update_open_event_tool_recurrence_no_habit_creates_and_attaches(monkeypatch):
    mock_ddb = Mock()
    mock_lambda = Mock()

    mock_ddb.get_item.return_value = {
        "Item": {
            "userId": {"S": "user-1"},
            "id": {"S": "evt-1"},
            "description": {"S": "before update"},
            "startDate": {"S": "2026-01-01T10:00:00+00:00"},
            "endDate": {"S": "2026-01-01T11:00:00+00:00"},
            "allDay": {"BOOL": False},
            "type": {"S": "personal"},
            "fixed": {"BOOL": False},
            "notifications": {"L": []},
        }
    }

    import tools.update_open_event_tool as tool_mod

    monkeypatch.setattr(tool_mod.uuid, "uuid4", lambda: "new-habit-id")

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({
            "frequency": 2,
            "time_unit": "weekly",
            "days": ["Mon", "Wed"],
            "stop_date": "2026-02-01"
        }),
        "UTC",
        open_event_id="evt-1",
    )

    assert result["action"] == "update"
    payload = json.loads(result["event_data"])
    assert payload["habitId"] == "new-habit-id"

    # Expect one Habits insert and one Events insert.
    assert mock_ddb.put_item.call_count == 2
    habits_call = mock_ddb.put_item.call_args_list[0]
    assert habits_call.kwargs["TableName"] == "Habits"

    habits_item = {
        k: deserializer.deserialize(v)
        for k, v in habits_call.kwargs["Item"].items()
    }
    assert habits_item["frequency"] == "2W"
    assert habits_item["days"] == ["Mon", "Wed"]
    assert habits_item["stopDate"] is None


def test_update_open_event_tool_recurrence_with_habit_splits_series(monkeypatch):
    mock_ddb = Mock()
    mock_lambda = Mock()

    event_item = {
        "Item": {
            "userId": {"S": "user-1"},
            "id": {"S": "evt-1"},
            "habitId": {"S": "hid-old"},
            "description": {"S": "before update"},
            "startDate": {"S": "2026-01-01T10:00:00+00:00"},
            "endDate": {"S": "2026-01-01T11:00:00+00:00"},
            "allDay": {"BOOL": False},
            "type": {"S": "personal"},
            "fixed": {"BOOL": False},
            "notifications": {"L": []},
        }
    }
    habit_item = {
        "Item": {
            "id": {"S": "hid-old"},
            "userId": {"S": "user-1"},
            "name": {"S": "before update"},
            "creationDate": {"S": "2025-12-01"},
            "frequency": {"S": "1D"},
            "days": {"L": []},
            "exceptionDates": {"L": []},
            "stopDate": {"NULL": True},
            "startTime": {"M": {"hour": {"N": "10"}, "minute": {"N": "0"}, "timezone": {"S": "UTC"}}},
            "length": {"N": "60"},
            "allDay": {"BOOL": False},
            "content": {"NULL": True},
            "fixed": {"BOOL": False},
            "notifications": {"L": []},
            "prevVersionHabitId": {"NULL": True},
            "priority": {"NULL": True},
            "eventType": {"S": "personal"},
        }
    }
    mock_ddb.get_item.side_effect = [event_item, habit_item]

    import tools.update_open_event_tool as tool_mod

    monkeypatch.setattr(tool_mod.uuid, "uuid4", lambda: "hid-new")

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"frequency": 3, "time_unit": "monthly", "days": ["10"]}),
        "UTC",
        open_event_id="evt-1",
    )

    assert result["action"] == "update"
    payload = json.loads(result["event_data"])
    assert payload["habitId"] == "hid-new"

    assert mock_ddb.update_item.call_count == 1
    assert mock_ddb.put_item.call_count == 2

    habits_call = mock_ddb.put_item.call_args_list[0]
    assert habits_call.kwargs["TableName"] == "Habits"
    habits_item = {
        k: deserializer.deserialize(v)
        for k, v in habits_call.kwargs["Item"].items()
    }
    assert habits_item["frequency"] == "3M"
    assert habits_item["days"] == ["10"]
    assert habits_item["prevVersionHabitId"] == "hid-old"
