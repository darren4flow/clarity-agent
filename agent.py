import os
import asyncio
from starlette.websockets import WebSocketDisconnect, WebSocket
from starlette.responses import JSONResponse
from bedrock_agentcore import BedrockAgentCoreApp
import logging
import base64
import json
import uuid
import pyaudio
from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from aws_sdk_bedrock_runtime.config import Config, HTTPAuthSchemeResolver, SigV4AuthScheme
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver
from s2s_session_manager import S2sSessionManager


# Audio configuration
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 1024

# Global variable to track credential refresh task
credential_refresh_task = None

app = BedrockAgentCoreApp()


# configure logging for stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.route("/ping", methods=["GET"])
async def ping():
    logger.debug("Ping endpoint called")
    return JSONResponse({"status": "ok"})


@app.websocket
async def websocket_handler(websocket, context):
    logger.info(f"WebSocket connection attempted from {websocket.client}")
    logger.debug(f"Headers: {websocket.headers}")
    
    user_id = websocket.query_params.get("userId", None)
    if not user_id:
        logger.warning("Missing userId in query parameters")
        await websocket.close(code=1008)  # Policy Violation
        return
    timezone = websocket.query_params.get("timezone", None)
    if not timezone:
        logger.warning("Missing timezone in query parameters, defaulting to UTC")
    
    # Accept the WebSocket connection
    await websocket.accept()
    logger.info(f"WebSocket connection accepted")
    
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    stream_manager = None
    forward_task = None
    
    try:
        # Main message processing loop
        while True:
            try:
                message = await websocket.receive_text()
                logger.debug("Received message from client")
                
                try:
                    data = json.loads(message)

                    # Handle wrapped body format
                    if "body" in data:
                        data = json.loads(data["body"])

                    if "event" not in data:
                        logger.warning("Received message without event field")
                        continue

                    event_type = list(data["event"].keys())[0]

                    # Handle session start - create new stream manager
                    if event_type == "sessionStart":
                        logger.info("Starting new session")

                        # Clean up existing session if any
                        if stream_manager:
                            logger.info("Cleaning up existing session")
                            await stream_manager.close()
                        if forward_task and not forward_task.done():
                            forward_task.cancel()
                            try:
                                await forward_task
                            except asyncio.CancelledError:
                                pass

                        # Create a new stream manager for this connection
                        stream_manager = S2sSessionManager(
                            model_id="amazon.nova-2-sonic-v1:0", region=aws_region, user_id=user_id, timezone=timezone
                        )

                        # Initialize the Bedrock stream
                        await stream_manager.initialize_stream()
                        logger.info("Stream initialized successfully")

                        # Start a task to forward responses from Bedrock to the WebSocket
                        forward_task = asyncio.create_task(
                            forward_responses(websocket, stream_manager)
                        )

                        # Now send the sessionStart event to Bedrock
                        await stream_manager.send_raw_event(data)
                        logger.info(
                            f"SessionStart event sent to Bedrock {json.dumps(data)}"
                        )

                        # Continue to next iteration to process next event
                        continue

                    # Handle session end - clean up resources
                    elif event_type == "sessionEnd":
                        logger.info("Ending session")

                        if stream_manager:
                            await stream_manager.close()
                            stream_manager = None
                        if forward_task and not forward_task.done():
                            forward_task.cancel()
                            try:
                                await forward_task
                            except asyncio.CancelledError:
                                pass
                            forward_task = None

                        # Continue to next iteration
                        continue

                    # Process events if we have an active stream manager
                    if stream_manager and stream_manager.is_active:
                        # Store prompt name and content names if provided
                        if event_type == "promptStart":
                            stream_manager.prompt_name = data["event"]["promptStart"][
                                "promptName"
                            ]
                        elif (
                            event_type == "contentStart"
                            and data["event"]["contentStart"].get("type") == "AUDIO"
                        ):
                            stream_manager.audio_content_name = data["event"][
                                "contentStart"
                            ]["contentName"]

                        # Handle audio input separately (queue-based processing)
                        if event_type == "audioInput":
                            prompt_name = data["event"]["audioInput"]["promptName"]
                            content_name = data["event"]["audioInput"]["contentName"]
                            audio_base64 = data["event"]["audioInput"]["content"]

                            # Add to the audio queue for async processing
                            stream_manager.add_audio_chunk(
                                prompt_name, content_name, audio_base64
                            )
                        else:
                            # Send other events directly to Bedrock
                            await stream_manager.send_raw_event(data)
                    elif event_type not in ["sessionStart", "sessionEnd"]:
                        logger.warning(
                            f"Received event {event_type} but no active stream manager"
                        )

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received from WebSocket: {e}")
                    try:
                        await websocket.send_json(
                            {"type": "error", "message": "Invalid JSON format"}
                        )
                    except Exception:
                        pass
                except Exception as exp:
                    logger.error(
                        f"Error processing WebSocket message: {exp}", exc_info=True
                    )
                    try:
                        await websocket.send_json(
                            {"type": "error", "message": str(exp)}
                        )
                    except Exception:
                        pass
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: {websocket.client}")
                logger.info(
                    f"Disconnect details: code={getattr(e, 'code', 'N/A')}, reason={getattr(e, 'reason', 'N/A')}"
                )
                if stream_manager and stream_manager.is_active:
                    logger.info(
                        "Bedrock stream was still active when WebSocket disconnected"
                    )
                break
            except Exception as e:
                logger.error(f"Websocket error: {e}", exc_info=True)
                break
            
    except Exception as e:
        logger.error(f"WebSocket handler error: {e}", exc_info=True)
        try:
            await websocket.send_json(
                {"type": "error", "message": "WebSocket handler error"}
            )
        except Exception:
            pass
    finally:
        # Clean up resources
        logger.info("Cleaning up WebSocket connection resources")
        if stream_manager:
            await stream_manager.close()
        if forward_task and not forward_task.done():
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass

        try:
            await websocket.close()
        except Exception as e:
            logger.error(f"Error closing websocket: {e}")

        logger.info("Connection closed")
        
        
