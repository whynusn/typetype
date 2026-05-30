pragma Singleton
import QtQuick 2.15

QtObject {
    /**
     * 从恢复设置中读取 criteria 并调用 setSliceCriteria。
     * restoredSettings: 对象（非 JSON 字符串），来自 getRestoredSliceSettings() 的解析结果。
     */
    function applyRestoredCriteria(appBridge, restoredSettings, settingsPanel, criteriaPanel) {
        var s = restoredSettings || {};
        if (!appBridge) return;
        var criteriaOn = s.condition_on !== undefined ? s.condition_on : criteriaPanel.conditionChecked;
        appBridge.setSliceCriteria(
            criteriaOn ? (s.key_stroke_min || criteriaPanel.keyStrokeMinValue) : 0,
            criteriaOn ? (s.speed_min || criteriaPanel.speedMinValue) : 0,
            criteriaOn ? (s.accuracy_min || criteriaPanel.accuracyMinValue) : 0,
            criteriaOn ? (s.pass_count_min || criteriaPanel.passCountMinValue) : 1,
            criteriaOn ? (s.on_fail_action || criteriaPanel.onFailActionValue) : "none",
            s.advance_mode || criteriaPanel.advanceModeValue,
            s.full_shuffle !== undefined ? s.full_shuffle : settingsPanel.fullShuffleChecked,
            s.auto_decrease_enabled !== undefined ? s.auto_decrease_enabled : criteriaPanel.autoDecreaseEnabled,
            s.key_stroke_decrease || criteriaPanel.keyStrokeDecreaseValue,
            s.speed_decrease || criteriaPanel.speedDecreaseValue,
            s.accuracy_decrease || criteriaPanel.accuracyDecreaseValue
        );
    }

    /**
     * 完整的 _startWithCriteria 流程：设置 criteria → 导航 → 调 loader。
     * loadFn: function(size) — 接收计算后的 slice size，执行实际加载。
     */
    function startWithCriteria(appBridge, navigationView, settingsPanel, criteriaPanel, restoredSettings, loadFn) {
        var s = restoredSettings || {};
        var size = s.slice_size > 0 ? s.slice_size : settingsPanel.sliceSize;
        applyRestoredCriteria(appBridge, s, settingsPanel, criteriaPanel);
        if (navigationView)
            navigationView.push(Qt.resolvedUrl("../pages/TypingPage.qml"));
        Qt.callLater(function() {
            if (appBridge && loadFn) loadFn(size);
        });
    }
}
