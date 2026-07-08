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
        tier: "local",
        label: qsTr("本地文库"),
        icon: "ic_fluent_library_20_regular"
    },

    registry: {
        supportsRefresh: true,
        supportsSearch: true,
        supportsProgress: false,
        supportsPreview: true,
        supportsShuffle: false,
        supportsEdit: false,
        supportsCountValidation: false,
        needsContentPrefetch: false,
        tier: "registry",
        label: qsTr("开源文库"),
        icon: "ic_fluent_text_bullet_list_20_regular"
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
        tier: "custom",
        label: qsTr("自定义"),
        icon: "ic_fluent_edit_20_regular"
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
    case "registry": return entrySourceKey(item)
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
    case "registry":
        bridge.loadLibraryText(id)
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
    case "registry": return true  // registry 在 hub 另有 registryLoading 判断
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

// registry 专属 — 暴露 raw 对象里封装的 sourceKey
function entrySourceKey(entry) { return entry ? (entry.sourceKey || "") : "" }


/* =========================================================================
 * 数据分派 —— 信息卡（cardTitle / cardCharCount / ...）
 * ========================================================================= */

function cardTitle(sourceKey, item, previewContent, customLabel) {
    if (sourceKey === "custom") return customLabel || qsTr("自定义文本")
    if (!item) return qsTr("未选择文本")

    switch (sourceKey) {
    case "jisubei":  return item.title || item.name || qsTr("未命名文本")
    case "local":    return articleTitle(item)
    case "registry": return item.label || item.sourceKey || ""
    case "trainer":  return trainerTitle(item)
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
    case "registry":
        return (previewContent && previewContent.length > 0) ? previewContent.length
               : (item.charCount || 0)
    case "trainer":  return trainerEntryCount(item)
    }
    return 0
}

function cardContent(sourceKey, item, previewContent, customText) {
    switch (sourceKey) {
    case "custom":   return (customText || "").substring(0, 200)
    case "jisubei":  return previewContent || ""
    case "registry": return (previewContent || "").substring(0, 200)
    case "local":    return (previewContent || "").substring(0, 200)
    case "trainer":  return (previewContent || "").substring(0, 200)
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

function _syncRegistry(catalog) {
    var arr = []
    if (catalog) {
        for (var i = 0; i < catalog.length; i++) {
            var c = catalog[i]
            var desc = c.description || ""
            if (c.charCount > 0) desc += (desc ? " • " : "") + c.charCount + qsTr("字")
            arr.push({
                title: c.label || c.key || "",
                subtitle: desc,
                raw: {
                    sourceKey: c.key,
                    label: c.label || c.key,
                    charCount: c.charCount || 0,
                    description: c.description || "",
                    category: c.category || "",
                    updateFreq: c.updateFreq || "",
                }
            })
        }
    }
    var message = arr.length > 0 ? qsTr("已加载 %1 篇开源文库文本").arg(arr.length) : qsTr("暂无开源文库文本")
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

function syncItems(sourceKey, rawData) {
    switch (sourceKey) {
    case "jisubei":  return _syncJisuBei(rawData)
    case "local":    return _syncLocal(rawData)
    case "registry": return _syncRegistry(rawData)
    case "trainer":  return _syncTrainer(rawData)
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
    case "registry":
        bridge.loadCatalog()
        return qsTr("正在加载开源文库目录...")
    case "trainer":
        bridge.loadTrainers()
        return qsTr("正在扫描练单器词库...")
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
    case "registry": return hub.catalogLoading || hub.registryLoading
    case "trainer":  return bridge.trainerLoading
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
