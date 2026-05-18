import logging
from io import StringIO
import json
import botocore.session
import urllib.parse
import pandas as pd
from typing import Dict, List, Any, Tuple

_logger = logging.getLogger(__name__)



class S3Client:
    def __init__(self, bucket_name: str):
        session = botocore.session.get_session()
        self._client = session.create_client("s3")
        self._bucket_name = bucket_name

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def get_s3_url(self, key: str) -> str:
        return f"s3://{self._bucket_name}/{key}"

    def get_web_url(self, key: str) -> str:
        encoded_key = urllib.parse.quote(key, safe="")
        return f"https://{self._bucket_name}.s3.us-east-1.amazonaws.com/{encoded_key}"

    def put_df(self, df: pd.DataFrame, file_name: str) -> None:
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        self.put_object(key=file_name, body=csv_buffer.getvalue())

    def put_object(self, key: str, body: str) -> None:
        _logger.info(f"Uploading {key} to {self._bucket_name}")
        result = self._client.put_object(Bucket=self._bucket_name, Key=key, Body=body)
        _logger.info(f"Result: {result}")

    def get_content(self, file_key: str) -> str:
        response = self._client.get_object(Bucket=self._bucket_name, Key=file_key)
        content = response["Body"].read().decode("utf-8")
        return content
