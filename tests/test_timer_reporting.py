import unittest
from datetime import date
from unittest.mock import patch

from src.galaxy_ceo_portal_reporting import (
    build_timer_card,
    date_coverage,
    duplicate_count,
    quality_check,
    quality_report,
    send_timer_report,
    spreadsheet_url,
)


class TimerReportingTests(unittest.TestCase):
    def test_date_coverage_reports_missing_and_extra_dates(self):
        report = date_coverage({date(2026, 9, 11), date(2026, 9, 13)}, date(2026, 9, 11), date(2026, 9, 12))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["missing_dates"], ["2026-09-12"])
        self.assertEqual(report["extra_dates"], ["2026-09-13"])

    def test_duplicate_count_allows_repeated_dates_but_counts_repeated_business_keys(self):
        self.assertEqual(duplicate_count(["2026-09-11", "2026-09-11"]), 1)
        self.assertEqual(duplicate_count([("2026-09-11", "DTT", 7, "总计"), ("2026-09-11", "DTT", 7, "总计")]), 1)

    def test_quality_report_and_card_keep_document_and_quality_details(self):
        quality = quality_report(
            [
                quality_check("日期覆盖与业务键不重复", "passed", "无缺失日期"),
                quality_check("映射", "warning", "暂缺 1 个公司名称"),
            ]
        )
        card = build_timer_card(
            "节目包",
            {
                "ready": True,
                "document": {"title": "日报", "url": "https://example.test/sheet", "status": "已更新"},
                "target_start_date": "2026-09-01",
                "target_end_date": "2026-09-13",
                "source_rows_read": 12,
                "rows_to_append": 12,
                "rows_to_delete": 0,
                "quality": quality,
                "verification": {"status": "passed"},
            },
            1,
            4,
            3,
        )
        content = card["elements"][0]["text"]["content"]
        self.assertEqual(card["header"]["template"], "yellow")
        self.assertIn("[日报](https://example.test/sheet)", content)
        self.assertIn("日期覆盖完整、业务键无重复", content)
        self.assertIn("暂缺 1 个公司名称", content)

    def test_spreadsheet_url_uses_configured_tenant_base(self):
        self.assertEqual(
            spreadsheet_url(
                {"FEISHU_SPREADSHEET_BASE_URL": "https://tenant.feishu.cn/sheets"},
                "sheet-token",
            ),
            "https://tenant.feishu.cn/sheets/sheet-token",
        )

    def test_send_timer_report_posts_an_interactive_card_to_exact_chat(self):
        class FakeClient:
            requests = []

            def __init__(self, _config):
                pass

            def request(self, method, path, **kwargs):
                self.requests.append((method, path, kwargs))
                if method == "GET":
                    return {"data": {"items": [{"name": "BI Plus Reporting", "chat_id": "chat-1"}]}}
                return {"data": {"message_id": "message-1"}}

        with patch("src.galaxy_ceo_portal_reporting.FeishuClient", FakeClient):
            result = send_timer_report(
                {"FEISHU_REPORTING_CHAT_NAME": "BI Plus Reporting"},
                "节目包",
                {"ready": False},
                1,
                1,
                1,
                error="database unavailable",
            )

        self.assertEqual(result["message_id"], "message-1")
        self.assertEqual(FakeClient.requests[-1][0], "POST")
        self.assertIn("receive_id_type=chat_id", FakeClient.requests[-1][1])
        self.assertEqual(FakeClient.requests[-1][2]["json"]["receive_id"], "chat-1")
        self.assertEqual(FakeClient.requests[-1][2]["json"]["msg_type"], "interactive")


if __name__ == "__main__":
    unittest.main()
