import logging
import json
from datetime import datetime, date, timedelta, time
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



def open_event(ddb_client, bedrock_client, opensearch_client, user_id, content, timezone):
  try:
    tz = ZoneInfo(timezone)
    logger.info(f"Processing open_event with content: {content}")
    event_details = json.loads(content)
    logger.info(f"Parsed event details for open_event: {event_details}")
    event_title = event_details.get("current_title")
    
    start_date = date.fromisoformat(event_details.get("current_start_date", None)) if event_details.get("current_start_date", None) else None
    start_time = event_details.get("current_start_time", None)
    
    # logger.info(f"The current start_datetime is: {start_datetime}")
    # logger.info(f"The new_start_datetime to open to is: {new_start_datetime}")
    
    # return {"result": "The open_event tool is under development and not yet implemented."}
    logger.info(f"Searching for event to open: title='{event_title}', start_date='{start_date}', start_time='{start_time}'")

    # Vectorize and Hybrid Search to find candidate events
    embed_response = bedrock_client.invoke_model(
        body=json.dumps({"inputText": event_title}),
        modelId="amazon.titan-embed-text-v1"
    )
    query_vector = json.loads(embed_response['body'].read())['embedding']
    logger.info(f"Generated embedding for event title: {event_title}")
    filters = [{"term": {"userId": user_id}}]
        
    # Search OpenSearch habits index for matching title 
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
    matching_habit_names_found = opensearch_habits_response['hits']['total']['value']
    logger.info(f"Found {matching_habit_names_found} matching habits: ")
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
            # Find the habit configs that repeat on the target date and time
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
            
            # If we have exactly one match, proceed to open
            if len(matches) == 1:
                # get the habit data from DynamoDB
                habitId = matches[0]['_source']['habitId']
                ddb_habit_item = ddb_client.get_item(
                    TableName='Habits',
                    Key={'userId': {'S': cfg.userId}, 'id': {'S': habitId}}
                )
                if not ddb_habit_item.get('Item'):
                    return {"result": f"Could not find the recurring event config in the database for title '{event_title}'."}
                habit_item = {k: deserializer.deserialize(v) for k, v in ddb_habit_item['Item'].items()}
                cfg = RepeatingEventConfigModel.model_validate(habit_item)
                logger.info(f"Fetched recurring event config from DynamoDB: {habit_item}")
                start_datetime = datetime.combine(start_date, time(cfg.startTime.hour, cfg.startTime.minute)).replace(tzinfo=ZoneInfo(cfg.startTime.timezone))
                end_datetime = start_datetime + timedelta(minutes=cfg.length)
                return {
                        "result": f"Found the matching event. I'm including the details in the response so the client can open the event occurrence on {start_datetime.isoformat()} for recurring event '{event_title}'.",
                        "event_details": {
                            "name": cfg.name,
                            "habitId": cfg.id,
                            "startDate": start_datetime.isoformat(),
                            "endDate": end_datetime.isoformat(),
                            "allDay": cfg.allDay
                        },
                        "tool_name": "open_event"
                    }
                
            elif len(matches) > 1:
                if start_time:
                    return {"result": f"Unable to open because I found {len(matches)} recurring events with title '{event_title}' matching the provided start date and time."}
                else:
                    return {"result": f"Unable to open because I found {len(matches)} recurring events with title '{event_title}' matching the provided start date. Please provide the start time as well to identify the specific occurrence."}
            else:
                logger.info(f"No matching occurrences found on {utils.pprint_date(start_date, start_time)} for recurring event '{event_title}'. This is probably due to exception dates.")
        else:
            return {"result": f"Cannot open event '{event_title}' without a start date and time because it is a recurring event. Please provide the start date and time to identify the specific occurrence to open."}
    else:
        logger.info("No matching habits that will autogenerate the event found on the specified date is found. Checking saved events now.")
    
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
    logger.info(f"OpenSearch returned {len(unfiltered_hits)} hits for event open search")
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
        logger.info(f"Single matching event found for open: {target_doc}")
    elif start_date and start_time:
        # filter by start date if provided
        search_dt = datetime.fromisoformat(f"{start_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
        for hit in hits:
            if hit['_source']['startDate'] == search_dt.isoformat():
                target_doc = hit
                logger.info(f"Matching event found for open with start datetime: {target_doc}")
                break
        if not target_doc:
            return {"result": f"found multiple events with title '{event_title}' but none match the provided start date and time {search_dt.isoformat()}."}
    elif start_date:
        #TODO: handle the case that only one event matches. Also, handle the case that the current allDay flag is true.
        options = [f"on {hit['_source']['startDate']}" for hit in hits]
        return {"result": f"found {total_found} matches for '{event_title}' on date '{start_date}': {', '.join(options)}. Please provide the start time as well to identify the specific event to open."}
    elif start_time:
        # search for today's date with the provided time
        today_date = datetime.now(tz).date()
        search_dt = datetime.fromisoformat(f"{today_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
        for hit in hits:
            if hit['_source']['startDate'] == search_dt.isoformat():
                target_doc = hit
                logger.info(f"Matching event found for open with start datetime: {target_doc}")
                break
        if not target_doc:
            return {"result": f"found multiple events with title '{event_title}' but none match the provided start time {start_time} on today's date."}
    else:
        options = [f"on {hit['_source']['startDate']}" for hit in hits]
        return {
            "result": f"Found {total_found} matches for '{event_title}': {', '.join(options)}. Which one should I open?"
        }
    
    # Found the saved event to open
    if target_doc:
        os_id = target_doc['_id']
        target_event = EventIndexModel.model_validate(target_doc['_source'])
        eventId = target_event.id
        habitId = target_doc['_source'].get('habitId', None)
        
        return {"result": f"Found the matching event to open. I'm including the eventId in the response so the client can open this event occurrence.",
                "event_details": {
                    "eventId": eventId,
                },
                "tool_name": "open_event"
            }
    else:
        return {"result": "No matching event found to open."}
  except Exception as e:
      logger.error(f"Error during event open: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that open request."}