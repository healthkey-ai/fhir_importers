from typing import Any
import abc
from pydantic import BaseModel


class BedrockResponse(BaseModel):
    output: dict[str, Any]
    input_tokens: int
    output_tokens: int
    total_tokens: int


class BedrockClient(abc.ABC):
    @abc.abstractmethod
    def chat_generate(self, model: str, body: dict) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def post_generate(self, model: str, body: dict) -> BedrockResponse:
        raise NotImplementedError
