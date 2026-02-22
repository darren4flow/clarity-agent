import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import uuid
import logging
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import utils


# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()

def create_event(ddb_client, user_id, content, timezone):
  try:
    tz = ZoneInfo(timezone)
    event_details = json.loads(content)
    event_title = event_details.get("title", None)
    naive_start_datetime = event_details.get("start_datetime", None)
    length_minutes = event_details.get("length_minutes", 15)

    missing_fields = []
    if not event_title:
      missing_fields.append("title")
    if not naive_start_datetime:
      missing_fields.append("start_datetime")
    if not length_minutes:
      missing_fields.append("length_minutes")

    if missing_fields:
      return {
          "result": f"Missing required event details: {', '.join(missing_fields)}."
      }

    start_datetime = datetime.fromisoformat(naive_start_datetime).replace(tzinfo=tz)
    end_datetime = start_datetime + timedelta(minutes=length_minutes)

    notifications = []
    for notification in event_details.get("notifications", []):
      if "time_before" in notification and "time_unit" in notification:
        notifications.append({
          "id": str(uuid.uuid4()),
          "timeBefore": notification["time_before"],
          "timeUnit": notification["time_unit"],
        })

    if "recurrence" in event_details and event_details["recurrence"]:
      new_habit = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "name": event_title,
        "content": None,
        "creationDate": datetime.now(tz).strftime('%Y-%m-%d'), # YYYY-MM-DD in user's timezone
        "type": event_details.get("type", "personal"),
        "priority": event_details.get("priority", None),
        "fixed": event_details.get("fixed", False),
        "stopDate": event_details["recurrence"].get("stop_date", None),
        "frequency": str(event_details["recurrence"]["frequency"]) + utils.time_unit_map(event_details["recurrence"]["time_unit"]),
        "notifications": notifications,
        "days": event_details["recurrence"]["days"],
        "allDay": event_details.get("all_day", False),
        "exceptionDates": [],
        "prevVersionHabitId": None,
        "startTime": {
          "hour": start_datetime.hour,
          "minute": start_datetime.minute,
          "timezone": timezone
        },
        "length": event_details.get("length_minutes", 15),
      }
      ddb_habit_item= {k: serializer.serialize(v) for k, v in new_habit.items()}
      ddb_client.put_item(TableName='Habits', Item=ddb_habit_item)
      logger.info(f"DynamoDB put_item succeeded for habit: {new_habit}")
      result = f"Recuring event '{event_title}' created: {new_habit}"
    else:
      new_event = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "done": event_details.get("done", False),
        "description": event_title,
        "habitId": None,
        "allDay": event_details.get("all_day", False),
        "type": event_details.get("type", "personal"),
        "fixed": event_details.get("fixed", False),
        "priority": event_details.get("priority", None),
        "content": None,
        "startDate": start_datetime.isoformat(),
        "endDate": end_datetime.isoformat(),
        "notifications": notifications
      }
      ddb_event_item= {k: serializer.serialize(v) for k, v in new_event.items()}
      ddb_client.put_item(TableName='Events', Item=ddb_event_item)
      logger.info(f"DynamoDB put_item succeeded for event: {new_event}")
      result = f"Event '{event_title}' created: {new_event}"

    logger.info(f"Created event: {result}")
    logger.info(f"Event details: {event_details}")
  except Exception as e:
    logger.error(f"Error creating event: {e}", exc_info=True)
    result = f"Failed to create event: {str(e)}"
  
  return {"result": result}