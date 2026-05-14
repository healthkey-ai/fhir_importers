import json
import logging


from infrastructure.gemini_client.gemini_client import GeminiClient, GeminiResponse, GeminiGenerateTextResponse

_logger = logging.getLogger(__name__)


class GeminiClientImplementation(GeminiClient):
    def __init__(self):
        from google.cloud import aiplatform
        from vertexai.preview.generative_models import GenerativeModel, GenerationConfig
        aiplatform.init(project="data-engineering-458413", location="us-central1")

    def chat_generate(self, model: str, body: str) -> GeminiResponse:
        response = self.generate_text(model, body)
        return GeminiResponse(
            output=self._parse_json(response.output),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
        )

    def generate_text(self, model: str, body: str) -> GeminiGenerateTextResponse:
        from google.cloud import aiplatform
        from vertexai.preview.generative_models import (
            GenerativeModel,
            GenerationConfig,
            SafetySetting,
            HarmCategory,
            HarmBlockThreshold,
        )

        config = GenerationConfig(
            temperature=0,
            top_k=1,
            top_p=1,
            max_output_tokens=65535,
            candidate_count=1,
        )

        safety_settings = [
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.OFF,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.OFF,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.OFF,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.OFF,
            ),
        ]

        _logger.info(f"Gemini Request: {model=}, {body=}")
        api = GenerativeModel(model)
        response = api.generate_content(
            body,
            generation_config=config,
            safety_settings=safety_settings,
        )
        print(response.text)
        usage = response.usage_metadata
        return GeminiGenerateTextResponse(
            output=response.text,
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
            total_tokens=usage.total_token_count,
        )


    @staticmethod
    def _parse_json(text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        text = text.strip()
        text = text.removeprefix("```json")
        text = text.removeprefix('"')
        text = text.removesuffix('"')
        text = text.removesuffix("```")
        text = text.removesuffix('"')

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        text = text.replace(r'\"', '__ESCAPED_QUOTE__')
        text = text.replace("\\", "")
        text = text.replace('__ESCAPED_QUOTE__', r'\"')

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            _logger.error(f"Error while decoding json:")
            _logger.error(text)
            raise e
