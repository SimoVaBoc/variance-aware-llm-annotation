"""Fake provider clients for Chapter 3 tests.

Nothing here opens a socket. Every client replays a scripted list of responses
or exceptions, so the adapter and execution layers are exercised end to end
without contacting an external API.
"""

from __future__ import annotations

from typing import Any


class Obj:
    """Attribute-style stand-in for an SDK response object."""

    def __init__(self, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(self, key, value)


class ScriptedResponder:
    """Return, or raise, the next scripted item on each call."""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        if not self.script:
            raise AssertionError("Fake client was called more times than scripted")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeOpenAIClient:
    """Mimics ``client.chat.completions.create(**kwargs)``."""

    def __init__(self, script: list[Any]) -> None:
        self.responder = ScriptedResponder(script)
        self.chat = Obj(completions=Obj(create=self.responder))

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.responder.calls


class FakeAnthropicClient:
    """Mimics ``client.messages.create(**kwargs)``."""

    def __init__(self, script: list[Any]) -> None:
        self.responder = ScriptedResponder(script)
        self.messages = Obj(create=self.responder)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return self.responder.calls


def openai_response(
    text: str,
    *,
    model: str = "gpt-5.6-terra-2026-01-01",
    request_id: str = "req-openai-1",
    fingerprint: str | None = "fp_abc123",
    prompt_tokens: int = 120,
    completion_tokens: int = 1,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    """A mapping-shaped OpenAI chat completion response."""

    return {
        "id": request_id,
        "model": model,
        "system_fingerprint": fingerprint,
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


def openai_response_object(text: str, **kwargs: Any) -> Obj:
    """The same payload as an attribute-style object, as the real SDK returns."""

    payload = openai_response(text, **kwargs)
    choice = payload["choices"][0]
    return Obj(
        id=payload["id"],
        model=payload["model"],
        system_fingerprint=payload["system_fingerprint"],
        choices=[
            Obj(
                message=Obj(role="assistant", content=choice["message"]["content"]),
                finish_reason=choice["finish_reason"],
            )
        ],
        usage=Obj(
            prompt_tokens=payload["usage"]["prompt_tokens"],
            completion_tokens=payload["usage"]["completion_tokens"],
        ),
    )


def anthropic_response(
    text: str,
    *,
    model: str = "claude-sonnet-5-20260101",
    request_id: str = "req-anthropic-1",
    input_tokens: int = 130,
    output_tokens: int = 1,
    stop_reason: str = "end_turn",
) -> dict[str, Any]:
    """A mapping-shaped Anthropic messages response."""

    return {
        "id": request_id,
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


class StatusError(Exception):
    """Stand-in for an SDK error that carries an HTTP status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(Exception):
    """Stand-in for an SDK rate-limit error identified by class name."""


class RecordingSleep:
    """Collects sleep durations instead of pausing the test run."""

    def __init__(self) -> None:
        self.durations: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.durations.append(seconds)


class SequenceJitter:
    """Deterministic replacement for ``random.random``."""

    def __init__(self, values: list[float] | None = None) -> None:
        self.values = list(values) if values else [0.5]
        self.index = 0

    def __call__(self) -> float:
        value = self.values[self.index % len(self.values)]
        self.index += 1
        return value
