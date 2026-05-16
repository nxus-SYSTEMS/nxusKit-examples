"""Tiny template renderer for public example configs."""

from __future__ import annotations

import re
from typing import Any


_VAR_RE = re.compile(r"{{\s*([a-zA-Z0-9_.-]+)\s*}}")


def render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value: Any = variables
        for part in match.group(1).split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return match.group(0)
        return str(value)

    return _VAR_RE.sub(replace, template)
