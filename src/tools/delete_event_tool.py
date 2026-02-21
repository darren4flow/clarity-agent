import json
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo
import sys
from pathlib import Path
import logging
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repeating_event_config_model import HabitIndexModel
import utils


# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()

def delete_event(ddb_client, bedrock_client, opensearch_client, user_id, content, timezone):
  try:
      tz = ZoneInfo(timezone)
      logger.info(f"Processing delete_event with content: {content}")
      event_details = json.loads(content)
      event_title = event_details.get("title")
      
      start_date = date.fromisoformat(event_details.get("start_date", None)) if event_details.get("start_date", None) else None
      start_time = event_details.get("start_time", None)
      
      #naive_start_datetime = event_details.get("start_datetime")
      #start_datetime = None
      
      logger.info(f"Searching for event to delete: title='{event_title}', start_date='{start_date}', start_time='{start_time}'")
      # 1. Vectorize and Hybrid Search to find candidate events
      embed_response = bedrock_client.invoke_model(
          body=json.dumps({"inputText": event_title}),
          modelId="amazon.titan-embed-text-v1"
      )
      query_vector = json.loads(embed_response['body'].read())['embedding']
      logger.info(f"Generated embedding for event title: {event_title}")
      filters = [{"term": {"userId": user_id}}]
      #if naive_start_datetime:
      #    start_datetime = datetime.fromisoformat(naive_start_datetime).replace(tzinfo=tz)
      
      search_body ={
          "size": 5,
          "track_total_hits": True,
          "query": {
              "bool": {
                  "filter": filters,
                  "should": [
                      {"match": {"title": {"query": event_title, "fuzziness": "AUTO"}}},
                      {"knn": {"title_vector": {"vector": query_vector, "k": 5}}},
                  ],
                  "minimum_should_match": 1,
              }
          }
      }
      opensearch_habits_response = opensearch_client.search(
          index="habits",
          body=search_body
      )
      logger.info(f"OpenSearch habits search response: {opensearch_habits_response}")
      matching_habit_names_found = opensearch_habits_response['hits']['total']['value']
      logger.info(f"Found {matching_habit_names_found} matching habits:")
      unfiltered_habit_hits = opensearch_habits_response['hits']['hits']
      habit_hits = []
      for hit in unfiltered_habit_hits:
          if hit['_score'] >= 1.0:  # filter out low relevance matches
              habit_hits.append(hit)
          logger.info(f"score: {hit['_score']}, title: {hit['_source']['title']}")
      
      if len(habit_hits) > 0:
          logger.info(f"Found {len(habit_hits)} matching habits with title '{event_title}'")
          if start_date:
              matches = []
              for habit_hit in habit_hits:
                  cfg = HabitIndexModel.model_validate(habit_hit['_source'])
                  if utils.isRepeatingOnDay(cfg, start_date):
                      if start_time:
                          new_tz = ZoneInfo(cfg.startTime.timezone)
                          new_dt = datetime(start_date.year, start_date.month, start_date.day, cfg.startTime.hour, cfg.startTime.minute, tzinfo=new_tz)
                          start_datetime_obj = datetime.fromisoformat(f"{start_date.isoformat()}T{start_time}:00").replace(tzinfo=new_tz)
                          if new_dt == start_datetime_obj:
                              matches.append(habit_hit)
                              logger.info(f"Found a repeating event config that matches the title and time and repeats on the target date {start_date}")
                      else:
                          matches.append(habit_hit)
                          logger.info(f"Found a repeating event config that matches the title and repeats on the target date {start_date}")
              if len(matches) == 1:
                  if event_details.get("this_event_only", False):
                      logger.info(f"Deleting only this occurrence on {utils.pprint_date(start_date, start_time)} for recurring event '{matches[0]['_source']['title']}'")
                      new_exception_dates = cfg.exceptionDates or []
                      new_exception_dates.append(start_date)
                      update_expression = "SET exceptionDates = :ed"
                      expression_attribute_values = {":ed": serializer.serialize(utils._to_dynamodb_compatible(new_exception_dates))}
                      ddb_client.update_item(
                          TableName='Habits',
                          Key={'userId': {'S': cfg.userId}, 'id': {'S': cfg.id}},
                          UpdateExpression=update_expression,
                          ExpressionAttributeValues=expression_attribute_values
                      )
                      # opensearch_client.update(
                      #     index="habits",
                      #     id=matches[0]['_id'],
                      #     body={"doc": {"exceptionDates": [d.isoformat() for d in new_exception_dates]}},
                      #     refresh=True
                      # )
                      logger.info(f"Deleted only this occurrence on {utils.pprint_date(start_date, start_time)} for recurring event '{matches[0]['_source']['title']}'")
                      return {"result": f"Successfully deleted only the occurrence on {utils.pprint_date(start_date, start_time)} for recurring event '{matches[0]['_source']['title']}'."}
                  elif event_details.get("this_and_future_events", False):
                      logger.info(f"Deleting this and future occurrences from {utils.pprint_date(start_date, start_time)} for recurring event '{matches[0]['_source']['title']}'")
                      new_stop_date = start_date
                      update_expression = "SET stopDate = :sd"
                      expression_attribute_values = {":sd": serializer.serialize(utils._to_dynamodb_compatible(new_stop_date))}
                      ddb_client.update_item(
                          TableName='Habits',
                          Key={'userId': {'S': cfg.userId}, 'id': {'S': cfg.id}},
                          UpdateExpression=update_expression,
                          ExpressionAttributeValues=expression_attribute_values
                      )
                      # opensearch_client.update(
                      #     index="habits",
                      #     id=matches[0]['_id'],
                      #     body={"doc": {"stopDate": new_stop_date.isoformat()}},
                      #     refresh=True
                      # )
                      logger.info(f"Deleted this and future occurrences from {utils.pprint_date(start_date, start_time)} for recurring event '{matches[0]['_source']['title']}'")
                      return {"result": f"Successfully deleted this and future occurrences from {utils.pprint_date(start_date, start_time)} for recurring event '{matches[0]['_source']['title']}'."}
                  else:
                      return {"result": f"Do you want to delete only the occurrence on {utils.pprint_date(start_date, start_time)}? Or do you want to delete this event and all future occurrences?"}
              elif len(matches) > 1:
                  return {"result": f"Unable to delete because I found {len(matches)} recurring events with title '{event_title}' matching the provided start date and time."}
              else:
                  logger.info(f"No matching occurrences found on {utils.pprint_date(start_date, start_time)} for recurring event '{event_title}'. This is probably due to exception dates.")
          else:
              return {"result": f"Cannot delete event '{event_title}' without a start date and time because it is a recurring event. Please provide the start date and time to identify the specific occurrence to delete."}
      # if naive_start_datetime:
      #     filters.append({"term": {"startDate": start_datetime.isoformat()}})
      #     logger.info(f"Added startDate filter for search: {start_datetime.isoformat()}")
      if start_date and start_time:
          start_datetime = datetime.fromisoformat(f"{start_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
          filters.append({"term": {"startDate": start_datetime.isoformat()}})
          logger.info(f"Added startDate term filter for search: {start_datetime.isoformat()}")
      elif start_date:
          start_range, end_range = utils.get_utc_day_bounds(start_date, timezone)
          filters.append({"range": {"startDate": {"gte": start_range.isoformat(), "lte": end_range.isoformat()}}})
          logger.info(f"Added startDate range filter for search: gte {start_range.isoformat()} lte {end_range.isoformat()}")
      elif start_time:
          # search for today's date with the provided time
          today_date = datetime.now(tz).date()
          search_datetime = datetime.fromisoformat(f"{today_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
          filters.append({"term": {"startDate": search_datetime.isoformat()}})
          logger.info(f"Added startDate term filter for search: {search_datetime.isoformat()}")
      
      
      search_body["query"]["bool"]["filter"] = filters
      opensearch_response = opensearch_client.search(
          index="calendar-events",
          body=search_body
      )
      unfiltered_hits = opensearch_response['hits']['hits']
      logger.info(f"OpenSearch returned {len(unfiltered_hits)} hits for event delete search")
      hits = []
      for hit in unfiltered_hits:
          if hit['_score'] >= 1.0:  # filter out low relevance matches
              hits.append(hit)
          logger.info(f"score: {hit['_score']}, title: {hit['_source']['title']} startDate: {hit['_source']['startDate']}")
      total_found = len(hits)
              
      if total_found == 0:
          result_msg = f"No events found matching title '{event_title}'"
          if start_date:
              result_msg += f" and start date '{start_date}'"
          if start_time:
              result_msg += f" and start time '{start_time}'."
          logger.info(result_msg  )
          return {"result": result_msg}
      
      # handle ambiguity vs exact match
      target_doc = None
      if total_found == 1:
          # exact match
          target_doc = hits[0]
          logger.info(f"Single matching event found for deletion: {target_doc}")
      elif start_date and start_time:
          # filter by start date if provided
          search_dt = datetime.fromisoformat(f"{start_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
          for hit in hits:
              if hit['_source']['startDate'] == search_dt.isoformat():
                  target_doc = hit
                  logger.info(f"Matching event found for deletion with start date: {target_doc}")
                  break
          if not target_doc:
              return {"result": f"found multiple events with title '{event_title}' but none match the provided start date {search_dt.isoformat()}."}
      elif start_date:
          options = [f"on {hit['_source']['startDate']}" for hit in hits]
          return {"result": f"found {total_found} matches for '{event_title}' on date '{start_date}': {', '.join(options)}. Please provide the start time as well to identify the specific event to delete."}
      elif start_time:
          today_date = datetime.now(tz).date()
          search_dt = datetime.fromisoformat(f"{today_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
          for hit in hits:
              if hit['_source']['startDate'] == search_dt.isoformat():
                  target_doc = hit
                  logger.info(f"Matching event found for deletion with start datetime: {target_doc}")
                  break
          if not target_doc:
              return {"result": f"found multiple events with title '{event_title}' but none match the provided start time {start_time} on today's date."}
      else:
          options = [f"on {hit['_source']['startDate']}" for hit in hits]
          return {"result": f"Found {total_found} matches for '{event_title}': {', '.join(options)}. Which one should I delete?"}
      
      if target_doc:
          os_id = target_doc['_id']
          eventId = target_doc['_source']['eventId']
          habitId = target_doc['_source'].get('habitId', None)
          if habitId:
              if event_details.get("this_event_only", False):
                  #opensearch_client.delete(index="calendar-events", id=os_id)
                  ddb_client.delete_item(
                      TableName='Events',
                      Key={'userId': {'S': user_id}, 'id': {'S': eventId}}
                  )
                  return {"result": f"Successfully deleted only the occurrence on {target_doc['_source']['startDate']} for recurring event '{event_title}'."}
              elif event_details.get("this_and_future_events", False):
                  new_stop_date = datetime.fromisoformat(target_doc['_source']['startDate']).date()
                  # update the habit to set stopDate in DynamoDB and OpenSearch
                  update_expression = "SET stopDate = :sd"
                  expression_attribute_values = {":sd": serializer.serialize(utils._to_dynamodb_compatible(new_stop_date))}
                  ddb_client.update_item(
                      TableName='Habits',
                      Key={'userId': {'S': user_id}, 'id': {'S': habitId}},
                      UpdateExpression=update_expression,
                      ExpressionAttributeValues=expression_attribute_values
                  )
                  # opensearch_client.update(
                  #     index="habits",
                  #     id=habitId,
                  #     body={"doc": {"stopDate": new_stop_date.isoformat()}},
                  #     refresh=True
                  # )
                  # delete the event occurrence
                  # opensearch_client.delete(index="calendar-events", id=os_id)
                  ddb_client.delete_item(
                      TableName='Events',
                      Key={'userId': {'S': user_id}, 'id': {'S': eventId}}
                  )
                  return {"result": f"Successfully deleted this and future occurrences from {target_doc['_source']['startDate']} for recurring event '{event_title}'."}
              else:
                  return {"result": f"Do you want to delete only the occurrence on {target_doc['_source']['startDate']}? Or do you want to delete this event and all future occurrences?"}
          # opensearch_client.delete(index="calendar-events", id=os_id)
          ddb_client.delete_item(
              TableName='Events',
              Key={'userId': {'S': user_id}, 'id': {'S': eventId}}
          )
          return {"result": f"Successfully deleted the event '{event_title}'."}
      else:
          return {"result": "No matching event found to delete."}
  except Exception as e:
      logger.error(f"Error during event deletion: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that delete request."}