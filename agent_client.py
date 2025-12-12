import asyncio
import websockets
import json
from bedrock_agentcore.runtime import AgentCoreRuntimeClient
import os

async def local_websocket():
    runtime_arn = os.getenv('AGENT_ARN')
    if not runtime_arn:
        raise ValueError("AGENT_ARN environment variable is required")
      
    # Initialize client
    client = AgentCoreRuntimeClient(region="us-east-1")

    # Generate WebSocket connection with authentication
    # ws_url, headers = client.generate_ws_connection(
    #     runtime_arn=runtime_arn
    # )
    
    sigv4_url = client.generate_presigned_url(
        runtime_arn=runtime_arn,
        expires=300  # 5 minutes
    )
    
    print(f"SigV4 Presigned URL: {sigv4_url}")

    # try:
    #     async with websockets.connect(ws_url, additional_headers=headers) as websocket:
    #         # Send a message
    #         await websocket.send(json.dumps({"inputText": "Hello WebSocket!"}))
            
    #         # Receive the echo response
    #         response = await websocket.recv()
    #         print(f"Received: {response}")
    # except Exception as e:
    #     print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(local_websocket())