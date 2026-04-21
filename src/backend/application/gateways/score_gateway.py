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
        plain_text = ScoreSummaryDTO.from_score_data(score_data).to_plain_text()
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
        accuracy = (
            (total_chars - total_wrong) / total_chars * 100 if total_chars > 0 else 0
        )
        effective_speed = avg_speed * accuracy / 100

        items = [
            ("速度", avg_speed, "字/分", ".1f"),
            ("有效速度", effective_speed, "字/分", ".1f"),
            ("码长", avg_code_length, "击/字", ".2f"),
            ("击键", avg_keystroke, "击/秒", ".1f"),
            ("准确率", accuracy, "%", ".1f"),
            ("回改", total_correction, "次", "d"),
            ("退格", total_backspace, "次", "d"),
            ("总字数", total_chars, "字", "d"),
            ("总用时", total_time, "秒", ".1f"),
        ]

        lines = [f"<b>综合成绩（{slice_count}片）</b><br>"]
        for label, value, unit, fmt in items:
            lines.append(f"{label}: <b>{value:{fmt}}</b> {unit}<br>")
        return "".join(lines)

    def build_aggregate_plain_text(
        self, slice_stats: list[dict], slice_count: int
    ) -> str:
        """构建分片模式综合成绩纯文本（用于剪贴板）。"""
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
        accuracy = (
            (total_chars - total_wrong) / total_chars * 100 if total_chars > 0 else 0
        )
        effective_speed = avg_speed * accuracy / 100

        lines = [f"综合成绩（{slice_count}片）"]
        lines.append(f"速度: {avg_speed:.1f} 字/分")
        lines.append(f"有效速度: {effective_speed:.1f} 字/分")
        lines.append(f"码长: {avg_code_length:.2f} 击/字")
        lines.append(f"击键: {avg_keystroke:.1f} 击/秒")
        lines.append(f"准确率: {accuracy:.1f}%")
        lines.append(f"回改: {total_correction} 次")
        lines.append(f"退格: {total_backspace} 次")
        lines.append(f"总字数: {total_chars} 字")
        lines.append(f"总用时: {total_time:.1f} 秒")
        return "\n".join(lines)
