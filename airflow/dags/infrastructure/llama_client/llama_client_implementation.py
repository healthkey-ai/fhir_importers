import requests
import json
import logging
from typing import Any

from infrastructure.llama_client.llama_client import LlamaClient

_logger = logging.getLogger(__name__)

class LlamaClientImplementation(LlamaClient):
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._headers = {
            "Content-Type": "application/json",
            "Host": "localhost",
        }

    def post_generate(self, model: str, prompt: str, response_format: dict) -> dict[str, Any]:
        url = self._base_url + "/generate"
        data = {
            #"model": "llama3.2:1b",
            "model": model,
            #"model": "deepseek-r1:32b",
            "prompt": prompt,
            "stream": False,
            "format": response_format,
            "temperature": 0,
            "options": {
                "num_ctx": 8192,
            },
            "top_k": 1,
            "top_p": 1.0,
        }
        _logger.info(f"POST {url}")
        _logger.info(f"Data: {data}")
        response = requests.post(url, headers=self._headers.copy(), json=data)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            _logger.error(f"Error: {e}")
            _logger.error(f"Response: {response.text}")
            _logger.error(f"Status code: {response.status_code}")
            raise
        data = response.json()
        assert data["done"] is True
        return json.loads(data["response"])
