import logging
import json
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
from boto3.dynamodb.conditions import Key
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repeating_event_config_model import HabitIndexModel
import utils

# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()

def read_events(ddb_client, user_id, content, timezone):
  try:
    tz = ZoneInfo(timezone)
    logger.info(f"Processing read_events with content: {content}")
    event_details = json.loads(content)

    start_date = date.fromisoformat(event_details.get("start_date")) if event_details.get("start_date") else None
    end_date = date.fromisoformat(event_details.get("end_date")) if event_details.get("end_date") else None
    start_time_str = event_details.get("start_time")
    end_time_str = event_details.get("end_time")

    today = datetime.now(tz).date()
    if start_date is None:
        if end_date is not None:
            start_date = today
        elif start_time_str or end_time_str:
            start_date = today
        else:
            start_date = today

    if end_date is None:
        end_date = start_date

    if start_time_str:
        start_time_value = datetime.strptime(start_time_str, "%H:%M").time()
    else:
        start_time_value = time(0, 0, 0)

    if end_time_str:
        end_time_value = datetime.strptime(end_time_str, "%H:%M").time()
    elif start_time_str:
        end_time_value = start_time_value
    else:
        end_time_value = time(23, 59, 59)

    if end_date < start_date:
        return {"result": "End date must be on or after start date."}

    if end_time_value < start_time_value and start_date == end_date:
        return {"result": "End time must be on or after start time."}

    def is_within_window(dt: datetime) -> bool:
        local_dt = dt.astimezone(tz) if dt.tzinfo else dt.replace(tzinfo=tz)
        local_date = local_dt.date()
        if local_date < start_date or local_date > end_date:
            return False
        if start_time_str or end_time_str:
            local_time = local_dt.time()
            return start_time_value <= local_time <= end_time_value
        return True
    
    window_start_dt = datetime.combine(start_date, start_time_value).replace(tzinfo=tz)
    window_end_dt = datetime.combine(end_date, end_time_value).replace(tzinfo=tz)

    results = []

    events_response = ddb_client.query(
        TableName='Events',
        IndexName='userId-startDate-index',
        KeyConditionExpression=(
            Key('userId').eq(user_id)
            & Key('startDate').between(window_start_dt.isoformat(), window_end_dt.isoformat())
        )
    )
    event_items = events_response.get("Items", [])
    for item in event_items:
        event_item = {k: deserializer.deserialize(v) for k, v in item.items()}
        start_date_str = event_item.get("startDate")
        end_date_str = event_item.get("endDate")
        if not start_date_str or not end_date_str:
            continue
        results.append({
            "title": event_item.get("description") or event_item.get("title") or "",
            "startDate": start_date_str,
            "endDate": end_date_str
        })

    habits_response = ddb_client.query(
        TableName='Habits',
        KeyConditionExpression=Key('userId').eq(user_id)
    )
    habit_items = habits_response.get("Items", [])
    for item in habit_items:
        habit_item = {k: deserializer.deserialize(v) for k, v in item.items()}
        try:
            cfg = HabitIndexModel.model_validate(habit_item)
        except Exception as e:
            logger.warning(f"Skipping habit due to validation error: {e}")
            continue

        current_date = start_date
        while current_date <= end_date:
            if utils.isRepeatingOnDay(cfg, current_date):
                habit_tz = ZoneInfo(cfg.startTime.timezone)
                start_dt = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    cfg.startTime.hour,
                    cfg.startTime.minute,
                    tzinfo=habit_tz
                )
                if is_within_window(start_dt):
                    end_dt = start_dt + timedelta(minutes=cfg.length)
                    results.append({
                        "title": cfg.name,
                        "startDate": start_dt.astimezone(tz).isoformat(),
                        "endDate": end_dt.astimezone(tz).isoformat()
                    })
            current_date += timedelta(days=1)

    results.sort(key=lambda e: datetime.fromisoformat(e["startDate"]))

    if not results:
        return {"result": "No events found for that time range.", "events": []}

    return {"result": f"Found {len(results)} events.", "events": results}
  except Exception as e:
      logger.error(f"Error during read_events: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that read request."}