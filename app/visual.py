"""Rounded raster backgrounds with software rendering; no shaders or timers."""
from PySide6.QtCore import Property,QRectF,QUrl,Signal
from PySide6.QtGui import QImage,QPainter,QPainterPath
from PySide6.QtQuick import QQuickPaintedItem

class RoundedImage(QQuickPaintedItem):
    sourceChanged=Signal()
    radiusChanged=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self._source=QUrl();self._image=QImage();self._radius=20.0
    @Property(QUrl,notify=sourceChanged)
    def source(self):return self._source
    @source.setter
    def source(self,value):
        if value==self._source:return
        self._source=value;self._image=QImage(value.toLocalFile()) if value.isLocalFile() else QImage()
        self.sourceChanged.emit();self.update()
    @Property(float,notify=radiusChanged)
    def radius(self):return self._radius
    @radius.setter
    def radius(self,value):
        self._radius=max(0.0,value);self.radiusChanged.emit();self.update()
    def paint(self,painter):
        if self._image.isNull():return
        bounds=QRectF(0,0,self.width(),self.height());clip=QPainterPath();clip.addRoundedRect(bounds,self._radius,self._radius)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setClipPath(clip);painter.drawImage(bounds,self._image)
