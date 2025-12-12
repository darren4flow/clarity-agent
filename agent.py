import asyncio
from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

@app.websocket
async def websocket_handler(websocket, context):
    """Simple echo WebSocket handler."""
    await websocket.accept()

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except asyncio.CancelledError:
                # Propagate cancellation so upstream shutdown logic keeps working.
                raise
            except Exception as receive_error:
                print(f"Receive error: {receive_error}")
                break

            if data is None:
                # Treat null payloads as keep-alives; ignore and continue.
                continue

            try:
                # Echo back
                await websocket.send_json({"echo": data})
            except Exception as send_error:
                print(f"Send error: {send_error}")
                break
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await websocket.close()

if __name__ == "__main__":
    app.run(log_level="info")