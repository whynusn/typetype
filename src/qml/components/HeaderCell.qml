import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI

Rectangle {
    property string text: ""
    property int cellWidth: 60

    Layout.preferredWidth: cellWidth
    Layout.fillHeight: true
    color: "transparent"

    Text {
        anchors.centerIn: parent
        typography: Typography.Caption
        font.weight: Font.DemiBold
        text: parent.text
    }
}
