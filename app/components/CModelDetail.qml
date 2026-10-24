import QtQuick
import QtQuick.Layouts
import "../theme"
import "../shell/Labels.js" as L

// Details of one model (C2): certification, licence, features, context, cost, latency, hardware and network needs.
// prefix names the objects (modelDetailTitle, currentModelTitle ...) so two details can sit on one page.
ColumnLayout {
    id: detail
    property var model: null
    property string prefix: "model"
    property string titleText: model ? model.label : ""
    property bool showCaption: true
    Layout.fillWidth: true
    spacing: Theme.space(6)

    Text {
        objectName: detail.prefix + "Title"
        visible: detail.model !== null
        text: detail.titleText
        textFormat: Text.PlainText
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontSection
        font.weight: 600
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null && detail.showCaption
        text: detail.model ? (detail.model.kind === "local" ? "Local" : "Nuvem") + " · provedor " + detail.model.provider + " · " + detail.model.model : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
    }
    Text {
        objectName: detail.prefix + "Certification"
        visible: detail.model !== null
        text: detail.model ? "Certificação: " + core.certificationBadge(detail.model.certification.state) + (detail.model.certification.evidence ? " · evidência: " + detail.model.certification.evidence : "") + (detail.model.certification.date ? " · data " + detail.model.certification.date : "") : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? "Licença: " + detail.model.license + "\nQuantização: " + (detail.model.quantization || "não se aplica") + "\nHash (SHA-256): " + (detail.model.sha256 || "não se aplica") + "\nBackend: " + detail.model.backend : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WrapAnywhere
        Layout.fillWidth: true
    }
    Repeater {
        model: ["streaming", "tool_use", "vision", "cancel"]
        delegate: Text {
            required property string modelData
            visible: detail.model !== null
            text: "Recurso " + modelData + ": " + core.featureLabel(detail.model ? detail.model.features[modelData] : "unknown")
            textFormat: Text.PlainText
            color: Theme.textMuted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontHelp
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? "Contexto: " + (detail.model.features.context_tokens === null ? "não informado" : detail.model.features.context_tokens + " tokens") : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? (detail.model.cost.currency === null ? "Custo: não informado" : "Custo (USD por milhão de tokens): entrada " + detail.model.cost.input_per_mtok + " · saída " + detail.model.cost.output_per_mtok) : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? "Latência: " + L.latencyText(detail.model.latency_hint) + " · hardware mínimo: RAM " + (detail.model.min_hardware.ram_gb === null ? "não informada" : detail.model.min_hardware.ram_gb + " GB") + ", GPU " + L.gpuText(detail.model.min_hardware.gpu) : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? (detail.model.offline ? "Funciona offline" : "Requer rede") : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        Layout.fillWidth: true
    }
    Text {
        objectName: detail.prefix + "CloudNotice"
        visible: detail.model !== null && detail.model.kind === "cloud"
        text: "Mensagens serão enviadas ao provedor escolhido na nuvem"
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
