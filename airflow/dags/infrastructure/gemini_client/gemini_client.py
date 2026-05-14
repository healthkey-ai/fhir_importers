import abc
from typing import Any

from pydantic import BaseModel


class GeminiResponse(BaseModel):
    output: dict[str, Any]
    input_tokens: int
    output_tokens: int
    total_tokens: int


class GeminiGenerateTextResponse(BaseModel):
    output: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


class GeminiClient(abc.ABC):
    @abc.abstractmethod
    def generate_text(self, model: str, body: str) -> GeminiGenerateTextResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def chat_generate(self, model: str, body: str) -> GeminiResponse:
        raise NotImplementedError
