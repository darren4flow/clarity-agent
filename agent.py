import asyncio

from starlette.websockets import WebSocketDisconnect

from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.websocket
async def websocket_handler(websocket, context):
    await websocket.accept()
    disconnected = False
    try:
        while True:
            try:
                event = await websocket.receive()
            except asyncio.CancelledError:
                raise
            except WebSocketDisconnect:
                disconnected = True
                break
            except Exception as receive_error:
                print(f"Receive error: {receive_error}")
                break

            typ = event.get("type")

            if typ == "websocket.receive":
                if event.get("bytes") is not None:
                    chunk = event["bytes"]
                    if chunk:
                        await websocket.send_bytes(chunk)  # echo PCM
                elif event.get("text") is not None:
                    text = event["text"]
                    await websocket.send_text(text)       # echo JSON/text
            elif typ == "websocket.disconnect":
                disconnected = True
                break
    finally:
        if not disconnected:
            try:
                await websocket.close()
            except Exception as close_error:
                print(f"Close error: {close_error}")

if __name__ == "__main__":
    app.run(log_level="info")