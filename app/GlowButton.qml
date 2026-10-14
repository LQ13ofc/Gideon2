import QtQuick
import QtQuick.Controls
Button {
    id: control
    property color accent: "#7693ff"
    property string image: ""
    implicitHeight: 44
    padding: 12
    Accessible.name: text
    background: Rectangle {
        radius: 12
        color: control.checked || control.down ? "#304ba1" : control.hovered ? "#243a68" : "#17294b"
        border.width: control.activeFocus || control.checked ? 2 : 1
        border.color: control.activeFocus || control.checked ? control.accent : "#354976"
        opacity: control.enabled ? 1 : 0.45
    }
    contentItem: Row {
        spacing: 10
        Image { source: control.image; width: control.image ? 24 : 0; height: 24; visible: control.image !== ""; anchors.verticalCenter: parent.verticalCenter; fillMode: Image.PreserveAspectFit }
        Text { visible: control.text !== ""; text: control.text; color: control.enabled ? "#edf2ff" : "#8898b8"; font: control.font; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText }
    }
}
