.pragma library

/**
 * TextSourceBehaviors — 载文来源的能力注册表 + 数据分派（QML 版 trait 的能力矩阵）。
 *
 * 两层抽象：
 *   1. capabilities[sourceKey]  → 每个来源能做什么（那张矩阵的权威来源）
 *   2. 分派函数（cardTitle / syncItems / loadList / itemsListPropertyName …）
 *      把 hub 的 switch 分支收进来，新增来源只加 1 条 entry。
 *
 * 职责边界：
 *   - capabilities：声明式，UI 直接读 flag 决定显隐。
 *   - 数据分派函数（cardXxx / syncItems / progressKeyAndId）：纯变换，无副作用。
 *   - loadList / syncItems：带 I/O，但把「调哪个 bridge 方法」的决定收进注册表，
 *     hub 只剩一行 dispatch：`var r = SrcBehav.syncItems(currentSource, rawData)`。
 */

var capabilities = {

    jisubei: {
        supportsRefresh: true,
        supportsSearch: true,
        supportsProgress: true,
        supportsPreview: true,
        supportsShuffle: false,
        supportsEdit: false,
        supportsCountValidation: true,
        needsContentPrefetch: true,
        launchKind: "materialized_text",
        tier: "network",
        label: qsTr("极速杯"),
        icon: "ic_fluent_document_text_20_regular"
    },

    local: {
        supportsRefresh: true,
        supportsSearch: true,
        supportsProgress: true,
        supportsPreview: true,
        supportsShuffle: false,
        supportsEdit: true,
        supportsCountValidation: false,
        needsContentPrefetch: true,
        launchKind: "segmented_source",
        tier: "local",
        label: qsTr("本地文库"),
        icon: "ic_fluent_library_20_regular"
    },

    trainer: {
        supportsRefresh: true,
        supportsSearch: true,
        supportsProgress: true,
        supportsPreview: true,
        supportsShuffle: false,
        supportsEdit: false,
        supportsCountValidation: false,
        needsContentPrefetch: true,
        launchKind: "segmented_source",
        tier: "local",
        label: qsTr("练单器"),
        icon: "ic_fluent_apps_list_detail_20_regular"
    },

    custom: {
        supportsRefresh: false,
        supportsSearch: false,
        supportsProgress: false,
        supportsPreview: true,
        supportsShuffle: true,
        supportsEdit: false,
        supportsCountValidation: true,
        needsContentPrefetch: false,
        launchKind: "materialized_text",
        tier: "custom",
        label: qsTr("自定义"),
        icon: "ic_fluent_edit_20_regular"
    },

    repos: {
        supportsRefresh: true,
        supportsSearch: false,
        supportsProgress: false,
        supportsPreview: false,
        supportsShuffle: false,
        supportsEdit: false,
        supportsCountValidation: false,
        needsContentPrefetch: false,
        launchKind: "repos_management",
        tier: "repos",
        label: qsTr("源仓库"),
        icon: "ic_fluent_cloud_arrow_down_20_regular"
    },

    rule: {
        supportsRefresh: false,
        supportsSearch: false,
        supportsProgress: true,
        supportsPreview: false,
        supportsShuffle: false,
        supportsEdit: false,
        supportsCountValidation: false,
        needsContentPrefetch: false,
        launchKind: "repos_management",
        tier: "rule",
        label: qsTr("规则源"),
        icon: "ic_fluent_code_20_regular"
    },

    script: {
        supportsRefresh: false,
        supportsSearch: false,
        supportsProgress: true,
        supportsPreview: false,
        supportsShuffle: false,
        supportsEdit: false,
        supportsCountValidation: false,
        needsContentPrefetch: false,
        launchKind: "repos_management",
        tier: "script",
        label: qsTr("脚本源"),
        icon: "ic_fluent_code_script_20_regular"
    }
}


/* =========================================================================
 * 预览分派 — 统一处理所有来源的异步预览加载与去重
 * ========================================================================= */

// 对于每个需要 async prefetch 的来源，提取用于预览请求的标识
function previewId(sourceKey, item) {
    if (!item) return ""
    switch (sourceKey) {
    case "jisubei":  return item.id !== undefined ? item.id : ""
    case "local":    return articleId(item)
    case "trainer":  return trainerId(item)
    }
    return ""
}

// 通过 bridge 发起异步预览请求，统一分派
function startPreview(bridge, sourceKey, id) {
    if (!bridge || !id) return false
    switch (sourceKey) {
    case "jisubei":
        bridge.getTextContentById(id)
        return true
    case "local":
        bridge.loadLocalArticlePreview(id)
        return true
    case "trainer":
        bridge.loadTrainerPreview(id)
        return true
    }
    return false
}