def split_large_event(response, max_size=16000):
    """
    Split a large event into smaller chunks by dividing the content field.
    For audio events, ensures splits occur at sample boundaries to avoid noise.
    Returns a list of events to send.
    """
    event = json.dumps(response)
    event_size = len(event.encode("utf-8"))

    # If event is small enough, return as-is
    if event_size <= max_size:
        return [response]

    # Get event type and data
    if "event" not in response:
        return [response]

    event_type = list(response["event"].keys())[0]
    event_data = response["event"][event_type]

    # Only split events that have a 'content' field (audioOutput, textOutput, etc.)
    if "content" not in event_data:
        logger.warning(
            f"Event {event_type} is large ({event_size} bytes) but has no content field to split"
        )
        return [response]

    content = event_data["content"]

    # Calculate how much content we can fit per chunk
    # Create a template event to measure overhead
    template_event = response.copy()
    template_event["event"] = {event_type: event_data.copy()}
    template_event["event"][event_type]["content"] = ""
    overhead = len(json.dumps(template_event).encode("utf-8"))

    # Calculate max content size per chunk (leave some margin)
    max_content_size = max_size - overhead - 100

    # For audio events, align to sample boundaries
    # Base64 encoding: 4 chars = 3 bytes of binary data
    # PCM 16-bit: 2 bytes per sample
    # Must align to multiples of 4 chars for valid base64 (no padding issues)
    if event_type == "audioOutput":
        # Align to 4-char boundaries for complete base64 groups
        # This ensures each chunk is valid base64 without padding issues
        alignment = 4
        max_content_size = (max_content_size // alignment) * alignment
        logger.debug(
            f"Audio splitting: aligned chunk size to {max_content_size} chars (base64 boundary)"
        )

    # Split content into chunks
    chunks = []
    for i in range(0, len(content), max_content_size):
        chunk_content = content[i : i + max_content_size]

        # For base64 content, ensure proper padding if needed
        if event_type == "audioOutput":
            # Each chunk should be a multiple of 4 chars (already aligned above)
            # But verify and add padding if somehow needed
            remainder = len(chunk_content) % 4
            if remainder != 0:
                # This shouldn't happen due to alignment, but just in case
                padding_needed = 4 - remainder
                chunk_content += "=" * padding_needed
                logger.warning(f"Added {padding_needed} padding chars to audio chunk")

        # Create new event with chunked content
        chunk_event = response.copy()
        chunk_event["event"] = {event_type: event_data.copy()}
        chunk_event["event"][event_type]["content"] = chunk_content

        chunks.append(chunk_event)

    logger.info(
        f"Split {event_type} event ({event_size} bytes) into {len(chunks)} chunks"
    )
    return chunks


async def forward_responses(websocket: WebSocket, stream_manager):
    """Forward responses from Bedrock to the WebSocket client."""
    try:
        while True:
            # Get next response from the output queue
            response = await stream_manager.output_queue.get()

            # Send to WebSocket
            try:
                # Check if event needs to be split
                event = json.dumps(response)
                event_size = len(event.encode("utf-8"))

                # Get event type for logging
                event_type = (
                    list(response.get("event", {}).keys())[0]
                    if "event" in response
                    else "unknown"
                )

                # Split large events
                if event_size > 10000:
                    logger.warning(
                        f"!!!! Large {event_type} event detected (size: {event_size} bytes) - splitting..."
                    )
                    events_to_send = split_large_event(response, max_size=10000)
                else:
                    events_to_send = [response]

                # Send all chunks
                for idx, event_chunk in enumerate(events_to_send):
                    chunk_json = json.dumps(event_chunk)
                    chunk_size = len(chunk_json.encode("utf-8"))

                    await websocket.send_text(chunk_json)

                    if len(events_to_send) > 1:
                        logger.debug(
                            f"Forwarded {event_type} chunk {idx + 1}/{len(events_to_send)} to client (size: {chunk_size} bytes)"
                        )
                    else:
                        logger.debug(
                            f"Forwarded {event_type} to client (size: {chunk_size} bytes)"
                        )

            except Exception as e:
                logger.error(f"Error sending response to client: {e}", exc_info=True)
                # Check if it's a connection error that should break the loop
                error_str = str(e).lower()
                if "closed" in error_str or "disconnect" in error_str:
                    logger.info("WebSocket connection closed, stopping forward task")
                    break
                # For other errors, log but continue trying
                logger.warning("Continuing to forward responses despite error")
    except asyncio.CancelledError:
        logger.debug("Forward responses task cancelled")
    except Exception as e:
        logger.error(f"Error forwarding responses: {e}", exc_info=True)
    finally:
        logger.info("Forward responses task ended")

if __name__ == "__main__":
    app.run(log_level="info")