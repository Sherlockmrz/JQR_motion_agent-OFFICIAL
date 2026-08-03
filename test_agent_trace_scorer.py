#!/usr/bin/env python3
"""agent_trace_scorer 的确定性离线测试。"""

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agent_trace_scorer import (
    main,
    parse_log_files,
    render_markdown_report,
    score_trace,
    select_recent_traces,
)


def trace_line(trace, time_text, label, message):
    return f"[trace={trace}][{time_text}][{label}] {message}"


class AgentTraceScorerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_log(self, lines, name="agent_20260725_100000.log"):
        path = self.log_dir / name
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def parse_one(self, lines):
        path = self.write_log(lines)
        records = parse_log_files([path])
        self.assertEqual(len(records), 1)
        return records[0]

    def test_non_vln_first_attempt_success_scores_100(self):
        trace = "20260725-100001"
        record = self.parse_one([
            trace_line(trace, "10:00:01.000", "机器状态灯", "上层发来任务：机器状态灯（set_robot_light_state），参数={}"),
            trace_line(trace, "10:00:01.010", "机器状态灯", "Motion Agent 开始执行，设置机器状态灯：{}"),
            trace_line(trace, "10:00:01.020", "机器状态灯", "机器状态灯执行结束，返回 success=true（返回字段 type/success）"),
            trace_line(trace, "10:00:01.030", "机器状态灯", "准备回复上层：任务成功 success=true，本次耗时 0.03 秒"),
            trace_line(trace, "10:00:01.040", "机器状态灯", "结果已回复给客户端 127.0.0.1:1"),
        ])

        score = score_trace(record)
        self.assertEqual(score.status, "SUCCESS")
        self.assertEqual(score.attempts, 1)
        self.assertEqual(score.total_score, 100)

    def test_vln_five_round_success_scores_100(self):
        trace = "20260725-100002"
        lines = [
            trace_line(trace, "10:00:02.000", "找物", "上层发来任务：找水杯，原始指令=\"\""),
            trace_line(trace, "10:00:02.010", "找物", "Motion Agent 开始执行，转换成 VLN 导航请求：go_to_object/object_id=水杯"),
        ]
        lines.extend(
            trace_line(trace, f"10:00:02.{20 + index:03d}", "找物", f"VLN推理：动作{index}")
            for index in range(5)
        )
        lines.extend([
            trace_line(trace, "10:00:03.000", "找物", "VLN 导航执行结束，返回 success=true（返回字段 type/success）"),
            trace_line(trace, "10:00:03.010", "找物", "准备回复上层：任务成功 success=true，本次耗时 1.01 秒"),
            trace_line(trace, "10:00:03.020", "找物", "结果已回复给客户端 127.0.0.1:1"),
        ])

        score = score_trace(self.parse_one(lines))
        self.assertEqual(score.action_rounds, 5)
        self.assertEqual(score.efficiency_score, 20)
        self.assertEqual(score.total_score, 100)

    def test_failed_cancelled_and_invalid_states(self):
        failed = self.parse_one([
            trace_line("20260725-100003", "10:00:03.000", "找物", "上层发来任务：找水杯，原始指令=\"\""),
            trace_line("20260725-100003", "10:00:03.010", "找物", "VLN 导航执行结束，返回 success=false（返回字段 type/success）"),
            trace_line("20260725-100003", "10:00:03.020", "找物", "结果已回复给客户端 127.0.0.1:1"),
        ])
        failed_score = score_trace(failed)
        self.assertEqual(failed_score.status, "FAILED")
        self.assertEqual(failed_score.result_score, 0)
        self.assertEqual(failed_score.efficiency_score, 0)

        cancelled = self.parse_one([
            trace_line("20260725-100004", "10:00:04.000", "找物", "上层发来任务：找水杯，原始指令=\"\""),
            trace_line("20260725-100004", "10:00:04.010", "找物", "Motion Agent 开始执行，转换成 VLN 导航请求：go_to_object/object_id=水杯"),
            trace_line("20260725-100004", "10:00:04.020", "找物", "[搜索任务] go_to_object 已被 stop_move 中断"),
            trace_line("20260725-100004", "10:00:04.030", "找物", "结果已回复给客户端 127.0.0.1:1"),
        ])
        cancelled_score = score_trace(cancelled)
        self.assertEqual(cancelled_score.status, "CANCELLED")
        self.assertIsNone(cancelled_score.total_score)

        invalid = self.parse_one([
            trace_line("20260725-100005", "10:00:05.000", "找物", "上层发来任务：找水杯，原始指令=\"\""),
            trace_line("20260725-100005", "10:00:05.010", "stop_move", "上层发来任务：stop_move（stop_move），参数={}"),
        ])
        invalid_score = score_trace(invalid)
        self.assertEqual(invalid_score.status, "INVALID")
        self.assertIsNone(invalid_score.total_score)

    def test_command_without_final_and_success_without_final(self):
        command_only = self.parse_one([
            trace_line("20260725-100006", "10:00:06.000", "找物", "上层发来任务：找水杯，原始指令=\"\""),
            trace_line("20260725-100006", "10:00:06.010", "找物", "Motion Agent 开始执行，转换成 VLN 导航请求：go_to_object/object_id=水杯"),
            trace_line("20260725-100006", "10:00:06.020", "找物", "VLN推理：向前探索"),
        ])
        command_score = score_trace(command_only)
        self.assertEqual(command_score.status, "INCOMPLETE")
        self.assertEqual(command_score.result_score, 35)
        self.assertEqual(command_score.evidence_score, 6)

        completion = self.parse_one([
            trace_line("20260725-100007", "10:00:07.000", "头部控制", "上层发来任务：头部控制（set_head_motor_control），参数={}"),
            trace_line("20260725-100007", "10:00:07.010", "头部控制", "头部控制执行成功"),
            trace_line("20260725-100007", "10:00:07.020", "头部控制", "结果已回复给客户端 127.0.0.1:1"),
        ])
        completion_score = score_trace(completion)
        self.assertEqual(completion_score.status, "SUCCESS_WITHOUT_FINAL")
        self.assertEqual(completion_score.result_score, 45)

    def test_scoring_window_ignores_lines_after_first_reply(self):
        trace = "20260725-100008"
        lines = [
            trace_line(trace, "10:00:08.000", "找物", "上层发来任务：找水杯，原始指令=\"\""),
            trace_line(trace, "10:00:08.010", "找物", "Motion Agent 开始执行，转换成 VLN 导航请求：go_to_object/object_id=水杯"),
            trace_line(trace, "10:00:08.020", "找物", "VLN推理：向前探索"),
            trace_line(trace, "10:00:08.030", "找物", "VLN 导航执行结束，返回 success=true（返回字段 type/success）"),
            trace_line(trace, "10:00:08.040", "找物", "结果已回复给客户端 127.0.0.1:1"),
        ]
        lines.extend(
            trace_line(trace, f"10:00:09.{index:03d}", "找物", f"VLN推理：后台动作{index}")
            for index in range(20)
        )

        score = score_trace(self.parse_one(lines))
        self.assertEqual(score.action_rounds, 1)
        self.assertEqual(score.total_score, 100)

    def test_false_positive_zeros_result_and_efficiency(self):
        trace = "20260725-100009"
        record = self.parse_one([
            trace_line(trace, "10:00:09.000", "stop_move", "上层发来任务：stop_move（stop_move），参数={}"),
            trace_line(trace, "10:00:09.010", "stop_move", "stop_move执行结束，返回 success=true（返回字段 type/success）"),
            trace_line(trace, "10:00:09.020", "stop_move", "结果已回复给客户端 127.0.0.1:1"),
        ])

        score = score_trace(record, false_positive=True)
        self.assertEqual(score.status, "FALSE_POSITIVE")
        self.assertEqual(score.result_score, 0)
        self.assertEqual(score.efficiency_score, 0)
        self.assertEqual(score.total_score, 20)

    def test_recent_ten_selection_and_report_audit_fields(self):
        lines = []
        for index in range(12):
            trace = f"20260725-10{index:04d}"
            lines.append(
                trace_line(
                    trace,
                    f"10:00:{index:02d}.000",
                    "状态灯查询",
                    "上层发来任务：状态灯查询（get_status_light_state），参数={}",
                )
            )
        path = self.write_log(lines)
        candidates = parse_log_files([path])
        selected = select_recent_traces(candidates, 10)

        self.assertEqual(len(selected), 10)
        self.assertEqual(selected[0].trace_id, "20260725-100002")
        self.assertEqual(selected[-1].trace_id, "20260725-100011")

        scores = [score_trace(record) for record in selected]
        report = render_markdown_report(selected, scores, [path], len(candidates), 10)
        self.assertIn("发现含“上层发来任务”的 Trace：12 条", report)
        self.assertIn("编号 1 为所选范围最早", report)
        self.assertIn("完整 Trace 日志", report)
        self.assertIn("CANCELLED", report)

    def test_interactive_count_and_save_choice(self):
        trace = "20260725-100012"
        self.write_log([
            trace_line(trace, "10:00:12.000", "stop_move", "上层发来任务：stop_move（stop_move），参数={}"),
            trace_line(trace, "10:00:12.010", "stop_move", "stop_move执行结束，返回 success=true（返回字段 type/success）"),
            trace_line(trace, "10:00:12.020", "stop_move", "结果已回复给客户端 127.0.0.1:1"),
        ])
        output_dir = self.log_dir / "reports"

        with patch("builtins.input", side_effect=["1", "", "n"]), patch(
            "sys.stdout", new_callable=StringIO
        ) as output:
            result = main([
                "--log-dir", str(self.log_dir),
                "--output-dir", str(output_dir),
            ])

        self.assertEqual(result, 0)
        self.assertIn("已选择不保存", output.getvalue())
        self.assertFalse(output_dir.exists())

        with patch("builtins.input", side_effect=["1", "", "y"]), patch(
            "sys.stdout", new_callable=StringIO
        ):
            result = main([
                "--log-dir", str(self.log_dir),
                "--output-dir", str(output_dir),
            ])

        self.assertEqual(result, 0)
        self.assertEqual(len(list(output_dir.glob("agent_trace_score_*.md"))), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
