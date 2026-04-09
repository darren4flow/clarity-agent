import logging
import json
from datetime import datetime, date, timedelta, time
from annotated_types import doc
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
import uuid
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.repeating_event_config_model import HabitIndexModel, RepeatingEventConfigModel, FREQ_RE
from models.event_model import EventIndexModel, EventModel
import utils

# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()



def update_open_event_tool(ddb_client, lambda_client, user_id, update_request, timezone, open_event_id=None, last_open_event_update=None):
  try:
    # If there is no open event, we can't update content, so we should return an appropriate message
    if not open_event_id:
      return {"result": "No event is currently open to update. Please open an event before trying to update its content."}

    tz = ZoneInfo(timezone)
    request_details = json.loads(update_request)
    logger.info(f"Parsed event details for update_open_event: {request_details}")
    
    action = request_details.get("action", None)
    if action == "undo":
      if not last_open_event_update:
        return {
          "result": "There is no prior open event update to undo.",
          "tool_name": "update_open_event",
          "action": "undo_noop"
        }

      snapshot_event_id = last_open_event_update.get("event_id")
      if snapshot_event_id and snapshot_event_id != open_event_id:
        return {
          "result": "Cannot undo because the open event changed.",
          "tool_name": "update_open_event",
          "action": "undo_noop"
        }

      snapshot_event_data = last_open_event_update.get("event_data")
      if isinstance(snapshot_event_data, str):
        snapshot_event_data = json.loads(snapshot_event_data)

      if not isinstance(snapshot_event_data, dict):
        return {
          "result": "Could not undo because the previous event snapshot is invalid.",
          "tool_name": "update_open_event",
          "action": "undo_noop"
        }

      try:
        ddb_snapshot_item = {k: serializer.serialize(v) for k, v in snapshot_event_data.items()}
        ddb_client.put_item(
          TableName='Events',
          Item=ddb_snapshot_item
        )
        logger.info(f"Successfully restored prior event snapshot for eventId {open_event_id} and userId {user_id}")
      except Exception as e:
        logger.error(f"Error undoing event update in DynamoDB: {e}", exc_info=True)
        return {"result": "Sorry, I couldn't undo the event update in the database."}

      return {
        "result": "Undid the last update.",
        "tool_name": "update_open_event",
        "action": "undo",
        "event_data": json.dumps(snapshot_event_data),
        "updated_fields": json.dumps({})
      }
    else:
      def _normalize_recurrence_frequency(raw_frequency, raw_time_unit, fallback_frequency=None):
        # Accept numeric interval + time_unit (preferred), with safe fallbacks.
        if raw_time_unit is not None:
          unit_suffix = utils.time_unit_map(str(raw_time_unit).lower())
          interval = int(raw_frequency) if raw_frequency is not None else 1
          return f"{interval}{unit_suffix}"

        if raw_frequency is None:
          return fallback_frequency

        frequency_str = str(raw_frequency)
        if FREQ_RE.match(frequency_str):
          return frequency_str

        if frequency_str.isdigit():
          if fallback_frequency and FREQ_RE.match(fallback_frequency):
            old_unit = re.sub(r"^\d+", "", fallback_frequency)
            return f"{int(frequency_str)}{old_unit}"
          return f"{int(frequency_str)}D"

        return frequency_str

      def _parse_datetime(value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
          return parsed.replace(tzinfo=tz)
        return parsed

      # get the event from DynamoDB
      ddb_event_item = ddb_client.get_item(
            TableName='Events',
            Key={'userId': {'S': user_id}, 'id': {'S': open_event_id}}
        )
      if not ddb_event_item.get('Item'):
        return {"result": f"Could not find the event in the database for that eventId."}
      logger.info(f"Fetched event item from DynamoDB for update: {ddb_event_item}")
      event_item = {k: deserializer.deserialize(v) for k, v in ddb_event_item['Item'].items()}
      current_start_datetime = datetime.fromisoformat(event_item["startDate"]).replace(tzinfo=tz)
      current_end_datetime = datetime.fromisoformat(event_item["endDate"]).replace(tzinfo=tz)
      current_length = int((current_end_datetime - current_start_datetime).total_seconds() / 60)

      new_start_date = None
      new_start_time_str = None
      new_end_date = None
      new_end_time_str = None

      to_update_fields = {k: v for k, v in request_details.items() if k not in ["action"] and v is not None}
      has_recurrence_intent = "recurrence" in to_update_fields and to_update_fields["recurrence"] is not None
      updated_fields = {}
      for key, value in to_update_fields.items():
        if key == "title":
          updated_fields["description"] = value
        elif key == "notifications":
          updated_fields["notifications"] = utils.add_ids_to_notifications(value)
        elif key == "tasks_content_prompt":
          updated_fields["content"] = utils.generate_update_content(lambda_client, user_id, value, event_item.get("content", None))
        elif key == "start_date":
          new_start_date = date.fromisoformat(value)
          new_start_datetime = utils.get_new_start_datetime(
            current_start_datetime,
            new_start_date=new_start_date,
            new_start_time_str=new_start_time_str
          )
          updated_fields["startDate"] = new_start_datetime.isoformat()
        elif key == "start_time":
          new_start_time_str = value
          new_start_datetime = utils.get_new_start_datetime(
            current_start_datetime,
            new_start_date=new_start_date,
            new_start_time_str=new_start_time_str
          )
          updated_fields["startDate"] = new_start_datetime.isoformat()
        elif key == "end_date":
          new_end_date = date.fromisoformat(value)
        elif key == "end_time":
          new_end_time_str = value
        elif key == "recurrence":
            if "frequency" in value:
              new_frequency = _normalize_recurrence_frequency(value.get("frequency"), value.get("timeUnit"))
              if not new_frequency or not FREQ_RE.match(new_frequency):
                return {"result": "Invalid recurrence frequency. Use numeric frequency with time_unit (daily/weekly/monthly/yearly)."}
              updated_fields["frequency"] = new_frequency
            if "days" in value:
              updated_fields["days"] = value["days"]
            if "stop_date" in value:
              updated_fields["stopDate"] = value["stop_date"]
        else:
          updated_fields[key] = value

      if any(v is not None for v in [new_start_date, new_start_time_str, new_end_date, new_end_time_str]):
        try:
          new_start_datetime = utils.get_new_start_datetime(
            current_start_datetime,
            new_start_date=new_start_date,
            new_start_time_str=new_start_time_str
          )
          new_end_datetime = utils.get_new_end_datetime(
            current_length,
            current_start_datetime,
            current_end_datetime,
            new_start_date=new_start_date,
            new_start_time_str=new_start_time_str,
            new_end_date=new_end_date,
            new_end_time_str=new_end_time_str
          )
          updated_fields["startDate"] = new_start_datetime.isoformat()
          updated_fields["endDate"] = new_end_datetime.isoformat()
        except Exception as e:
          return {"result": f"Invalid date/time update: {e}"}

      effective_start_datetime = datetime.fromisoformat(updated_fields.get("startDate", event_item["startDate"])).replace(tzinfo=tz)
      effective_end_datetime = datetime.fromisoformat(updated_fields.get("endDate", event_item["endDate"])).replace(tzinfo=tz)
      if effective_end_datetime <= effective_start_datetime:
        return {"result": "Invalid date/time range: end date/time must be after start date/time."}

      effective_start_local = effective_start_datetime.astimezone(tz)
      effective_end_local = effective_end_datetime.astimezone(tz)
      effective_length_minutes = int((effective_end_local - effective_start_local).total_seconds() / 60)

      if has_recurrence_intent:
        # stop_date is currently accepted but intentionally ignored for new config creation.
        if event_item.get("habitId"):
          old_habit_id = event_item["habitId"]
          ddb_config_item = ddb_client.get_item(
            TableName='Habits',
            Key={'userId': {'S': user_id}, 'id': {'S': old_habit_id}}
          )
          if not ddb_config_item.get('Item'):
            return {"result": "Could not find the recurring event config in the database for the open event."}

          config_item = {k: deserializer.deserialize(v) for k, v in ddb_config_item['Item'].items()}
          cfg = RepeatingEventConfigModel.model_validate(config_item)

          new_stop_date = current_start_datetime.date()
          ddb_client.update_item(
            TableName='Habits',
            Key={'userId': {'S': user_id}, 'id': {'S': cfg.id}},
            UpdateExpression="SET stopDate = :sd",
            ExpressionAttributeValues={":sd": serializer.serialize(utils._to_dynamodb_compatible(new_stop_date))}
          )

          new_repeat_config = {
            "id": str(uuid.uuid4()),
            "userId": cfg.userId,
            "name": updated_fields.get("description", event_item.get("description", cfg.name)),
            "content": updated_fields.get("content", event_item.get("content", cfg.content)),
            "creationDate": effective_start_local.date().strftime('%Y-%m-%d'),
            "type": updated_fields.get("type", event_item.get("type", cfg.eventType)),
            "priority": updated_fields.get("priority", event_item.get("priority", cfg.priority)),
            "fixed": updated_fields.get("fixed", event_item.get("fixed", cfg.fixed)),
            "stopDate": None,
            "frequency": updated_fields.get("frequency", cfg.frequency),
            "notifications": updated_fields.get("notifications", event_item.get("notifications", cfg.notifications or [])),
            "days": updated_fields.get("days") if updated_fields.get("days") is not None else cfg.days,
            "allDay": updated_fields.get("allDay", event_item.get("allDay", cfg.allDay)),
            "exceptionDates": cfg.exceptionDates or [],
            "prevVersionHabitId": cfg.id,
            "startTime": {
              "hour": effective_start_local.hour,
              "minute": effective_start_local.minute,
              "timezone": timezone
            },
            "length": effective_length_minutes,
          }
          validated_new_repeat = RepeatingEventConfigModel.model_validate(new_repeat_config)
          normalized_repeat = validated_new_repeat.model_dump(mode="python")
          ddb_habit_item = {
            k: serializer.serialize(utils._to_dynamodb_compatible(v))
            for k, v in normalized_repeat.items()
          }
          ddb_client.put_item(TableName='Habits', Item=ddb_habit_item)
          updated_fields["habitId"] = normalized_repeat["id"]
        else:
          new_repeat_config = {
            "id": str(uuid.uuid4()),
            "userId": user_id,
            "name": updated_fields.get("description", event_item.get("description", "Recurring Event")),
            "content": updated_fields.get("content", event_item.get("content", None)),
            "creationDate": effective_start_local.date().strftime('%Y-%m-%d'),
            "type": updated_fields.get("type", event_item.get("type", "personal")),
            "priority": updated_fields.get("priority", event_item.get("priority", None)),
            "fixed": updated_fields.get("fixed", event_item.get("fixed", False)),
            "stopDate": None,
            "frequency": updated_fields.get("frequency", None),
            "notifications": updated_fields.get("notifications", event_item.get("notifications", [])),
            "days": updated_fields.get("days", []),
            "allDay": updated_fields.get("allDay", event_item.get("allDay", False)),
            "exceptionDates": [effective_start_local.date().strftime('%Y-%m-%d')],
            "prevVersionHabitId": None,
            "startTime": {
              "hour": effective_start_local.hour,
              "minute": effective_start_local.minute,
              "timezone": timezone
            },
            "length": effective_length_minutes,
          }
          validated_new_repeat = RepeatingEventConfigModel.model_validate(new_repeat_config)
          normalized_repeat = validated_new_repeat.model_dump(mode="python")
          ddb_habit_item = {
            k: serializer.serialize(utils._to_dynamodb_compatible(v))
            for k, v in normalized_repeat.items()
          }
          ddb_client.put_item(TableName='Habits', Item=ddb_habit_item)
          updated_fields["habitId"] = normalized_repeat["id"]
      
      
      updated_event = {**event_item, **updated_fields}
      try:
        ddb_event_item= {k: serializer.serialize(v) for k, v in updated_event.items()}
        ddb_client.put_item(
          TableName='Events',
          Item=ddb_event_item
        )
        logger.info(f"Successfully updated event in DynamoDB with eventId {open_event_id} for userId {user_id}. Updated fields: {updated_fields.keys()}")
      except Exception as e:
        logger.error(f"Error updating event in DynamoDB: {e}", exc_info=True)
        return {"result": "Sorry, I couldn't update the event in the database."}
      
      return {
        "result": "Updated the event.",
        "tool_name": "update_open_event",
        "action": "update",
        "event_data": json.dumps(updated_event),
        "updated_fields": json.dumps(updated_fields)
      }
      
  except Exception as e:
      logger.error(f"Error during event content update: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that update request."}