import logging
import json
from datetime import datetime, date, timedelta, time
from annotated_types import doc
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
import uuid
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.repeating_event_config_model import HabitIndexModel, RepeatingEventConfigModel
from models.event_model import EventIndexModel, EventModel
import utils

# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()



def update_event_content(ddb_client, lambda_client, user_id, update_request, timezone, open_event_id=None):
  try:
    # If there is no open event, we can't update content, so we should return an appropriate message
    if not open_event_id:
      return {"result": "No event is currently open to update. Please open an event before trying to update its content."}

    tz = ZoneInfo(timezone)
    request_details = json.loads(update_request)
    logger.info(f"Parsed event details for update_event_content: {request_details}")
    
    action = request_details.get("action", None)
    if action == "undo":
      logger.info("Received undo action for update_event_content. Returning undo response.")
      return {
        "result": "Undoing",
        "tool_name": "update_event_content",
        "content_update": {
          "event_id": open_event_id,
          "op": "undo",
          "steps": 1
        }
      }
    else:
      """
        I must get the event's content from the database using the open_event_id.
        Then, I will use the change_instructions 
      """
      if request_details.get("change_instructions") is None:
        return {"result": "No change instructions provided. Please include change instructions to update the event content."}
      # get the event from DynamoDB
      ddb_event_item = ddb_client.get_item(
            TableName='Events',
            Key={'userId': {'S': user_id}, 'id': {'S': open_event_id}}
        )
      if not ddb_event_item.get('Item'):
        return {"result": f"Could not find the event in the database for that eventId."}
      logger.info(f"Fetched event item from DynamoDB for update: {ddb_event_item}")
      event_item = {k: deserializer.deserialize(v) for k, v in ddb_event_item['Item'].items()}
      event_content = event_item.get("content")
      if event_content is None:
        event_content  = {"content": [{"type": "paragraph"}], "type": "doc"}
      payload = {
        "userId": user_id,
        "prompt": request_details["change_instructions"],
        "content": event_content
      }
      print(f"Payload for content update Lambda: {payload}")
      response = lambda_client.invoke(
          FunctionName='clarityGenerateEditorContentService',
          InvocationType='RequestResponse',
          Payload=json.dumps(payload).encode('utf-8')
      )
      raw_payload = response["Payload"].read().decode("utf-8")

      if response.get("FunctionError"):
          logger.error(f"Lambda returned an error: {raw_payload}")
          return {"result": "The content generation Lambda returned an error."}

      lambda_result = json.loads(raw_payload) if raw_payload else {}
      result_body = json.loads(lambda_result.get("body", "{}"))
      
      print(f"Lambda result for content update: {lambda_result}")
      
      return {
        "result": "Updated the event content.",
        "tool_name": "update_event_content",
        "content_update": {
          "op": "replace_doc",
          "event_id": open_event_id,
          "updated_doc": result_body.get("doc")

        }
      }
      
    
    
  except Exception as e:
      logger.error(f"Error during event content update: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that update request."}