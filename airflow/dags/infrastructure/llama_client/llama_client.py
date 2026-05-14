from typing import Any
import abc



class LlamaClient(abc.ABC):
    def post_generate(self, model: str, prompt: str, response_format: dict) -> dict[str, Any]:
        raise NotImplementedError
