// Keeps an item inside the scrolling page that holds it: the nearest Flickable above the item (PageFrame is a ScrollView).
// Used when an item takes keyboard focus or was just added, so a control below the fold is never focused out of view.
// Hidden items (their effective visibility is false) are left alone.
function revealItem(item) {
    if (!item || !item.visible) return
    var flick = item.parent
    while (flick && flick.contentY === undefined) flick = flick.parent
    if (!flick || !flick.contentItem) return
    var top = item.mapToItem(flick.contentItem, 0, 0).y
    var bottom = top + item.height
    var y = flick.contentY
    if (top < y) y = top
    else if (bottom > y + flick.height) y = bottom - flick.height
    var maxY = Math.max(0, flick.contentHeight - flick.height)
    flick.contentY = Math.max(0, Math.min(maxY, y))
}
