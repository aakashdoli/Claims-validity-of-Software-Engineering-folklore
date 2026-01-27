# src/se_claims_tool/llm/azure_client.py
from __future__ import annotations

import os
from typing import Dict, List


class AzureChatClient:
    """
    Azure OpenAI chat wrapper using environment variables.

    Expected env vars:
      AZURE_OPENAI_ENDPOINT (base, e.g., https://bth-ai.azure-api.net/student)
      AZURE_OPENAI_API_KEY
      AZURE_OPENAI_API_VERSION
      AZURE_OPENAI_DEPLOYMENT
    """

    def __init__(self) -> None:
        try:
            from openai import AzureOpenAI  # openai>=1.x
        except ImportError as e:
            raise RuntimeError("openai package not installed. pip install openai") from e

        endpoint = (os.environ.get("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
        api_key = (os.environ.get("AZURE_OPENAI_API_KEY") or "").strip()
        api_version = (os.environ.get("AZURE_OPENAI_API_VERSION") or "").strip()
        self.deployment = (os.environ.get("AZURE_OPENAI_DEPLOYMENT") or "").strip()

        # Normalize endpoint: AzureOpenAI client appends "/openai/..." internally
        if endpoint.endswith("/openai"):
            endpoint = endpoint[: -len("/openai")]

        if not endpoint:
            raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT")
        if not api_key:
            raise RuntimeError("Missing AZURE_OPENAI_API_KEY")
        if not api_version:
            raise RuntimeError("Missing AZURE_OPENAI_API_VERSION")
        if not self.deployment:
            raise RuntimeError("Missing AZURE_OPENAI_DEPLOYMENT")

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    def chat_json(self, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""