// 统一判断「载入跟打」按钮是否可点亮
// local/trainer 本地读取不依赖预览内容（canLoad 在 hub 中被调用时不传 previewContent）
function canLoadButton(sourceKey, selectedItem, previewContent) {
    if (!selectedItem) return false
    switch (sourceKey) {
    case "custom":  return customTextLen() > 0
    case "jisubei": return previewContent && previewContent.length > 0
    default:        return true  // local / trainer 选中即可
    }
}


/* =========================================================================
 * 公共辅助（纯变换）
 * ========================================================================= */

function articleId(article) {
    if (!article) return ""
    return article.articleId !== undefined ? article.articleId
         : article.article_id !== undefined ? article.article_id
         : article.id !== undefined ? article.id
         : article.client_id !== undefined ? article.client_id : ""
}

function articleTitle(article) { return article ? (article.title || article.name || article.filename || qsTr("未命名文章")) : qsTr("未选择文章") }
function articleCharCount(article) { return article ? (article.charCount || article.char_count || article.contentLength || article.content_length || article.length || 0) : 0 }

function trainerId(item) { return item ? (item.trainerId || item.trainer_id || item.id || "") : "" }
function trainerTitle(item) { return item ? (item.title || item.name || trainerId(item) || qsTr("未命名词库")) : qsTr("未选择词库") }
function trainerEntryCount(item) { return item ? (item.entryCount || item.entry_count || item.count || 0) : 0 }



/* =========================================================================
 * 数据分派 —— 信息卡（cardTitle / cardCharCount / ...）
 * ========================================================================= */

function cardTitle(sourceKey, item, previewContent, customLabel) {
    if (sourceKey === "custom") return customLabel || qsTr("自定义文本")
    if (!item) return qsTr("未选择文本")

    switch (sourceKey) {
    case "jisubei":  return item.title || item.name || qsTr("未命名文本")
    case "local":    return articleTitle(item)
    case "trainer":  return trainerTitle(item)
    case "rule":     return item.title || item.source_label || item._rule_id || qsTr("规则文本")
    case "script":   return item.title || item.source_label || qsTr("脚本文本")
    }
    return qsTr("未选择文本")
}

function cardCharCount(sourceKey, item, previewContent, customLen) {
    if (sourceKey === "custom") return customLen || 0
    if (!item) return 0

    switch (sourceKey) {
    case "jisubei":
        return (previewContent && previewContent.length > 0) ? previewContent.length
               : (item.charCount || item.char_count || 0)
    case "local":    return articleCharCount(item)
    case "trainer":  return trainerEntryCount(item)
    case "rule":     return item.char_count || item.charCount || 0
    case "script":   return item.char_count || item.charCount || 0
    }
    return 0
}

function cardContent(sourceKey, item, previewContent, customText) {
    switch (sourceKey) {
    case "custom":   return (customText || "").substring(0, 1000)
    case "jisubei":  return (previewContent || "").substring(0, 1000)
    case "local":    return (previewContent || "").substring(0, 1000)
    case "trainer":  return (previewContent || "").substring(0, 1000)
    case "rule":     return (item ? (item.content || item.preview || "").substring(0, 1000) : "")
    case "script":   return (item ? (item.content || item.preview || "").substring(0, 1000) : "")
    }
    return ""
}

function cardIdText(sourceKey, item, serverTextId) {
    if (sourceKey === "jisubei" && serverTextId) return qsTr("ID: %1").arg(serverTextId)
    return ""
}

function progressKeyAndId(sourceKey, item, previewContent, customText, serverTextId) {
    switch (sourceKey) {
    case "local":
        return { key: "local_article", identifier: articleId(item) || "" }
    case "trainer":
        return { key: "trainer", identifier: trainerId(item) || "" }
    case "jisubei":
        return { key: "custom_text", identifier: previewContent || "" }
    case "custom":
        return { key: "custom_text", identifier: customText || "" }
    case "rule":
    case "script":
        // 进度键格式：ott:{authority}:{entry_id}@{revision_id}
        if (item && item.authority && item.entry_id && item.current_revision_id) {
            return {
                key: "ott",
                identifier: item.authority + ":" + item.entry_id + "@" + item.current_revision_id
            }
        }
        return { key: "", identifier: "" }
    }
    return { key: "", identifier: "" }
}

// custom 来源字数校验：custom 没有统一的 selectedItem，这里暴露给 hub 注入
var _customTextLenFn = null
function registerCustomTextLenGetter(fn) { _customTextLenFn = fn }
function customTextLen() { return _customTextLenFn ? _customTextLenFn() : 0 }


/* =========================================================================
 * 列表同步分派 —— syncItems(sourceKey, rawData) → { items, statusMessage }
 * 把「原始 bridge 数据 → 统一的 { title, subtitle, raw } 列表」的 per-source
 * 变换收进注册表。新增来源只需加一个 convertXxx 函数。
 * ========================================================================= */

