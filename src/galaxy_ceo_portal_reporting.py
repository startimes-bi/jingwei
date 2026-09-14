"""Feishu reporting cards and small, structured quality summaries for timers."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from src.galaxy_ceo_portal_raw_data import BJ_TZ, FeishuClient, FeishuError


LOG = logging.getLogger("galaxy_ceo_portal_reporting")
DEFAULT_CHAT_NAME = "BI Plus Reporting"


def quality_check(name: str, status: str, detail: str) -> dict[str, str]:
    """Create a serializable quality-check item for timer results."""

    if status not in {"passed", "warning", "failed", "skipped"}:
        raise ValueError(f"unsupported quality status: {status!r}")
    return {"name": name, "status": status, "detail": detail}


def quality_report(checks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize checks without hiding warnings or skipped validations."""

    normalized = [
        {
            "name": str(item.get("name") or "未命名检查"),
            "status": str(item.get("status") or "warning"),
            "detail": str(item.get("detail") or ""),
        }
        for item in checks
    ]
    counts = {status: sum(item["status"] == status for item in normalized) for status in (
        "passed",
        "warning",
        "failed",
        "skipped",
    )}
    overall = "failed" if counts["failed"] else "warning" if counts["warning"] else "passed"
    return {"status": overall, **counts, "checks": normalized}


def duplicate_count(keys: Sequence[Any]) -> int:
    """Return the number of repeated keys after the first occurrence."""

    seen: set[Any] = set()
    duplicates = 0
    for key in keys:
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def date_coverage(
    actual_dates: Sequence[date] | set[date],
    start: date,
    end: date,
) -> dict[str, Any]:
    """Compare the dates present in a target against its required inclusive window."""

    expected = set()
    current = start
    while current <= end:
        expected.add(current)
        current += timedelta(days=1)
    actual = set(actual_dates)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    return {
        "status": "passed" if not missing and not extra else "failed",
        "expected_days": len(expected),
        "actual_days": len(actual),
        "missing_dates": [item.isoformat() for item in missing[:20]],
        "extra_dates": [item.isoformat() for item in extra[:20]],
        "missing_count": len(missing),
        "extra_count": len(extra),
    }


def spreadsheet_url(config: Mapping[str, str], spreadsheet_token: str) -> str:
    """Build a user-facing spreadsheet URL from non-secret runtime config."""

    base = str(config.get("FEISHU_SPREADSHEET_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    if "{token}" in base:
        return base.replace("{token}", quote(spreadsheet_token, safe=""))
    return f"{base}/{quote(spreadsheet_token, safe='')}"


def _short_text(value: Any, limit: int = 900) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "未知"
    total = max(0, int(round(float(seconds))))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分 {remainder} 秒"
    if minutes:
        return f"{minutes} 分 {remainder} 秒"
    return f"{remainder} 秒"


def _format_attempts(attempts: int | None, max_attempts: int | None) -> str:
    if attempts is None:
        return "未知"
    return f"{attempts}/{max_attempts}" if max_attempts is not None else str(attempts)


def _quality_lines(report: Mapping[str, Any] | None) -> list[str]:
    if not report:
        return ["- ⚪ 本次未生成结构化质检摘要"]
    passed = int(report.get("passed", 0))
    warnings = int(report.get("warning", 0))
    failed = int(report.get("failed", 0))
    skipped = int(report.get("skipped", 0))
    lines = [f"**质检摘要：** ✅ {passed} 项｜⚠️ {warnings} 项｜❌ {failed} 项"]
    if skipped:
        lines[0] += f"｜⚪ {skipped} 项未执行"
    checks = report.get("checks", [])
    details = [item for item in checks if item.get("status") in {"warning", "failed", "skipped"}]
    if not details and passed:
        names = {str(item.get("name")) for item in checks if item.get("status") == "passed"}
        if "日期覆盖与业务键不重复" in names:
            lines.append("- ✅ 日期覆盖完整、业务键无重复；其他已执行的轻量质检均通过")
        else:
            lines.append("- ✅ 所有已执行的轻量质检均通过")
        return lines
    for item in details[:8]:
        marker = {"warning": "⚠️", "failed": "❌", "skipped": "⚪"}.get(
            item.get("status"), "⚠️"
        )
        detail = f"：{_short_text(item.get('detail'))}" if item.get("detail") else ""
        lines.append(f"- {marker} {item.get('name', '未命名检查')}{detail}")
    if any(
        item.get("name") == "日期覆盖与业务键不重复" and item.get("status") == "passed"
        for item in checks
    ):
        lines.append("- ✅ 日期覆盖完整、业务键无重复")
    if len(details) > 8:
        lines.append(f"- …另有 {len(details) - 8} 项提醒未在卡片展开")
    return lines


def build_timer_card(
    pipeline_name: str,
    result: Mapping[str, Any] | None,
    attempts: int | None,
    max_attempts: int | None,
    duration_seconds: float | int | None,
    error: BaseException | str | None = None,
) -> dict[str, Any]:
    """Build a compact card; details only expand when a check needs attention."""

    result = dict(result or {})
    ready = bool(result.get("ready")) and error is None
    quality = result.get("quality")
    quality_status = str(quality.get("status")) if isinstance(quality, Mapping) else "passed"
    failed = not ready or quality_status == "failed"
    has_warning = quality_status == "warning"
    template = "red" if failed else "yellow" if has_warning else "green"
    status_text = "❌ 失败" if failed else "✅ 成功（有提醒）" if has_warning else "✅ 成功"

    document = result.get("document") if isinstance(result.get("document"), Mapping) else {}
    document_title = str(document.get("title") or result.get("title") or "未生成")
    document_status = str(document.get("status") or ("已更新" if ready else "未更新"))
    document_link = str(document.get("url") or "")
    document_text = f"[{document_title}]({document_link})" if document_link else document_title

    target_start = result.get("target_start_date")
    target_end = result.get("target_end_date")
    if target_start and target_end:
        data_window = f"{target_start} ~ {target_end}"
    else:
        data_window = "未形成数据窗口"

    total_attempts = max_attempts
    actions = []
    if result.get("source_rows_read") is not None:
        actions.append(f"读取数据库 {result['source_rows_read']} 行")
    if result.get("rows_to_append") is not None:
        actions.append(f"新增 {result['rows_to_append']} 行")
    if result.get("rows_to_delete") is not None:
        actions.append(f"删除 {result['rows_to_delete']} 行")
    if result.get("verification"):
        actions.append("写入后回读校验通过")
    if not actions:
        actions.append("未执行数据写入")

    lines = [
        f"**运行状态：** {status_text}",
        f"**完成时间：** {datetime.now(BJ_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"**尝试次数：** {_format_attempts(attempts, total_attempts)}",
        f"**运行耗时：** {_format_duration(duration_seconds)}",
        "",
        "---",
        "",
        f"**产出文档：** {document_text}",
        f"**文档状态：** {document_status}",
        f"**数据窗口：** {data_window}",
    ]
    if result.get("source_latest_date"):
        lines.append(f"**数据库共同最新日期：** {result['source_latest_date']}")
    if result.get("feishu_max_date"):
        lines.append(f"**飞书表运行前最新日期：** {result['feishu_max_date']}")
    if result.get("expected_yesterday"):
        lines.append(f"**期望日期：** {result['expected_yesterday']}")
    lines.extend(["", "**本次完成：**", *[f"- {action}" for action in actions]])
    lines.extend(["", *_quality_lines(quality)])

    error_text = _short_text(error or result.get("error"))
    if error_text:
        lines.extend(["", f"**错误：** {error_text}"])
    if result.get("dry_run"):
        lines.extend(["", "> dry-run：只读取和校验，未写入飞书。"])

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": f"银河CEO门户｜{pipeline_name}数据日报"},
        },
        "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}}],
    }


