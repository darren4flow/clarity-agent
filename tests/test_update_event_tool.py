import sys
from pathlib import Path
from xxlimited import new
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import pytest
from unittest.mock import Mock
from types import SimpleNamespace
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import utils
from utils import get_utc_day_bounds
import tools.update_event_tool
import tools.create_event_tool


@pytest.mark.asyncio
async def test_getdatetool_returns_timezone():
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="u", timezone="UTC")
    res = await s.processToolUse("getDateTool", {})
    assert isinstance(res, dict)
    assert "in UTC" in res["result"]

@pytest.mark.asyncio
async def test_create_event_calls_ddb_put_item(monkeypatch):
    # replace ddb_client and serializer with mocks
    mock_ddb = Mock()
    mock_put = Mock()
    mock_ddb.put_item = mock_put
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.create_event_tool, "serializer", Mock(serialize=lambda v: v))

    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    event = {
        "title": "Test Meeting",
        "start_datetime": "2026-01-25T10:00:00",
        "length_minutes": 30,
        "notifications": [{"time_before": 10, "time_unit": "minutes"}]
    }
    tool_content = {"content": json.dumps(event)}
    res = await s.processToolUse("create_event", tool_content)

    print(res)

    assert isinstance(res, dict)
    assert "Event 'Test Meeting' created" in res["result"]
    assert mock_put.called

"""
------------------------------------------------------------------------------
START unsaved events, this event only tests
------------------------------------------------------------------------------
"""  
@pytest.mark.asyncio
async def test_update_repeating_unsaved_timed_event_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "length": 15
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    cfg = {        
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": False,
        "eventType": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None
    }
    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "this_event_only": True,
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "done": True,
        "fixed": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence" in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    actual_new_event = res["new_event"]
    del actual_new_event["id"]
    expected_new_event = {
      "userId": "test-user",
      "done": True,
      "description": "Updated Title",
      "habitId": "hid",
      "allDay": False,
      "type": "personal",
      "fixed": True,  
      "priority": "Critical",
      "content": None,
      "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
      "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
      "notifications": []
    }
    assert actual_new_event == expected_new_event


    expected_new_exception_dates = [datetime.now(ZoneInfo("UTC")).date()]
    actual_new_exception_dates = res["new_exception_dates"]
    assert actual_new_exception_dates == expected_new_exception_dates
      
