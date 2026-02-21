import logging
import json
from datetime import datetime, date, timedelta, time
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
import uuid
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repeating_event_config_model import HabitIndexModel, RepeatingEventConfigModel
import utils

# Configure logging
logger = logging.getLogger(__name__)
serializer = TypeSerializer()
deserializer = TypeDeserializer()

def update_event(ddb_client, bedrock_client, opensearch_client, user_id, content, timezone):
  try:
    tz = ZoneInfo(timezone)
    logger.info(f"Processing update_event with content: {content}")
    event_details = json.loads(content)
    logger.info(f"Parsed event details for update: {event_details}")
    to_update_fields = {k: v for k, v in event_details.items() if k not in ["current_title", "current_start_date", "current_start_time", "this_event_only", "this_and_future_events"] and v is not None}
    event_title = event_details.get("current_title")
    
    start_date = date.fromisoformat(event_details.get("current_start_date", None)) if event_details.get("current_start_date", None) else None
    start_time = event_details.get("current_start_time", None)
    
    new_start_date = date.fromisoformat(to_update_fields.get('new_start_date', None)) if to_update_fields.get('new_start_date', None) else None
    new_start_time = to_update_fields.get('new_start_time', None)   
    
    # logger.info(f"The current start_datetime is: {start_datetime}")
    # logger.info(f"The new_start_datetime to update to is: {new_start_datetime}")
    
    # return {"result": "The update_event tool is under development and not yet implemented."}
    logger.info(f"Searching for event to update: title='{event_title}', start_date='{start_date}', start_time='{start_time}'")

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
    logger.info(f"OpenSearch habits search response: {opensearch_habits_response}")
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
            
            # If we have exactly one match, proceed to update
            if len(matches) == 1:
                # get the habit data from DynamoDB
                habitId = matches[0]['_source']['habitId']
                ddb_habit_item = ddb_client.get_item(
                    TableName='Habits',
                    Key={'userId': {'S': cfg.userId}, 'id': {'S': cfg.id}}
                )
                if not ddb_habit_item.get('Item'):
                    return {"result": f"Could not find the recurring event config in the database for title '{event_title}'."}
                habit_item = {k: deserializer.deserialize(v) for k, v in ddb_habit_item['Item'].items()}
                cfg = RepeatingEventConfigModel.model_validate(habit_item)
                logger.info(f"Fetched recurring event config from DynamoDB: {habit_item}")
                start_datetime = datetime.combine(start_date, time(cfg.startTime.hour, cfg.startTime.minute)).replace(tzinfo=ZoneInfo(cfg.startTime.timezone))
                end_datetime = start_datetime + timedelta(minutes=cfg.length)
                try:
                    allDay_value = utils.get_new_all_day(cfg.allDay, to_update_fields)
                except Exception as e:
                    logger.error(f"Error determining allDay value for update: {e}", exc_info=True)
                    return {"result": f"Error {e}"}
                new_start_datetime = utils.get_new_start_datetime(start_datetime, new_start_date, new_start_time)
                new_end_datetime = utils.get_new_end_datetime(
                        cfg.length,
                        start_datetime,
                        end_datetime,
                        new_start_date,
                        new_start_time,
                        new_end_date = to_update_fields.get("new_end_date", None),
                        new_end_time_str= to_update_fields.get("new_end_time", None),
                        new_length_minutes= to_update_fields.get("new_length_minutes", None)
                )
                if new_end_datetime is None:
                    return {"result": "Unable to determine new end datetime for the updated event occurrence."}
                
                if event_details.get("this_event_only", False):
                    logger.info(f"Updating only this occurrence on {start_datetime} for recurring event '{matches[0]['_source']['title']}'")
                    new_exception_dates = cfg.exceptionDates or []
                    new_exception_dates.append(start_datetime.date())
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
                    
                    logger.info(f"Added {start_datetime} to the repeating event config's exception dates")
                    new_event = {
                        "id": str(uuid.uuid4()),
                        "userId": cfg.userId,
                        "done": to_update_fields.get("done", False),
                        "description": to_update_fields.get("new_title", cfg.name),
                        "habitId": cfg.id,
                        "allDay": allDay_value,
                        "type": to_update_fields.get("type", cfg.eventType),
                        "fixed": to_update_fields.get("fixed", cfg.fixed),
                        "priority": to_update_fields.get("priority", cfg.priority),
                        "content": to_update_fields.get("content", cfg.content),
                        "startDate": new_start_datetime.isoformat(),
                        "endDate": new_end_datetime.isoformat(),
                        "notifications": to_update_fields.get("notifications", cfg.notifications) 
                    }
                    # save to DynamoDB
                    ddb_event_item= {k: serializer.serialize(v) for k, v in new_event.items()}
                    ddb_client.put_item(TableName='Events', Item=ddb_event_item)
                    logger.info(f"Updated single event occurrence in DynamoDB: {new_event}")   
                    return {
                        "result": f"Successfully updated only the occurrence on {start_datetime.strftime('%m/%d/%Y %I:%M %p')} for recurring event '{matches[0]['_source']['title']}'.",
                        "new_event": new_event,
                        "new_exception_dates": new_exception_dates
                    }
                elif event_details.get("this_and_future_events", False):
                    logger.info(f"Updating this and future occurrences from {start_datetime} for recurring event '{matches[0]['_source']['title']}'")
                    
                    # stop the current repeating event config
                    new_stop_date = start_datetime.date()
                    cfg.stopDate = new_stop_date
                    update_expression = "SET stopDate = :sd"
                    expression_attribute_values = {":sd": serializer.serialize(utils._to_dynamodb_compatible(new_stop_date))}
                    ddb_client.update_item(
                        TableName='Habits',
                        Key={'userId': {'S': cfg.userId}, 'id': {'S': cfg.id}},
                        UpdateExpression=update_expression,
                        ExpressionAttributeValues=expression_attribute_values
                    )
                    
                    # used for unit test
                    updated_repeat_config = {k: serializer.serialize(utils._to_dynamodb_compatible(v))
                                              for k, v in cfg.model_dump().items()}
                    updated_repeat_config['type'] = updated_repeat_config.pop('eventType')

                    
                    # opensearch_client.update(
                    #     index="habits",
                    #     id=matches[0]['_id'],
                    #     body={"doc": {"stopDate": new_stop_date.isoformat()}},
                    #     refresh=True
                    # )
                    logger.info(f"Set the stop date of the current repeating event config to {new_stop_date}")
                    new_repeat_config = {
                        "id": str(uuid.uuid4()),
                        "userId": cfg.userId,
                        "name": to_update_fields.get("new_title", cfg.name),
                        "content": to_update_fields.get("content", cfg.content),
                        "creationDate": new_start_datetime.date().strftime('%Y-%m-%d'),
                        "type": to_update_fields.get("type", cfg.eventType),
                        "priority": to_update_fields.get("priority", cfg.priority),
                        "fixed": to_update_fields.get("fixed", cfg.fixed),
                        "stopDate": None,
                        "frequency": to_update_fields.get("frequency", cfg.frequency),
                        "notifications": to_update_fields.get("notifications", cfg.notifications),
                        "days": to_update_fields.get("days", cfg.days),
                        "allDay": allDay_value,
                        "exceptionDates": [],
                        "prevVersionHabitId": cfg.id,
                        "startTime": {
                          "hour": new_start_datetime.hour,
                          "minute": new_start_datetime.minute,
                          "timezone": timezone
                        },
                        "length": to_update_fields.get("new_length_minutes", cfg.length),
                    }
                    ddb_habit_item= {k: serializer.serialize(v) for k, v in new_repeat_config.items()}
                    ddb_client.put_item(TableName='Habits', Item=ddb_habit_item)
                    logger.info(f"Created new repeating event config in DynamoDB: {new_repeat_config}")
                    
                    
                    logger.info(f"Updated this and future occurrences from {start_datetime} for recurring event '{matches[0]['_source']['title']}'")
                    return {"result": f"Successfully updated this and future occurrences from {start_datetime.strftime('%m/%d/%Y %I:%M %p')} for recurring event '{matches[0]['_source']['title']}'.",
                            "new_repeat_config": new_repeat_config,
                            "updated_repeat_config": updated_repeat_config
                            }
                else:
                    return {"result": f"Do you want to update only the occurrence on {start_datetime.strftime('%m/%d/%Y %I:%M %p')}? Or do you want to update this event and all future occurrences?"}
            elif len(matches) > 1:
                if start_time:
                    return {"result": f"Unable to update because I found {len(matches)} recurring events with title '{event_title}' matching the provided start date and time."}
                else:
                    return {"result": f"Unable to update because I found {len(matches)} recurring events with title '{event_title}' matching the provided start date. Please provide the start time as well to identify the specific occurrence."}
            else:
                logger.info(f"No matching occurrences found on {utils.pprint_date(start_date, start_time)} for recurring event '{event_title}'. This is probably due to exception dates.")
        else:
            return {"result": f"Cannot update event '{event_title}' without a start date and time because it is a recurring event. Please provide the start date and time to identify the specific occurrence to update."}
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
    logger.info(f"OpenSearch returned {len(unfiltered_hits)} hits for event update search")
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
        logger.info(f"Single matching event found for update: {target_doc}")
    elif start_date and start_time:
        # filter by start date if provided
        search_dt = datetime.fromisoformat(f"{start_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
        for hit in hits:
            if hit['_source']['startDate'] == search_dt.isoformat():
                target_doc = hit
                logger.info(f"Matching event found for update with start datetime: {target_doc}")
                break
        if not target_doc:
            return {"result": f"found multiple events with title '{event_title}' but none match the provided start date and time {search_dt.isoformat()}."}
    elif start_date:
        options = [f"on {hit['_source']['startDate']}" for hit in hits]
        return {"result": f"found {total_found} matches for '{event_title}' on date '{start_date}': {', '.join(options)}. Please provide the start time as well to identify the specific event to update."}
    elif start_time:
        # search for today's date with the provided time
        today_date = datetime.now(tz).date()
        search_dt = datetime.fromisoformat(f"{today_date.isoformat()}T{start_time}:00").replace(tzinfo=tz)
        for hit in hits:
            if hit['_source']['startDate'] == search_dt.isoformat():
                target_doc = hit
                logger.info(f"Matching event found for update with start datetime: {target_doc}")
                break
        if not target_doc:
            return {"result": f"found multiple events with title '{event_title}' but none match the provided start time {start_time} on today's date."}
    else:
        options = [f"on {hit['_source']['startDate']}" for hit in hits]
        return {
            "result": f"Found {total_found} matches for '{event_title}': {', '.join(options)}. Which one should I update?"
        }
    
    # Found the saved event to update
    if target_doc:
        os_id = target_doc['_id']
        eventId = target_doc['_source']['eventId']
        habitId = target_doc['_source'].get('habitId', None)
        
        # get the event from DynamoDB
        ddb_event_item = ddb_client.get_item(
            TableName='Events',
            Key={'userId': {'S': user_id}, 'id': {'S': eventId}}
        )
        if not ddb_event_item.get('Item'):
            return {"result": f"Could not find the event in the database for title '{event_title}'."}
        logger.info(f"Fetched event item from DynamoDB for update: {ddb_event_item}")
        event_item = {k: deserializer.deserialize(v) for k, v in ddb_event_item['Item'].items()}
        
        # calculate the new start and end datetimes based on the provided update fields and current datetimes (and the allDay value)
        current_start_datetime = datetime.fromisoformat(event_item['startDate']).replace(tzinfo=tz)
        current_end_datetime = datetime.fromisoformat(event_item['endDate']).replace(tzinfo=tz)
        current_length = int((current_end_datetime - current_start_datetime).total_seconds() / 60)
        try:
            allDay_value = utils.get_new_all_day(event_item.get("allDay", False), to_update_fields)
        except Exception as e:
            logger.error(f"Error determining allDay value for update: {e}", exc_info=True)
            return {"result": f"Error {e}"}
        new_start_datetime = utils.get_new_start_datetime(current_start_datetime, new_start_date, new_start_time)
        new_end_datetime = utils.get_new_end_datetime(
                current_length,
                current_start_datetime,
                current_end_datetime,
                new_start_date,
                new_start_time,
                new_end_date = to_update_fields.get("new_end_date", None),
                new_end_time_str= to_update_fields.get("new_end_time", None),
                new_length_minutes= to_update_fields.get("new_length_minutes", None)
        )
        if new_end_datetime is None:
            return {"result": "Unable to determine new end datetime for the updated event occurrence."}
        
        if habitId:
            if event_details.get("this_event_only", False):
                updated_fields = {
                        "done": to_update_fields.get("done", event_item.get("done", False)),
                        "description": to_update_fields.get("new_title", event_item["description"]),
                        "allDay": allDay_value,
                        "type": to_update_fields.get("type", event_item.get("type", "personal")),
                        "fixed": to_update_fields.get("fixed", event_item.get("fixed", False)),
                        "priority": to_update_fields.get("priority", event_item.get("priority", None)),
                        "content": to_update_fields.get("content", event_item.get("content", None)),
                        "startDate": new_start_datetime.isoformat(),
                        "endDate": new_end_datetime.isoformat(),
                        "notifications": to_update_fields.get("notifications", event_item.get("notifications", []))
                }
                updated_event = {**event_item, **updated_fields}
                # save to DynamoDB
                ddb_event_item= {k: serializer.serialize(v) for k, v in updated_event.items()}
                ddb_client.put_item(TableName='Events', Item=ddb_event_item)
                logger.info(f"Updated single event occurrence in DynamoDB: {updated_event}")
                return {"result": f"Successfully updated only the occurrence on {target_doc['_source']['startDate']} for recurring event '{event_title}'.",
                        "updated_event": updated_event}
            elif event_details.get("this_and_future_events", False):
                # get the repeat config data from DynamoDB
                ddb_config_item = ddb_client.get_item(
                    TableName='Habits',
                    Key={'userId': {'S': user_id}, 'id': {'S': habitId}}
                )
                if not ddb_config_item.get('Item'):
                    return {"result": f"Could not find the recurring event config in the database for title '{event_title}'."}
                
                # Update the current repeat config to set stopDate
                config_item = {k: deserializer.deserialize(v) for k, v in ddb_config_item['Item'].items()}
                logger.info(f"Fetched recurring event config from DynamoDB: {config_item}")
                cfg = RepeatingEventConfigModel.model_validate(config_item)
                new_stop_date = current_start_datetime.date()
                cfg.stopDate = new_stop_date
                
                # used for unit test
                updated_repeat_config = {k: serializer.serialize(utils._to_dynamodb_compatible(v))
                                            for k, v in cfg.model_dump().items()
                                        }
                updated_repeat_config['type'] = updated_repeat_config.pop('eventType')
                
                # update the current config to set stopDate in DynamoDB (and OpenSearch)
                update_expression = "SET stopDate = :sd"
                expression_attribute_values = {":sd": serializer.serialize(utils._to_dynamodb_compatible(new_stop_date))}
                ddb_client.update_item(
                    TableName='Habits',
                    Key={'userId': {'S': user_id}, 'id': {'S': cfg.id}},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values
                )

                # create the new repeat config
                new_repeat_config = {
                        "id": str(uuid.uuid4()),
                        "userId": cfg.userId,
                        "name": to_update_fields.get("new_title", cfg.name),
                        "content": to_update_fields.get("content", cfg.content),
                        "creationDate": new_start_datetime.strftime('%Y-%m-%d'),
                        "type": to_update_fields.get("type", cfg.eventType),
                        "priority": to_update_fields.get("priority", cfg.priority),
                        "fixed": to_update_fields.get("fixed", cfg.fixed),
                        "stopDate": None,
                        "frequency": to_update_fields.get("frequency", cfg.frequency),
                        "notifications": to_update_fields.get("notifications", cfg.notifications),
                        "days": to_update_fields.get("days", cfg.days),
                        "allDay": allDay_value,
                        "exceptionDates": cfg.exceptionDates or [],
                        "prevVersionHabitId": cfg.id,
                        "startTime": {
                          "hour": new_start_datetime.hour,
                          "minute": new_start_datetime.minute,
                          "timezone": timezone
                        },
                        "length": to_update_fields.get("new_length_minutes", cfg.length),
                }
                # save new repeat config to DynamoDB
                new_ddb_config_item= {k: serializer.serialize(v) for k, v in new_repeat_config.items()}
                ddb_client.put_item(TableName='Habits', Item=new_ddb_config_item)
                logger.info(f"Created new repeating event config in DynamoDB: {new_repeat_config}")
                
                # Now update the event occurrence
                updated_fields = {
                        "done": to_update_fields.get("done", event_item.get("done", False)),
                        "description": to_update_fields.get("new_title", event_item["description"]),
                        "allDay": allDay_value,
                        "type": to_update_fields.get("type", event_item.get("type", "personal")),
                        "fixed": to_update_fields.get("fixed", event_item.get("fixed", False)),
                        "priority": to_update_fields.get("priority", event_item.get("priority", None)),
                        "content": to_update_fields.get("content", event_item.get("content", None)),
                        "startDate": new_start_datetime.isoformat(),
                        "endDate": new_end_datetime.isoformat(),
                        "notifications": to_update_fields.get("notifications", event_item.get("notifications", []))
                }
                updated_event = {**event_item, **updated_fields}
                # save to DynamoDB
                ddb_event_item= {k: serializer.serialize(v) for k, v in updated_event.items()}
                ddb_client.put_item(TableName='Events', Item=ddb_event_item)
                logger.info(f"Updated single event occurrence in DynamoDB: {updated_event}")
                
                return {"result": f"Successfully updated this and future occurrences from {target_doc['_source']['startDate']} for recurring event '{event_title}'." ,
                        "updated_repeat_config": updated_repeat_config,
                        "new_repeat_config": new_repeat_config,
                        "updated_event": updated_event
                        }
            else:
                return {"result": f"Do you want to update only the occurrence on {target_doc['_source']['startDate']}? Or do you want to update this event and all future occurrences?"}
        else:
            updated_fields = {
                    "done": to_update_fields.get("done", event_item.get("done", False)),
                    "description": to_update_fields.get("new_title", event_item["description"]),
                    "allDay": allDay_value,
                    "type": to_update_fields.get("type", event_item.get("type", "personal")),
                    "fixed": to_update_fields.get("fixed", event_item.get("fixed", False)),
                    "priority": to_update_fields.get("priority", event_item.get("priority", None)),
                    "content": to_update_fields.get("content", event_item.get("content", None)),
                    "startDate": new_start_datetime.isoformat(),
                    "endDate": new_end_datetime.isoformat(),
                    "notifications": to_update_fields.get("notifications", event_item.get("notifications", []))
            }
            updated_event = {**event_item, **updated_fields}
            # save to DynamoDB
            ddb_event_item= {k: serializer.serialize(v) for k, v in updated_event.items()}
            ddb_client.put_item(TableName='Events', Item=ddb_event_item)
            logger.info(f"Updated nonrepeating event in DynamoDB: {updated_event}")  
        
        return {"result": f"Successfully updated the event '{event_title}'.",
                "updated_event": updated_event}
    else:
        return {"result": "No matching event found to update."}
  except Exception as e:
      logger.error(f"Error during event update: {e}", exc_info=True)
      return {"result": "Sorry, I couldn't process that update request."}