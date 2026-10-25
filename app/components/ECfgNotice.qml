import QtQuick
import "../shell"

// The one state notice of the Configurações tab: Core offline, a voice session running, a restart pending or safe mode.
// Empty (and hidden) when there is nothing to say. The text is the Core's own message in safe mode and restart.
Banner {
    objectName: "configurationMessage"
    kind: "warn"
    text: AppState.configNotice()
    // U1: a pending restart applies the saved change; the owner can apply it now (the Core refuses during a session).
    actionText: (typeof core !== "undefined" && core && core.configurationStatus === "restart_required" && core.coreRestartAvailable) ? "Reiniciar agora" : ""
    onActionRequested: core.coreRestart()
}