@pytest.mark.asyncio
async def test_update_repeating_unsaved_timed_event_to_all_day_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "length": 15
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    #monkeypatch.setattr(s2s_session_manager.HabitIndexModel, "model_validate", Mock(return_value=cfg))
    #monkeypatch.setattr(s2s_session_manager.RepeatingEventConfigModel, "model_validate", Mock(return_value=cfg))

    # ensure utils reports the habit repeats on the target day
    #monkeypatch.setattr(s2s_session_manager.utils, "isRepeatingOnDay", Mock(return_value=True))
    cfg = {        
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": False,
        "eventType": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "this_event_only": True,
        "new_title": "Updated Title",
        "done": True,
        "fixed": True,
        "allDay": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence" in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    actual_new_event = res["new_event"]
    del actual_new_event["id"]
    expected_new_event = {
      "userId": "test-user",
      "done": True,
      "description": "Updated Title",
      "habitId": "hid",
      "allDay": True,
      "type": "personal",
      "fixed": True,  
      "priority": "Critical",
      "content": None,
      "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
      "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
      "notifications": []
    }
    assert actual_new_event == expected_new_event


    expected_new_exception_dates = [datetime.now(ZoneInfo("UTC")).date()]
    actual_new_exception_dates = res["new_exception_dates"]
    assert actual_new_exception_dates == expected_new_exception_dates
    
    
@pytest.mark.asyncio
async def test_update_repeating_unsaved_all_day_event_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "allDay": True,
            "exceptionDates": [],
            "length": 15
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    #monkeypatch.setattr(s2s_session_manager.HabitIndexModel, "model_validate", Mock(return_value=cfg))
    #monkeypatch.setattr(s2s_session_manager.RepeatingEventConfigModel, "model_validate", Mock(return_value=cfg))

    # ensure utils reports the habit repeats on the target day
    #monkeypatch.setattr(s2s_session_manager.utils, "isRepeatingOnDay", Mock(return_value=True))
    cfg = {        
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": True,
        "eventType": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "this_event_only": True,
        "new_title": "Updated Title",
        "done": True,
        "fixed": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence" in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    actual_new_event = res["new_event"]
    del actual_new_event["id"]
    expected_new_event = {
      "userId": "test-user",
      "done": True,
      "description": "Updated Title",
      "habitId": "hid",
      "allDay": True,
      "type": "personal",
      "fixed": True,  
      "priority": "Critical",
      "content": None,
      "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
      "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
      "notifications": []
    }
    assert actual_new_event == expected_new_event


    expected_new_exception_dates = [datetime.now(ZoneInfo("UTC")).date()]
    actual_new_exception_dates = res["new_exception_dates"]
    assert actual_new_exception_dates == expected_new_exception_dates

@pytest.mark.asyncio
async def test_update_repeating_unsaved_all_day_to_timed_event_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "allDay": True,
            "exceptionDates": [],
            "length": 15
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    #monkeypatch.setattr(s2s_session_manager.HabitIndexModel, "model_validate", Mock(return_value=cfg))
    #monkeypatch.setattr(s2s_session_manager.RepeatingEventConfigModel, "model_validate", Mock(return_value=cfg))

    # ensure utils reports the habit repeats on the target day
    #monkeypatch.setattr(s2s_session_manager.utils, "isRepeatingOnDay", Mock(return_value=True))
    cfg = {        
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": True,
        "eventType": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "new_start_time": "10:00",
        "this_event_only": True,
        "new_title": "Updated Title",
        "done": True,
        "fixed": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence" in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    actual_new_event = res["new_event"]
    del actual_new_event["id"]
    expected_new_event = {
      "userId": "test-user",
      "done": True,
      "description": "Updated Title",
      "habitId": "hid",
      "allDay": False,
      "type": "personal",
      "fixed": True,  
      "priority": "Critical",
      "content": None,
      "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
      "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
      "notifications": []
    }
    assert actual_new_event == expected_new_event


    expected_new_exception_dates = [datetime.now(ZoneInfo("UTC")).date()]
    actual_new_exception_dates = res["new_exception_dates"]
    assert actual_new_exception_dates == expected_new_exception_dates
"""
------------------------------------------------------------------------------
END unsaved events, this event only tests
------------------------------------------------------------------------------
"""   


 
"""
------------------------------------------------------------------------------
START repeating unsaved events, this and future events tests
------------------------------------------------------------------------------
"""      
@pytest.mark.asyncio
async def test_update_repeating_unsaved_timed_event_this_and_future_events(monkeypatch):
    """
    We have a recurring event. We want to update the current repeat event config to have a new stopDate.
    We want to create a new repeating event config starting from the specified occurrence date with the updated details.
    """
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "length": 15,
            "allDay": False
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    cfg = {
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": False,
        "type": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None,
        "prevVersionHabitId": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "new_start_time": "11:00",
        "this_and_future_events": True,
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "fixed": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated this and future occurrences from " in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_cfg = res["updated_repeat_config"]
    expected_updated_cfg = cfg.copy()
    expected_updated_cfg["stopDate"] = datetime.now(ZoneInfo("UTC")).date().isoformat()
    assert actual_updated_cfg == expected_updated_cfg
    
    
    # Ensure that the new repeat config has the updated details
    actual_new_cfg = res["new_repeat_config"]
    del actual_new_cfg["id"]
    expected_new_cfg = {
      "userId": "test-user",
      "startTime": {"timezone": "UTC", "hour": 11, "minute": 0},
      "exceptionDates": [],
      "length": payload["new_length_minutes"],
      "allDay": False,
      "type": "personal", 
      "fixed": payload["fixed"],
      "priority": payload["priority"],
      "content": None,
      "notifications": [],
      "name": payload["new_title"],
      "creationDate": (datetime.now(ZoneInfo("UTC")).date()).isoformat(),
      "frequency": "1D",
      "days": [],
      "stopDate": None,
      "prevVersionHabitId": "hid"
    }
    assert actual_new_cfg == expected_new_cfg

@pytest.mark.asyncio
async def test_update_repeating_unsaved_all_day_event_this_and_future_events(monkeypatch):
    """
    We have a recurring event. We want to update the current repeat event config to have a new stopDate.
    We want to create a new repeating event config starting from the specified occurrence date with the updated details.
    """
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "length": 15,
            "allDay": True
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    cfg = {
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": True,
        "type": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None,
        "prevVersionHabitId": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "this_and_future_events": True,
        "new_title": "Updated Title",
        "fixed": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated this and future occurrences from " in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_cfg = res["updated_repeat_config"]
    expected_updated_cfg = cfg.copy()
    expected_updated_cfg["stopDate"] = datetime.now(ZoneInfo("UTC")).date().isoformat()
    assert actual_updated_cfg == expected_updated_cfg
    
    
    # Ensure that the new repeat config has the updated details
    actual_new_cfg = res["new_repeat_config"]
    del actual_new_cfg["id"]
    expected_new_cfg = {
      "userId": "test-user",
      "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
      "exceptionDates": [],
      "length": 15,
      "allDay": True,
      "type": "personal", 
      "fixed": payload["fixed"],
      "priority": payload["priority"],
      "content": None,
      "notifications": [],
      "name": payload["new_title"],
      "creationDate": (datetime.now(ZoneInfo("UTC")).date()).isoformat(),
      "frequency": "1D",
      "days": [],
      "stopDate": None,
      "prevVersionHabitId": "hid"
    }
    assert actual_new_cfg == expected_new_cfg

@pytest.mark.asyncio
async def test_update_repeating_unsaved_timed_event_to_all_day_this_and_future_events(monkeypatch):
    """
    We have a recurring event. We want to update the current repeat event config to have a new stopDate.
    We want to create a new repeating event config starting from the specified occurrence date with the updated details.
    """
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "length": 15,
            "allDay": False
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    cfg = {
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": False,
        "type": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None,
        "prevVersionHabitId": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "new_start_date": (datetime.now(ZoneInfo("UTC")) + timedelta(days=1)).date().isoformat(),
        "this_and_future_events": True,
        "new_title": "Updated Title",
        "fixed": True,
        "allDay": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated this and future occurrences from " in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_cfg = res["updated_repeat_config"]
    expected_updated_cfg = cfg.copy()
    expected_updated_cfg["stopDate"] = datetime.now(ZoneInfo("UTC")).date().isoformat()
    assert actual_updated_cfg == expected_updated_cfg
    
    
    # Ensure that the new repeat config has the updated details
    actual_new_cfg = res["new_repeat_config"]
    del actual_new_cfg["id"]
    expected_new_cfg = {
      "userId": "test-user",
      "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
      "exceptionDates": [],
      "length": 15,
      "allDay": True,
      "type": "personal", 
      "fixed": payload["fixed"],
      "priority": payload["priority"],
      "content": None,
      "notifications": [],
      "name": payload["new_title"],
      "creationDate": (datetime.now(ZoneInfo("UTC"))+ timedelta(days=1)).date().isoformat(),
      "frequency": "1D",
      "days": [],
      "stopDate": None,
      "prevVersionHabitId": "hid"
    }
    assert actual_new_cfg == expected_new_cfg

@pytest.mark.asyncio
async def test_update_repeating_unsaved_all_day_event_to_timed_this_and_future_events(monkeypatch):
    """
    We have a recurring event. We want to update the current repeat event config to have a new stopDate.
    We want to create a new repeating event config starting from the specified occurrence date with the updated details.
    """
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1.0,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [],
            "length": 15,
            "allDay": True
        }
    }
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", Mock(search=Mock(return_value={"hits": {"total": {"value": 1}, "hits": [habit_hit]}})))

    # prepare cfg returned by HabitIndexModel.model_validate / RepeatingEventConfigModel.model_validate
    cfg = {
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [],
        "length": 15,
        "allDay": True,
        "type": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None,
        "prevVersionHabitId": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": cfg})
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "new_start_time": "11:00",
        "this_and_future_events": True,
        "new_title": "Updated Title",
        "fixed": True,
        "priority": "Critical"
    }
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated this and future occurrences from " in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_cfg = res["updated_repeat_config"]
    expected_updated_cfg = cfg.copy()
    expected_updated_cfg["stopDate"] = datetime.now(ZoneInfo("UTC")).date().isoformat()
    assert actual_updated_cfg == expected_updated_cfg
    
    
    # Ensure that the new repeat config has the updated details
    actual_new_cfg = res["new_repeat_config"]
    del actual_new_cfg["id"]
    expected_new_cfg = {
      "userId": "test-user",
      "startTime": {"timezone": "UTC", "hour": 11, "minute": 0},
      "exceptionDates": [],
      "length": 15,
      "allDay": False,
      "type": "personal", 
      "fixed": payload["fixed"],
      "priority": payload["priority"],
      "content": None,
      "notifications": [],
      "name": payload["new_title"],
      "creationDate": (datetime.now(ZoneInfo("UTC"))).date().isoformat(),
      "frequency": "1D",
      "days": [],
      "stopDate": None,
      "prevVersionHabitId": "hid"
    }
    assert actual_new_cfg == expected_new_cfg


"""
------------------------------------------------------------------------------
END repeating unsaved events, this and future events tests
------------------------------------------------------------------------------
"""   


"""
------------------------------------------------------------------------------
START repeating saved event, this event only tests
------------------------------------------------------------------------------
"""  
@pytest.mark.asyncio
async def test_update_repeating_saved_timed_event_this_event_only(monkeypatch):
    """
    In this case we have a repeat event config that has an exception date on the date the user specified 
    because that repeating event has been saved for that day. Which means we just need to modify the existing
    saved event. Nothing needs to be done to the repeat event config.
    """
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "this_event_only": True,
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "fixed": True,
        "priority": "critical"
    }

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [datetime.now(ZoneInfo("UTC")).date().isoformat()],  # ensure exception date exists because it's a saved event
            "length": 15
        }
    }
    habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Habit",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 1}, "hits": [events_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)


    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence on " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
        "description": "Updated Title",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": True,
        "content": None,
        "notifications": [],
        "priority": "critical"
    }
    assert actual_updated_event == expected_updated_event
    
