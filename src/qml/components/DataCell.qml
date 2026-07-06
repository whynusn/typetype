import QtQuick 2.15
import QtQuick.Layouts 1.15
import RinUI

Rectangle {
    id: root
    property int cellWidth: 60
    default property alias content: contentArea.data

    Layout.preferredWidth: cellWidth
    Layout.fillHeight: true
    color: "transparent"

    Item {
        id: contentArea
        anchors.fill: parent
    }
}