def find_reporting_chat(client: FeishuClient, chat_name: str) -> str:
    """Find an exact group name, following Feishu pagination when needed."""

    page_token = ""
    while True:
        path = "/open-apis/im/v1/chats?page_size=100"
        if page_token:
            path += f"&page_token={quote(page_token, safe='')}"
        payload = client.request("GET", path)
        data = payload.get("data", {})
        for item in data.get("items", []) or []:
            if str(item.get("name") or "") == chat_name:
                chat_id = str(item.get("chat_id") or "")
                if chat_id:
                    return chat_id
        if not data.get("has_more"):
            break
        next_token = str(data.get("page_token") or "")
        if not next_token or next_token == page_token:
            break
        page_token = next_token
    raise FeishuError(f"reporting chat was not found: {chat_name!r}")


def send_timer_report(
    config: Mapping[str, str],
    pipeline_name: str,
    result: Mapping[str, Any] | None,
    attempts: int | None,
    max_attempts: int | None,
    duration_seconds: float | int | None,
    error: BaseException | str | None = None,
) -> dict[str, str]:
    """Send one timer result card and return safe message metadata."""

    chat_name = str(config.get("FEISHU_REPORTING_CHAT_NAME") or DEFAULT_CHAT_NAME).strip()
    if not chat_name:
        raise FeishuError("FEISHU_REPORTING_CHAT_NAME is empty")
    client = FeishuClient(config)
    chat_id = find_reporting_chat(client, chat_name)
    card = build_timer_card(
        pipeline_name,
        result,
        attempts,
        max_attempts,
        duration_seconds,
        error,
    )
    payload = client.request(
        "POST",
        "/open-apis/im/v1/messages?receive_id_type=chat_id",
        json={
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
    )
    message_id = str(payload.get("data", {}).get("message_id") or "")
    return {"status": "sent", "chat": chat_name, "message_id": message_id}


def safe_send_timer_report(
    config: Mapping[str, str],
    pipeline_name: str,
    result: Mapping[str, Any] | None,
    attempts: int | None,
    max_attempts: int | None,
    duration_seconds: float | int | None,
    error: BaseException | str | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, str]:
    """Never turn a notification outage into a data-pipeline outage."""

    logger = logger or LOG
    try:
        return send_timer_report(
            config,
            pipeline_name,
            result,
            attempts,
            max_attempts,
            duration_seconds,
            error,
        )
    except Exception as exc:  # noqa: BLE001 - notification is deliberately best effort.
        logger.warning("could not send Feishu timer report: %s", exc)
        return {"status": "failed", "error": _short_text(exc, 500)}
