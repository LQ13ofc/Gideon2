import QtQuick
import "../shell"

// The one state notice of the Configurações tab: Core offline, a voice session running, a restart pending or safe mode.
// Empty (and hidden) when there is nothing to say. The text is the Core's own message in safe mode and restart.
Banner {
    objectName: "configurationMessage"
    kind: "warn"
    text: AppState.configNotice()
}
