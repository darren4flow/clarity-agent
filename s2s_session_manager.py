import asyncio
import json
import warnings
import uuid
import logging
from s2s_events import S2sEvent
import time
from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from aws_sdk_bedrock_runtime.config import Config
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
import boto3
from boto3.dynamodb.types import TypeSerializer
from datetime import datetime
from zoneinfo import ZoneInfo
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from repeating_event_config_model import RepeatingEventConfig
import utils

# Suppress warnings
warnings.filterwarnings("ignore")

# Configure logging
logger = logging.getLogger(__name__)

ddb_client = boto3.client('dynamodb', region_name='us-east-1')
serializer = TypeSerializer()
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')

# Initialize OpenSearch client
os_host = "search-clarity-domain-act5b626lr54k4h722hub6uxhe.us-east-1.es.amazonaws.com"
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, 'us-east-1', 'es', session_token=credentials.token)
opensearch_client = OpenSearch(
    hosts = [{'host': os_host, 'port': 443}],
    http_auth = awsauth,
    use_ssl = True,
    verify_certs = True,
    connection_class = RequestsHttpConnection
)


class S2sSessionManager:
    """Manages bidirectional streaming with AWS Bedrock using asyncio"""
    
    def __init__(self, region, model_id, user_id, timezone):
        """Initialize the stream manager."""
        self.model_id = model_id
        self.region = region
        self.user_id = user_id
        self.timezone = timezone
        
        # Audio and output queues with size limits to prevent memory issues
        self.audio_input_queue = asyncio.Queue(maxsize=100)  # Limit to 100 audio chunks (~2-3 seconds of audio)
        self.output_queue = asyncio.Queue(maxsize=200)  # Larger output queue for responses
        
        self.response_task = None
        self.stream = None
        self.is_active = False
        self.bedrock_client = None
        
        # Session information
        self.prompt_name = None  # Will be set from frontend
        self.content_name = None  # Will be set from frontend
        self.audio_content_name = None  # Will be set from frontend
        self.toolUseContent = ""
        self.toolUseId = ""
        self.toolName = ""
        
        # Track active tool processing tasks
        self.tool_processing_tasks = set()

    def _initialize_client(self):
        """
        Initialize the Bedrock client using EnvironmentCredentialsResolver.
        
        Credentials are managed by server.py which either:
        - Uses existing environment variables (local mode)
        - Fetches and refreshes credentials from IMDS (EC2 mode)
        """
        logger.info("Initializing Bedrock client with EnvironmentCredentialsResolver")
        
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.bedrock_client = BedrockRuntimeClient(config=config)
        logger.info("Bedrock client initialized successfully")

    def reset_session_state(self):
        """Reset session state for a new session."""
        # Cancel any ongoing tool processing tasks
        for task in list(self.tool_processing_tasks):
            if not task.done():
                task.cancel()
        self.tool_processing_tasks.clear()
        
        # Clear queues
        while not self.audio_input_queue.empty():
            try:
                self.audio_input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Reset tool use state
        self.toolUseContent = ""
        self.toolUseId = ""
        self.toolName = ""
        
        # Reset session information
        self.prompt_name = None
        self.content_name = None
        self.audio_content_name = None

    async def initialize_stream(self):
        """Initialize the bidirectional stream with Bedrock."""
        try:
            if not self.bedrock_client:
                self._initialize_client()
        except Exception:
            self.is_active = False
            logger.error("Failed to initialize Bedrock client")
            raise

        try:
            # Initialize the stream
            self.stream = await self.bedrock_client.invoke_model_with_bidirectional_stream(
                InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
            )
            self.is_active = True
            
            # Start listening for responses
            self.response_task = asyncio.create_task(self._process_responses())

            # Start processing audio input
            asyncio.create_task(self._process_audio_input())
            
            # Wait a bit to ensure everything is set up
            await asyncio.sleep(0.1)
            
            logger.info("Stream initialized successfully")
            return self
        except Exception:
            self.is_active = False
            logger.error("Failed to initialize stream.")
            raise
    
    async def send_raw_event(self, event_data):
        """Send a raw event to the Bedrock stream."""
        try:
            if not self.stream or not self.is_active:
                logger.warning("Stream not initialized or closed")
                return
            
            event_json = json.dumps(event_data)
            #if "audioInput" not in event_data["event"]:
            #    print(event_json)
            event = InvokeModelWithBidirectionalStreamInputChunk(
                value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
            )
            await self.stream.input_stream.send(event)

            # Close session
            if "sessionEnd" in event_data["event"]:
                await self.close()
            
        except Exception:
            logger.error("Error sending event to Bedrock")
            # Don't close the stream on send errors, let Bedrock handle it
            # The response processing loop will detect if the stream is broken
    
    async def _process_audio_input(self):
        """Process audio input from the queue and send to Bedrock."""
        while self.is_active:
            try:
                # Get audio data from the queue
                data = await self.audio_input_queue.get()
                
                # Extract data from the queue item
                prompt_name = data.get('prompt_name')
                content_name = data.get('content_name')
                audio_bytes = data.get('audio_bytes')
                
                if not audio_bytes or not prompt_name or not content_name:
                    logger.warning("Missing required audio data properties")
                    continue

                # Create the audio input event
                audio_event = S2sEvent.audio_input(prompt_name, content_name, audio_bytes.decode('utf-8') if isinstance(audio_bytes, bytes) else audio_bytes)
                
                # Send the event
                await self.send_raw_event(audio_event)
                
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Error processing audio.")
    
    def add_audio_chunk(self, prompt_name, content_name, audio_data):
        """Add an audio chunk to the queue."""
        # The audio_data is already a base64 string from the frontend
        try:
            self.audio_input_queue.put_nowait({
                'prompt_name': prompt_name,
                'content_name': content_name,
                'audio_bytes': audio_data
            })
        except asyncio.QueueFull:
            # Queue is full - drop this chunk to prevent backpressure
            # This is acceptable for real-time audio streaming
            logger.warning("Audio input queue full, dropping audio chunk to prevent backpressure")
            pass
    
    async def _process_responses(self):
        """Process incoming responses from Bedrock."""
        while self.is_active:
            try:            
                output = await self.stream.await_output()
                result = await output[1].receive()
                
                if result.value and result.value.bytes_:
                    response_data = result.value.bytes_.decode('utf-8')
                    logger.debug(f"Received event: {response_data}")
                    
                    json_data = json.loads(response_data)
                    json_data["timestamp"] = int(time.time() * 1000)  # Milliseconds since epoch
                    
                    event_name = None
                    if 'event' in json_data:
                        event_name = list(json_data["event"].keys())[0]
                        
                        # Log contentEnd events for debugging
                        if event_name == "contentEnd":
                            content_end_data = json_data["event"]["contentEnd"]
                            logger.debug(f"Received contentEnd: type={content_end_data.get('type')}, stopReason={content_end_data.get('stopReason')}, role={content_end_data.get('role', 'N/A')}")
                        
                        # Handle tool use detection
                        if event_name == 'toolUse':
                            self.toolUseContent = json_data['event']['toolUse']
                            self.toolName = json_data['event']['toolUse']['toolName']
                            self.toolUseId = json_data['event']['toolUse']['toolUseId']
                            logger.info(f"Tool use detected: {self.toolName}, ID: {self.toolUseId}")
                        # Process tool use when content ends
                        elif event_name == 'contentEnd' and json_data['event'][event_name].get('type') == 'TOOL':
                            prompt_name = json_data['event']['contentEnd'].get("promptName")
                            logger.debug("Starting tool processing in background")
                            # Process tool in background task to avoid blocking
                            task = asyncio.create_task(
                                self._handle_tool_processing(prompt_name, self.toolName, self.toolUseContent, self.toolUseId)
                            )
                            self.tool_processing_tasks.add(task)
                            task.add_done_callback(self.tool_processing_tasks.discard)
                    
                    # Put the response in the output queue for forwarding to the frontend
                    try:
                        # Use put_nowait to avoid blocking, but handle queue full gracefully
                        self.output_queue.put_nowait(json_data)
                    except asyncio.QueueFull:
                        # Queue is full - log warning but don't break the stream
                        # This can happen during high-throughput audio responses
                        logger.warning("Output queue full, dropping response to prevent backpressure")
                        # Continue processing instead of breaking the stream


            except json.JSONDecodeError as ex:
                logger.error(f"JSON decode error in _process_responses: {ex}")
                await self.output_queue.put({"raw_data": response_data})
                # Don't break on JSON errors, continue processing
                continue
            except StopAsyncIteration:
                # Stream has ended normally
                logger.info("Bedrock stream has ended (StopAsyncIteration)")
                break
            except Exception as e:
                # Handle ValidationException and other errors
                error_str = str(e)
                if "ValidationException" in error_str:
                    logger.error(f"Bedrock validation error: {error_str}")
                    # Send error to client but don't break the stream
                    await self.output_queue.put({
                        "event": {"error": {"message": f"Validation error: {error_str}"}}
                    })
                    continue
                else:
                    logger.error(f"Error receiving response from Bedrock: {e}", exc_info=True)
                    # Only break on serious errors
                    break

        logger.info("Bedrock response processing loop ended, closing stream")
        self.is_active = False
        await self.close()

    async def _handle_tool_processing(self, prompt_name, tool_name, tool_use_content, tool_use_id):
        """Handle tool processing in background without blocking event processing"""
        try:
            logger.info(f"[Tool Processing] Starting: {tool_name} with ID: {tool_use_id}")
            toolResult = await self.processToolUse(tool_name, tool_use_content)
            logger.info(f"[Tool Processing] Completed: {tool_name}")
                
            # Send tool start event
            toolContent = str(uuid.uuid4())
            tool_start_event = S2sEvent.content_start_tool(prompt_name, toolContent, tool_use_id)
            await self.send_raw_event(tool_start_event)
            
            # Also send tool start event to WebSocket client
            tool_start_event_copy = tool_start_event.copy()
            tool_start_event_copy["timestamp"] = int(time.time() * 1000)
            await self.output_queue.put(tool_start_event_copy)
            
            # Send tool result event
            if isinstance(toolResult, dict):
                content_json_string = json.dumps(toolResult)
            else:
                content_json_string = toolResult

            tool_result_event = S2sEvent.text_input_tool(prompt_name, toolContent, content_json_string)
            logger.debug(f"Tool result: {tool_result_event}")
            await self.send_raw_event(tool_result_event)
            
            # Also send tool result event to WebSocket client
            tool_result_event_copy = tool_result_event.copy()
            tool_result_event_copy["timestamp"] = int(time.time() * 1000)
            await self.output_queue.put(tool_result_event_copy)

            # Send tool content end event
            tool_content_end_event = S2sEvent.content_end(prompt_name, toolContent)
            await self.send_raw_event(tool_content_end_event)
            
            # Also send tool content end event to WebSocket client
            tool_content_end_event_copy = tool_content_end_event.copy()
            tool_content_end_event_copy["timestamp"] = int(time.time() * 1000)
            await self.output_queue.put(tool_content_end_event_copy)
            
        except Exception as e:
            logger.error(f"Error in tool processing: {e}", exc_info=True)

    async def processToolUse(self, toolName, toolUseContent):
        """Return the tool result"""
        logger.debug(f"Tool Use Content: {toolUseContent}")

        tz = ZoneInfo(self.timezone)
        toolName = toolName.lower()
        content, result = None, None
        try:
            if toolUseContent.get("content"):
                # Parse the JSON string in the content field
                content = toolUseContent.get("content")  # Pass the JSON string directly to the agent
                logger.debug(f"Extracted query: {content}")
            
            # Simple toolUse to get system time in UTC
            if toolName == "getdatetool":
                result = (
                    datetime.now(tz)
                    .strftime('%A, %Y-%m-%d %I:%M:%S %p %Z')
                    .lstrip("0")
                    + f" in {self.timezone}"
                )
            
            if toolName == "create_event":
                # Simulate event creation
                event_details = json.loads(content)
                event_title = event_details.get("title", None)
                naive_start_datetime = event_details.get("start_datetime", None)
                naive_end_datetime = event_details.get("end_datetime", None)
                
                missing_fields = []
                if not event_title:
                  missing_fields.append("title")
                if not naive_start_datetime:
                  missing_fields.append("start_datetime")
                if not naive_end_datetime:
                  missing_fields.append("end_datetime")

                if missing_fields:
                  return {
                      "result": f"Missing required event details: {', '.join(missing_fields)}."
                  }
                
                start_datetime = datetime.fromisoformat(naive_start_datetime).replace(tzinfo=tz)
                end_datetime = datetime.fromisoformat(naive_end_datetime).replace(tzinfo=tz)
                
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
                    "userId": self.user_id,
                    "name": event_title,
                    "content": None,
                    "creationDate": datetime.now(tz).strftime('%Y-%m-%d'), # YYYY-MM-DD in user's timezone
                    "type": event_details.get("type", "personal"),
                    "priority": event_details.get("priority", None),
                    "fixed": event_details.get("fixed", False),
                    "stopDate": event_details["recurrence"].get("stop_date", None),
                    "frequency": event_details["recurrence"]["frequency"],
                    "notifications": notifications,
                    "days": event_details["recurrence"]["days"],
                    "allDay": event_details.get("all_day", False),
                    "exceptionDates": [datetime.now(tz).strftime('%Y-%m-%d')],
                    "prevVersionHabitId": None,
                    "startTime": {
                      "hour": start_datetime.hour,
                      "minute": start_datetime.minute,
                      "timezone": self.timezone
                    },
                    "endTime": {
                      "hour": end_datetime.hour,
                      "minute": end_datetime.minute,
                      "timezone": self.timezone
                    },
                  }
                  ddb_habit_item= {k: serializer.serialize(v) for k, v in new_habit.items()}
                  ddb_client.put_item(TableName='Habits', Item=ddb_habit_item)
                  logger.info(f"DynamoDB put_item succeeded for habit: {new_habit}")
                  result = f"Recuring event '{event_title}' created: {new_habit}"
                else:
                  new_event = {
                    "id": str(uuid.uuid4()),
                    "userId": self.user_id,
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
                
            elif toolName == "delete_event":
                try:
                    logger.info(f"Processing delete_event with content: {content}")
                    event_details = json.loads(content)
                    event_title = event_details.get("title")
                    naive_start_datetime = event_details.get("start_datetime")
                    start_datetime = None
                    
                    logger.info(f"Searching for event to delete: title='{event_title}', start_datetime='{naive_start_datetime}'")
                    # 1. Vectorize and Hybrid Search to find candidate events
                    embed_response = bedrock_client.invoke_model(
                        body=json.dumps({"inputText": event_title}),
                        modelId="amazon.titan-embed-text-v1"
                    )
                    query_vector = json.loads(embed_response['body'].read())['embedding']
                    logger.info(f"Generated embedding for event title: {event_title}")
                    filters = [{"term": {"userId": self.user_id}}]
                    if naive_start_datetime:
                        start_datetime = datetime.fromisoformat(naive_start_datetime).replace(tzinfo=tz)
                    
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
                    habit_hits = opensearch_habits_response['hits']['hits']
                    if matching_habit_names_found > 0:
                        logger.info(f"Found {matching_habit_names_found} matching habits with title '{event_title}'")
                        if start_datetime:
                            matches = []
                            for habit_hit in habit_hits:
                                cfg = RepeatingEventConfig.model_validate(habit_hit['_source'])
                                if utils.isRepeatingOnDay(cfg, start_datetime.date()):
                                    new_tz = ZoneInfo(cfg.startTime.timezone)
                                    d = start_datetime.date()
                                    new_dt = datetime(d.year, d.month, d.day, cfg.startTime.hour, cfg.startTime.minute, tzinfo=new_tz)
                                    if new_dt == start_datetime:
                                        matches.append(habit_hit)
                            if len(matches) == 1:
                                return {"result": f"Do you want to delete only the occurrence on {start_datetime.strftime('%m/%d/%Y %I:%M %p')}? Or do you want to delete this event and all future occurrences? Or all occurrences?"}
                            elif len(matches) > 1:
                                return {"result": f"Unable to delete because I found {len(matches)} recurring events with title '{event_title}' matching the provided start date and time."}
                        else:
                            return {"result": f"Cannot delete event '{event_title}' without a start date and time because it is a recurring event. Please provide the start date and time to identify the specific occurrence to delete."}
    
                    if naive_start_datetime:
                        filters.append({"term": {"startDate": start_datetime.isoformat()}})
                        logger.info(f"Added startDate filter for search: {start_datetime.isoformat()}")
                    search_body["query"]["bool"]["filter"] = filters
                    opensearch_response = opensearch_client.search(
                        index="calendar-events",
                        body=search_body
                    )
                    hits = opensearch_response['hits']['hits']
                    total_found = opensearch_response['hits']['total']['value']
                    
                    logger.info(f"OpenSearch returned {len(hits)} hits for event deletion search")
                    for hit in hits:
                        logger.info(f"score: {hit['_score']}, title: {hit['_source']['title']} startDate: {hit['_source']['startDate']}")
                    
                    if total_found == 0:
                        logger.info(f"No events found matching title '{event_title}' for deletion")
                        return {"result": f"No matching events found for title '{event_title}'."}
                    
                    # handle ambiguity vs exact match
                    target_doc = None
                    if total_found == 1:
                        # exact match
                        target_doc = hits[0]
                        logger.info(f"Single matching event found for deletion: {target_doc}")
                    elif start_datetime:
                        # filter by start date if provided
                        for hit in hits:
                            if hit['_source']['startDate'] == start_datetime.isoformat():
                                target_doc = hit
                                logger.info(f"Matching event found for deletion with start date: {target_doc}")
                                break
                        if not target_doc:
                            return {"result": f"found multiple events with title '{event_title}' but none match the provided start date {start_datetime.isoformat()}."}
                    else:
                        options = [f"on {hit['_source']['startDate']}" for hit in hits]
                        return {
                            "result": f"Found {total_found} matches for '{event_title}': {', '.join(options)}. Which one should I delete?"
                        }
                    
                    if target_doc:
                        os_id = target_doc['_id']
                        eventId = target_doc['_source']['eventId']
                        habitId = target_doc['_source'].get('habitId', None)
                        if habitId:
                            return {"result": f"Do you want to delete only the occurrence on {target_doc['_source']['startDate']}? Or do you want to delete this event and all future occurrences? Or all occurrences?"}
                        opensearch_client.delete(index="calendar-events", id=os_id)
                        ddb_client.delete_item(
                            TableName='Events',
                            Key={'userId': {'S': self.user_id}, 'id': {'S': eventId}}
                        )
                        return {"result": f"Successfully deleted the event '{event_title}'."}
                    else:
                        return {"result": "No matching event found to delete."}
                except Exception as e:
                    logger.error(f"Error during event deletion: {e}", exc_info=True)
                    return {"result": "Sorry, I couldn't process that delete request."}

            if not result:
                result = "no result found"

            return {"result": result}
        except Exception as ex:
            logger.error(f"[Tool Error] Exception in processToolUse for {toolName}: {ex}", exc_info=True)
            return {"result": "An error occurred while attempting to retrieve information related to the toolUse event."}
    
    async def close(self):
        """Close the stream properly."""
        if not self.is_active:
            logger.debug("Stream already closed, skipping cleanup")
            return
            
        logger.info("Closing Bedrock stream and cleaning up resources")
        self.is_active = False
        
        # Cancel any ongoing tool processing tasks
        for task in list(self.tool_processing_tasks):
            if not task.done():
                task.cancel()
        
        # Wait for all tool tasks to complete or be cancelled
        if self.tool_processing_tasks:
            await asyncio.gather(*self.tool_processing_tasks, return_exceptions=True)
        self.tool_processing_tasks.clear()
        
        # Clear audio queue to prevent processing old audio data
        while not self.audio_input_queue.empty():
            try:
                self.audio_input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Clear output queue
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        # Reset tool use state
        self.toolUseContent = ""
        self.toolUseId = ""
        self.toolName = ""
        
        # Reset session information
        self.prompt_name = None
        self.content_name = None
        self.audio_content_name = None
        
        if self.stream:
            try:
                await self.stream.input_stream.close()
            except Exception as e:
                logger.debug(f"Error closing stream: {e}")
        
        if self.response_task and not self.response_task.done():
            self.response_task.cancel()
            try:
                await self.response_task
            except asyncio.CancelledError:
                pass
        
        # Set stream to None to ensure it's properly cleaned up
        self.stream = None
        self.response_task = None
        
        logger.info("Bedrock stream closed successfully")
        