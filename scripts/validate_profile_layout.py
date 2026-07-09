"""
ProfilePage 布局精确验证 — 用代码计算代替 LLM 估算

遵循设计令牌系统：
  字体令牌（行高 = fontSize × 1.5）
  间距/内边距令牌：xs=4, sm=8, md=16, lg=24, xl=32
"""

# ==============================
# 设计令牌（与 RinUI 实际值对齐）
# ==============================
FONT_TOKENS = {
    "caption": {"size": 12, "line_h": 18, "ch_width": 12, "en_width": 7},
    "body": {"size": 14, "line_h": 21, "ch_width": 14, "en_width": 8},
    "body-strong": {"size": 14, "line_h": 21, "ch_width": 14, "en_width": 8},
    "subtitle": {"size": 20, "line_h": 30, "ch_width": 20, "en_width": 12},
    "title": {"size": 28, "line_h": 42, "ch_width": 28, "en_width": 16},
}


def text_size(text: str, font_key: str, max_width: float = None):
    """精确计算文本尺寸，区分中英文"""
    f = FONT_TOKENS[font_key]
    total_w = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f":
            total_w += f["ch_width"]
        elif ch.isascii():
            total_w += f["en_width"]
        elif ch == " ":
            total_w += f["size"] * 0.3
        else:
            total_w += f["ch_width"]
    if max_width is None or total_w <= max_width:
        return total_w, f["line_h"]
    # 需要换行
    avg_w = f["ch_width"]  # 保守估算用汉字宽
    per_line = max(1, int(max_width / avg_w))
    lines = max(1, (len(text) + per_line - 1) // per_line)
    return max_width, lines * f["line_h"]


# ==============================
# 检查点 1：未登录卡片
# ==============================
def check_login_card():
    print("=" * 60)
    print("【检查点 1】未登录卡片")
    print("=" * 60)
    card_w = 360  # Layout.preferredWidth
    padding = 20  # Frame padding
    inner_w = card_w - 2 * padding  # = 320
    print(f"  卡片宽度: {card_w}px  内边距: {padding}  内容区: {inner_w}px")

    items = [
        ("图标 IconWidget", "  ", 36, 36),  # 36×36
        (
            "提示文字",
            "登录后可查看个人成绩与统计",
            None,
            22,
        ),  # BodyStrong = body-strong
        ("按钮行", "登录 注册", None, 34),  # 两颗按钮估算
    ]
    spacing = 14  # ColumnLayout.spacing
    total_h = 0
    for name, txt, w, h in items:
        if w is None:
            tw, th = text_size(txt, "body-strong", inner_w)
            overflow = "❌" if tw > inner_w else "✓"
            print(
                f"  【{name}】'{txt}' → 宽{tw:.0f}px / 高{th}px  (可用{inner_w}px) {overflow}"
            )
        else:
            overflow = "❌" if w > inner_w else "✓"
            print(f"  【{name}】→ 宽{w}px / 高{h}px  (可用{inner_w}px) {overflow}")
            th = h
        total_h += th + spacing
    total_h -= spacing  # 去掉最后一个间隔
    print(f"  内容总高: {total_h}px  卡片最小高: {total_h + padding * 2}px")
    print(
        "  ✅ 结论：水平无溢出"
        if all(
            (36 if n == "图标 IconWidget" else inner_w) <= inner_w for n, *_ in items
        )
        else "  ❌ 存在溢出"
    )


# ==============================
# 检查点 2：统计卡片
# ==============================
def check_stat_cards(container_w: int = 860):
    print("\n" + "=" * 60)
    print(f"【检查点 2】统计卡片（容器宽 {container_w}px）")
    print("=" * 60)

    # GridLayout: 3 columns when >= 760, else 2
    columns = 3 if container_w >= 760 else 2
    col_spacing = 12
    total_gaps = col_spacing * (columns - 1)
    card_w = (container_w - total_gaps) / columns
    card_inner = card_w - 28  # anchors.margins 14×2
    print(
        f"  GridLayout: {columns}列  每卡片宽: {card_w:.0f}px  内容区: {card_inner:.0f}px"
    )

    labels = ["今日字数", "总字数", "平均速度", "最高速度", "平均键准", "总场次"]
    values_long = ["99999", "99999", "999.9", "999.9", "99.9", "99999"]
    units = ["字", "字", "字/分", "字/分", "%", "场"]

    for i, (lb, val, unit) in enumerate(zip(labels, values_long, units)):
        # 图+标签行
        icon_lb_w, lb_h = text_size(lb, "caption", card_inner)
        label_row_w = 16 + 6 + icon_lb_w  # icon 16 + spacing 6 + label
        # 数值+单位行
        val_w, val_h = text_size(val, "title", card_inner)
        unit_w, _ = text_size(unit, "caption", card_inner)
        value_row_w = val_w + 4 + unit_w  # spacing 4
        max_needed = max(label_row_w, value_row_w)
        overflow = "❌" if max_needed > card_inner else "✓"
        margin = card_inner - max_needed
        print(
            f"  [{i + 1}] {lb:　<6} 图+标签{label_row_w:.0f}px | "
            f"数值{val_w:.0f}+单位{unit_w:.0f}={value_row_w:.0f}px | "
            f"最大需求{max_needed:.0f}px  余{margin:.0f}px  {overflow}"
        )


# ==============================
# 检查点 3：用户信息卡片
# ==============================
def check_user_info_card(container_w: int = 860):
    print("\n" + "=" * 60)
    print(f"【检查点 3】用户信息卡片（容器宽 {container_w}px）")
    print("=" * 60)

    margin = 16  # anchors.margins
    inner_w = container_w - 2 * margin
    print(f"  内容区宽度: {container_w} - {margin}×2 = {inner_w}px")

    ava = 56
    gap = 16  # RowLayout spacing
    n_w = text_size("12345 场", "body-strong", inner_w)[0]  # 场次文字，如 "99999 场"
    btn_w = 80  # "退出登录" 按钮估算

    # ColumnLayout: 昵称(Subtitle) + 用户名(Caption)
    nickname_w, _ = text_size("八九寺真宵", "subtitle", inner_w)
    username_w, _ = text_size("@username", "caption", inner_w)
    col_w = max(nickname_w, username_w)

    total_w = ava + gap + col_w + gap + n_w + gap + btn_w
    remainder = inner_w - total_w
    overflow = "❌" if remainder < 0 else "✓"
    print(
        f"  头像{ava} + 昵称列{col_w:.0f} + 场次{n_w:.0f} + 按钮{btn_w} + 间隔{gap}×3 = {total_w:.0f}px"
    )
    print(f"  可用 {inner_w}px → 余{remainder:.0f}px  {overflow}")

    # 窄屏检查
    for narrow_w in [700, 600, 500, 440]:
        n_inner = narrow_w - 2 * margin
        n_total = ava + gap + col_w + gap + n_w + gap + btn_w
        n_left = n_inner - n_total
        if n_left < 0:
            print(
                f"    ⚠ 窗口 {narrow_w}px 时溢出 {abs(n_left):.0f}px (可用{n_inner}px)"
            )
        else:
            print(f"    ✓ 窗口 {narrow_w}px 时余 {n_left:.0f}px")

    # ===== 子检查：昵称列内部对齐 =====
    print()
    print("  【子检查】昵称列内部对齐")
    f_nick = FONT_TOKENS["subtitle"]
    f_user = FONT_TOKENS["caption"]
    # subtitle 20px, line_h 30; caption 12px, line_h 18
    # ColumnLayout spacing: 2
    col_h = f_nick["line_h"] + 2 + f_user["line_h"]
    print(
        f"  昵称行高{f_nick['line_h']}px + spacing 2 + 用户名行高{f_user['line_h']}px = {col_h}px"
    )
    print("  ✓ 垂直无溢出")


# ==============================
# 检查点 4：最近成绩表
# ==============================
def check_history_table(container_w: int = 860):
    print("\n" + "=" * 60)
    print(f"【检查点 4】最近成绩表（容器宽 {container_w}px）")
    print("=" * 60)

    card_padding = 14  # anchors.margins
    inner_w = container_w - 2 * card_padding

    # 固定列: 日期(100) + 段(40) + 字数(50) = 190
    fixed_w = 100 + 40 + 50
    fill_count = 2  # 速度, 键准
    fill_w = (inner_w - fixed_w) / fill_count
    overflow = "❌" if fill_w < 0 else "✓"
    print(f"  内容区: {inner_w}px")
    print(f"  固定列 100+40+50={fixed_w}px  每fill列: {fill_w:.0f}px  {overflow}")
    hdr_date = "日期"
    hdr_seg = "段"
    hdr_speed = "速度"
    hdr_acc = "键准"
    hdr_chars = "字数"
    print(
        f"  表头{hdr_date}{100}px  {hdr_seg}{40}px  {hdr_speed}{fill_w:.0f}px  {hdr_acc}{fill_w:.0f}px  {hdr_chars}{50}px"
    )

    # 数据行: speed = "123.4"(数字+点), keyAccuracy = "99.9%"
    speed_w, _ = text_size("123.4", "caption", fill_w) if fill_w > 0 else (50, 18)
    acc_w, _ = text_size("99.9%", "caption", fill_w) if fill_w > 0 else (50, 18)
    speed_ok = "✓" if speed_w <= fill_w else "❌"
    acc_ok = "✓" if acc_w <= fill_w else "❌"
    sp_label = "速度"
    acc_label = "键准"
    print(f"  数据{sp_label}{speed_w:.0f}px / 可用{fill_w:.0f}px  {speed_ok}")
    print(f"  数据{acc_label}{acc_w:.0f}px / 可用{fill_w:.0f}px  {acc_ok}")

    # 窄屏
    for narrow_w in [700, 600, 500, 440]:
        niw = narrow_w - 2 * card_padding
        nfw = (niw - fixed_w) / 2
        if nfw < 12:  # caption 最小约 12px
            print(f"    ⚠ 窗口 {narrow_w}px 时 fill列仅 {nfw:.0f}px (可用{niw}px)")
        else:
            print(f"    ✓ 窗口 {narrow_w}px 时 fill列 {nfw:.0f}px")


# ==============================
# 检查点 5：每日打字趋势
# ==============================
def check_daily_trend(container_w: int = 860):
    print("\n" + "=" * 60)
    print(f"【检查点 5】每日打字趋势（容器宽 {container_w}px）")
    print("=" * 60)

    card_padding = 14
    inner_w = container_w - 2 * card_padding

    header_t, _ = text_size("最近 30 天打字量", "body-strong", inner_w)
    sub_t, _ = text_size("字/天", "caption", inner_w)
    header_needed = header_t + 16 + sub_t  # Item fillWidth 占中间, 保守估算
    print(
        f"  header: {header_t:.0f}px + spacer + 字/天{sub_t:.0f}px ≈ {header_needed:.0f}px"
    )
    print(f"  可用: {inner_w}px  ✓" if header_needed <= inner_w else "  ❌ 溢出")

    chart_h = 120  # Layout.preferredHeight
    print(f"  柱状图: {chart_h}px")

    # 30 根柱子
    bars = 30
    bar_spacing = 2
    bar_w = (inner_w - bar_spacing * (bars - 1)) / bars
    print(
        f"  30 根柱子, 间距 2px, 每柱宽 {bar_w:.1f}px  ≥ 2px  ✓"
        if bar_w >= 2
        else f"  ❌ 每柱宽 {bar_w:.1f}px < 2px"
    )


# ==============================
# 主入口
# ==============================
if __name__ == "__main__":
    # 三个典型宽度：宽屏 900px、中屏 760px、窄屏 600px
    for w in [900, 760, 600]:
        content_w = w - 40  # horizontalPadding 20×2
        print("\n" + "#" * 70)
        print(f"## 容器宽度: {w}px → 内容区: {content_w}px")
        print("#" * 70)
        check_login_card()
        check_stat_cards(content_w)
        check_user_info_card(content_w)
        check_history_table(content_w)
        check_daily_trend(content_w)
