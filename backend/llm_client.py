import json
import os
import re
from typing import Any, Optional, Type

from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq
from pydantic import BaseModel

load_dotenv()


class _DictView(dict):
    def __init__(self, mapping: dict[str, Any]) -> None:
        wrapped = {k: _wrap_structured(v) for k, v in mapping.items()}
        super().__init__(wrapped)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(f"'dict' object has no attribute '{name}'") from exc


def _wrap_structured(value: Any) -> Any:
    if isinstance(value, dict):
        return _DictView(value)
    if isinstance(value, list):
        return [_wrap_structured(item) for item in value]
    return value


def _extract_json(raw: str) -> Any:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if match:
            return json.loads(match.group(1))
        raise


def _resolve_prompt(prompt: Optional[str], kwargs: dict[str, Any]) -> str:
    if prompt:
        return str(prompt)
    for key in (
        "user_prompt",
        "input_prompt",
        "user_message",
        "input_text",
        "text",
        "query",
        "messages_prompt",
    ):
        val = kwargs.get(key)
        if val:
            return str(val)
    raise TypeError(f"Missing prompt argument. Received kwargs keys: {list(kwargs.keys())}")


def _resolve_system(system_prompt: str, system_instruction: str, kwargs: dict[str, Any]) -> str:
    if system_prompt:
        return system_prompt
    if system_instruction:
        return system_instruction
    for key in ("system", "system_msg", "instructions"):
        val = kwargs.get(key)
        if val:
            return str(val)
    return ""


def _resolve_model_and_schema(
    schema_hint: Optional[Any], kwargs: dict[str, Any]
) -> tuple[Optional[Type[BaseModel]], Optional[str]]:
    model_cls: Optional[Type[BaseModel]] = None
    schema_text: Optional[str] = None

    candidates = [schema_hint] + list(kwargs.values())
    for item in candidates:
        if isinstance(item, type) and issubclass(item, BaseModel):
            model_cls = item
            break

    if model_cls is not None:
        schema_text = json.dumps(model_cls.model_json_schema(), indent=2)
        return model_cls, schema_text

    for key in (
        "schema",
        "json_schema",
        "schema_hint",
        "output_schema",
        "response_schema",
        "structure",
        "format_hint",
        "example",
    ):
        val = kwargs.get(key)
        if val is not None:
            schema_text = val if isinstance(val, str) else json.dumps(val, indent=2)
            break

    if schema_text is None and schema_hint is not None:
        schema_text = schema_hint if isinstance(schema_hint, str) else json.dumps(schema_hint, indent=2)

    return None, schema_text


class FreeLLMClient:
    def __init__(self) -> None:
        self.gemini_api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        self.gemini_model = (os.getenv("GEMINI_MODEL") or "gemini-2.5-flash").strip()

        self.groq_api_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.groq_model = (os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b").strip()

        self._gemini = (
            genai.Client(
                api_key=self.gemini_api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )
            if self.gemini_api_key
            else None
        )
        self._groq = Groq(api_key=self.groq_api_key) if self.groq_api_key else None

    def available_providers(self) -> list[str]:
        providers: list[str] = []
        if self._gemini:
            providers.append("gemini")
        if self._groq:
            providers.append("groq")
        return providers

    def generate_text(
        self,
        prompt: Optional[str] = None,
        system_prompt: str = "",
        system_instruction: str = "",
        temperature: float = 0.3,
        **kwargs: Any,
    ) -> str:
        resolved_prompt = _resolve_prompt(prompt, kwargs)
        sys_msg = _resolve_system(system_prompt, system_instruction, kwargs).strip()
        errors: list[str] = []

        if self._gemini:
            try:
                resp = self._gemini.models.generate_content(
                    model=self.gemini_model,
                    contents=resolved_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_msg or None,
                        temperature=temperature,
                    ),
                )
                if resp.text:
                    return resp.text.strip()
            except Exception as exc:
                errors.append(f"Gemini error: {exc}")

        if self._groq:
            try:
                messages = []
                if sys_msg:
                    messages.append({"role": "system", "content": sys_msg})
                messages.append({"role": "user", "content": resolved_prompt})
                resp = self._groq.chat.completions.create(
                    model=self.groq_model,
                    messages=messages,
                    temperature=temperature,
                )
                content = resp.choices[0].message.content
                if content:
                    return content.strip()
            except Exception as exc:
                errors.append(f"Groq error: {exc}")

        joined = " | ".join(errors) if errors else "No LLM client configured."
        raise RuntimeError(
            f"No working free LLM response succeeded. Set GEMINI_API_KEY or GROQ_API_KEY in .env. {joined}"
        )

    def generate_json(
        self,
        prompt: Optional[str] = None,
        system_prompt: str = "",
        system_instruction: str = "",
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> str:
        resolved_prompt = _resolve_prompt(prompt, kwargs)
        sys_msg = _resolve_system(system_prompt, system_instruction, kwargs).strip()
        errors: list[str] = []

        if self._gemini:
            try:
                resp = self._gemini.models.generate_content(
                    model=self.gemini_model,
                    contents=resolved_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_msg or None,
                        response_mime_type="application/json",
                        temperature=temperature,
                    ),
                )
                if resp.text:
                    return resp.text
            except Exception as exc:
                errors.append(f"Gemini error: {exc}")

        if self._groq:
            try:
                messages = []
                if sys_msg:
                    messages.append({"role": "system", "content": sys_msg})
                messages.append({"role": "user", "content": resolved_prompt})
                resp = self._groq.chat.completions.create(
                    model=self.groq_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=temperature,
                )
                content = resp.choices[0].message.content
                if content:
                    return content
            except Exception as exc:
                errors.append(f"Groq error: {exc}")

        joined = " | ".join(errors) if errors else "No LLM client configured."
        raise RuntimeError(
            f"No working free LLM response succeeded. Set GEMINI_API_KEY or GROQ_API_KEY in .env. {joined}"
        )

    def generate_structured(
        self,
        prompt: Optional[str] = None,
        system_prompt: str = "",
        system_instruction: str = "",
        schema_hint: Optional[Any] = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Any:
        resolved_prompt = _resolve_prompt(prompt, kwargs)
        sys_msg = _resolve_system(system_prompt, system_instruction, kwargs).strip()
        model_cls, schema_text = _resolve_model_and_schema(schema_hint, kwargs)

        if schema_text:
            full_prompt = (
                f"{resolved_prompt}\n\n"
                f"Return a single valid JSON object strictly conforming to this JSON Schema:\n"
                f"{schema_text}"
            )
        else:
            full_prompt = f"{resolved_prompt}\n\nReturn strictly valid JSON only."

        raw = self.generate_json(
            prompt=full_prompt,
            system_prompt=sys_msg,
            temperature=temperature,
        )
        parsed = _extract_json(raw)

        if model_cls is not None:
            return model_cls.model_validate(parsed)

        return _wrap_structured(parsed)