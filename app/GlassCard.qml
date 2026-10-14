import QtQuick
Rectangle {
    property int theme: 0
    radius: 20
    border.width: 1
    border.color: "#344779"
    gradient: Gradient {
        GradientStop { position: 0; color: theme === 2 ? "#1c2939" : theme === 1 ? "#253c59" : "#1c2e56" }
        GradientStop { position: 1; color: theme === 2 ? "#131e2a" : theme === 1 ? "#16273e" : "#111e38" }
    }
}
