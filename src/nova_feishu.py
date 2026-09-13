"""Small read-only Feishu Sheets client used by the Nova importer."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote
from urllib.request import Request, urlopen


FEISHU_BASE_URL = "https://open.feishu.cn"


class ConfigurationError(RuntimeError):
    pass


class FeishuError(RuntimeError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ConfigurationError(f"controlled env file is not readable: {path}")
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigurationError(f"invalid env syntax at line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key.replace("_", "").isalnum() or not key[0].isalpha():
            raise ConfigurationError(f"invalid env key at line {line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def required(config: Mapping[str, str], key: str) -> str:
    value = os.environ.get(key, config.get(key, "")).strip()
    if not value:
        raise ConfigurationError(f"missing controlled configuration: {key}")
    return value


class FeishuClient:
    """Only exposes authentication, sheet listing and range reads."""

    def __init__(self, config: Mapping[str, str]):
        self._base_url = config.get("FEISHU_BASE_URL", FEISHU_BASE_URL).rstrip("/")
        app_id = required(config, "FEISHU_APP_ID")
        app_secret = required(config, "FEISHU_APP_SECRET")
        payload = self._request(
            "POST",
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": app_id, "app_secret": app_secret},
            token=None,
        )
        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise FeishuError("Feishu authentication did not return a tenant token")
        self._token = token

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        token: str | None = "pending",
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token == "pending" and hasattr(self, "_token"):
            headers["Authorization"] = f"Bearer {self._token}"
        encoded = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(4):
            request = Request(f"{self._base_url}{path}", data=encoded, headers=headers, method=method)
            try:
                with urlopen(request, timeout=60) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    status = int(response.status)
            except Exception as exc:
                if attempt == 3:
                    raise FeishuError(f"Feishu request failed: {method} {path}") from exc
                time.sleep(2**attempt)
                continue
            if status < 200 or status >= 300 or payload.get("code") != 0:
                raise FeishuError(
                    f"Feishu request rejected: {method} {path}; "
                    f"http={status}; code={payload.get('code')}; msg={payload.get('msg')}"
                )
            return payload
        raise AssertionError("unreachable")

    def list_sheets(self, spreadsheet_token: str) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"/open-apis/sheets/v3/spreadsheets/{quote(spreadsheet_token, safe='')}/sheets/query",
        )
        sheets = payload.get("data", {}).get("sheets", [])
        return sheets if isinstance(sheets, list) else []

    def read_range(self, spreadsheet_token: str, range_name: str) -> list[list[Any]]:
        encoded_range = quote(range_name, safe="!:$")
        payload = self._request(
            "GET",
            f"/open-apis/sheets/v2/spreadsheets/{quote(spreadsheet_token, safe='')}/values/{encoded_range}",
        )
        values = payload.get("data", {}).get("valueRange", {}).get("values", [])
        return values if isinstance(values, list) else []