function _syncJisuBei(texts) {
    var arr = []
    if (texts) {
        for (var i = 0; i < texts.length; i++) {
            var t = texts[i]
            arr.push({ title: t.title || "", subtitle: qsTr("%1 字").arg(t.charCount !== undefined ? t.charCount : 0), raw: t })
        }
    }
    var message = arr.length > 0 ? qsTr("已加载 %1 篇文本").arg(arr.length) : qsTr("未找到文本")
    return { items: arr, statusMessage: message }
}

function _syncLocal(articles) {
    var arr = []
    if (articles) {
        for (var i = 0; i < articles.length; i++) {
            var a = articles[i]
            arr.push({ title: articleTitle(a), subtitle: qsTr("%1 字").arg(articleCharCount(a)), raw: a })
        }
    }
    var message = arr.length > 0 ? qsTr("已加载 %1 篇本地文章").arg(arr.length) : qsTr("未找到本地文章")
    return { items: arr, statusMessage: message }
}

function _syncTrainer(items) {
    var arr = []
    if (items) {
        for (var i = 0; i < items.length; i++) {
            var it = items[i]
            arr.push({ title: trainerTitle(it), subtitle: qsTr("%1 项").arg(trainerEntryCount(it)), raw: it })
        }
    }
    var message = arr.length > 0 ? qsTr("已加载 %1 个词库").arg(arr.length) : qsTr("未找到练单器词库")
    return { items: arr, statusMessage: message }
}

function _syncRepos(repos) {
    var arr = []
    if (repos) {
        for (var i = 0; i < repos.length; i++) {
            var r = repos[i]
            var subtitleParts = []
            if (r.name) subtitleParts.push(r.name)
            if (r.error) subtitleParts.push(r.error)
            else if (r.loaded === false) subtitleParts.push(qsTr("未加载"))
            else subtitleParts.push(qsTr("%1 个源").arg(r.instance_count || r.instanceCount || 0))
            arr.push({
                title: r.url || "",
                subtitle: subtitleParts.join(" · "),
                raw: r
            })
        }
    }
    var message = arr.length > 0 ? qsTr("已加载 %1 个源仓库").arg(arr.length) : qsTr("暂无源仓库订阅")
    return { items: arr, statusMessage: message }
}

function _syncRule(entries) {
    var arr = []
    if (entries) {
        for (var i = 0; i < entries.length; i++) {
            var e = entries[i]
            arr.push({
                title: e.title || e.source_label || qsTr("规则文本"),
                subtitle: qsTr("%1 字").arg(e.char_count || e.charCount || 0),
                raw: e
            })
        }
    }
    var message = arr.length > 0 ? qsTr("已加载 %1 条规则文本").arg(arr.length) : qsTr("规则未抓到文本")
    return { items: arr, statusMessage: message }
}

function _syncScript(entries) {
    // 与 _syncRule 共享渲染逻辑
    return _syncRule(entries)
}

function syncItems(sourceKey, rawData) {
    switch (sourceKey) {
    case "jisubei":  return _syncJisuBei(rawData)
    case "local":    return _syncLocal(rawData)
    case "trainer":  return _syncTrainer(rawData)
    case "repos":    return _syncRepos(rawData)
    case "rule":     return _syncRule(rawData)
    case "script":   return _syncScript(rawData)
    }
    return { items: [], statusMessage: "" }
}


/* =========================================================================
 * 列表加载分派 —— loadList(bridge, sourceKey) → 发出对应 bridge 调用 + 状态消息
 * custom 无列表，返回 null。
 * ========================================================================= */

function loadList(bridge, sourceKey) {
    switch (sourceKey) {
    case "jisubei":
        bridge.loadTextList("jisubei")
        return qsTr("正在加载极速杯文本列表...")
    case "local":
        bridge.loadLocalArticles()
        return qsTr("正在扫描本地文库...")
    case "trainer":
        bridge.loadTrainers()
        return qsTr("正在扫描练单器词库...")
    case "repos":
        bridge.refreshRepos()
        return qsTr("正在加载源仓库订阅...")
    }
    return null  // custom 无列表加载
}


/* =========================================================================
 * 加载中继 —— isLoading(sourceKey, bridge, hub)
 * ========================================================================= */

function isLoading(sourceKey, bridge, hub) {
    if (!bridge) return false
    switch (sourceKey) {
    case "jisubei":  return bridge.textListLoading
    case "local":    return bridge.localArticleLoading
    case "trainer":  return bridge.trainerLoading
    case "repos":    return hub.reposLoading
    case "custom":   return false
    }
    return false
}


/* =========================================================================
 * 当前来源列表属性名 —— 供 selectListItem 统一读取
 * ========================================================================= */

function itemsListPropertyName(sourceKey) {
    return sourceKey + "Items"
}
