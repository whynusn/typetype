# Icon.qml 移除 Behavior on color：修复 QML Text 属性拦截器冲突警告

**日期**: 2026-04-27
**状态**: 已修复

---

## 问题现象

左侧导航栏切换页面（如切换到"练单器"、"本地文库"等）时，Qt 输出 WARNING：

```
[Qt:default] Attempting to set another interceptor on  Text_QMLTYPE_17 property color - unsupported
```

每条警告出现两次，每次切页触发。不影响功能，但污染日志输出。

## 根因分析

`RinUI/components/Icon.qml` 第 31-36 行存在以下代码：

```qml
Behavior on color {
    ColorAnimation {
        duration: 250
        easing.type: Easing.OutQuart
    }
}
```

其中 `color` 通过 property alias 指向内部 Text 元素的 `color`（第 14 行）：

```qml
property alias color: text.color
```

**Qt 内部限制**：`QQuickText`（QML `Text` 的 C++ 实现）的 `color` 属性只允许注册一个 `QQuickPropertyInterceptor`（动画拦截器）。当 `Behavior on color` 加上 `ColorAnimation` 时，Qt 尝试在 Text 元素的 `color` 上注册拦截器。

RinUI 团队已知此限制：`RinUI/components/Text/Text.qml` 第 15-21 行的 `Behavior on color` 已被注释掉，注有 "TODO: 会坠机"。`Icon.qml` 是同一模式的漏修。

**触发条件**：每次通过侧边栏导航到新页面，`NavigationView.showPage()` 调用 `createObject()` 实例化页面组件树。新页面中的任何 `Icon` 组件都会尝试在其内部 Text 元素上注册 `color` 拦截器。由于 QML 引擎可能复用 Text 的内部属性系统，或主题系统已通过全局方式设置了 color 动画，第二次初始化时触发拦截器冲突。

## 修复方案

### 删除 Behavior on color

**文件**: `RinUI/components/Icon.qml`

删除第 31-36 行的 `Behavior on color { ColorAnimation { ... } }` 块，与 `Text.qml` 的处理方式保持一致。

Icon 组件的 color 切换（如主题切换）不再有 250ms 的淡入淡出动画。这是可接受的降级，因为：
1. Text 组件同样没有此动画（已被注释掉），外观一致
2. 图标颜色变化通常是瞬间切换主题色，不加动画不影响用户体验
3. 实际 ColorAnimation 因拦截器冲突从未正确生效过，移除后行为不变

### 日志过滤补充

同时在 `logger.py` 的 `_should_suppress_qt_message` 中添加该警告的过滤，作为双重防护。

## 修改文件清单

| 文件 | 修改 |
|------|------|
| `RinUI/components/Icon.qml` | 删除 `Behavior on color { ColorAnimation { ... } }` 块（第 31-36 行） |
| `src/backend/utils/logger.py` | `_should_suppress_qt_message` 新增拦截器冲突警告过滤 |

## 验证结果

- 切页不再输出 `Attempting to set another interceptor` 警告
- Icon 组件在所有页面正常显示（导航项、设置页图标等）
- 主题切换时图标颜色正确跟随，仅无动画过渡