@pytest.mark.asyncio
async def test_update_repeating_saved_all_day_event_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "this_event_only": True,
        "new_title": "Updated Title",
        "fixed": True,
        "priority": "critical"
    }

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [datetime.now(ZoneInfo("UTC")).date().isoformat()],  # ensure exception date exists because it's a saved event
            "length": 15,
            "allDay": True
        }
    }
    habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Habit",
        "done": False,
        "allDay": True,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 1}, "hits": [events_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)


    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence on " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "description": "Updated Title",
        "done": False,
        "allDay": True,
        "type": "personal",
        "fixed": True,
        "content": None,
        "notifications": [],
        "priority": "critical"
    }
    assert actual_updated_event == expected_updated_event

@pytest.mark.asyncio
async def test_update_repeating_saved_timed_event_to_all_day_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "this_event_only": True,
        "new_title": "Updated Title",
        "fixed": True,
        "allDay": True,
        "priority": "critical"
    }

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [datetime.now(ZoneInfo("UTC")).date().isoformat()],  # ensure exception date exists because it's a saved event
            "length": 15,
            "allDay": False
        }
    }
    habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Habit",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 1}, "hits": [events_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)


    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence on " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "description": "Updated Title",
        "done": False,
        "allDay": True,
        "type": "personal",
        "fixed": True,
        "content": None,
        "notifications": [],
        "priority": "critical"
    }
    assert actual_updated_event == expected_updated_event


