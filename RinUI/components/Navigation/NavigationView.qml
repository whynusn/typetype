import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 2.15
import "../../themes"
import "../../components"
import "../../windows"


RowLayout {
    // 外观 / Appearance //
    property bool appLayerEnabled: true  // 应用层背景
    property alias navExpandWidth: navigationBar.expandWidth  // 导航栏宽度
    property alias navMinimumExpandWidth: navigationBar.minimumExpandWidth  // 导航栏保持展开时窗口的最小宽度

    property alias navigationBar: navigationBar  // 导航栏
    property alias navigationItems: navigationBar.navigationItems  // 导航栏item
    property alias currentPage: navigationBar.currentPage  // 当前页面索引
    property string defaultPage: ""  // 默认索引项
    property var window: parent  // 窗口对象
    
    // Global state injection //
    property bool loggedin: false  // 登录状态，从 Main.qml 传递给所有页面

    // 页面组件缓存(Component)和实例缓存
    property var componentCache: ({})
    property var pageInstances: ({})
    property var currentPageInstance: null

    signal pageChanged()  // 页面切换信号

    id: navigationView
    anchors.fill: parent

    Connections {
        target: window
        function onWidthChanged() {
            if (navigationBar.isNotOverMinimumWidth()) {
                if (!navigationBar.collapsed) {
                    navigationBar.collapsed = true
                    navigationBar.collapsedByAutoResize = true
                }
            } else {
                if (navigationBar.collapsed && navigationBar.collapsedByAutoResize) {
                    navigationBar.collapsed = false
                    navigationBar.collapsedByAutoResize = false
                }
            }
        }
    }

    Component.onCompleted: {
        if (navigationBar.isNotOverMinimumWidth()) {
            if (!navigationBar.collapsed) {
                navigationBar.collapsed = true
                navigationBar.collapsedByAutoResize = true
            }
        }
        if (navigationItems.length > 0) {
            let initialPage = defaultPage !== "" ? defaultPage : navigationItems[0].page
            showPage(initialPage)
        }
    }

    NavigationBar {
        id: navigationBar
        window: navigationView.window
        windowTitle: window.title
        windowIcon: window.icon
        windowWidth: window.width
        closeButtonVisible: window && window.closeVisible !== undefined ? window.closeVisible : true
        minimizeButtonVisible: window && window.minimizeVisible !== undefined ? window.minimizeVisible : true
        maximizeButtonVisible: window && window.maximizeVisible !== undefined ? window.maximizeVisible : true
        useNativeMacControls: window && window.useNativeMacFrame !== undefined ? window.useNativeMacFrame : false
        stackView: pageContainer  // 指向容器以保持 NavigationItem 兼容性
        z: 999
        Layout.fillHeight: true
    }

    // 主体内容区域
    Item {
        id: pageContainer
        Layout.fillWidth: true
        Layout.fillHeight: true

        // 导航栏展开自动收起
        MouseArea {
            id: collapseCatcher
            anchors.fill: parent
            z: 1
            hoverEnabled: true
            acceptedButtons: Qt.AllButtons

            visible: !navigationBar.collapsed && navigationBar.isNotOverMinimumWidth()

            onClicked: {
                navigationBar.collapsed = true
                navigationBar.collapsedByAutoResize = false
            }
        }

        Rectangle {
            id: appLayer
            width: parent.width + Utils.windowDragArea + radius
            height: parent.height + Utils.windowDragArea + radius
            color: Theme.currentTheme.colors.layerColor
            border.color: Theme.currentTheme.colors.cardBorderColor
            border.width: 1
            opacity: (window && window.appLayerEnabled !== undefined) ? window.appLayerEnabled : navigationView.appLayerEnabled
            radius: Theme.currentTheme.appearance.windowRadius
        }

        // 同步所有页面实例的尺寸
        onWidthChanged: {
            let keys = Object.keys(pageInstances)
            for (let i = 0; i < keys.length; i++) {
                let instance = pageInstances[keys[i]]
                if (instance) instance.width = pageContainer.width
            }
        }
        onHeightChanged: {
            let keys = Object.keys(pageInstances)
            for (let i = 0; i < keys.length; i++) {
                let instance = pageInstances[keys[i]]
                if (instance) instance.height = pageContainer.height
            }
        }
    }

    // 安全设置页面属性（兼容没有该属性的页面如 SettingsPage）
    function setPropertySafe(obj, prop, value) {
        if (obj && prop in obj) {
            obj[prop] = value
        }
    }

    // 登录状态变化时同步给所有已创建的页面实例
    onLoggedinChanged: {
        let keys = Object.keys(pageInstances)
        for (let i = 0; i < keys.length; i++) {
            setPropertySafe(pageInstances[keys[i]], "loggedin", loggedin)
        }
    }

    function showPage(pageUrl, properties) {
        let pageKey = normalizeKeyFromPage(pageUrl)
        if (currentPage === pageKey) return

        if (!componentCache[pageKey]) {
            let component = Qt.createComponent(pageUrl)
            if (component.status === Component.Error) {
                console.error("Failed to load component:", pageUrl, component.errorString())
                return
            }
            componentCache[pageKey] = component
        }

        let pageInstance = pageInstances[pageKey]
        if (!pageInstance) {
            let targetObjectName = pageKey.includes("/") ?
                pageKey.split("/").pop().replace(".qml", "") : pageKey
            pageInstance = componentCache[pageKey].createObject(pageContainer, Object.assign({}, properties || {}, {
                objectName: targetObjectName,
                visible: false
            }))
            if (!pageInstance) {
                console.error("Failed to create page instance:", pageKey)
                return
            }
            pageInstance.width = pageContainer.width
            pageInstance.height = pageContainer.height
            // 安全设置可选属性（部分页面如 SettingsPage 没有这些属性）
            setPropertySafe(pageInstance, "loggedin", navigationView.loggedin)
            setPropertySafe(pageInstance, "active", false)
            pageInstances[pageKey] = pageInstance
        }

        if (currentPageInstance && currentPageInstance !== pageInstance) {
            setPropertySafe(currentPageInstance, "active", false)
            currentPageInstance.visible = false
        }

        pageInstance.visible = true
        setPropertySafe(pageInstance, "active", true)
        currentPageInstance = pageInstance
        currentPage = pageKey
        pageChanged()
    }

    function push(page, properties) {
        if (properties === undefined) properties = {}
        showPage(page, properties)
    }

    function safePush(page, reload, fromNavigation, properties) {
        if (properties === undefined) properties = {}
        let pageKey = normalizeKeyFromPage(page)
        if (reload && pageInstances[pageKey]) {
            pageInstances[pageKey].destroy()
            delete pageInstances[pageKey]
        }
        showPage(page, properties)
    }

    function normalizeKeyFromPage(page) {
        if (page instanceof Component) {
            return page.objectName || page.toString()
        } else if (typeof page === "string") {
            return page
        } else {
            return page.toString()
        }
    }
}
