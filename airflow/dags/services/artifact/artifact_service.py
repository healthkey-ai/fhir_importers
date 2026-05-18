import io
import json
import logging
from typing import Any, Dict, List, Tuple

import pandas as pd
from pydantic import BaseModel

from infrastructure.s3 import S3Client

_logger = logging.getLogger(__name__)

JsonableContent = Dict[str, Any] | List[Any] | Tuple[Any, ...]

ArtifactKey = str


class Artifact(BaseModel):
    key: str
    bucket: str

    @property
    def web_url(self) -> str:
        return f"https://{self.bucket}.s3.us-east-1.amazonaws.com/{self.key}"

    @property
    def s3_url(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class ArtifactService:
    def __init__(self, s3_client: S3Client):
        self._s3_client = s3_client

    @staticmethod
    def build_artifact_key(dag_id: str, run_id: str, task_id: str, key: str) -> ArtifactKey:
        """Builds an artifact key."""
        return f"artifacts/{dag_id}/{run_id}/{task_id}/{key}"

    def get_web_url(self, key: ArtifactKey) -> str:
        """Returns the web URL for an artifact."""
        return self._s3_client.get_web_url(key)

    def get_s3_url(self, key: ArtifactKey) -> str:
        """Returns the S3 URL for an artifact."""
        return self._s3_client.get_s3_url(key)

    def upload_json(self, key: ArtifactKey, content: JsonableContent) -> None:
        """Uploads a JSON-serializable content to S3 and returns the artifact key."""
        _logger.info(f"Uploading {key}")
        self._s3_client.put_object(key, json.dumps(content))

    def upload_df(self, key: ArtifactKey, df: pd.DataFrame) -> None:
        """Uploads a Pandas DataFrame to S3."""
        _logger.info(f"Uploading {key}")
        self._s3_client.put_df(df, key)

    def download_json(self, artifact_key: ArtifactKey) -> JsonableContent:
        """Downloads a JSON-serializable content from S3."""
        _logger.info(f"Downloading {artifact_key}")
        return json.loads(self._s3_client.get_content(artifact_key))

    def download_df(self, artifact_key: ArtifactKey) -> pd.DataFrame:
        """Downloads a Pandas DataFrame from S3."""
        _logger.info(f"Downloading {artifact_key}")
        csv_content = self._s3_client.get_content(artifact_key)
        return pd.read_csv(io.StringIO(csv_content))