@pytest.mark.asyncio
async def test_update_repeating_saved_all_day_event_to_timed_this_event_only(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "new_start_time": "11:00",
        "this_event_only": True,
        "new_title": "Updated Title",
        "fixed": True,
        "priority": "critical"
    }

    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    habit_hit = {
        "_id": "hid",
        "_score": 1,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [datetime.now(ZoneInfo("UTC")).date().isoformat()],  # ensure exception date exists because it's a saved event
            "length": 15,
            "allDay": True
        }
    }
    habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Habit",
        "done": False,
        "allDay": True,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 1}, "hits": [events_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)


    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated only the occurrence on " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:15:00+00:00",
        "description": "Updated Title",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": True,
        "content": None,
        "notifications": [],
        "priority": "critical"
    }
    assert actual_updated_event == expected_updated_event
"""
------------------------------------------------------------------------------
END repeating saved event, this event only tests
------------------------------------------------------------------------------
""" 


@pytest.mark.asyncio
async def test_update_repeating_saved_event_this_and_future_events(monkeypatch):
    """
    So this repeat event config has an exception date on the specified date.
    We'll set a stop date equal to the specified date
    We'll update the existing event
    We'll create a new repeat event config
    """
    """
    We have a recurring event. We want to update the current repeat event config to have a new stopDate.
    We want to create a new repeating event config starting from the specified occurrence date with the updated details.
    """
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")

    # call processToolUse for update_event with this_event_only = true
    payload = {
        "current_title": "Test Habit",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "this_and_future_events": True,
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "fixed": True,
        "priority": "critical"
    }
    
    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))

    # mock OpenSearch habits search (one habit hit)
    # It has an exception date
    habit_hit = {
        "_id": "hid",
        "_score": 1,
        "_source": {
            "userId": "test-user",
            "habitId": "hid",
            "title": "Test Habit",
            "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
            "stopDate": None,
            "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
            "frequency": "1D",
            "days": [],
            "exceptionDates": [datetime.now(ZoneInfo("UTC")).date().isoformat()],
            "length": 15
        }
    }
    habits_resp = {"hits": {"total": {"value": 1}, "hits": [habit_hit]}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": "hid",
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Habit",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 1}, "hits": [events_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)
    
    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')
    
    
    habit_data = {
        "userId": "test-user",
        "id": "hid",
        "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
        "exceptionDates": [datetime.now(ZoneInfo("UTC")).date().isoformat()],
        "length": 15,
        "allDay": False,
        "type": "personal", 
        "fixed": False,
        "priority": None,
        "content": None,
        "notifications": [],
        "name": "Test Habit",
        "creationDate": (datetime.now(ZoneInfo("UTC")).date() - timedelta(days=1)).isoformat(),
        "frequency": "1D",
        "days": [],
        "stopDate": None,
        "prevVersionHabitId": None
    }

    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(side_effect=[{"Item": ddb_event_data}, {"Item": habit_data}])
    mock_ddb.update_item = Mock()
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))

    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated this and future occurrences " in res["result"]
    assert mock_ddb.update_item.called
    assert mock_ddb.put_item.called
    
    
    # Ensure that the old repeat config has a stop date set
    actual_updated_cfg = res["updated_repeat_config"]
    expected_updated_cfg = habit_data.copy()
    expected_updated_cfg["stopDate"] = datetime.now(ZoneInfo("UTC")).date().isoformat()
    assert actual_updated_cfg == expected_updated_cfg
    
    
    # Ensure that the new repeat config has the updated details
    actual_new_cfg = res["new_repeat_config"]
    del actual_new_cfg["id"]
    expected_new_cfg = {
      "userId": "test-user",
      "startTime": {"timezone": "UTC", "hour": 10, "minute": 0},
      "exceptionDates": [datetime.now(ZoneInfo("UTC")).date()],
      "length": payload["new_length_minutes"],
      "allDay": False,
      "type": "personal", 
      "fixed": payload["fixed"],
      "priority": payload["priority"],
      "content": None,
      "notifications": [],
      "name": payload["new_title"],
      "creationDate": (datetime.now(ZoneInfo("UTC")).date()).isoformat(),
      "frequency": "1D",
      "days": [],
      "stopDate": None,
      "prevVersionHabitId": "hid"
    }
    assert actual_new_cfg == expected_new_cfg
    
    updated_new_event = res["updated_event"]
    del updated_new_event["id"]
    expected_updated_event = {
      "userId": "test-user",
      "done": False,
      "description": payload["new_title"],
      "habitId": "hid",
      "allDay": False,
      "type": "personal",
      "fixed": payload["fixed"],
      "priority": payload["priority"],
      "content": None,
      "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
      "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
      "notifications": []
    }
    assert updated_new_event == expected_updated_event
  
