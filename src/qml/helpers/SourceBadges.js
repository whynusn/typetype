.pragma library

/**
 * SourceBadges — 开源文库源的 trust/tier 徽章文案与配色单一事实源。
 *
 * 使用方：RepoEntriesPanel（组头徽章）、RepoConfigDialog（信任状态行）、
 * SourceInfoDialog（tier 标签）。新增 trust_state / source_type 时只改这里。
 *
 * 注意：.pragma library 无法访问 RinUI Theme 单例，配色函数由调用方
 * 传入 Theme.currentTheme.colors。
 */

// ---- 信任状态 ----

// 未知/空状态返回 ""（调用方据此隐藏徽章）
function trustLabel(state) {
    if (state === "verified") return qsTr("已验证")
    if (state === "pending") return qsTr("待确认")
    if (state === "failed") return qsTr("验证失败")
    if (state === "unverified") return qsTr("未验证")
    return ""
}

function trustColor(state, colors) {
    if (state === "verified") return colors.systemSuccessColor
    if (state === "pending") return colors.systemCautionColor
    if (state === "failed") return colors.systemCriticalColor
    return colors.textSecondaryColor
}

// ---- 源类型 tier ----

// 短标签（组头徽章）
function tierShort(type) {
    if (type === "ott-instance") return "L0"
    if (type === "ott-rule") return "L1"
    if (type === "ott-bridge") return "L2"
    if (type === "ott-script") return "L3"
    return ""
}

// 长标签（详情弹窗）
function tierLabel(type) {
    if (type === "ott-instance") return qsTr("L0 静态实例")
    if (type === "ott-rule") return qsTr("L1 声明式规则")
    if (type === "ott-bridge") return qsTr("L2 桥接")
    if (type === "ott-script") return qsTr("L3 签名脚本")
    return qsTr("未知类型")
}
