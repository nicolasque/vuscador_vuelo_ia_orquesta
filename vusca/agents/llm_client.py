"""LLM Client for Google Gemini with heuristic fallback."""

import json
import logging
from typing import Optional, Dict, Any
from vusca import config

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper around google-genai with fallback handling."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.model_name = model or config.GEMINI_MODEL
        self._client = None
        self._init_client()

    def _init_client(self):
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Google GenAI client with model {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI: {e}")
                self._client = None

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        if not self._client:
            return None
        try:
            from google.genai import types
            config_params = {}
            if system_instruction:
                config_params["system_instruction"] = system_instruction

            cfg = types.GenerateContentConfig(**config_params) if config_params else None
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=cfg,
            )
            return response.text
        except Exception as e:
            logger.warning(f"Error calling Gemini API: {e}")
            return None

    def generate_json(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self._client:
            return None
        try:
            from google.genai import types
            config_params = {"response_mime_type": "application/json"}
            if system_instruction:
                config_params["system_instruction"] = system_instruction

            cfg = types.GenerateContentConfig(**config_params)
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=cfg,
            )
            if response.text:
                return json.loads(response.text)
        except Exception as e:
            logger.warning(f"Error calling Gemini JSON API: {e}")
        return None
