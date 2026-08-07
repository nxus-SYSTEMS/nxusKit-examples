"""Released nxuskit-cli compatibility provider for v1.0.5 local Ollama calls."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def resolve_nxuskit_cli() -> Path:
    """Resolve a released nxuskit-cli without modifying the SDK installation."""

    candidates: list[Path] = []
    sdk_dir = os.environ.get("NXUSKIT_SDK_DIR")
    if sdk_dir:
        candidates.append(Path(sdk_dir).expanduser() / "bin" / "nxuskit-cli")
    candidates.append(
        Path.home() / ".nxuskit" / "sdk" / "current" / "bin" / "nxuskit-cli"
    )
    on_path = shutil.which("nxuskit-cli")
    if on_path:
        candidates.append(Path(on_path))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise RuntimeError("released nxuskit-cli was not found")


def _message_dict(message: Any) -> dict[str, str]:
    role = getattr(message, "role", None)
    if hasattr(role, "value"):
        role = role.value
    content = getattr(message, "content", None)
    if role not in {"system", "user", "assistant"} or not isinstance(content, str):
        raise ValueError("nxuskit-cli messages must contain a supported role and text")
    return {"role": role, "content": content}


def _response_content(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        raise RuntimeError("nxuskit-cli Ollama call returned malformed JSON output")
    result = payload.get("result")
    if result is not None and not isinstance(result, Mapping):
        raise RuntimeError("nxuskit-cli Ollama call returned malformed JSON output")
    candidates = [
        result.get("content") if isinstance(result, Mapping) else None,
        payload.get("content"),
    ]
    message = payload.get("message")
    if message is not None and not isinstance(message, Mapping):
        raise RuntimeError("nxuskit-cli Ollama call returned malformed JSON output")
    if isinstance(message, Mapping):
        candidates.append(message.get("content"))
    for content in candidates:
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise RuntimeError("nxuskit-cli Ollama call returned no response content")


class NxuskitCliOllamaProvider:
    """Provider-like adapter that keeps local Ollama calls inside nxusKit v1.0.5."""

    backend_label = "nxuskit-cli / Rust Ollama provider"

    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: float,
        cli_path: Path | None = None,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        if not isinstance(model, str) or not model or "\n" in model or "\r" in model:
            raise ValueError("Ollama model must be non-empty single-line text")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0
        ):
            raise ValueError("Ollama timeout must be a finite positive number")
        self.model = model
        self.timeout_seconds = float(timeout_seconds)
        self.cli_path = (cli_path or resolve_nxuskit_cli()).expanduser()
        self._command_runner = command_runner

    def chat(
        self,
        messages: Sequence[Any],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: Mapping[str, Any] | None = None,
        **_unsupported: Any,
    ) -> SimpleNamespace:
        request: dict[str, Any] = {
            "messages": [_message_dict(message) for message in messages],
            "thinking_mode": "disabled",
            "response_format": dict(response_format or {"type": "text"}),
        }
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        with tempfile.TemporaryDirectory(prefix="nxuskit-csg-") as temporary:
            directory = Path(temporary)
            request_path = directory / "request.json"
            output_path = directory / "response.json"
            request_path.write_text(
                json.dumps(request, ensure_ascii=False),
                encoding="utf-8",
            )
            argv = [
                str(self.cli_path),
                "call",
                "--provider",
                "ollama",
                "--model",
                self.model,
                "--input",
                str(request_path),
                "--format",
                "json",
                "--output",
                str(output_path),
                "--quiet",
            ]
            try:
                completed = self._command_runner(
                    argv,
                    check=False,
                    shell=False,
                    timeout=self.timeout_seconds,
                    text=True,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired:
                timeout = f"{self.timeout_seconds:g}"
                raise RuntimeError(
                    "nxuskit-cli Ollama call exceeded the configured "
                    f"{timeout} second timeout"
                ) from None
            if completed.returncode != 0:
                raise RuntimeError("nxuskit-cli Ollama call failed")
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
                raise RuntimeError(
                    "nxuskit-cli Ollama call returned malformed JSON output"
                ) from None
            return SimpleNamespace(content=_response_content(payload))
