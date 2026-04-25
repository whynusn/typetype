"""Score Gateway - DTO 转换 + 剪贴板操作。

将领域对象转换为 DTO，供 UI 层使用。
"""

from ...models.dto.score_dto import HistoryRecordDTO, ScoreSummaryDTO
from ...models.entity.session_stat import SessionStat
from ...ports.clipboard import ClipboardWriter


class ScoreGateway:
    """成绩网关，封装 DTO 转换和剪贴板操作。

    职责：
    - 将 SessionStat 转换为 HistoryRecordDTO
    - 将 SessionStat 转换为 ScoreSummaryDTO
    - 将分数摘要复制到剪贴板

    不负责：
    - 业务流程编排
    - 数据持久化
    """

    def __init__(self, clipboard: ClipboardWriter):
        self._clipboard = clipboard

    def build_history_record(
        self, score_data: SessionStat
    ) -> dict[str, float | int | str]:
        """构建历史记录字典。"""
        return HistoryRecordDTO.from_score_data(score_data).to_dict()

    def build_score_message(self, score_data: SessionStat | None) -> str:
        """构建分数摘要 HTML。"""
        if not score_data:
            return "获取分数失败"
        return ScoreSummaryDTO.from_score_data(score_data).to_html()

    def copy_score_to_clipboard(self, score_data: SessionStat | None) -> None:
        """复制分数摘要纯文本到剪贴板。"""
        if not score_data:
            return
        plain_text = ScoreSummaryDTO.from_score_data(score_data).to_clipboard_text()
        self._clipboard.setText(plain_text)

    def build_aggregate_message(self, slice_stats: list[dict], slice_count: int) -> str:
        """构建分片模式综合成绩 HTML 消息。

        Args:
            slice_stats: 每片 SessionStat 快照列表（dict 格式）
            slice_count: 片数
        """
        n = len(slice_stats)
        if n == 0:
            return ""

        avg_speed = sum(s["speed"] for s in slice_stats) / n
        avg_keystroke = sum(s["keyStroke"] for s in slice_stats) / n
        avg_code_length = sum(s["codeLength"] for s in slice_stats) / n
        total_chars = sum(s["char_count"] for s in slice_stats)
        total_wrong = sum(s["wrong_char_count"] for s in slice_stats)
        total_backspace = sum(s["backspace_count"] for s in slice_stats)
        total_correction = sum(s["correction_count"] for s in slice_stats)
        total_time = sum(s["time"] for s in slice_stats)
        total_key_strokes = sum(s.get("key_stroke_count", 0) for s in slice_stats)
        key_accuracy = (
            (total_key_strokes - total_backspace - total_correction * avg_code_length)
            / total_key_strokes
            * 100
            if total_key_strokes > 0
            else 100.0
        )

        # 统一指标顺序：速度 → 击键 → 码长 → 错字 → 回改 → 退格 → 键准 → 字数 → 用时 → 键数
        # 格式：秒/% 单位紧贴值，其他单位前有空格，无单位无空格
        items = [
            ("速度", f"{avg_speed:.2f}", "字/分"),
            ("击键", f"{avg_keystroke:.2f}", "击/秒"),
            ("码长", f"{avg_code_length:.2f}", "击/字"),
            ("错字", f"{total_wrong}", "字"),
            ("回改", f"{total_correction}", "次"),
            ("退格", f"{total_backspace}", "次"),
            ("键准", f"{key_accuracy:.2f}", "%"),
            ("字数", f"{total_chars}", ""),
            ("用时", f"{total_time:.3f}", "秒"),
            ("键数", f"{total_key_strokes}", ""),
        ]

        lines = [f"<b>综合成绩（{slice_count}片）</b><br>"]
        for label, value_str, unit in items:
            if unit in ("秒", "%"):
                lines.append(f"{label}: <b>{value_str}</b>{unit}<br>")
            elif unit:
                lines.append(f"{label}: <b>{value_str}</b> {unit}<br>")
            else:
                lines.append(f"{label}: <b>{value_str}</b><br>")
        return "".join(lines)

    def build_aggregate_plain_text(
        self, slice_stats: list[dict], slice_count: int
    ) -> str:
        """构建分片模式综合成绩纯文本（木易单行格式，用于剪贴板）。"""
        n = len(slice_stats)
        if n == 0:
            return ""

        avg_speed = sum(s["speed"] for s in slice_stats) / n
        avg_keystroke = sum(s["keyStroke"] for s in slice_stats) / n
        avg_code_length = sum(s["codeLength"] for s in slice_stats) / n
        total_chars = sum(s["char_count"] for s in slice_stats)
        total_wrong = sum(s["wrong_char_count"] for s in slice_stats)
        total_backspace = sum(s["backspace_count"] for s in slice_stats)
        total_correction = sum(s["correction_count"] for s in slice_stats)
        total_time = sum(s["time"] for s in slice_stats)
        total_key_strokes = sum(s.get("key_stroke_count", 0) for s in slice_stats)
        key_accuracy = (
            (total_key_strokes - total_backspace - total_correction * avg_code_length)
            / total_key_strokes
            * 100
            if total_key_strokes > 0
            else 100.0
        )

        return (
            f"综合成绩（{slice_count}片）"
            f" 速度{avg_speed:.2f}"
            f" 击键{avg_keystroke:.2f}"
            f" 码长{avg_code_length:.2f}"
            f" 字数{total_chars}"
            f" 错字{total_wrong}"
            f" 用时{total_time:.3f}秒"
            f" 键准{key_accuracy:.2f}%"
            f" 回改{total_correction}"
            f" 键数{total_key_strokes}"
            f" 退格{total_backspace}"
        )
