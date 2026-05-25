from __future__ import annotations

from math import ceil

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class WaveformSeekBar(QWidget):
    _PLACEHOLDER_BINS = tuple(0.2 for _ in range(100))

    sliderReleased = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._maximum = 300_000
        self._value = 0
        self._single_step = 1_000
        self._page_step = 10_000
        self._signals_blocked = False
        self._drag_active = False
        self._accent = QColor("#DAA435")
        self._theme_mode = "dark"
        self._rounded = False
        self._buffered_position_ms: int | None = None
        self._waveform_bins: tuple[float, ...] = ()
        self._waveform_known_position_ms = 0
        self._waveform_mode = "plain"
        self._waveform_enabled = False
        self.setMouseTracking(True)
        self.setObjectName("seek-slider")
        self.setMinimumHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setSingleStep(self, value: int) -> None:  # noqa: N802
        self._single_step = max(1, value)

    def setPageStep(self, value: int) -> None:  # noqa: N802
        self._page_step = max(1, value)

    def setMaximum(self, value: int) -> None:  # noqa: N802
        self._maximum = max(1, value)
        self._value = min(self._value, self._maximum)
        self.update()

    def setValue(self, value: int) -> None:  # noqa: N802
        bounded = max(0, min(self._maximum, value))
        if bounded == self._value:
            return
        self._value = bounded
        self.update()

    def value(self) -> int:
        return self._value

    def blockSignals(self, block: bool) -> bool:  # noqa: N802
        previous = self._signals_blocked
        self._signals_blocked = block
        return previous

    def set_visuals(
        self,
        *,
        accent: str,
        theme_mode: str,
        rounded: bool,
    ) -> None:
        self._accent = QColor(accent)
        self._theme_mode = theme_mode
        self._rounded = rounded
        self.update()

    def set_waveform_state(
        self,
        *,
        buffered_position_ms: int | None,
        waveform_bins: tuple[float, ...],
        waveform_known_position_ms: int,
        waveform_mode: str,
    ) -> None:
        if (
            buffered_position_ms == self._buffered_position_ms
            and waveform_bins is self._waveform_bins
            and waveform_known_position_ms == self._waveform_known_position_ms
            and waveform_mode == self._waveform_mode
        ):
            return
        self._buffered_position_ms = buffered_position_ms
        self._waveform_bins = waveform_bins
        self._waveform_known_position_ms = waveform_known_position_ms
        self._waveform_mode = waveform_mode
        self.update()

    def set_waveform_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._waveform_enabled:
            return
        self._waveform_enabled = enabled
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._drag_active = True
        self._set_value_from_x(event.position().x())
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_active:
            self._set_value_from_x(event.position().x())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_active and event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            self._set_value_from_x(event.position().x())
            if not self._signals_blocked:
                self.sliderReleased.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        groove_rect = self._groove_rect()
        groove_radius = 4 if self._rounded else 1
        base_color = QColor("#cfd7e5" if self._theme_mode == "light" else "#25324a")
        buffered_color = QColor(self._accent)
        buffered_color.setAlpha(80)
        played_color = QColor(self._accent)
        unplayed_wave_color = QColor(self._accent)
        unplayed_wave_color.setAlpha(110)
        handle_fill = QColor("#ffffff" if self._theme_mode == "light" else "#101722")
        handle_border = QColor(self._accent)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(base_color)
        painter.drawRoundedRect(groove_rect, groove_radius, groove_radius)

        if self._buffered_position_ms is not None:
            buffered_ratio = max(0.0, min(1.0, self._buffered_position_ms / self._maximum))
            buffered_rect = QRectF(groove_rect)
            buffered_rect.setWidth(groove_rect.width() * buffered_ratio)
            if buffered_rect.width() > 0:
                painter.setBrush(buffered_color)
                painter.drawRoundedRect(buffered_rect, groove_radius, groove_radius)

        if self._should_paint_waveform():
            self._paint_waveform(
                painter,
                groove_rect=groove_rect,
                played_color=played_color,
                pending_color=unplayed_wave_color,
            )
        else:
            played_ratio = max(0.0, min(1.0, self._value / self._maximum))
            played_rect = QRectF(groove_rect)
            played_rect.setWidth(groove_rect.width() * played_ratio)
            if played_rect.width() > 0:
                painter.setBrush(played_color)
                painter.drawRoundedRect(played_rect, groove_radius, groove_radius)

        handle_center_x = groove_rect.left() + groove_rect.width() * max(
            0.0,
            min(1.0, self._value / self._maximum),
        )
        handle_center = QPointF(handle_center_x, groove_rect.center().y())
        painter.setPen(QPen(handle_border, 1.6))
        painter.setBrush(handle_fill)
        painter.drawEllipse(handle_center, 7, 7)

    def _should_paint_waveform(self) -> bool:
        if self._maximum <= 0 or not self._waveform_enabled:
            return False
        if self._waveform_bins and self._waveform_known_position_ms > 0:
            return True
        return self._waveform_mode == "loading"

    def _paint_waveform(
        self,
        painter: QPainter,
        *,
        groove_rect: QRectF,
        played_color: QColor,
        pending_color: QColor,
    ) -> None:
        is_placeholder = not self._waveform_bins
        bins = self._waveform_bins or self._PLACEHOLDER_BINS
        known_ratio = (
            1.0
            if is_placeholder
            else max(0.0, min(1.0, self._waveform_known_position_ms / self._maximum))
        )
        known_bins = (
            len(bins)
            if is_placeholder
            else max(1, min(len(bins), round(len(bins) * known_ratio)))
        )
        known_width = groove_rect.width() * known_ratio
        waveform_base_height = 9.0
        half_height = max(5.0, waveform_base_height * 2.15)
        pen_width = max(1.0, known_width / max(known_bins, 120))
        played_limit = max(0.0, min(1.0, self._value / self._maximum)) * groove_rect.width()

        for index in range(known_bins):
            amplitude = max(0.08, min(1.0, bins[index]))
            if known_bins == 1:
                x = groove_rect.left() + known_width / 2
            else:
                x = groove_rect.left() + known_width * (index / (known_bins - 1))
            height = half_height * amplitude
            color = played_color if (x - groove_rect.left()) <= played_limit else pending_color
            painter.setPen(
                QPen(
                    color,
                    pen_width,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(
                QPointF(x, groove_rect.center().y() - height / 2),
                QPointF(x, groove_rect.center().y() + height / 2),
            )
        if not is_placeholder and known_bins < len(bins):
            tail_rect = QRectF(
                groove_rect.left() + known_width,
                groove_rect.top(),
                groove_rect.width() - known_width,
                groove_rect.height(),
            )
            if tail_rect.width() > 0:
                tail_color = QColor("#d9e0ec" if self._theme_mode == "light" else "#2b364d")
                tail_color.setAlpha(150)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(tail_color)
                painter.drawRoundedRect(tail_rect, 4, 4)

    def _groove_rect(self) -> QRectF:
        margin_x = 10.0
        groove_height = 3.2 if self._waveform_enabled else 9.0
        center_y = self.height() / 2
        width = max(20.0, self.width() - margin_x * 2)
        return QRectF(margin_x, center_y - groove_height / 2, width, groove_height)

    def _set_value_from_x(self, x: float) -> None:
        groove_rect = self._groove_rect()
        ratio = 0.0 if groove_rect.width() <= 0 else (x - groove_rect.left()) / groove_rect.width()
        bounded_ratio = max(0.0, min(1.0, ratio))
        self.setValue(ceil(self._maximum * bounded_ratio))