@pytest.mark.asyncio
async def test_update_nonrepeating_event(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Event",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "fixed": True,
        "priority": "critical",
        "done": True,
        "type": "work"
    }
    
    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))
    
    habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": None,
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Event",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 1}, "hits": [events_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)
    
    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')
    
    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))
    
   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated the event " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called

    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": None,
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
        "description": payload["new_title"],
        "done": payload["done"],
        "allDay": False,
        "type": payload["type"],
        "fixed": payload["fixed"],
        "content": None,
        "notifications": [],
        "priority": payload["priority"]
    }
    assert actual_updated_event == expected_updated_event
    
    
@pytest.mark.asyncio
async def test_update_nonrepeating_event_multiple_matches_date_and_time_given(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Event",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "fixed": True,
        "priority": "critical",
        "done": True,
        "type": "work"
    }
    
    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))
    
    habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": None,
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Event",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    event2_data = event_data.copy()
    event2_data['startDate'] = (datetime.now(ZoneInfo("UTC")).date() + timedelta(days=1)).isoformat() + "T11:00:00+00:00"
    event2_data['endDate'] = (datetime.now(ZoneInfo("UTC")).date() + timedelta(days=1)).isoformat() + "T11:15:00+00:00"
    event2_data['eventId'] = "eid2"
    event2_hit = {
        "_id": "eid2",
        "_source": event2_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 2}, "hits": [events_hit, event2_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)
    
    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')
    
    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))
    
   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated the event " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called

    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": None,
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
        "description": payload["new_title"],
        "done": payload["done"],
        "allDay": False,
        "type": payload["type"],
        "fixed": payload["fixed"],
        "content": None,
        "notifications": [],
        "priority": payload["priority"]
    }
    assert actual_updated_event == expected_updated_event



    
