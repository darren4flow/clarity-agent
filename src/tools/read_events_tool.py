import logging
import json
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.repeating_event_config_model import HabitIndexModel
from models.event_model import EventIndexModel
import utils

# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()

def read_events(ddb_client, user_id, content, timezone):
  try:
    tz = ZoneInfo(timezone)
    display_datetime_format = "%m/%d/%y %I:%M %p"

    def to_local_datetime(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tz)
        return parsed.astimezone(tz)

    def to_display_datetime(value: str) -> str:
        return to_local_datetime(value).strftime(display_datetime_format)

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
    
    window_start_utc = utils.to_utc_iso_z(window_start_dt)
    window_end_utc = utils.to_utc_iso_z(window_end_dt)

    results = []
    user_id_attr = serializer.serialize(user_id)

    logger.info(f"Querying events for user {user_id} between {window_start_utc} and {window_end_utc}")
    logger.info(f"Serialized user_id: {user_id_attr}, window_start: {serializer.serialize(window_start_utc)}, window_end: {serializer.serialize(window_end_utc)}")
    events_response = ddb_client.query(
        TableName='Events',
        IndexName='userId-startDate-index',
        KeyConditionExpression='userId = :user_id AND startDate BETWEEN :window_start AND :window_end',
        ExpressionAttributeValues={
            ':user_id': user_id_attr,
            ':window_start': serializer.serialize(window_start_utc),
            ':window_end': serializer.serialize(window_end_utc)
        }
    )
    event_items = events_response.get("Items", [])
    for item in event_items:
        event_item = {k: deserializer.deserialize(v) for k, v in item.items()}
        try:
            event = EventIndexModel.model_validate(event_item)
        except Exception as e:
            logger.warning(f"Skipping event due to validation error: {e}")
            continue
        start_date_str = event.startDate.isoformat()
        end_date_str = event.endDate.isoformat()
        if not start_date_str or not end_date_str:
            continue
        results.append({
            "title": event.description or "",
            "startDate": start_date_str,
            "endDate": end_date_str
        })

    habits_response = ddb_client.query(
        TableName='Habits',
        KeyConditionExpression='userId = :user_id',
        ExpressionAttributeValues={':user_id': user_id_attr}
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

    results.sort(key=lambda e: to_local_datetime(e["startDate"]))

    for event in results:
        event["startDate"] = to_display_datetime(event["startDate"])
        event["endDate"] = to_display_datetime(event["endDate"])

    if not results:
        return {"result": "No events found for that time range.", "events": []}

    return {"result": f"Found {len(results)} events.", "events": results}
  except Exception as e:
      logger.error(f"Error during read_events: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that read request."}