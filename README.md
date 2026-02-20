# Clarity's AI Voice Agent

This repo is responsible for the AI voice agent that is being used in development for Clarity, which is an AI-powered calendar. (useclarity.io)

It is built using AWS's Bedrock Agentcore and Nova 2 Sonic's speech-to-speech LLM model.

The tool's currently available to this agent are:
  - Create Events
  - Read Events
  - Update Events
  - Delete Events

It utitlizes AWS OpenSearch so that it can do a vector search to identify event's by paraphrased names. It also intelligently handles the case that events are recurring 

### Steps to Run Locally

1. Create a virtual environment with python 3.12.4
  `python -m venv venv`
2. Activate the virtual environment
  `source .venv/bin/activate`
3. Install the requirments
  `pip install requirements.txt`
4. Set the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
  `export AWS_SECRET_ACCESS_KEY=<key_value>`
  `export AWS_ACCESS_KEY_ID-<key_id>`