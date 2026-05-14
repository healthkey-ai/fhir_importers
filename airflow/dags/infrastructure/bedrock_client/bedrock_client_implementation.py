import json
import logging

import boto3

from infrastructure.bedrock_client.bedrock_client import BedrockClient, BedrockResponse

_logger = logging.getLogger(__name__)


class BedrockClientImplementation(BedrockClient):
    def __init__(self, personal: bool = False):
        self._client = boto3.client(
            "bedrock-runtime",
            region_name="us-east-1",
            endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"
        )

    def chat_generate(self, model: str, body: dict) -> str:
        response = self._client.invoke_model(
            modelId=model,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )
        response_body = json.loads(response["body"].read())
        text = response_body['output']['message']['content'][0]['text']
        return text

    def post_generate(self, model: str, body: dict) -> BedrockResponse:
        response = self._client.invoke_model(
            modelId=model,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body)
        )
        response_body = json.loads(response["body"].read())
        text = response_body['output']['message']['content'][0]['text']
        usage = response_body['usage']
        return BedrockResponse(
            output=self._parse_json(text),
            input_tokens=usage["inputTokens"],
            output_tokens=usage["outputTokens"],
            total_tokens=usage["totalTokens"]
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        text = text.removeprefix("```json")
        text = text.removeprefix('"')
        text = text.removesuffix("```")
        text = text.removesuffix('"')

        replace_map = {
            "\\\<": "<",
            "\\\>": ">",
            "\<": "<",
            "\>": ">",
        }
        for k, v in replace_map.items():
            text = text.replace(k, v)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            _logger.error(f"Error while decoding json:")
            _logger.error(text)
            raise e
