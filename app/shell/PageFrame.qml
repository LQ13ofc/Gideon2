import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Content area of one page: scrolls inside the window; the column is centred and at most 1100 px wide.
// Side margins: 32 px from 1164 px of width, 16 px below. Every page is a PageFrame with its content as children.
ScrollView {
    id: frame
    default property alias content: column.data
    readonly property int margin: frame.availableWidth >= 1164 ? 32 : 16
    clip: true
    contentWidth: availableWidth

    ColumnLayout {
        id: column
        width: Math.min(Theme.contentMax, frame.availableWidth - 2 * frame.margin)
        x: Math.max(frame.margin, (frame.availableWidth - width) / 2)
        spacing: Theme.space(24)
        Layout.bottomMargin: Theme.space(24)
    }
}
