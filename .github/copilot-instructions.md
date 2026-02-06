# Copilot instructions for clarityAgent

## Big picture architecture
- The entrypoint is [agent.py](agent.py), a Starlette WebSocket app (BedrockAgentCoreApp) that accepts a `userId` + optional `timezone` query param and forwards events to Bedrock.
- Real-time streaming is managed by `S2sSessionManager` in [s2s_session_manager.py](s2s_session_manager.py): it opens a bidirectional Bedrock stream, queues audio via `audio_input_queue`, and pushes model outputs to `output_queue` for the WebSocket forward task.
- Event payload shapes are centralized in `S2sEvent` helpers in [s2s_events.py](s2s_events.py) (e.g., `sessionStart`, `promptStart`, `contentStart`, `audioInput`, `toolResult`). Follow these helpers when adding new event types.
- Tool-use events are handled inside `S2sSessionManager.processToolUse()` and run in background tasks (`_handle_tool_processing`) to avoid blocking streaming.

## External integrations and data flow
- DynamoDB tables: `Events` and `Habits` are written/read via boto3 with `TypeSerializer`/`TypeDeserializer` (see [s2s_session_manager.py](s2s_session_manager.py)).
- OpenSearch is used for hybrid search in indexes `habits` and `calendar-events` with a Titan embedding model for vector search.
- Bedrock runtime is used for both streaming responses and embeddings (`amazon.titan-embed-text-v1`).
- Timezone handling uses `ZoneInfo` and is passed from the WebSocket query param; tool logic assumes timezone-aware datetimes.

## Project-specific patterns and conventions
- Recurrence logic lives in [utils.py](utils.py) (`isRepeatingOnDay`, date math helpers); recurring-event configs are modeled by Pydantic models in [repeating_event_config_model.py](repeating_event_config_model.py).
- When updating repeating events, logic branches for `this_event_only` vs `this_and_future_events` and may create a new repeating config while setting `stopDate` on the old one.
- DynamoDB serialization needs `_to_dynamodb_compatible()` for dates, Decimals, UUIDs, etc. in [utils.py](utils.py).
- Large outbound events are split in [agent.py](agent.py) `split_large_event()`; audio chunks must align to base64 boundaries.

## Tests and local workflow
- Tests are pytest-based with extensive monkeypatching of boto3/OpenSearch clients (see [tests/test_update_event_tool.py](tests/test_update_event_tool.py) and [tests/test_get_end_datetime.py](tests/test_get_end_datetime.py)).
- `get_new_end_datetime()` and related scheduling edge cases are validated in [tests/test_get_end_datetime.py](tests/test_get_end_datetime.py); keep its invariants when changing date logic.

## Key files to reference when editing
- Streaming + tool orchestration: [s2s_session_manager.py](s2s_session_manager.py)
- WebSocket lifecycle + forwarding: [agent.py](agent.py)
- Event payload schemas: [s2s_events.py](s2s_events.py)
- Recurrence models + validation: [repeating_event_config_model.py](repeating_event_config_model.py)
- Date math utilities: [utils.py](utils.py)
