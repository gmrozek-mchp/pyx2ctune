"""Factory that creates Qt input widgets from YAML InputDef specifications."""

from __future__ import annotations

from typing import Any

import serial.tools.list_ports
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from mctoolbox.wizard_schema import InputDef


class FilePathWidget(QWidget):
    """QLineEdit + Browse button for file selection."""

    def __init__(self, file_filter: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Select file...")
        layout.addWidget(self._edit, stretch=1)
        btn = QPushButton("Browse\u2026")
        btn.setFixedWidth(80)
        btn.clicked.connect(self._browse)
        layout.addWidget(btn)
        self._filter = file_filter or "All Files (*)"

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", self._filter)
        if path:
            self._edit.setText(path)

    def value(self) -> str:
        return self._edit.text().strip()

    def set_value(self, val: str) -> None:
        self._edit.setText(val)


class SerialPortWidget(QWidget):
    """QComboBox with a Refresh button for serial port selection."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setMinimumWidth(180)
        layout.addWidget(self._combo, stretch=1)
        btn = QPushButton("Refresh")
        btn.setFixedWidth(70)
        btn.clicked.connect(self._refresh)
        layout.addWidget(btn)
        self._refresh()

    def _refresh(self) -> None:
        self._combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in sorted(ports, key=lambda x: x.device):
            desc = (
                f"{p.device}"
                if not p.description or p.description == "n/a"
                else f"{p.device} - {p.description}"
            )
            self._combo.addItem(desc, p.device)

    def value(self) -> str:
        return self._combo.currentData() or self._combo.currentText()

    def set_value(self, val: str) -> None:
        idx = self._combo.findData(val)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            self._combo.setEditText(val)


def create_input_widget(
    input_def: InputDef,
    parent: QWidget | None = None,
) -> QWidget:
    """Create a Qt widget appropriate for the given InputDef."""
    t = input_def.type

    if t == "float":
        w = QDoubleSpinBox(parent)
        if input_def.range:
            w.setRange(input_def.range[0], input_def.range[1])
        else:
            w.setRange(-1e9, 1e9)
        w.setDecimals(input_def.decimals)
        if input_def.step is not None:
            w.setSingleStep(input_def.step)
        if input_def.suffix:
            w.setSuffix(input_def.suffix)
        if input_def.default is not None:
            w.setValue(float(input_def.default))
        return w

    if t == "integer":
        w = QSpinBox(parent)
        if input_def.range:
            w.setRange(int(input_def.range[0]), int(input_def.range[1]))
        else:
            w.setRange(-2**31, 2**31 - 1)
        if input_def.step is not None:
            w.setSingleStep(int(input_def.step))
        if input_def.suffix:
            w.setSuffix(input_def.suffix)
        if input_def.default is not None:
            w.setValue(int(input_def.default))
        return w

    if t == "choice":
        w = QComboBox(parent)
        for opt in input_def.options or []:
            w.addItem(str(opt))
        if input_def.default is not None:
            idx = w.findText(str(input_def.default))
            if idx >= 0:
                w.setCurrentIndex(idx)
        return w

    if t == "bool":
        w = QCheckBox(input_def.label, parent)
        if input_def.default is not None:
            w.setChecked(bool(input_def.default))
        return w

    if t == "file_path":
        w = FilePathWidget(file_filter=input_def.filter, parent=parent)
        if input_def.default:
            w.set_value(str(input_def.default))
        return w

    if t == "serial_port":
        w = SerialPortWidget(parent=parent)
        if input_def.default:
            w.set_value(str(input_def.default))
        return w

    # Fallback: plain text
    w = QLineEdit(parent)
    if input_def.default is not None:
        w.setText(str(input_def.default))
    return w


def get_widget_value(widget: QWidget) -> Any:
    """Extract the current value from a widget created by create_input_widget."""
    if isinstance(widget, QDoubleSpinBox):
        return widget.value()
    if isinstance(widget, QSpinBox):
        return widget.value()
    if isinstance(widget, QComboBox):
        return widget.currentText()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, FilePathWidget):
        return widget.value()
    if isinstance(widget, SerialPortWidget):
        return widget.value()
    if isinstance(widget, QLineEdit):
        return widget.text().strip()
    return None


def set_widget_value(widget: QWidget, value: Any) -> None:
    """Set the value on a widget created by create_input_widget."""
    if value is None:
        return
    if isinstance(widget, QDoubleSpinBox):
        widget.setValue(float(value))
    elif isinstance(widget, QSpinBox):
        widget.setValue(int(value))
    elif isinstance(widget, QComboBox):
        idx = widget.findText(str(value))
        if idx >= 0:
            widget.setCurrentIndex(idx)
    elif isinstance(widget, QCheckBox):
        widget.setChecked(bool(value))
    elif isinstance(widget, FilePathWidget):
        widget.set_value(str(value))
    elif isinstance(widget, SerialPortWidget):
        widget.set_value(str(value))
    elif isinstance(widget, QLineEdit):
        widget.setText(str(value))
