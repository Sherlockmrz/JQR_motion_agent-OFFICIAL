#!/usr/bin/env python3
"""按需评分最近的 Motion Agent 任务 Trace，并生成可审计 Markdown 报告。"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional, Sequence


TRACE_LINE_RE = re.compile(
    r"^\[trace=([^\]]+)\]\[(\d{2}:\d{2}:\d{2}\.\d{3})\]"
    r"\[([^\]]+)\]\s?(.*)$"
)
TRACE_TIME_RE = re.compile(
    r"^(\d{8})-(\d{6})(?:-(\d{3,6}))?(?:-\d+)?$"
)
LOG_FILE_RE = re.compile(r"agent_(\d{8})_(\d{6})\.log$")
TASK_START_TEXT = "上层发来任务"
REPLY_MARKERS = (
    "结果已回复给客户端",
    "客户端已断开，最终结果无法发送",
)
VLN_TASK_TYPES = {"go_to_object", "go_find_person", "follow_person"}
CONTROL_TASK_TYPES = {"stop_move", "emergency_stop"}

TERMINAL_REASON_RE = re.compile(
    r"超时|任务执行异常|处理消息失败|无法连接|连接异常|连接失败|任务执行失败"
)
EXECUTION_REQUEST_RE = re.compile(
    r"Motion Agent 开始执行|控制指令已发布|已发送控制命令|下发.*(?:命令|控制)"
)
STRONG_COMPLETION_RE = re.compile(
    r"(?:任务|控制|动作|导航|识别|查找|设置|读取|清除|唤醒)"
    r".{0,40}(?:成功|完成)|(?:执行成功|成功完成|已经完成|已完成)"
)
COMPLETION_EXCLUSIONS = (
    "开始执行",
    "准备回复",
    "继续执行",
    "初始化成功",
    "启动成功",
    "连接成功",
    "服务成功",
)
RETRY_RE = re.compile(
    r"失败.{0,30}(?:重试|重新尝试|再次尝试)|"
    r"(?:重试|重新尝试|再次尝试).{0,30}失败|第\s*\d+\s*次重试",
    re.IGNORECASE,
)
RETRY_EXCLUSIONS = (
    "灯",
    "药箱",
    "状态回读",
    "轮询",
    "路点",
    "头颈",
    "搜索姿态",
    "电机",
    "进度",
    "后台恢复",
    "重新发送",
)


@dataclass
class TraceLine:
    raw: str
    message: str
    label: str
    time_text: str
    line_number: int


@dataclass
class TraceRecord:
    trace_id: str
    source: Path
    lines: list[TraceLine] = field(default_factory=list)
    source_mtime: float = 0.0

    @property
    def start_indices(self) -> list[int]:
        return [
            index
            for index, line in enumerate(self.lines)
            if TASK_START_TEXT in line.message
        ]

    @property
    def started_at(self) -> datetime:
        match = TRACE_TIME_RE.match(self.trace_id)
        if match:
            base = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
            fraction = match.group(3) or "0"
            microseconds = int(fraction.ljust(6, "0")[:6])
            return base.replace(microsecond=microseconds)

        file_match = LOG_FILE_RE.search(self.source.name)
        if file_match:
            base = datetime.strptime(
                file_match.group(1) + file_match.group(2), "%Y%m%d%H%M%S"
            )
            if self.start_indices:
                line_time = datetime.strptime(
                    self.lines[self.start_indices[0]].time_text, "%H:%M:%S.%f"
                ).time()
                candidate = base.replace(
                    hour=line_time.hour,
                    minute=line_time.minute,
                    second=line_time.second,
                    microsecond=line_time.microsecond,
                )
                if candidate < base - timedelta(hours=12):
                    candidate += timedelta(days=1)
                return candidate
            return base

        return datetime.fromtimestamp(self.source_mtime)

    def scoring_window(self) -> tuple[int, int]:
        starts = self.start_indices
        start = starts[0] if starts else 0
        end = len(self.lines) - 1
        for index in range(start, len(self.lines)):
            if any(marker in self.lines[index].message for marker in REPLY_MARKERS):
                end = index
                break
        return start, end


@dataclass
class ScoreResult:
    status: str
    result_score: Optional[int]
    efficiency_score: Optional[int]
    evidence_score: Optional[int]
    closure_score: Optional[int]
    total_score: Optional[int]
    task_type: str
    is_vln: bool
    action_rounds: Optional[int]
    attempts: Optional[int]
    result_reason: str
    efficiency_reason: str
    evidence_reason: str
    closure_reason: str
    false_positive: bool = False


def discover_log_files(log_dir: Path) -> list[Path]:
    return sorted(
        (path for path in log_dir.glob("agent_*.log") if path.is_file()),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )


def parse_log_files(files: Iterable[Path]) -> list[TraceRecord]:
    records: dict[tuple[str, str], TraceRecord] = {}

    for source in files:
        source = source.resolve()
        last_key: Optional[tuple[str, str]] = None
        with source.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                raw = raw_line.rstrip("\r\n")
                match = TRACE_LINE_RE.match(raw)
                if match:
                    trace_id, time_text, label, message = match.groups()
                    if trace_id == "-":
                        last_key = None
                        continue
                    key = (str(source), trace_id)
                    record = records.setdefault(
                        key,
                        TraceRecord(
                            trace_id=trace_id,
                            source=source,
                            source_mtime=source.stat().st_mtime,
                        ),
                    )
                    record.lines.append(
                        TraceLine(raw, message, label, time_text, line_number)
                    )
                    last_key = key
                elif last_key is not None and raw:
                    records[last_key].lines.append(
                        TraceLine(raw, raw, "续行", "", line_number)
                    )

    return [record for record in records.values() if record.start_indices]


def select_recent_traces(
    records: Sequence[TraceRecord], limit: int = 10
) -> list[TraceRecord]:
    ordered = sorted(
        records,
        key=lambda record: (
            record.started_at,
            record.source_mtime,
            record.start_indices[0],
            record.trace_id,
        ),
    )
    return ordered[-limit:]


def infer_task_type(messages: Sequence[str], first_line: TraceLine) -> str:
    start_message = first_line.message
    typed = re.search(r"（([A-Za-z0-9_]+)）", start_message)
    if typed:
        return typed.group(1)

    for message in messages:
        vln = re.search(
            r"转换成 VLN 导航请求：([A-Za-z0-9_]+)/", message
        )
        if vln:
            mapped = {
                "go_to_person": "go_find_person",
                "go_to_object": "go_to_object",
                "follow_person": "follow_person",
            }
            return mapped.get(vln.group(1), vln.group(1))

    if any("本地相机静态找人" in message for message in messages):
        return "find_person"
    if any("开始执行找物任务" in message for message in messages):
        return "find_object"
    return first_line.label or "unknown"


def _explicit_final(messages: Sequence[str]) -> tuple[Optional[bool], bool]:
    for message in messages:
        match = re.search(r"执行结束，返回 success=(true|false)", message)
        if match:
            return match.group(1) == "true", True
    for message in messages:
        match = re.search(r"准备回复上层：.*success=(true|false)", message)
        if match:
            return match.group(1) == "true", False
    return None, False


def _has_independent_completion(messages: Sequence[str]) -> bool:
    for message in messages:
        if any(exclusion in message for exclusion in COMPLETION_EXCLUSIONS):
            continue
        if STRONG_COMPLETION_RE.search(message):
            return True
    return False


def _count_retries(messages: Sequence[str]) -> int:
    retry_messages = {
        message
        for message in messages
        if RETRY_RE.search(message)
        and not any(exclusion in message for exclusion in RETRY_EXCLUSIONS)
    }
    return len(retry_messages)


def _efficiency_for_vln(rounds: int) -> int:
    if rounds <= 5:
        return 20
    if rounds <= 10:
        return 15
    if rounds <= 15:
        return 10
    return 5


def _efficiency_for_attempts(attempts: int) -> int:
    if attempts <= 1:
        return 20
    if attempts == 2:
        return 15
    if attempts == 3:
        return 10
    return 5


def score_trace(record: TraceRecord, false_positive: bool = False) -> ScoreResult:
    starts = record.start_indices
    first_start = record.lines[starts[0]]
    window_start, window_end = record.scoring_window()
    window_lines = record.lines[window_start : window_end + 1]
    messages = [line.message for line in window_lines]
    task_type = infer_task_type(messages, first_start)
    is_vln = task_type in VLN_TASK_TYPES or any(
        "VLN 导航请求" in message for message in messages
    )

    if len(starts) > 1:
        return ScoreResult(
            "INVALID", None, None, None, None, None, task_type, is_vln,
            None, None,
            f"同一 Trace 出现 {len(starts)} 条“上层发来任务”，按规则作废。",
            "INVALID 不评分。", "INVALID 不评分。", "INVALID 不评分。",
        )

    interrupted = any(
        "被 stop_move 中断" in message or "任务已被 stop_move 中断" in message
        for message in messages
    )
    if interrupted and task_type not in CONTROL_TASK_TYPES:
        return ScoreResult(
            "CANCELLED", None, None, None, None, None, task_type, is_vln,
            None, None,
            "普通任务被 stop_move 中断，标记 CANCELLED。",
            "CANCELLED 不评分。", "CANCELLED 不评分。", "CANCELLED 不评分。",
        )

    final_success, business_final = _explicit_final(messages)
    vln_rounds = sum("VLN推理：" in message for message in messages)
    independent_completion = _has_independent_completion(messages)
    terminal_reason = any(TERMINAL_REASON_RE.search(message) for message in messages)
    reply_logged = any(
        any(marker in message for marker in REPLY_MARKERS) for message in messages
    )
    execution_requested = any(EXECUTION_REQUEST_RE.search(message) for message in messages)

    if final_success is True:
        status = "SUCCESS"
        result_score = 60
        result_reason = "检测到明确的 success=true 最终结果。"
    elif final_success is False:
        status = "FAILED"
        result_score = 0
        result_reason = "检测到明确的 success=false 最终结果。"
    elif independent_completion:
        status = "SUCCESS_WITHOUT_FINAL"
        result_score = 45
        result_reason = "没有标准 final，但存在独立、明确的任务完成证据。"
    elif vln_rounds:
        status = "INCOMPLETE"
        result_score = 35
        result_reason = (
            f"没有 final，仅检测到 {vln_rounds} 条 VLN 中间 command，"
            "不能证明最终完成。"
        )
    else:
        status = "INCOMPLETE"
        result_score = 0
        result_reason = (
            "检测到超时或异常且没有完成证据。"
            if terminal_reason
            else "没有 final，也没有独立、明确的完成证据。"
        )

    action_rounds: Optional[int] = None
    attempts: Optional[int] = None
    if status == "SUCCESS":
        if is_vln:
            action_rounds = vln_rounds
            efficiency_score = _efficiency_for_vln(vln_rounds)
            efficiency_reason = (
                f"VLN 成功任务共 {vln_rounds} 轮动作，效率得分 {efficiency_score}。"
            )
        else:
            retry_count = _count_retries(messages)
            attempts = 1 + retry_count
            efficiency_score = _efficiency_for_attempts(attempts)
            efficiency_reason = (
                f"非 VLN 任务：1 次初始尝试 + {retry_count} 次明确失败重试，"
                f"共 {attempts} 次，效率得分 {efficiency_score}。"
            )
    else:
        efficiency_score = 0
        efficiency_reason = "执行效率仅在明确最终成功时计分。"

    if final_success is not None or independent_completion:
        evidence_score = 10
        evidence_reason = "存在明确执行终态或独立完成证据。"
    elif vln_rounds:
        evidence_score = 6
        evidence_reason = (
            f"只有 {vln_rounds} 条 VLN 中间 command，没有任务 final。"
        )
    elif execution_requested:
        evidence_score = 3
        evidence_reason = "只能证明 Agent 已发起执行，无法证明下游完成。"
    else:
        evidence_score = 0
        evidence_reason = "没有找到可验证的实际执行证据。"

    if terminal_reason and final_success is False and reply_logged:
        closure_score = 8
        closure_reason = (
            "下游缺少正常完成证据，但 Agent 明确记录超时/异常并完成最终回复。"
        )
    elif business_final and reply_logged:
        closure_score = 10
        closure_reason = "业务结果明确，且 Agent 已记录首次最终回复。"
    elif final_success is not None and reply_logged:
        closure_score = 10
        closure_reason = "Agent 明确形成最终结果并完成首次最终回复。"
    elif terminal_reason and (final_success is not None or reply_logged):
        closure_score = 8
        closure_reason = "虽无正常业务 final，但异常原因和任务结束均有记录。"
    elif final_success is not None or reply_logged:
        closure_score = 6
        closure_reason = "仅有最终结果或回复记录，闭环信息不完整。"
    elif terminal_reason:
        closure_score = 4
        closure_reason = "记录了超时/异常原因，但没有完整任务结束回复。"
    else:
        closure_score = 0
        closure_reason = "没有业务 final，也没有明确的日志结束闭环。"

    if false_positive:
        status = "FALSE_POSITIVE"
        result_score = 0
        efficiency_score = 0
        result_reason = "人工报告为假阳性：任务结果改为 0 分。"
        efficiency_reason = "假阳性不视为真实成功，执行效率改为 0 分。"

    total_score = result_score + efficiency_score + evidence_score + closure_score
    return ScoreResult(
        status,
        result_score,
        efficiency_score,
        evidence_score,
        closure_score,
        total_score,
        task_type,
        is_vln,
        action_rounds,
        attempts,
        result_reason,
        efficiency_reason,
        evidence_reason,
        closure_reason,
        false_positive,
    )


def _score_text(value: Optional[int]) -> str:
    return "不评分" if value is None else str(value)


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_console_entry(index: int, record: TraceRecord, score: ScoreResult) -> None:
    window_start, window_end = record.scoring_window()
    print("\n" + "=" * 88)
    print(
        f"[{index}] Trace={record.trace_id} | 任务={score.task_type} | "
        f"开始={record.started_at.isoformat(sep=' ', timespec='milliseconds')}"
    )
    print(f"来源={record.source} | 评分窗口=Trace行 {window_start + 1}-{window_end + 1}")
    print("-" * 88)
    for line in record.lines:
        print(line.raw)
    print("-" * 88)
    print(
        f"状态={score.status} | 结果={_score_text(score.result_score)}/60 | "
        f"效率={_score_text(score.efficiency_score)}/20 | "
        f"执行证据={_score_text(score.evidence_score)}/10 | "
        f"Trace闭环={_score_text(score.closure_score)}/10 | "
        f"总分={_score_text(score.total_score)}"
    )
    print(f"结果依据：{score.result_reason}")
    print(f"效率依据：{score.efficiency_reason}")
    print(f"证据依据：{score.evidence_reason}")
    print(f"闭环依据：{score.closure_reason}")


def _summary(scores: Sequence[ScoreResult]) -> tuple[Counter, Optional[float]]:
    counts = Counter(score.status for score in scores)
    numerator = counts["SUCCESS"] + counts["SUCCESS_WITHOUT_FINAL"]
    denominator = (
        numerator
        + counts["FAILED"]
        + counts["INCOMPLETE"]
        + counts["FALSE_POSITIVE"]
    )
    rate = (numerator / denominator * 100.0) if denominator else None
    return counts, rate


def render_markdown_report(
    records: Sequence[TraceRecord],
    scores: Sequence[ScoreResult],
    scanned_files: Sequence[Path],
    candidate_count: int,
    limit: int,
) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts, success_rate = _summary(scores)
    lines = [
        "# Motion Agent 最近任务 Trace 评分报告",
        "",
        f"- 生成时间：{generated}",
        f"- 扫描日志文件：{len(scanned_files)} 个",
        f"- 发现含“上层发来任务”的 Trace：{candidate_count} 条",
        f"- 选择规则：按任务开始时间升序排序后取最后 {limit} 条；报告编号 1 为所选范围最早，编号 {len(records)} 为最新。",
        f"- 实际评分：{len(records)} 条",
        "- 评分窗口：从该 Trace 首条“上层发来任务”到首次“结果已回复给客户端”；窗口后的日志不参与评分。",
        "- `trace=-` 的后台电机日志不属于任务 Trace，不参与评分。",
        "",
        "## 汇总",
        "",
        "| 状态 | 数量 |",
        "|---|---:|",
    ]
    for status in (
        "SUCCESS",
        "SUCCESS_WITHOUT_FINAL",
        "FAILED",
        "INCOMPLETE",
        "FALSE_POSITIVE",
        "CANCELLED",
        "INVALID",
    ):
        lines.append(f"| {status} | {counts[status]} |")
    rate_text = "无有效分母" if success_rate is None else f"{success_rate:.2f}%"
    lines.extend([
        "",
        f"成功率：**{rate_text}**",
        "",
        "公式：`(SUCCESS + SUCCESS_WITHOUT_FINAL) / (SUCCESS + SUCCESS_WITHOUT_FINAL + FAILED + INCOMPLETE + FALSE_POSITIVE)`；`CANCELLED` 和 `INVALID` 不进入分母。",
        "",
        "## 最近任务清单",
        "",
        "| 序号 | Trace ID | 开始时间 | 任务类型 | 状态 | 总分 | 来源 |",
        "|---:|---|---|---|---|---:|---|",
    ])
    for index, (record, score) in enumerate(zip(records, scores), start=1):
        lines.append(
            f"| {index} | `{record.trace_id}` | "
            f"{record.started_at.isoformat(sep=' ', timespec='milliseconds')} | "
            f"{_escape_table(score.task_type)} | {score.status} | "
            f"{_score_text(score.total_score)} | `{record.source.name}` |"
        )

    for index, (record, score) in enumerate(zip(records, scores), start=1):
        window_start, window_end = record.scoring_window()
        ignored = max(0, len(record.lines) - window_end - 1)
        lines.extend([
            "",
            f"## {index}. Trace `{record.trace_id}`",
            "",
            f"- 任务类型：`{score.task_type}`",
            f"- 开始时间：{record.started_at.isoformat(sep=' ', timespec='milliseconds')}",
            f"- 来源文件：`{record.source}`",
            f"- 源文件首任务行：{record.lines[record.start_indices[0]].line_number}",
            f"- 评分窗口：Trace 内第 {window_start + 1} 至 {window_end + 1} 行",
            f"- 窗口后忽略：{ignored} 行",
            "",
            "### 完整 Trace 日志",
            "",
            "```text",
        ])
        lines.extend(line.raw for line in record.lines)
        lines.extend([
            "```",
            "",
            "### 评分",
            "",
            "| 项目 | 得分 | 依据 |",
            "|---|---:|---|",
            f"| 任务结果 | {_score_text(score.result_score)} / 60 | {_escape_table(score.result_reason)} |",
            f"| 执行效率 | {_score_text(score.efficiency_score)} / 20 | {_escape_table(score.efficiency_reason)} |",
            f"| 执行证据 | {_score_text(score.evidence_score)} / 10 | {_escape_table(score.evidence_reason)} |",
            f"| Trace 闭环 | {_score_text(score.closure_score)} / 10 | {_escape_table(score.closure_reason)} |",
            "",
            f"**状态：{score.status}；总分：{_score_text(score.total_score)}**",
        ])

    lines.extend([
        "",
        "## 评分规则摘要",
        "",
        "- `success=true`：正常评分；明确成功 final 的任务结果为 60 分。",
        "- `success=false`：`FAILED`，任务结果和执行效率均为 0。",
        "- 普通任务被 `stop_move` 中断：`CANCELLED`，不评分、不进入成功率。",
        "- `stop_move`、`emergency_stop` 自身照常评分。",
        "- 一个 Trace 含多条“上层发来任务”：`INVALID`。",
        "- VLN 成功任务按 `VLN推理` 条数计轮次；非 VLN 按 1 + 明确失败重试次数计尝试。",
        "- 人工报告假阳性后，状态改为 `FALSE_POSITIVE`，任务结果和效率均为 0；证据和闭环保留。",
        "",
    ])
    return "\n".join(lines)


def parse_index_list(raw: str, count: int) -> set[int]:
    raw = raw.strip()
    if not raw:
        return set()
    parts = [part for part in re.split(r"[\s,，]+", raw) if part]
    result: set[int] = set()
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"不是有效序号：{part}")
        index = int(part)
        if not 1 <= index <= count:
            raise ValueError(f"序号超出范围：{index}（允许 1-{count}）")
        result.add(index)
    return result


def ask_false_positives(count: int) -> set[int]:
    while True:
        try:
            raw = input(
                f"\n评分检查：是否有假阳性？输入序号 1-{count}，"
                "多个用逗号分隔；没有则直接回车："
            )
        except EOFError:
            return set()
        try:
            return parse_index_list(raw, count)
        except ValueError as exc:
            print(f"输入无效：{exc}")


def ask_trace_limit(available: int, default: int = 10) -> int:
    default = min(default, available)
    while True:
        try:
            raw = input(
                f"发现 {available} 条任务 Trace，要评分最近几条？"
                f"输入 1-{available}（直接回车默认 {default}）："
            ).strip()
        except EOFError:
            return default
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= available:
            return int(raw)
        print(f"输入无效：请输入 1-{available} 的整数。")


def ask_save_report() -> bool:
    while True:
        try:
            raw = input("\n是否保存本次评分报告？[Y/n]：").strip().lower()
        except EOFError:
            return True
        if raw in {"", "y", "yes", "是", "1"}:
            return True
        if raw in {"n", "no", "否", "0"}:
            return False
        print("输入无效：请输入 y 或 n。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="评分最近的 Motion Agent 任务 Trace 并保存 Markdown 报告。"
    )
    parser.add_argument("--log-dir", type=Path, default=Path("logs/agent"))
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="评分最近几条；不指定时交互选择，默认 10。",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("agent_score_reports"))
    parser.add_argument(
        "--false-positive",
        default=None,
        help="非交互指定假阳性序号，例如 2,5。",
    )
    parser.add_argument("--no-prompt", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        print("--limit 必须大于 0", file=sys.stderr)
        return 2

    files = discover_log_files(args.log_dir)
    if not files:
        print(f"没有找到日志：{args.log_dir}/agent_*.log", file=sys.stderr)
        return 1

    candidates = parse_log_files(files)
    if not candidates:
        print("日志中没有包含“上层发来任务”的有效 Trace。", file=sys.stderr)
        return 1

    if args.limit is not None:
        limit = args.limit
    elif args.no_prompt:
        limit = 10
    else:
        limit = ask_trace_limit(len(candidates))

    selected = select_recent_traces(candidates, limit)

    print(
        f"扫描 {len(files)} 个日志文件，发现 {len(candidates)} 条任务 Trace；"
        f"按开始时间排序后选择最后 {len(selected)} 条。"
    )
    print("编号 1 是所选范围最早的一条，最后一个编号是最新任务。")

    preliminary = [score_trace(record) for record in selected]
    for index, (record, score) in enumerate(zip(selected, preliminary), start=1):
        render_console_entry(index, record, score)

    if args.false_positive is not None:
        try:
            false_positives = parse_index_list(args.false_positive, len(selected))
        except ValueError as exc:
            print(f"--false-positive 无效：{exc}", file=sys.stderr)
            return 2
    elif args.no_prompt:
        false_positives = set()
    else:
        false_positives = ask_false_positives(len(selected))

    final_scores = [
        score_trace(record, false_positive=index in false_positives)
        for index, record in enumerate(selected, start=1)
    ]
    if false_positives:
        selected_text = ", ".join(str(index) for index in sorted(false_positives))
        print(f"已将序号 {selected_text} 标记为 FALSE_POSITIVE。")
        for index in sorted(false_positives):
            score = final_scores[index - 1]
            print(f"  序号 {index}：状态={score.status}，调整后总分={score.total_score}")

    should_save = True if args.no_prompt else ask_save_report()
    if not should_save:
        print("\n已选择不保存，本次评分结果只在终端显示。")
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / (
        f"agent_trace_score_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    )
    report = render_markdown_report(
        selected, final_scores, files, len(candidates), limit
    )
    output_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存：{output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
