import QtQuick
import QtQuick.Window

// Test host for the WP-10a pages (scripts/test_personal_qml.py). The context properties `core`, `hostPageId` and
// `hostPageUrl` are set by the test before this file is loaded, as app/main.py sets `core` before Main.qml.
Window {
    objectName: "host"
    width: 1100
    height: 900
    visible: true
    property string pageId: hostPageId

    Loader {
        objectName: "page"
        anchors.fill: parent
        source: hostPageUrl
    }
}
