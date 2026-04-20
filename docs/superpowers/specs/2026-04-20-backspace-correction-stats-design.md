# 回改/退格统计指标设计

## 需求

新增两个打字统计指标：
- **回改**：用户删除字符的次数（选中多个字符并一键删除算 1 次）
- **退格**：用户按下退格键的次数（Wayland 通过 evdev 精确检测，非 Wayland 通过 QML 检测但受 IME preedit 限制可能不完整）

## 平台差异

| 指标 | Wayland (evdev) | 非 Wayland |
|------|----------------|------------|
| 回改 | QML textChanged | QML textChanged |
| 退格 | evdev KEY_BACKSPACE 检测（精确） | QML Keys.onPressed 检测（受 IME preedit 限制） |

**非 Wayland 退格统计**：通过 QML `Keys.onPressed` + `!isSpecialPlatform` 守卫实现，与码长/击键逻辑一致。在 fcitx5 等 IME 的 preedit 阶段，退格操作只影响 `preeditText` 而不触发 `Keys.onPressed`，因此统计可能不完整。Wayland 下两路互斥（evdev 路径在先，QML 路径由 `isSpecialPlatform` 守卫跳过），不会重复计数。

## 改动链路

```
SessionStat                    +backspace_count, +correction_count
    ↓
TypingService                  +accumulate_backspace(), +accumulate_correction()
    ↓
TypingAdapter                  +backspaceChanged signal, +correctionChanged signal
    ↓
Bridge                         +wrongNum（已有）, +backspace, +correction 属性
    ↓
LowerPane.qml                  growLength < 0 → accumulate_correction()
    ↓
Bridge.on_key_received()       evdev KEY_BACKSPACE → accumulate_backspace()
```

## 改动文件清单

| # | 文件 | 改动 | 风险 |
|---|------|------|------|
| 1 | `models/entity/session_stat.py` | 新增 backspace_count, correction_count 字段 | 低（纯数据字段） |
| 2 | `domain/services/typing_service.py` | 新增 accumulate_backspace(), accumulate_correction(), clear() 中归零 | 低（新增方法，不改现有逻辑） |
| 3 | `presentation/adapters/typing_adapter.py` | 新增 backspaceChanged, correctionChanged 信号 + 属性代理 | 低（新增信号，不改现有信号） |
| 4 | `presentation/bridge.py` | 新增 backspace, correction 属性 + on_key_received 检测 KEY_BACKSPACE | 低（在现有方法上追加） |
| 5 | `src/qml/typing/LowerPane.qml` | growLength < 0 时调用 appBridge.accumulateCorrection() | 低（追加一行） |
| 6 | `src/qml/typing/ScoreArea.qml` | 新增回改 PillButton 显示 | 低（追加 UI） |
| 7 | `models/dto/score_dto.py` | ScoreSummaryDTO 和 HistoryRecordDTO 加入新指标 | 低（追加字段） |
| 8 | `reference/bridge-slots.md` | 文档同步 | 无风险 |
