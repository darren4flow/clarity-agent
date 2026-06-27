import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import utils


def _lambda_client_for_result(lambda_result, status_code=200, function_error=None):
    response = {
        "StatusCode": status_code,
        "Payload": BytesIO(json.dumps(lambda_result).encode("utf-8")),
    }
    if function_error:
        response["FunctionError"] = function_error
    return Mock(invoke=Mock(return_value=response))


def test_generate_update_content_returns_doc_from_successful_lambda_response():
    generated_doc = {"type": "doc", "content": [{"type": "paragraph", "content": []}]}
    lambda_client = _lambda_client_for_result(
        {
            "statusCode": 200,
            "body": {"doc": generated_doc},
        }
    )

    result = utils.generate_update_content(
        lambda_client,
        user_id="user-1",
        prompt="add a checklist",
        event_content=None,
    )

    assert result == generated_doc


def test_generate_update_content_returns_doc_from_successful_string_body_response():
    generated_doc = {"type": "doc", "content": [{"type": "paragraph", "attrs": {"checked": False}}]}
    lambda_client = _lambda_client_for_result(
        {
            "statusCode": 200,
            "body": json.dumps({"doc": generated_doc}),
        }
    )

    result = utils.generate_update_content(
        lambda_client,
        user_id="user-1",
        prompt="add a checklist",
        event_content=None,
    )

    assert result == generated_doc


def test_generate_update_content_raises_on_payload_status_502():
    lambda_client = _lambda_client_for_result(
        {
            "statusCode": 502,
            "body": json.dumps({"message": "Bad Gateway"}),
        }
    )

    with pytest.raises(Exception, match="Error from content update Lambda"):
        utils.generate_update_content(
            lambda_client,
            user_id="user-1",
            prompt="add a checklist",
            event_content={"type": "doc", "content": []},
        )


def test_generate_update_content_raises_on_function_error():
    lambda_client = _lambda_client_for_result(
        {"errorMessage": "Unhandled exception"},
        function_error="Unhandled",
    )

    with pytest.raises(Exception, match="Error from content update Lambda"):
        utils.generate_update_content(
            lambda_client,
            user_id="user-1",
            prompt="add a checklist",
            event_content={"type": "doc", "content": []},
        )


def test_generate_update_content_raises_on_invoke_status_error():
    lambda_client = _lambda_client_for_result(
        {"message": "Service unavailable"},
        status_code=503,
    )

    with pytest.raises(Exception, match="Error from content update Lambda"):
        utils.generate_update_content(
            lambda_client,
            user_id="user-1",
            prompt="add a checklist",
            event_content={"type": "doc", "content": []},
        )
