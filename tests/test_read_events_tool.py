import sys
import json
import pytest
from unittest.mock import Mock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
import tools.read_events_tool 


def build_mock_ddb(events_items, habits_items):
    mock_ddb = Mock()

    def query_side_effect(**kwargs):
        table_name = kwargs.get("TableName")
        if table_name == "Events":
            return {"Items": events_items}
        if table_name == "Habits":
            return {"Items": habits_items}
        return {"Items": []}

    mock_ddb.query = Mock(side_effect=query_side_effect)
    return mock_ddb


@pytest.mark.asyncio
async def test_read_events_date_only_returns_sorted_events(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    today = datetime.now(ZoneInfo("UTC")).date()
    events_items = [
        {
            "userId": "test-user",
            "id": "e1",
            "description": "Meeting A",
            "startDate": f"{today.isoformat()}T09:00:00+00:00",
            "endDate": f"{today.isoformat()}T09:30:00+00:00",
        },
        {
            "userId": "test-user",
            "id": "e2",
            "description": "Meeting B",
            "startDate": f"{today.isoformat()}T08:00:00+00:00",
            "endDate": f"{today.isoformat()}T08:30:00+00:00",
        },
    ]

    mock_ddb = build_mock_ddb(events_items, [])
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.read_events_tool, "deserializer", Mock(deserialize=lambda v: v))

    payload = {"start_date": today.isoformat()}
    res = await s.processToolUse("read_events", {"content": json.dumps(payload)})

    assert res["result"] == "Found 2 events."
    assert res["events"] == [
        {
            "title": "Meeting B",
            "startDate": f"{today.strftime('%m/%d/%y')} 08:00 AM",
            "endDate": f"{today.strftime('%m/%d/%y')} 08:30 AM",
        },
        {
            "title": "Meeting A",
            "startDate": f"{today.strftime('%m/%d/%y')} 09:00 AM",
            "endDate": f"{today.strftime('%m/%d/%y')} 09:30 AM",
        },
    ]


@pytest.mark.asyncio
async def test_read_events_time_range_only_includes_generated_and_saved(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    today = datetime.now(ZoneInfo("UTC")).date()

    events_items = [
        {
            "userId": "test-user",
            "id": "e2",
            "description": "Inside Range",
            "startDate": f"{today.isoformat()}T10:15:00+00:00",
            "endDate": f"{today.isoformat()}T10:45:00+00:00",
        }
    ]

    habits_items = [
        {
            "habitId": "h1",
            "userId": "test-user",
            "name": "Daily Standup",
            "creationDate": today - timedelta(days=1),
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "length": 30,
        }
    ]

    mock_ddb = build_mock_ddb(events_items, habits_items)
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.read_events_tool, "deserializer", Mock(deserialize=lambda v: v))

    payload = {"start_time": "09:30", "end_time": "10:30"}
    res = await s.processToolUse("read_events", {"content": json.dumps(payload)})

    assert res["result"] == "Found 2 events."
    assert res["events"] == [
        {
            "title": "Daily Standup",
            "startDate": f"{today.strftime('%m/%d/%y')} 10:00 AM",
            "endDate": f"{today.strftime('%m/%d/%y')} 10:30 AM",
        },
        {
            "title": "Inside Range",
            "startDate": f"{today.strftime('%m/%d/%y')} 10:15 AM",
            "endDate": f"{today.strftime('%m/%d/%y')} 10:45 AM",
        },
    ]


@pytest.mark.asyncio
async def test_read_events_date_range_time_range_respects_exception_dates(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    today = datetime.now(ZoneInfo("UTC")).date()
    tomorrow = today + timedelta(days=1)

    habits_items = [
        {
            "habitId": "h2",
            "userId": "test-user",
            "name": "Morning Review",
            "creationDate": today - timedelta(days=2),
            "frequency": "1D",
            "days": [],
            "exceptionDates": [today],
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 9, "minute": 15},
            "length": 15,
        }
    ]

    mock_ddb = build_mock_ddb([], habits_items)
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.read_events_tool, "deserializer", Mock(deserialize=lambda v: v))

    payload = {
        "start_date": today.isoformat(),
        "end_date": tomorrow.isoformat(),
        "start_time": "09:00",
        "end_time": "09:30",
    }
    res = await s.processToolUse("read_events", {"content": json.dumps(payload)})

    assert res["result"] == "Found 1 events."
    assert res["events"] == [
        {
            "title": "Morning Review",
            "startDate": f"{tomorrow.strftime('%m/%d/%y')} 09:15 AM",
            "endDate": f"{tomorrow.strftime('%m/%d/%y')} 09:30 AM",
        }
    ]


@pytest.mark.asyncio
async def test_read_events_no_results_returns_friendly_message(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    today = datetime.now(ZoneInfo("UTC")).date()

    mock_ddb = build_mock_ddb([], [])
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.read_events_tool, "deserializer", Mock(deserialize=lambda v: v))

    payload = {"start_date": today.isoformat()}
    res = await s.processToolUse("read_events", {"content": json.dumps(payload)})

    assert res["result"] == "No events found for that time range."
    assert res["events"] == []


@pytest.mark.asyncio
async def test_read_events_uses_client_query_expression_strings(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    today = datetime.now(ZoneInfo("UTC")).date()

    mock_ddb = build_mock_ddb([], [])
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.read_events_tool, "deserializer", Mock(deserialize=lambda v: v))

    payload = {"start_date": today.isoformat()}
    await s.processToolUse("read_events", {"content": json.dumps(payload)})

    assert mock_ddb.query.call_count == 2

    events_query_kwargs = mock_ddb.query.call_args_list[0].kwargs
    habits_query_kwargs = mock_ddb.query.call_args_list[1].kwargs

    assert isinstance(events_query_kwargs["KeyConditionExpression"], str)
    assert events_query_kwargs["KeyConditionExpression"] == "userId = :user_id AND startDate BETWEEN :window_start AND :window_end"
    assert "ExpressionAttributeValues" in events_query_kwargs
    assert ":user_id" in events_query_kwargs["ExpressionAttributeValues"]
    assert ":window_start" in events_query_kwargs["ExpressionAttributeValues"]
    assert ":window_end" in events_query_kwargs["ExpressionAttributeValues"]

    assert isinstance(habits_query_kwargs["KeyConditionExpression"], str)
    assert habits_query_kwargs["KeyConditionExpression"] == "userId = :user_id"
    assert "ExpressionAttributeValues" in habits_query_kwargs
    assert ":user_id" in habits_query_kwargs["ExpressionAttributeValues"]
