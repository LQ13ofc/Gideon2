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

    function kindText(kind) { return kind === "local" ? qsTr("Local") : qsTr("Nuvem") }

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
        text: detail.model ? qsTr("%1 · provedor %2 · %3").arg(detail.kindText(detail.model.kind)).arg(detail.model.provider).arg(detail.model.model) : ""
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
        text: detail.model ? qsTr("Certificação: %1").arg(core.certificationBadge(detail.model.certification.state)) + (detail.model.certification.evidence ? qsTr(" · evidência: %1").arg(detail.model.certification.evidence) : "") + (detail.model.certification.date ? qsTr(" · data %1").arg(detail.model.certification.date) : "") : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? qsTr("Licença: %1\nQuantização: %2\nHash (SHA-256): %3\nBackend: %4").arg(detail.model.license).arg(detail.model.quantization || qsTr("não se aplica")).arg(detail.model.sha256 || qsTr("não se aplica")).arg(detail.model.backend) : ""
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
            text: qsTr("Recurso %1: %2").arg(modelData).arg(core.featureLabel(detail.model ? detail.model.features[modelData] : "unknown"))
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
        text: detail.model ? qsTr("Contexto: %1").arg(detail.model.features.context_tokens === null ? qsTr("não informado") : qsTr("%1 tokens").arg(detail.model.features.context_tokens)) : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? (detail.model.cost.currency === null ? qsTr("Custo: não informado") : qsTr("Custo (USD por milhão de tokens): entrada %1 · saída %2").arg(detail.model.cost.input_per_mtok).arg(detail.model.cost.output_per_mtok)) : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? qsTr("Latência: %1 · hardware mínimo: RAM %2, GPU %3").arg(L.latencyText(detail.model.latency_hint)).arg(detail.model.min_hardware.ram_gb === null ? qsTr("não informada") : qsTr("%1 GB").arg(detail.model.min_hardware.ram_gb)).arg(L.gpuText(detail.model.min_hardware.gpu)) : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: detail.model !== null
        text: detail.model ? (detail.model.offline ? qsTr("Funciona offline") : qsTr("Requer rede")) : ""
        textFormat: Text.PlainText
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        Layout.fillWidth: true
    }
    Text {
        objectName: detail.prefix + "CloudNotice"
        visible: detail.model !== null && detail.model.kind === "cloud"
        text: qsTr("Mensagens serão enviadas ao provedor escolhido na nuvem")
        textFormat: Text.PlainText
        color: Theme.warning
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontHelp
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
