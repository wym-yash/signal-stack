import json
import os
import re
from typing import Any, Optional, Type, TypeVar

from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq
from pydantic import BaseModel

load_dotenv()

ModelT = TypeVar("ModelT", bound=BaseModel)


def _inline_schema(schema: dict[str, Any], defs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Resolve $ref pointers against $defs so Gemini structured output handles nested models cleanly."""
    if defs is None:
        defs = schema.get("$defs", {})

    if isinstance(schema, dict):
        if "$ref" in schema:
            ref_name = schema["$ref"].split("/")[-1]
            resolved = json.loads(json.dumps(defs.get(ref_name, {})))
            for k, v in schema.items():
                if k != "$ref":
                    resolved[k] = v
            return _inline_schema(resolved, defs)

        cleaned: dict[str, Any] = {}
        for k, v in schema.items():
            if k == "$defs":
                continue
            cleaned[k] = _inline_schema(v, defs)
        return cleaned

    if isinstance(schema, list):
        return [_inline_schema(item, defs) for item in schema]

    return schema


def _extract_json_str(raw: str) -> str:
    """Strip markdown code fences if a model wraps JSON output."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return text[start : end + 1]
    return text


class FreeLLMClient:
    def __init__(self) -> None:
        self.gemini_key: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        self.groq_key: str = os.getenv("GROQ_API_KEY", "").strip()
        self.groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"

        self.gemini_client: Optional[genai.Client] = (
            genai.Client(api_key=self.gemini_key) if self.gemini_key else None
        )
        self.groq_client: Optional[Groq] = (
            Groq(api_key=self.groq_key) if self.groq_key else None
        )

    def available_providers(self) -> list[str]:
        providers: list[str] = []
        if self.gemini_client:
            providers.append("gemini")
        if self.groq_client:
            providers.append("groq")
        return providers

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema_model: Type[ModelT],
        temperature: float = 0.2,
    ) -> ModelT:
        errors: list[str] = []
        resolved_schema = _inline_schema(schema_model.model_json_schema())

        if self.gemini_client is not None:
            try:
                resp = self.gemini_client.models.generate_content(
                    model=self.gemini_model,
                    contents=f"{system_prompt}\n\n---\n\n{user_prompt}",
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                        response_schema=resolved_schema,
                    ),
                )
                raw_text = _extract_json_str(resp.text or "")
                return schema_model.model_validate_json(raw_text)
            except Exception as exc:
                errors.append(f"Gemini error: {exc}")

        if self.groq_client is not None:
            try:
                schema_json = json.dumps(resolved_schema)
                chat = self.groq_client.chat.completions.create(
                    model=self.groq_model,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                f"{system_prompt}\n\n"
                                "Return ONLY a valid JSON object matching this JSON Schema:\n"
                                f"{schema_json}"
                            ),
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = chat.choices[0].message.content or "{}"
                raw_text = _extract_json_str(content)
                return schema_model.model_validate_json(raw_text)
            except Exception as exc:
                errors.append(f"Groq error: {exc}")

        raise RuntimeError(
            "No working free LLM response succeeded. Set GEMINI_API_KEY or GROQ_API_KEY in .env. "
            + " | ".join(errors)
        )