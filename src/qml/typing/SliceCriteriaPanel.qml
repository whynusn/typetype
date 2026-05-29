import QtQuick 2.15
import QtQuick.Controls 2.15 as QQC
import QtQuick.Layouts 1.15
import RinUI

Frame {
    id: root
    radius: 6
    hoverable: false
    padding: 8

    // --- 外部可读写属性 ---
    property double keyStrokeMinValue: 6.0
    property int speedMinValue: 100
    property int accuracyMinValue: 95
    property int passCountMinValue: 1
    property string onFailActionValue: "retype"
    property bool autoDecreaseEnabled: false
    property double keyStrokeDecreaseValue: 0.0
    property int speedDecreaseValue: 0
    property int accuracyDecreaseValue: 0

    readonly property string validationMessage: _buildValidationMessage()

    // 别名属性
    property alias conditionChecked: conditionCheck.checked
    property alias advanceModeValue: advanceModeCombo.currentValue
    property bool fullShuffleChecked: false

    function _buildValidationMessage() {
        var ks = keyStrokeMinSpin.value / 100;
        if (isNaN(ks) || ks < 0 || ks > 999)
            return "击键阈值必须在 0 到 999 之间";

        var spd = speedMinSpin.value;
        if (spd < 0 || spd > 999)
            return "速度阈值必须在 0 到 999 之间";

        var acc = accuracyMinSpin.value;
        if (acc < 0 || acc > 100)
            return "键准阈值必须在 0 到 100 之间";

        var pc = passCountMinSpin.value;
        if (pc < 1 || pc > 9999)
            return "达标次数必须在 1 到 9999 之间";

        if (autoDecreaseEnabled) {
            var kd = keyStrokeDecreaseSpin.value / 100;
            if (isNaN(kd) || kd < 0 || kd > 100)
                return "击键降低值必须在 0 到 100 之间";

            var sd = speedDecreaseSpin.value;
            if (sd < 0 || sd > 999)
                return "速度降低值必须在 0 到 999 之间";

            var ad = accuracyDecreaseSpin.value;
            if (ad < 0 || ad > 100)
                return "键准降低值必须在 0 到 100 之间";
        }

        return "";
    }

    // --- 初始化：外部属性 → 控件 ---
    Component.onCompleted: {
        _applyExternalValues();
    }

    // --- 外部属性变化时同步到控件（避免回写循环）---
    onKeyStrokeMinValueChanged: {
        var expected = Math.round(keyStrokeMinValue * 100);
        if (keyStrokeMinSpin.value !== expected) keyStrokeMinSpin.value = expected;
    }
    onSpeedMinValueChanged: {
        if (speedMinSpin.value !== speedMinValue) speedMinSpin.value = speedMinValue;
    }
    onAccuracyMinValueChanged: {
        if (accuracyMinSpin.value !== accuracyMinValue) accuracyMinSpin.value = accuracyMinValue;
    }
    onPassCountMinValueChanged: {
        if (passCountMinSpin.value !== passCountMinValue) passCountMinSpin.value = passCountMinValue;
    }
    onKeyStrokeDecreaseValueChanged: {
        var expected = Math.round(keyStrokeDecreaseValue * 100);
        if (keyStrokeDecreaseSpin.value !== expected) keyStrokeDecreaseSpin.value = expected;
    }
    onSpeedDecreaseValueChanged: {
        if (speedDecreaseSpin.value !== speedDecreaseValue) speedDecreaseSpin.value = speedDecreaseValue;
    }
    onAccuracyDecreaseValueChanged: {
        if (accuracyDecreaseSpin.value !== accuracyDecreaseValue) accuracyDecreaseSpin.value = accuracyDecreaseValue;
    }
    onOnFailActionValueChanged: {
        if (onFailActionCombo.currentValue !== onFailActionValue) {
            for (var i = 0; i < onFailActionCombo.count; i++) {
                if (onFailActionCombo.model.get(i).value === onFailActionValue) {
                    onFailActionCombo.currentIndex = i;
                    break;
                }
            }
        }
    }

    function _applyExternalValues() {
        keyStrokeMinSpin.value = Math.round(keyStrokeMinValue * 100);
        speedMinSpin.value = speedMinValue;
        accuracyMinSpin.value = accuracyMinValue;
        passCountMinSpin.value = passCountMinValue;
        keyStrokeDecreaseSpin.value = Math.round(keyStrokeDecreaseValue * 100);
        speedDecreaseSpin.value = speedDecreaseValue;
        accuracyDecreaseSpin.value = accuracyDecreaseValue;
    }

    // --- 控件 → 外部属性（单向，无回写）---
    function _syncFromControls() {
        root.keyStrokeMinValue = keyStrokeMinSpin.value / 100;
        root.speedMinValue = speedMinSpin.value;
        root.accuracyMinValue = accuracyMinSpin.value;
        root.passCountMinValue = passCountMinSpin.value;
        root.keyStrokeDecreaseValue = keyStrokeDecreaseSpin.value / 100;
        root.speedDecreaseValue = speedDecreaseSpin.value;
        root.accuracyDecreaseValue = accuracyDecreaseSpin.value;
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Layout.fillWidth: true

            Text {
                typography: Typography.BodyStrong
                text: qsTr("自动推进")
            }

            Item { Layout.fillWidth: true }

            CheckBox {
                id: conditionCheck
                text: qsTr("开启")
            }
        }

        Text {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            typography: Typography.Caption
            text: qsTr("每段达标后自动跳转下一段，达标条件与未达标行为如下：")
            wrapMode: Text.Wrap
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 8

            Text {
                typography: Typography.Body
                text: qsTr("推进模式")
            }

            ComboBox {
                id: advanceModeCombo
                model: ListModel {
                    ListElement { text: "顺序下一段"; value: "sequential" }
                    ListElement { text: "随机下一段"; value: "random" }
                }
                textRole: "text"
                valueRole: "value"
            }

            Item { Layout.fillWidth: true }
        }

        Text {
            visible: conditionCheck.checked
            typography: Typography.Body
            text: qsTr("达标条件")
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 6

            Text { typography: Typography.Body; text: qsTr("击键 ≥") }
            SpinBox {
                id: keyStrokeMinSpin
                Layout.preferredWidth: 128
                Layout.preferredHeight: 34
                from: 0; to: 9999; value: 600; stepSize: 1; editable: true
                textFromValue: function(value, locale) {
                    return (value / 100).toFixed(2);
                }
                valueFromText: function(text, locale) {
                    return Math.round(parseFloat(text) * 100);
                }
                onValueChanged: root._syncFromControls()
            }
            Text { typography: Typography.Caption; text: qsTr("次/秒") }

            Text {
                visible: root.autoDecreaseEnabled
                typography: Typography.Caption
                text: qsTr("失败降")
                color: Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#4b88ff"
            }
            SpinBox {
                id: keyStrokeDecreaseSpin
                visible: root.autoDecreaseEnabled
                Layout.preferredWidth: 100
                Layout.preferredHeight: 34
                from: 0; to: 10000; value: 0; stepSize: 1; editable: true
                textFromValue: function(value, locale) {
                    return (value / 100).toFixed(2);
                }
                valueFromText: function(text, locale) {
                    return Math.round(parseFloat(text) * 100);
                }
                onValueChanged: root._syncFromControls()
            }

            Item { Layout.fillWidth: true }
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 6

            Text { typography: Typography.Body; text: qsTr("速度 ≥") }
            SpinBox {
                id: speedMinSpin
                Layout.preferredWidth: 128
                Layout.preferredHeight: 34
                from: 0; to: 999; value: 100; stepSize: 10; editable: true
                onValueChanged: root._syncFromControls()
            }
            Text { typography: Typography.Caption; text: qsTr("字/分") }

            Text {
                visible: root.autoDecreaseEnabled
                typography: Typography.Caption
                text: qsTr("失败降")
                color: Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#4b88ff"
            }
            SpinBox {
                id: speedDecreaseSpin
                visible: root.autoDecreaseEnabled
                Layout.preferredWidth: 100
                Layout.preferredHeight: 34
                from: 0; to: 999; value: 0; stepSize: 1; editable: true
                onValueChanged: root._syncFromControls()
            }
            Text {
                visible: root.autoDecreaseEnabled
                typography: Typography.Caption
                text: qsTr("字/分")
            }

            Item { Layout.fillWidth: true }
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 6

            Text { typography: Typography.Body; text: qsTr("键准 ≥") }
            SpinBox {
                id: accuracyMinSpin
                Layout.preferredWidth: 128
                Layout.preferredHeight: 34
                from: 0; to: 100; value: 95; stepSize: 5; editable: true
                onValueChanged: root._syncFromControls()
            }
            Text { typography: Typography.Caption; text: "%" }

            Text {
                visible: root.autoDecreaseEnabled
                typography: Typography.Caption
                text: qsTr("失败降")
                color: Theme.currentTheme ? Theme.currentTheme.colors.primaryColor : "#4b88ff"
            }
            SpinBox {
                id: accuracyDecreaseSpin
                visible: root.autoDecreaseEnabled
                Layout.preferredWidth: 100
                Layout.preferredHeight: 34
                from: 0; to: 100; value: 0; stepSize: 1; editable: true
                onValueChanged: root._syncFromControls()
            }
            Text {
                visible: root.autoDecreaseEnabled
                typography: Typography.Caption
                text: "%"
            }

            Item { Layout.fillWidth: true }
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 6

            Text { typography: Typography.Body; text: qsTr("连达标 ≥") }
            SpinBox {
                id: passCountMinSpin
                Layout.preferredWidth: 128
                Layout.preferredHeight: 34
                from: 1; to: 9999; value: 1; stepSize: 1; editable: true
                onValueChanged: root._syncFromControls()
            }
            Text { typography: Typography.Caption; text: qsTr("次") }
            Item { Layout.fillWidth: true }
        }

        Text {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            typography: Typography.Caption
            text: qsTr("击键、速度、键准均达标且无错字算一次合格")
            wrapMode: Text.Wrap
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 8

            Text { typography: Typography.Body; text: qsTr("未达标/有错字") }

            ComboBox {
                id: onFailActionCombo
                model: ListModel {
                    ListElement { text: "乱序重打"; value: "shuffle" }
                    ListElement { text: "重打"; value: "retype" }
                    ListElement { text: "无动作"; value: "none" }
                }
                textRole: "text"
                valueRole: "value"
                onCurrentIndexChanged: {
                    if (currentIndex >= 0 && currentIndex < count)
                        root.onFailActionValue = model.get(currentIndex).value;
                }
            }

            Item { Layout.fillWidth: true }
        }

        RowLayout {
            visible: conditionCheck.checked
            Layout.fillWidth: true
            spacing: 8

            CheckBox {
                id: autoDecreaseCheck
                text: qsTr("未达标自动降指标")
                checked: root.autoDecreaseEnabled
                onCheckedChanged: root.autoDecreaseEnabled = checked
            }

            Item { Layout.fillWidth: true }
        }

        Text {
            visible: root.validationMessage !== ""
            text: root.validationMessage
            font.pixelSize: 11
            color: Theme.currentTheme ? Theme.currentTheme.colors.systemCriticalColor : "#d13438"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }
}
