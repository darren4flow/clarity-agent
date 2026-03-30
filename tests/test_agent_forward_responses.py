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
