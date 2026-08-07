"""Contract tests for the released nxuskit-cli Ollama compatibility adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from nxuskit import Message
from nxuskit_cli_provider import NxuskitCliOllamaProvider


class RecordingRunner:
    def __init__(
        self,
        *,
        response: dict | None = None,
        returncode: int = 0,
        stderr: str = "",
        timeout: bool = False,
    ) -> None:
        self.response = response or {
            "ok": True,
            "result": {
                "content": "bounded answer",
                "provider": "ollama",
                "model": "gemma4:12b",
                "usage": {
                    "input_tokens": 1052,
                    "output_tokens": 190,
                    "total_tokens": 1242,
                },
                "finish_reason": "stop",
            },
        }
        self.returncode = returncode
        self.stderr = stderr
        self.timeout = timeout
        self.calls: list[dict] = []

    def __call__(
        self,
        argv,
        *,
        check,
        shell,
        timeout,
        text,
        capture_output,
    ):
        request_path = Path(argv[argv.index("--input") + 1])
        output_path = Path(argv[argv.index("--output") + 1])
        self.calls.append(
            {
                "argv": list(argv),
                "check": check,
                "shell": shell,
                "timeout": timeout,
                "text": text,
                "capture_output": capture_output,
                "request": json.loads(request_path.read_text(encoding="utf-8")),
                "request_path": request_path,
                "output_path": output_path,
            }
        )
        if self.timeout:
            raise subprocess.TimeoutExpired(argv, timeout)
        if self.returncode == 0:
            output_path.write_text(json.dumps(self.response), encoding="utf-8")
        return subprocess.CompletedProcess(
            argv,
            self.returncode,
            stdout="",
            stderr=self.stderr,
        )


def provider(runner: RecordingRunner, *, timeout: float = 300.0):
    return NxuskitCliOllamaProvider(
        model="gemma4:12b",
        timeout_seconds=timeout,
        cli_path=Path("/opt/nxuskit/bin/nxuskit-cli"),
        command_runner=runner,
    )


def test_text_call_uses_exact_cli_argv_and_bounded_request() -> None:
    """Catches bypassing nxuskit-cli or dropping the generation controls."""

    runner = RecordingRunner()

    response = provider(runner).chat(
        [Message.system("system prompt"), Message.user("user prompt")],
        temperature=0.1,
        max_tokens=700,
        response_format={"type": "text"},
    )

    assert response.content == "bounded answer"
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["argv"] == [
        "/opt/nxuskit/bin/nxuskit-cli",
        "call",
        "--provider",
        "ollama",
        "--model",
        "gemma4:12b",
        "--input",
        str(call["request_path"]),
        "--format",
        "json",
        "--output",
        str(call["output_path"]),
        "--quiet",
    ]
    assert call["shell"] is False
    assert call["check"] is False
    assert call["timeout"] == 300.0
    assert call["text"] is True
    assert call["capture_output"] is True
    assert call["request"] == {
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
        "temperature": 0.1,
        "max_tokens": 700,
        "thinking_mode": "disabled",
        "response_format": {"type": "text"},
    }
    assert provider(runner).backend_label == "nxuskit-cli / Rust Ollama provider"
    assert not call["request_path"].exists()
    assert not call["output_path"].exists()


def test_structured_call_preserves_exact_schema_and_900_token_ceiling() -> None:
    """Catches schema or output bounds being lost before the Rust provider."""

    runner = RecordingRunner()
    schema = {
        "type": "object",
        "required": ["goal", "candidate_actions"],
        "properties": {
            "goal": {"type": "object"},
            "candidate_actions": {"type": "array"},
        },
    }

    provider(runner).chat(
        [Message.system("extract"), Message.user("answer")],
        temperature=0.1,
        max_tokens=900,
        response_format={"type": "json_schema", "schema": schema},
    )

    request = runner.calls[0]["request"]
    assert request["max_tokens"] == 900
    assert request["thinking_mode"] == "disabled"
    assert request["response_format"] == {
        "type": "json_schema",
        "schema": schema,
    }


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({"result": {"content": ""}}, "returned no response content"),
        ({"result": []}, "returned malformed JSON output"),
        ({"unexpected": "shape"}, "returned no response content"),
    ],
)
def test_malformed_or_empty_cli_output_fails_with_stable_safe_error(
    response: dict, message: str
) -> None:
    """Catches raw CLI payloads or provider errors leaking into UI receipts."""

    runner = RecordingRunner(response=response)

    with pytest.raises(RuntimeError, match=message):
        provider(runner).chat(
            [Message.system("system"), Message.user("prompt")],
            temperature=0.1,
            max_tokens=700,
            response_format={"type": "text"},
        )


def test_nonzero_cli_exit_does_not_surface_stderr() -> None:
    """Catches subprocess stderr, which may contain sensitive local details, leaking."""

    runner = RecordingRunner(
        returncode=1,
        stderr="SECRET_CANARY provider rejected the request",
    )

    with pytest.raises(RuntimeError) as caught:
        provider(runner).chat(
            [Message.system("system"), Message.user("prompt")],
            temperature=0.1,
            max_tokens=700,
            response_format={"type": "text"},
        )

    assert str(caught.value) == "nxuskit-cli Ollama call failed"
    assert "SECRET_CANARY" not in str(caught.value)


def test_cli_timeout_uses_stable_safe_error() -> None:
    """Catches subprocess timeout details leaking paths or prompt data."""

    runner = RecordingRunner(timeout=True)

    with pytest.raises(RuntimeError) as caught:
        provider(runner, timeout=12.5).chat(
            [Message.system("system"), Message.user("prompt")],
            temperature=0.1,
            max_tokens=700,
            response_format={"type": "text"},
        )

    assert str(caught.value) == (
        "nxuskit-cli Ollama call exceeded the configured 12.5 second timeout"
    )
