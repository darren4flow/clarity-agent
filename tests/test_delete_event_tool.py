import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import pytest
from unittest.mock import Mock
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _mock_bedrock(monkeypatch):
	embed_body = Mock()
	embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
	monkeypatch.setattr(
		s2s_session_manager,
		"bedrock_client",
		Mock(invoke_model=Mock(return_value={"body": embed_body})),
	)


def _mock_serializer(monkeypatch):
	monkeypatch.setattr(s2s_session_manager, "serializer", Mock(serialize=lambda v: v))


@pytest.mark.asyncio
async def test_delete_repeating_unsaved_event_this_event_only(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)
	_mock_serializer(monkeypatch)
	monkeypatch.setattr(s2s_session_manager.utils, "isRepeatingOnDay", Mock(return_value=True))

	habit_hit = {
		"_id": "hid",
		"_score": 1.0,
		"_source": {
			"userId": "test-user",
			"habitId": "hid",
			"title": "Daily Standup",
			"creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
			"stopDate": None,
			"startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
			"frequency": "1D",
			"days": [],
			"exceptionDates": [],
			"length": 15,
		},
	}
	habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value=habits_resp)))

	mock_ddb = Mock()
	mock_ddb.update_item = Mock()
	monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)

	payload = {
		"title": "Daily Standup",
		"start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
		"start_time": "10:00",
		"this_event_only": True,
	}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "Successfully deleted only the occurrence" in res["result"]
	assert mock_ddb.update_item.called


@pytest.mark.asyncio
async def test_delete_repeating_unsaved_event_this_and_future(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)
	_mock_serializer(monkeypatch)
	monkeypatch.setattr(s2s_session_manager.utils, "isRepeatingOnDay", Mock(return_value=True))

	habit_hit = {
		"_id": "hid",
		"_score": 1.0,
		"_source": {
			"userId": "test-user",
			"habitId": "hid",
			"title": "Daily Standup",
			"creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
			"stopDate": None,
			"startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
			"frequency": "1D",
			"days": [],
			"exceptionDates": [],
			"length": 15,
		},
	}
	habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value=habits_resp)))

	mock_ddb = Mock()
	mock_ddb.update_item = Mock()
	monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)

	payload = {
		"title": "Daily Standup",
		"start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
		"start_time": "10:00",
		"this_and_future_events": True,
	}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "Successfully deleted this and future occurrences" in res["result"]
	assert mock_ddb.update_item.called


@pytest.mark.asyncio
async def test_delete_repeating_event_requires_start_date(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)
	_mock_serializer(monkeypatch)

	habit_hit = {
		"_id": "hid",
		"_score": 1.0,
		"_source": {
			"userId": "test-user",
			"habitId": "hid",
			"title": "Daily Standup",
			"creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
			"stopDate": None,
			"startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
			"frequency": "1D",
			"days": [],
			"exceptionDates": [],
			"length": 15,
		},
	}
	habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value=habits_resp)))

	mock_ddb = Mock()
	mock_ddb.update_item = Mock()
	monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)

	payload = {"title": "Daily Standup"}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "Cannot delete event 'Daily Standup'" in res["result"]
	assert not mock_ddb.update_item.called


@pytest.mark.asyncio
async def test_delete_nonrepeating_event_single_match(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)
	_mock_serializer(monkeypatch)

	habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
	event_data = {
		"eventId": "eid",
		"title": "Project Review",
		"startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
		"endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:30:00+00:00",
		"userId": "test-user",
	}
	events_resp = {"hits": {"total": {"value": 1}, "hits": [{"_id": "eid", "_source": event_data, "_score": 1.0}]}}

	mock_os = Mock()
	mock_os.search.side_effect = [habits_resp, events_resp]
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)

	mock_ddb = Mock()
	mock_ddb.delete_item = Mock()
	monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)

	payload = {
		"title": "Project Review",
		"start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
		"start_time": "10:00",
	}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "Successfully deleted the event 'Project Review'" in res["result"]
	assert mock_ddb.delete_item.called


@pytest.mark.asyncio
async def test_delete_saved_repeating_event_this_event_only(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)
	_mock_serializer(monkeypatch)

	habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
	event_data = {
		"eventId": "eid",
		"title": "Daily Standup",
		"startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
		"endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
		"userId": "test-user",
		"habitId": "hid",
	}
	events_resp = {"hits": {"total": {"value": 1}, "hits": [{"_id": "eid", "_source": event_data, "_score": 1.0}]}}

	mock_os = Mock()
	mock_os.search.side_effect = [habits_resp, events_resp]
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)

	mock_ddb = Mock()
	mock_ddb.delete_item = Mock()
	monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)

	payload = {
		"title": "Daily Standup",
		"start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
		"start_time": "10:00",
		"this_event_only": True,
	}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "Successfully deleted only the occurrence" in res["result"]
	assert mock_ddb.delete_item.called



@pytest.mark.asyncio
async def test_delete_saved_event_low_score_match(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)
	_mock_serializer(monkeypatch)

	habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
	event_data = {
		"eventId": "eid",
		"title": "Daily Standup",
		"startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
		"endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
		"userId": "test-user",
	}
	events_resp = {"hits": {"total": {"value": 1}, "hits": [{"_id": "eid", "_source": event_data, "_score": 0.5}]}}

	mock_os = Mock()
	mock_os.search.side_effect = [habits_resp, events_resp]
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)

	mock_ddb = Mock()
	mock_ddb.delete_item = Mock()
	monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)

	payload = {
		"title": "Daily Standup",
		"start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
		"start_time": "10:00",
		"this_event_only": True,
	}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "No events found matching title" in res["result"]


@pytest.mark.asyncio
async def test_delete_multiple_matches_date_only_prompts_for_time(monkeypatch):
	s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

	_mock_bedrock(monkeypatch)

	habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
	date_str = datetime.now(ZoneInfo("UTC")).date().isoformat()
	events_resp = {
		"hits": {
			"total": {"value": 2},
			"hits": [
				{"_id": "e1", "_score": 1, "_source": {"eventId": "e1", "title": "Team Sync", "startDate": date_str + "T09:00:00+00:00"}},
				{"_id": "e2", "_score": 1, "_source": {"eventId": "e2", "title": "Team Sync", "startDate": date_str + "T11:00:00+00:00"}},
			],
		}
	}

	mock_os = Mock()
	mock_os.search.side_effect = [habits_resp, events_resp]
	monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)

	payload = {
		"title": "Team Sync",
		"start_date": date_str,
	}
	res = await s.processToolUse("delete_event", {"content": json.dumps(payload)})

	assert isinstance(res, dict)
	assert "Please provide the start time" in res["result"]
