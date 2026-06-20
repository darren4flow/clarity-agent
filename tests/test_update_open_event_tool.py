import sys
import json
from pathlib import Path
from unittest.mock import Mock
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pytest
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
from tools.update_open_event_tool import update_open_event_tool


deserializer = TypeDeserializer()
serializer = TypeSerializer()


def _make_ddb_item(event_dict):
    return {k: serializer.serialize(v) for k, v in event_dict.items()}



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
        open_event_pre_last_update=None,
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
        open_event_pre_last_update={"event_id": "evt-1", "event_data": json.dumps(snapshot)},
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
        open_event_pre_last_update={"event_id": "evt-1", "event_data": "{}"},
    )

    assert result["action"] == "undo_noop"
    assert "open event changed" in result["result"].lower()
    assert not mock_ddb.put_item.called


def test_update_returns_pre_update_snapshot():
    """pre_update_snapshot in the result should reflect event state BEFORE the update."""
    mock_ddb = Mock()
    mock_lambda = Mock()

    original_event = {
        "userId": "user-1",
        "id": "evt-1",
        "description": "Original Title",
        "startDate": "2026-01-01T10:00:00",
        "endDate": "2026-01-01T11:00:00",
    }
    mock_ddb.get_item.return_value = {"Item": _make_ddb_item(original_event)}

    result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"title": "Updated Title"}),
        "UTC",
        open_event_id="evt-1",
        open_event_pre_last_update=None,
    )

    assert result["action"] == "update"
    assert "pre_update_snapshot" in result

    snapshot = json.loads(result["pre_update_snapshot"])
    assert snapshot["description"] == "Original Title"

    updated = json.loads(result["event_data"])
    assert updated["description"] == "Updated Title"


def test_update_then_undo_restores_original():
    """Round-trip: update followed by undo using pre_update_snapshot restores the original event."""
    mock_ddb = Mock()
    mock_lambda = Mock()

    original_event = {
        "userId": "user-1",
        "id": "evt-1",
        "description": "Original Title",
        "startDate": "2026-01-01T10:00:00",
        "endDate": "2026-01-01T11:00:00",
    }
    mock_ddb.get_item.return_value = {"Item": _make_ddb_item(original_event)}

    # First call: update the title
    update_result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"title": "Updated Title"}),
        "UTC",
        open_event_id="evt-1",
        open_event_pre_last_update=None,
    )
    assert update_result["action"] == "update"

    # Session manager stores pre_update_snapshot as the undo snapshot
    open_event_pre_last_update = {
        "event_id": "evt-1",
        "event_data": update_result["pre_update_snapshot"],
    }

    # Second call: undo
    undo_result = update_open_event_tool(
        mock_ddb,
        mock_lambda,
        "user-1",
        json.dumps({"action": "undo"}),
        "UTC",
        open_event_id="evt-1",
        open_event_pre_last_update=open_event_pre_last_update,
    )

    assert undo_result["action"] == "undo"
    restored = json.loads(undo_result["event_data"])
    assert restored["description"] == "Original Title"



@pytest.mark.asyncio
async def test_update_open_event_sets_open_event_pre_last_update(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="u", timezone="UTC")
    s.open_event_id = "evt-1"

    def fake_update_open_event_tool(*args, **kwargs):
        return {
            "result": "Updated the event.",
            "tool_name": "update_open_event_tool",
            "action": "update",
            "event_data": json.dumps({"userId": "u", "id": "evt-1", "description": "after"}),
            "pre_update_snapshot": json.dumps({"userId": "u", "id": "evt-1", "description": "before"}),
            "updated_fields": json.dumps({"description": "after"}),
        }

    monkeypatch.setattr(s2s_session_manager, "update_open_event_tool", fake_update_open_event_tool)

    await s.processToolUse("update_open_event", {"content": "{}"})

    assert s.open_event_pre_last_update is not None
    assert s.open_event_pre_last_update["event_id"] == "evt-1"


@pytest.mark.asyncio
async def test_close_event_clears_open_event_pre_last_update():
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="u", timezone="UTC")
    s.open_event_id = "evt-1"
    s.open_event_pre_last_update = {"event_id": "evt-1", "event_data": "{}"}

    result = await s.processToolUse("close_event", {"content": "{}"})

    assert result["tool_name"] == "close_event"
    assert s.open_event_id is None
    assert s.open_event_pre_last_update is None




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
        open_event_pre_last_update={"event_id": "evt-1", "event_data": snapshot},
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
