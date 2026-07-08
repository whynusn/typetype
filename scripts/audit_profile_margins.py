"""
ProfilePage 四边余量审计 — 逐容器检查 text 在容器中的上/下/左/右剩余空间
"""
import math

FONT = {
    "caption":   {"size":12,"lh":18,"ch":12,"en":7},
    "body-strong":{"size":14,"lh":21,"ch":14,"en":8},
    "subtitle":  {"size":20,"lh":30,"ch":20,"en":11},
    "body":      {"size":14,"lh":21,"ch":14,"en":8},
    "title":     {"size":28,"lh":42,"ch":28,"en":16},
}

def tw(text,font):
    f=FONT[font]; t=0
    for c in text:
        if '\u4e00'<=c<='\u9fff': t+=f["ch"]
        elif c.isascii(): t+=f["en"]
        elif c==' ': t+=f["size"]*0.3
        else: t+=f["ch"]
    return round(t,1)

SPACING={"xs":4,"sm":8,"md":16,"lg":24}
MARGIN={"tight":8,"normal":16,"loose":24}

def audit_card(label, inner_w, inner_h, texts):
    """
    检查一张卡片内，文字内容的四边余量。
    texts: [(text, font, x_offset_from_padding, y_offset_from_padding, h), ...]
    所有偏移量相对于 content area (已扣除 padding)
    """
    print(f"\n{'─'*60}")
    print(f"📦 {label}  (内容区 {inner_w}×{inner_h}px)")
    print(f"{'─'*60}")
    for txt, font, xo, yo, th in texts:
        w = tw(txt, font)
        h = FONT[font]["lh"]
        left = xo
        right = inner_w - xo - w
        top = yo
        bottom = inner_h - yo - h
        status = "✅" if all(v >= 0 for v in [left,right,top,bottom]) else "❌"
        print(f"  {status} [{txt}] w{w}h{h}")
        print(f"     左余{left:.0f}  右余{right:.0f}  上余{top:.0f}  下余{bottom:.0f}")

def audit():
    pw,ph = 860, 2000  # 宽屏基准

    # ── 1. 登录卡片 ──
    pad=MARGIN["loose"]  # 24
    card_max=480
    iw=card_max-2*pad  # 432
    # content height: icon 36 + spacing 16 + text 21 + spacing 16 + btnrow 32 = 121
    audit_card("登录卡片", iw, 121, [
        ("登录后可查看个人成绩与统计","body-strong", 0, 52, 21),  # icon 36 + spacing 16
        ("登录","body-strong", (iw-176)/2, 89, 32),  # btn row x_center
    ])

    # ── 2. 用户信息卡片 ──
    pad=MARGIN["normal"]  # Frame padding=16 → anchors.fill
    iw2=860-2*pad  # 828 (RowLayout width)
    rlh=56  # RowLayout height = max(avatar 56, ColumnLayout 52, text 21, btn ~32)
    # ColumnLayout(height 52) centered in RowLayout(height 56) → y_offset=2
    cl_y=2
    audit_card("用户信息卡片", iw2, rlh, [
        ("八九寺真宵","subtitle", 72, cl_y, 30),   # x=56+16=72
        ("@username","caption", 72, cl_y+30+4, 18), # below nickname
        ("99999 场","body-strong", iw2-80-16-62, (rlh-21)/2, 21),  # before btn+gap
    ])

    # ── 3. 统计卡片 (GridLayout 3列, 每卡 ~279px) ──
    card_w=(860-24)/3  # Grid 3列, gap 16*2=32, (860-32)/3=276
    iw3=card_w-MARGIN["normal"]*2  # 276-32=244
    # Column content: label_row(18) + spacing(8) + value_row(42) = 68
    audit_card("统计卡片(平均速度)", iw3, 68, [
        ("平均速度","caption", 22, 0, 18),  # icon 16 + spacing 6
        ("999.9","title", 0, 26, 42),  # label 18 + spacing 8
        ("字/分","caption", 80+4, 26, 18),  # value spacing 4
    ])
    audit_card("统计卡片(总场次)", iw3, 68, [
        ("总场次","caption", 22, 0, 18),
        ("99999","title", 0, 26, 42),
        ("场","caption", 80+4, 26, 18),
    ])

    # ── 4. 每日趋势卡片 ──
    pad=MARGIN["normal"]
    iw4=860-2*pad  # 828
    # header(21) + spacing(8) + chart(120) = 149
    audit_card("每日趋势卡片", iw4, 149, [
        ("最近 30 天打字量","body-strong", 0, 0, 21),
        ("字/天","caption", iw4-31, 1, 18),  # right-aligned, y centered in 21
    ])

    # ── 5. 历史成绩表 ──
    pad=MARGIN["normal"]
    iw5=860-2*pad  # 828
    # header row: date(120) + seg(40) + speed(fill) + acc(fill) + chars(60) + spacing 4*4=16
    fill_w=(iw5-120-40-60-16)/2  # =296 each
    hdr_x=[0, 120+4, 120+40+8, 120+40+fill_w+12, 120+40+2*fill_w+16]
    hdr_w=[120, 40, fill_w, fill_w, 60]
    texts_5=[]
    for i,(lab,fw) in enumerate(zip(["日期","段","速度","键准","字数"], hdr_w)):
        tx = hdr_x[i]
        al = fw-24 if i>=2 else 0  # right-aligned text offset from left
        texts_5.append((lab if i<2 else "","caption", tx, 0, 18))
    # 省略具体的右对齐文字位置；用空串跳过
    audit_card("成绩表头", iw5, 18, texts_5)
    audit_card("成绩表(数据行)", iw5, 36, [
        ("2026-07-08 16:35","caption", 4, 9, 18), # leftMargin xs=4
        ("12","caption", 124+4, 9, 18),  # after date(120)+spacing(4)
        ("123.4","caption", hdr_x[2]+fill_w-35, 9, 18), # right-aligned
        ("99.9%","caption", hdr_x[3]+fill_w-35, 9, 18),
        ("999字","caption", hdr_x[4]+60-40, 9, 18), # right-aligned
    ])

if __name__=="__main__":
    audit()
