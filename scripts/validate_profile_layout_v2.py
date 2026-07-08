"""
ProfilePage 精确布局验证 v2 — 逐子容器迭代 + 同级相对位置 + 父容器边界检查

核心方法：
  1. 从叶子节点（Text）开始计算精确尺寸
  2. 自底向上逐层合并入父容器
  3. 每层检查：同级间距、是否重叠、父边界是否溢出
  4. 输出每个容器的绝对坐标和边界状态
"""
import json
import math

# ==============================
# 设计令牌
# ==============================
SPACING = {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32}
PADDING = {"none": 0, "tight": 8, "normal": 16, "loose": 24}
FONTS = {
    "caption":      {"size": 12, "lh": 18, "ch": 12, "en": 7},
    "body":         {"size": 14, "lh": 21, "ch": 14, "en": 8},
    "body-strong":  {"size": 14, "lh": 21, "ch": 14, "en": 8},
    "body-lg":      {"size": 16, "lh": 24, "ch": 16, "en": 9},
    "subtitle":     {"size": 20, "lh": 30, "ch": 20, "en": 11},
    "title":        {"size": 28, "lh": 42, "ch": 28, "en": 16},
    "headline":     {"size": 24, "lh": 36, "ch": 24, "en": 13},
}


def text_size(text: str, font: str, max_w: float = None):
    """返回 (width, height) — 精确到 0.1"""
    f = FONTS[font]
    tw = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f':
            tw += f["ch"]
        elif ch.isascii():
            tw += f["en"]
        elif ch == ' ':
            tw += f["size"] * 0.3
        else:
            tw += f["ch"]
    if max_w is None or tw <= max_w:
        return round(tw, 1), f["lh"]
    # 换行
    per = max(1, int(max_w / f["ch"]))
    lines = max(1, (len(text) + per - 1) // per)
    return round(max_w, 1), lines * f["lh"]


# ==============================
# 组件树 spec — 完整描述 ProfilePage
# ==============================
# 每个节点：{type, font?, text?, gap?, padding?, children?, w?, h?, x?, y?}
# w/h/x/y 由验证引擎填充

SPEC = {
    "root": {
        "type": "Column",
        "gap": "lg",            # 24
        "padding": "none",      # 0 — Flickable 内 ColumnLayout 无 padding
        "desc": "顶级 ColumnLayout",
        "children": ["login_card", "user_info", "stat_grid",
                     "trend_card", "history_card"]
    },
    # ---- 未登录卡片 ----
    "login_card": {
        "type": "Card",
        "padding": "loose",     # 24
        "child_gap": "md",      # 16 — ColumnLayout spacing
        "align": "center",
        "maxWidth": 480,
        "desc": "登录提示卡片 Frame",
        "children": ["login_icon", "login_text", "login_buttons"]
    },
    "login_icon": {
        "type": "Fixed",
        "w": 36, "h": 36,
        "desc": "头像图标"
    },
    "login_text": {
        "type": "Text",
        "font": "body-strong",
        "text": "登录后可查看个人成绩与统计",
        "desc": "提示文字"
    },
    "login_buttons": {
        "type": "Row",
        "gap": "md",            # 16
        "padding": "none",
        "desc": "登录/注册按钮行",
        "children": ["btn_login", "btn_register"]
    },
    "btn_login": {"type": "Fixed", "w": 80, "h": 32, "desc": "登录按钮"},
    "btn_register": {"type": "Fixed", "w": 80, "h": 32, "desc": "注册按钮"},

    # ---- 用户信息卡片 ----
    "user_info": {
        "type": "Card",
        "padding": "normal",    # 16
        "desc": "用户信息 Frame",
        "children": ["user_row"]
    },
    "user_row": {
        "type": "Row",
        "gap": "md",           # 16
        "padding": "none",
        "desc": "头像/昵称/场次/退出 RowLayout",
        "children": ["avatar", "nickname_col", "match_count", "btn_logout"]
    },
    "avatar": {"type": "Fixed", "w": 56, "h": 56, "desc": "头像"},
    "nickname_col": {
        "type": "Column",
        "gap": "xs",           # 4
        "padding": "none",
        "desc": "昵称+用户名 Column",
        "children": ["nickname", "username"]
    },
    "nickname": {"type": "Text", "font": "subtitle", "text": "八九寺真宵",
                 "desc": "用户昵称"},
    "username": {"type": "Text", "font": "caption", "text": "@username",
                 "desc": "用户名"},
    "match_count": {"type": "Text", "font": "body-strong", "text": "99999 场",
                    "desc": "历史场次"},
    "btn_logout": {"type": "Fixed", "w": 80, "h": 32, "desc": "退出按钮"},

    # ---- 统计卡片网格 (取 1 张代表性卡片, 实际在 GridLayout 中重复) ----
    "stat_grid": {
        "type": "Grid",
        "columns": 3,
        "gap": "md",
        "desc": "统计卡片 GridLayout (3列)",
        "children": ["stat_1", "stat_2", "stat_3", "stat_4", "stat_5", "stat_6"]
    },
    # 用"平均速度"作为最宽场景（"999.9" + "字/分"）
    "stat_1": {"type": "StatCard", "label": "今日字数", "value": "99999", "unit": "字",
               "desc": "统计卡片(今日字数)"},
    "stat_2": {"type": "StatCard", "label": "总字数", "value": "99999", "unit": "字",
               "desc": "统计卡片(总字数)"},
    "stat_3": {"type": "StatCard", "label": "平均速度", "value": "999.9", "unit": "字/分",
               "desc": "统计卡片(平均速度)"},
    "stat_4": {"type": "StatCard", "label": "最高速度", "value": "999.9", "unit": "字/分",
               "desc": "统计卡片(最高速度)"},
    "stat_5": {"type": "StatCard", "label": "平均键准", "value": "99.9", "unit": "%",
               "desc": "统计卡片(平均键准)"},
    "stat_6": {"type": "StatCard", "label": "总场次", "value": "99999", "unit": "场",
               "desc": "统计卡片(总场次)"},

    # ---- 每日趋势卡片 ----
    "trend_card": {
        "type": "Card",
        "padding": "normal",
        "desc": "每日趋势 Frame",
        "children": ["trend_col"]
    },
    "trend_col": {
        "type": "Column",
        "gap": "sm",
        "padding": "none",
        "desc": "趋势内 Column",
        "children": ["trend_header", "trend_chart"]
    },
    "trend_header": {
        "type": "Row",
        "gap": "md",
        "padding": "none",
        "desc": "趋势标题行 (居中用 Item spacer)",
        "children": ["trend_title", "trend_spacer", "trend_unit"]
    },
    "trend_title": {"type": "Text", "font": "body-strong", "text": "最近 30 天打字量",
                    "desc": "趋势标题"},
    "trend_spacer": {"type": "Flex", "desc": "弹性间隔 Item"},
    "trend_unit": {"type": "Text", "font": "caption", "text": "字/天",
                   "desc": "趋势单位"},
    "trend_chart": {"type": "Fixed", "w": 0, "h": 120, "desc": "柱状图区域"},

    # ---- 最近成绩卡片 ----
    "history_card": {
        "type": "Card",
        "padding": "normal",
        "desc": "最近成绩 Frame",
        "children": ["history_col"]
    },
    "history_col": {
        "type": "Column",
        "gap": "sm",
        "padding": "none",
        "desc": "成绩内 Column",
        "children": ["history_title", "history_divider", "history_header",
                     "history_list", "history_empty"]
    },
    "history_title": {"type": "Text", "font": "body-strong", "text": "最近成绩",
                      "desc": "成绩标题"},
    "history_divider": {"type": "Fixed", "w": 0, "h": 1, "desc": "分隔线"},
    "history_header": {
        "type": "Row",
        "gap": "xs",
        "padding": "none",
        "desc": "成绩表头 Row",
        "children": ["h_date", "h_seg", "h_speed", "h_acc", "h_chars"]
    },
    "h_date": {"type": "Text", "font": "caption", "text": "日期", "fillW": 120,
               "desc": "表头-日期"},
    "h_seg": {"type": "Text", "font": "caption", "text": "段", "fillW": 40,
              "desc": "表头-段"},
    "h_speed": {"type": "Text", "font": "caption", "text": "速度", "align": "right",
                "desc": "表头-速度"},
    "h_acc": {"type": "Text", "font": "caption", "text": "键准", "align": "right",
              "desc": "表头-键准"},
    "h_chars": {"type": "Text", "font": "caption", "text": "字数", "fillW": 60,
                "align": "right", "desc": "表头-字数"},
    "history_list": {"type": "Fixed", "w": 0, "h": 240, "desc": "成绩列表 ListView"},
    "history_empty": {"type": "Text", "font": "caption",
                      "text": "暂无历史记录，打完一局后会自动记录",
                      "desc": "空状态提示"},
}

# StatCard 模板展开
_STATCARD_TEMPLATE = {
    "type": "Column",
    "gap": "sm",
    "padding": "normal",
    "desc_template": "统计卡片({label})",
    "children": ["stat_label_row", "stat_value_row"]
}

def build_spec():
    """完整展开 StatCard 模板"""
    s = dict(SPEC)
    for i in range(1, 7):
        key = f"stat_{i}"
        sc = s[key]
        label, value, unit = sc["label"], sc["value"], sc["unit"]
        lid = f"{key}_label"
        vid = f"{key}_value"
        s[lid] = {
            "type": "Row", "gap": "sm", "padding": "none",
            "desc": f"{label}标签行",
            "children": [f"{key}_icon", f"{key}_label_text"]
        }
        s[f"{key}_icon"] = {"type": "Fixed", "w": 16, "h": 16, "desc": f"{label}图标"}
        s[f"{key}_label_text"] = {"type": "Text", "font": "caption", "text": label,
                                   "desc": f"{label}标签"}
        s[vid] = {
            "type": "Row", "gap": "xs", "padding": "none",
            "desc": f"{label}数值行",
            "children": [f"{key}_val", f"{key}_unit"]
        }
        s[f"{key}_val"] = {"type": "Text", "font": "title", "text": value,
                            "desc": f"{label}数值"}
        s[f"{key}_unit"] = {"type": "Text", "font": "caption", "text": unit,
                             "desc": f"{label}单位"}
        s[key] = {
            "type": "Column",
            "gap": "sm",
            "padding": "normal",
            "desc": f"统计卡片({label})",
            "children": [lid, vid]
        }
    return s


# ==============================
# 递归验证引擎
# ==============================
class LayoutResult:
    """单个组件的计算结果"""
    def __init__(self, id, w, h, x=0, y=0):
        self.id = id
        self.w = w
        self.h = h
        self.x = x  # 相对于父容器的 x
        self.y = y  # 相对于父容器的 y
        self.children = []
        self.overflow = None
        self.sibling_overlap = None
        self.boundary_ok = True

    def __repr__(self):
        return f"{self.id} @({self.x},{self.y}) {self.w}×{self.h}"


def validate(element_id: str, spec: dict,
             parent_w: float, parent_h: float,
             depth: int = 0) -> LayoutResult:
    """
    递归验证一个组件，自底向上。
    parent_w/h: 父容器可用空间（已扣除 padding）。
    返回 布局结果。
    """
    node = spec[element_id]
    t = node["type"]
    indent = "  " * depth

    # ---- 叶子节点 ----
    if t == "Text":
        max_avail = parent_w if node.get("fillW") else None
        w, h = text_size(node["text"], node["font"], max_avail)
        # fillW 列：如果 fillW 有值，用它作最小宽度
        if node.get("fillW") and node["fillW"] > w:
            w = node["fillW"]
        r = LayoutResult(element_id, w, h)
        # 溢出检查
        if w > parent_w:
            r.overflow = f"text宽度{w:.0f} > 可用{parent_w:.0f}, 溢出{w-parent_w:.0f}px"
        if h > parent_h:
            r.overflow = r.overflow or f"text高度{h:.0f} > 可用{parent_h:.0f}"
        return r

    if t == "Fixed":
        w = node.get("w", 0)
        h = node.get("h", 0)
        if node.get("fillW") or node.get("type") == "Flex":
            w = parent_w  # fillWidth
        r = LayoutResult(element_id, w, h)
        return r

    if t == "Flex":
        # 弹性伸缩占位 (如 Item fillWidth) — 宽0，高0，由 Row 分配空间和行高
        return LayoutResult(element_id, 0, 0)

    # ---- StatCard inline 展开 ----
    if t == "StatCard":
        # 已由 build_spec() 展开
        raise ValueError(f"StatCard {element_id} 未展开")

    # ---- 容器节点 ----
    gap = SPACING.get(node.get("gap", "md"), 16)
    pad = PADDING.get(node.get("padding", "none"), 0)
    children_ids = node.get("children", [])

    # 扣除 padding 后的可用空间
    inner_w = parent_w - 2 * pad
    inner_h = parent_h - 2 * pad

    # 递归验证子节点
    child_results = []
    for cid in children_ids:
        cr = validate(cid, spec, inner_w, inner_h, depth + 1)
        child_results.append(cr)

    # ---- 计算容器尺寸 + 同级位置 ----
    if t in ("Row",):
        x = pad
        max_h = 0
        total_w = 0
        flex_idx = None
        for i, cr in enumerate(child_results):
            cr.x = x
            cr.y = pad
            x += cr.w
            if i < len(child_results) - 1:
                x += gap
            max_h = max(max_h, cr.h)
            total_w += cr.w
            if spec[cr.id].get("type") == "Flex":
                flex_idx = i
        total_w += gap * max(0, len(child_results) - 1)

        # Flex 子项吞掉剩余空间
        if flex_idx is not None and total_w < inner_w:
            surplus = inner_w - total_w
            cr = child_results[flex_idx]
            cr.w += surplus
            total_w += surplus
            # 重新计算后续兄弟位置
            x = cr.x + cr.w + gap
            for j in range(flex_idx + 1, len(child_results)):
                child_results[j].x = x
                x += child_results[j].w + gap

        # 如果还有 fillW 列且仍有剩余，再分配
        if total_w < inner_w:
            fill_count = sum(1 for cr in child_results if spec[cr.id].get("fillW"))
            if fill_count > 0:
                surplus = inner_w - total_w
                share = surplus / fill_count
                for cr in child_results:
                    if spec[cr.id].get("fillW"):
                        cr.w += share
                total_w = inner_w
                # 重新计算位置
                x = pad
                for cr in child_results:
                    cr.x = x
                    x += cr.w + gap

        r = LayoutResult(element_id, total_w + 2 * pad, max_h + 2 * pad)

    elif t in ("Column",):
        y = pad
        max_w = 0
        total_h = 0
        for i, cr in enumerate(child_results):
            cr.x = pad
            cr.y = y
            y += cr.h
            if i < len(child_results) - 1:
                y += gap
            max_w = max(max_w, cr.w)
            total_h += cr.h
        total_h += gap * max(0, len(child_results) - 1)
        # fillW 子项占满容器宽度
        for cr in child_results:
            if spec[cr.id].get("fillW"):
                cr.w = max(cr.w, inner_w)
                max_w = max(max_w, cr.w)

        r = LayoutResult(element_id, max_w + 2 * pad, total_h + 2 * pad)

    elif t == "Card":
        # Card = 内含一个 Column/Row（多子当作 Column）
        if not child_results:
            r = LayoutResult(element_id, 0, 0)
        elif len(child_results) == 1:
            child_results[0].x = pad
            child_results[0].y = pad
            r = LayoutResult(element_id,
                             child_results[0].w + 2 * pad,
                             child_results[0].h + 2 * pad)
        else:
            # 多子作为 Column
            y = pad
            max_w = 0
            total_h = 0
            # 查找内部 gap — 用 child_gap 或默认 sm
            inner_gap = SPACING.get(node.get("child_gap", "sm"), 8)
            for i, cr in enumerate(child_results):
                cr.x = pad
                cr.y = y
                y += cr.h
                if i < len(child_results) - 1:
                    y += inner_gap
                max_w = max(max_w, cr.w)
                total_h += cr.h
            total_h += inner_gap * max(0, len(child_results) - 1)
            r = LayoutResult(element_id,
                             max_w + 2 * pad,
                             total_h + 2 * pad)

    elif t == "Grid":
        cols = node.get("columns", 2)
        col_gap = gap
        # 均分宽度
        cell_w = (parent_w - col_gap * (cols - 1)) / cols
        # 递归计算子项时可用宽度 = cell_w
        # 但子项已经用 inner_w 算过了，需要重新用 cell_w 算
        # 重新计算子项尺寸（用正确的 cell 宽度）
        child_results = []
        for cid in children_ids:
            cr = validate(cid, spec, cell_w, parent_h, depth + 1)
            child_results.append(cr)

        row_h = 0
        total_w = 0
        row_y = pad
        for i, cr in enumerate(child_results):
            col = i % cols
            row = i // cols
            if col == 0:
                row_y = pad + (row_h + gap) * row if row > 0 else pad
            cr.x = pad + col * (cell_w + col_gap)
            cr.y = row_y
            row_h = max(row_h, cr.h)
            total_w = max(total_w, cr.x + cr.w)
        nrows = (len(child_results) + cols - 1) // cols
        total_h = nrows * (row_h + gap) - gap + 2 * pad
        r = LayoutResult(element_id, total_w + pad, total_h)

    else:
        raise ValueError(f"未知类型 {t}")

    r.children = child_results

    # ---- 溢出检查 ----
    if r.w > parent_w:
        r.overflow = (f"容器总宽{r.w:.0f} > 父可用{parent_w:.0f}, "
                      f"溢出{r.w - parent_w:.0f}px")
    if r.h > parent_h:
        r.overflow = (r.overflow or "") + (
            f"容器总高{r.h:.0f} > 父可用{parent_h:.0f}"
        ) if r.overflow else (
            f"容器总高{r.h:.0f} > 父可用{parent_h:.0f}"
        )

    # ---- 同级相对位置检查 ----
    if len(child_results) >= 2:
        # 对 Grid 类型：跳过行内的垂直重叠检查（子项在不同 x 位置）
        for i in range(len(child_results)):
            a = child_results[i]
            for j in range(i + 1, len(child_results)):
                b = child_results[j]
                if t == "Row":
                    a_right = a.x + a.w
                    if a_right > b.x + 0.5:  # 允许 0.5px 舍入误差
                        overlap = a_right - b.x
                        r.sibling_overlap = (
                            f"兄弟重叠: {a.id}(右{a_right:.0f}) → {b.id}(左{b.x:.0f}), "
                            f"重叠{overlap:.0f}px")
                elif t in ("Column",):
                    a_bot = a.y + a.h
                    if a_bot > b.y + 0.5:
                        overlap = a_bot - b.y
                        r.sibling_overlap = (
                            f"兄弟重叠: {a.id}(底{a_bot:.0f}) → {b.id}(顶{b.y:.0f}), "
                            f"重叠{overlap:.0f}px")
                elif t == "Grid":
                    # Grid 中，只检查真正在同一 x 范围重叠的卡片
                    a_right = a.x + a.w
                    b_right = b.x + b.w
                    a_bot = a.y + a.h
                    b_bot = b.y + b.h
                    x_overlap = a.x < b_right and b.x < a_right
                    y_overlap = a.y < b_bot and b.y < a_bot
                    if x_overlap and y_overlap and i != j:
                        r.sibling_overlap = (
                            f"Grid重叠: {a.id}({a.x:.0f},{a.y:.0f}"
                            f"→{a_right:.0f},{a_bot:.0f}) "
                            f"vs {b.id}({b.x:.0f},{b.y:.0f}"
                            f"→{b_right:.0f},{b_bot:.0f})")

    return r


def print_tree(r: LayoutResult, depth: int = 0, parent_w: float = None,
               parent_h: float = None):
    """美化打印布局树"""
    indent = "  " * depth
    prefix = f"{indent}{r.id}"
    dims = f"@{r.x:.0f},{r.y:.0f} {r.w:.0f}×{r.h:.0f}"
    status = "✅"
    issues = []
    if r.overflow:
        status = "❌"
        issues.append(f"溢出: {r.overflow}")
    if r.sibling_overlap:
        status = "❌"
        issues.append(f"重叠: {r.sibling_overlap}")
    # 父边界检查
    if parent_w is not None and r.x < 0:
        status = "❌"
        issues.append(f"越界左{r.x:.0f}")
    if parent_h is not None and r.y < 0:
        status = "❌"
        issues.append(f"越界上{r.y:.0f}")

    print(f"{prefix} {status} [{dims}]")
    for iss in issues:
        print(f"{indent}   ⚠ {iss}")
    for child in r.children:
        print_tree(child, depth + 1, r.w, r.h)


def report_sibling_relationships(r: LayoutResult, depth: int = 0):
    """输出同级容器的相对位置关系"""
    indent = "  " * depth
    if len(r.children) >= 2:
        print(f"\n{indent}📦 父容器 [{r.id}]  {r.w:.0f}×{r.h:.0f}")
        for child in r.children:
            print(f"{indent}  ├─ {child.id}: "
                  f"x={child.x:.0f} y={child.y:.0f} "
                  f"w={child.w:.0f} h={child.h:.0f} "
                  f"右={child.x+child.w:.0f} 底={child.y+child.h:.0f}")
    for child in r.children:
        report_sibling_relationships(child, depth + 1)


def report_boundary_status(r: LayoutResult, parent_w: float = None,
                           parent_h: float = None, depth: int = 0):
    """检查父容器边界是否完好"""
    indent = "  " * depth
    issues = []
    if parent_w is not None:
        if r.x + r.w > parent_w:
            issues.append(f"❌ 右边界溢出: x+r.w({r.x+r.w:.0f}) > parent_w({parent_w:.0f})")
        if r.y + r.h > parent_h:
            issues.append(f"❌ 下边界溢出: y+r.h({r.y+r.h:.0f}) > parent_h({parent_h:.0f})")
        if r.x < 0:
            issues.append(f"❌ 左边界越界: x({r.x:.0f}) < 0")
        if r.y < 0:
            issues.append(f"❌ 上边界越界: y({r.y:.0f}) < 0")
    if not issues:
        if parent_w is not None:
            bottom_free = parent_h - (r.y + r.h) if parent_h else 0
            right_free = parent_w - (r.x + r.w) if parent_h else 0
            issues.append(f"✅ 右余{right_free:.0f}px 下余{bottom_free:.0f}px")

    print(f"{indent}[{r.id}] 边界: {'; '.join(issues)}" if issues else
          f"{indent}[{r.id}] 边界: ✅ 子元素均在容器内")

    for child in r.children:
        report_boundary_status(child, r.w, r.h, depth + 1)


# ==============================
# 主入口
# ==============================
if __name__ == "__main__":
    print("=" * 70)
    print("ProfilePage 精确布局验证 v2")
    print("=" * 70)

    spec = build_spec()

    for container_w, label in [(900, "宽屏 900px"), (760, "中屏 760px"),
                                (600, "窄屏 600px")]:
        content_w = container_w - 40  # horizontalPadding 20×2
        print(f"\n{'#' * 70}")
        print(f"## 容器: {label} → 内容区 {content_w}px")
        print(f"{'#' * 70}")

        root_r = validate("root", spec, content_w, 5000)  # 高度不限

        print(f"\n【布局树 (自顶向下)】")
        print_tree(root_r)

        print(f"\n【同级相对位置关系】")
        report_sibling_relationships(root_r)

        print(f"\n【父容器边界状态】")
        report_boundary_status(root_r, content_w, 5000)

        # 汇总 — 使用可变对象替代 nonlocal
        results = {"ok": True}

        def check_issues(r):
            if r.overflow or r.sibling_overlap:
                results["ok"] = False
            for c in r.children:
                check_issues(c)
        check_issues(root_r)

        status = "✅ 全部通过" if results["ok"] else "❌ 存在溢出或重叠"
        print(f"\n  → 验证结论: {status}")
