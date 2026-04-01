import sys
import json
import asyncio
import pytest
from pathlib import Path
from starlette.websockets import WebSocketState

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent


class FakeWebSocket:
    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.sent_messages = []
        self.close_code = None
        self.close_reason = None

    async def send_text(self, text):
        if self.client_state == WebSocketState.DISCONNECTED:
            raise RuntimeError("WebSocket closed")
        self.sent_messages.append(text)

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.close_reason = reason
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED


class FakeStreamManager:
    def __init__(self, *, is_active, session_end_sent):
        self.output_queue = asyncio.Queue()
        self.is_active = is_active
        self._session_end_sent = session_end_sent


class FakeContextStreamManager:
    def __init__(self, prompt_name):
        self.prompt_name = prompt_name
        self.events = []

    async def send_raw_event(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_forward_responses_closes_on_fatal_error_event():
    ws = FakeWebSocket()
    stream_manager = FakeStreamManager(is_active=True, session_end_sent=False)
    await stream_manager.output_queue.put(
        {
            "event": {
                "error": {
                    "message": "Stream error from Bedrock",
                    "code": "BEDROCK_STREAM_FATAL",
                    "fatal": True,
                }
            }
        }
    )

    await agent.forward_responses(ws, stream_manager)

    assert len(ws.sent_messages) == 1
    payload = json.loads(ws.sent_messages[0])
    assert payload["event"]["error"]["fatal"] is True
    assert ws.close_code == 1011


@pytest.mark.asyncio
async def test_forward_responses_closes_on_unexpected_inactive_stream_timeout(monkeypatch):
    ws = FakeWebSocket()
    stream_manager = FakeStreamManager(is_active=False, session_end_sent=False)

    async def fake_wait_for(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(agent.asyncio, "wait_for", fake_wait_for)

    await agent.forward_responses(ws, stream_manager)

    assert ws.close_code == 1011
    assert ws.close_reason == "Upstream stream failed"


@pytest.mark.asyncio
async def test_forward_responses_does_not_close_after_normal_session_end_timeout(monkeypatch):
    ws = FakeWebSocket()
    stream_manager = FakeStreamManager(is_active=False, session_end_sent=True)

    async def fake_wait_for(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(agent.asyncio, "wait_for", fake_wait_for)

    await agent.forward_responses(ws, stream_manager)

    assert ws.close_code is None


@pytest.mark.asyncio
async def test_forward_responses_closes_on_end_conversation_control_event():
    ws = FakeWebSocket()
    stream_manager = FakeStreamManager(is_active=True, session_end_sent=False)
    await stream_manager.output_queue.put(
        {
            "type": "end_conversation",
            "reason": "Tool requested conversation end",
        }
    )

    await agent.forward_responses(ws, stream_manager)

    assert ws.close_code == 1000
    assert ws.close_reason == "Conversation ended"


@pytest.mark.asyncio
async def test_send_open_event_context_sends_three_events():
    stream_manager = FakeContextStreamManager(prompt_name="prompt-1")

    sent = await agent.send_open_event_context(stream_manager, "evt-123")

    assert sent is True
    assert len(stream_manager.events) == 3
    assert "contentStart" in stream_manager.events[0]["event"]
    assert stream_manager.events[0]["event"]["contentStart"]["role"] == "USER"
    assert "textInput" in stream_manager.events[1]["event"]
    assert "contentEnd" in stream_manager.events[2]["event"]
    assert "evt-123" in stream_manager.events[1]["event"]["textInput"]["content"]


@pytest.mark.asyncio
async def test_send_open_event_context_returns_false_without_prompt_name():
    stream_manager = FakeContextStreamManager(prompt_name=None)

    sent = await agent.send_open_event_context(stream_manager, "evt-123")

    assert sent is False
    assert stream_manager.events == []


@pytest.mark.asyncio
async def test_send_closed_event_context_sends_event_id_when_present():
    stream_manager = FakeContextStreamManager(prompt_name="prompt-1")

    sent = await agent.send_closed_event_context(stream_manager, "evt-777")

    assert sent is True
    assert len(stream_manager.events) == 3
    assert stream_manager.events[0]["event"]["contentStart"]["role"] == "USER"
    assert "evt-777" in stream_manager.events[1]["event"]["textInput"]["content"]


@pytest.mark.asyncio
async def test_send_closed_event_context_works_without_previous_event_id():
    stream_manager = FakeContextStreamManager(prompt_name="prompt-1")

    sent = await agent.send_closed_event_context(stream_manager, None)

    assert sent is True
    assert len(stream_manager.events) == 3
    assert (
        "I see you closed the event"
        in stream_manager.events[1]["event"]["textInput"]["content"]
    )