@pytest.mark.asyncio
async def test_update_nonrepeating_event_multiple_matches_only_date_given(monkeypatch):
    s = S2sSessionManager(region="us-east-1", model_id="m", user_id="test-user", timezone="UTC")
    
    payload = {
        "current_title": "Test Event",
        "current_start_date": datetime.now(ZoneInfo("UTC")).date().isoformat(),
        "current_start_time": "10:00",
        "new_title": "Updated Title",
        "new_length_minutes": 60,
        "fixed": True,
        "priority": "critical",
        "done": True,
        "type": "work"
    }
    
    # mock Bedrock embed response
    embed_body = Mock()
    embed_body.read = Mock(return_value=json.dumps({"embedding": [0.1, 0.2]}).encode("utf-8"))
    monkeypatch.setattr(s2s_session_manager, "bedrock_client", Mock(invoke_model=Mock(return_value={"body": embed_body})))
    
    habits_resp = {"hits": {"total": {"value": 0}, "hits": []}}
    event_data = {
        "eventId": "eid",
        "userId": "test-user",
        "habitId": None,
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:15:00+00:00",
        "title": "Test Event",
        "done": False,
        "allDay": False,
        "type": "personal",
        "fixed": False,
        "content": None,
        "notifications": [],
        "priority": None
    }
    events_hit = {
        "_id": "eid",
        "_source": event_data,
        "_score": 1
    }
    event2_data = event_data.copy()
    event2_data['startDate'] = (datetime.now(ZoneInfo("UTC")).date() + timedelta(days=1)).isoformat() + "T11:00:00+00:00"
    event2_data['endDate'] = (datetime.now(ZoneInfo("UTC")).date() + timedelta(days=1)).isoformat() + "T11:15:00+00:00"
    event2_data['eventId'] = "eid2"
    event2_hit = {
        "_id": "eid2",
        "_source": event2_data,
        "_score": 1
    }
    events_resp = {"hits": {"total": {"value": 2}, "hits": [events_hit, event2_hit]}}
    mock_os = Mock()
    mock_os.search.side_effect = [habits_resp, events_resp]
    monkeypatch.setattr(s2s_session_manager, "opensearch_client", mock_os)
    
    ddb_event_data = event_data.copy()
    ddb_event_data['id'] = ddb_event_data.pop('eventId')
    ddb_event_data['description'] = ddb_event_data.pop('title')
    
    # mock DynamoDB + serializer/deserializer
    mock_ddb = Mock()
    mock_ddb.get_item = Mock(return_value={"Item": ddb_event_data})
    mock_ddb.put_item = Mock()
    monkeypatch.setattr(s2s_session_manager, "ddb_client", mock_ddb)
    monkeypatch.setattr(tools.update_event_tool, "serializer", Mock(serialize=lambda v: v))
    monkeypatch.setattr(tools.update_event_tool, "deserializer", Mock(deserialize=lambda v: v))
    
   # call processToolUse for update_event with this_event_only = true
    res = await s.processToolUse("update_event", {"content": json.dumps(payload)})
    
    assert isinstance(res, dict)
    assert "Successfully updated the event " in res["result"]
    assert mock_ddb.get_item.called
    assert mock_ddb.put_item.called

    # Ensure that the old repeat config has a stop date set
    actual_updated_event = res["updated_event"]
    expected_updated_event = {
        "id": "eid",
        "userId": "test-user",
        "habitId": None,
        "startDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T10:00:00+00:00",
        "endDate": datetime.now(ZoneInfo("UTC")).date().isoformat() + "T11:00:00+00:00",
        "description": payload["new_title"],
        "done": payload["done"],
        "allDay": False,
        "type": payload["type"],
        "fixed": payload["fixed"],
        "content": None,
        "notifications": [],
        "priority": payload["priority"]
    }
    assert actual_updated_event == expected_updated_event
    
    
def test_get_utc_day_bounds():
    # set to today's date in Eastern Time
    tz = ZoneInfo("America/New_York")
    today_et = datetime.now(tz).date()
    
    start, end = get_utc_day_bounds(today_et, "America/New_York")
    # check that the start is 00:00 ET in UTC
    expected_start = datetime.combine(today_et, time(0, 0), tzinfo=tz).astimezone(ZoneInfo("UTC"))
    expected_end = expected_start + timedelta(days=1)
    assert start == expected_start
    assert end == expected_end
    
def test_get_utc_day_bounds_dst_spring_forward():
    tz = ZoneInfo("America/New_York")
    local_date = datetime(2024, 3, 10).date()  # DST starts in US

    start, end = get_utc_day_bounds(local_date, "America/New_York")

    expected_start = datetime.combine(local_date, time(0, 0), tzinfo=tz).astimezone(ZoneInfo("UTC"))
    expected_end = datetime.combine(datetime(2024, 3, 11).date(), time(0, 0), tzinfo=tz).astimezone(ZoneInfo("UTC"))

    assert start == expected_start
    assert end == expected_end
    assert (end - start) == timedelta(hours=23)