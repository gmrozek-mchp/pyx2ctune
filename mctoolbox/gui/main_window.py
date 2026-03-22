"""Main application window for mctoolbox GUI."""

from __future__ import annotations

import numpy as np
import serial.tools.list_ports
from PyQt5.QtCore import Qt, QSettings, QThread, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mctoolbox.gui.plot_widget import PlotWidget
from mctoolbox.gui.scope_panel import ScopePanel
from mctoolbox.gui.tabs.current_tab import CurrentLoopTab
from mctoolbox.gui.tabs.openloop_tab import OpenLoopTab
from mctoolbox.gui.tabs.velocity_tab import VelocityLoopTab
from mctoolbox.gui.wizard import WizardPanel
from mctoolbox.gui.workers import Command, SessionWorker

_MONO = QFont()
_MONO.setStyleHint(QFont.Monospace)
_MONO.setPointSize(10)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("mctoolbox -- Motor Tuning")
        self.setMinimumSize(1100, 700)

        self._session = None
        self._settings = QSettings("mctoolbox", "mctoolbox")
        self._view_cache: dict[str, tuple] = {}  # view_id → (response, metrics)

        self._build_ui()
        self._start_worker()
        self._connect_signals()
        self._set_ui_state(connected=False)
        self._restore_settings()

        self._speed_timer = QTimer(self)
        self._speed_timer.setInterval(500)
        self._speed_timer.timeout.connect(self._poll_speed)

    # ── UI Construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        root.addWidget(self._build_connection_panel())

        splitter = self._splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: tabbed control panels
        self._tabs = QTabWidget()
        self._current_tab = CurrentLoopTab()
        self._velocity_tab = VelocityLoopTab()
        self._openloop_tab = OpenLoopTab()
        self._tabs.addTab(self._current_tab, "Current Loop")
        self._tabs.addTab(self._velocity_tab, "Velocity Loop")
        self._tabs.addTab(self._openloop_tab, "Open Loop")

        # Right: scope panel + plot + metrics
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._scope_panel = ScopePanel()
        right_layout.addWidget(self._scope_panel, stretch=0)
        self._plot = PlotWidget()
        right_layout.addWidget(self._plot, stretch=3)
        right_layout.addWidget(self._build_metrics_panel(), stretch=0)

        # Wizard sidebar (hidden by default)
        self._wizard_panel = WizardPanel()
        self._wizard_panel.hide()

        splitter.addWidget(self._wizard_panel)
        splitter.addWidget(self._tabs)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([0, 360, 740])

        root.addWidget(splitter, stretch=1)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _build_connection_panel(self) -> QGroupBox:
        grp = QGroupBox("Connection")
        layout = QGridLayout(grp)

        layout.addWidget(QLabel("Port:"), 0, 0)
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(200)
        layout.addWidget(self._port_combo, 0, 1)

        self._refresh_ports_btn = QPushButton("Refresh")
        self._refresh_ports_btn.setFixedWidth(70)
        layout.addWidget(self._refresh_ports_btn, 0, 2)

        layout.addWidget(QLabel("Baud:"), 0, 3)
        self._baud_spin = QSpinBox()
        self._baud_spin.setRange(9600, 921600)
        self._baud_spin.setValue(115200)
        self._baud_spin.setFixedWidth(90)
        layout.addWidget(self._baud_spin, 0, 4)

        layout.addWidget(QLabel("ELF:"), 1, 0)
        self._elf_edit = QLineEdit()
        self._elf_edit.setPlaceholderText("Path to firmware .elf file")
        layout.addWidget(self._elf_edit, 1, 1, 1, 3)
        self._elf_browse = QPushButton("Browse...")
        self._elf_browse.setFixedWidth(80)
        layout.addWidget(self._elf_browse, 1, 4)

        layout.addWidget(QLabel("Params:"), 2, 0)
        self._params_edit = QLineEdit()
        self._params_edit.setPlaceholderText("Path to parameters.json (optional)")
        layout.addWidget(self._params_edit, 2, 1, 1, 3)
        self._params_browse = QPushButton("Browse...")
        self._params_browse.setFixedWidth(80)
        layout.addWidget(self._params_browse, 2, 4)

        btn_layout = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._disconnect_btn = QPushButton("Disconnect")
        self._wizard_toggle_btn = QPushButton("Wizard")
        self._wizard_toggle_btn.setCheckable(True)
        self._wizard_toggle_btn.setFixedWidth(70)
        btn_layout.addStretch()
        btn_layout.addWidget(self._wizard_toggle_btn)
        btn_layout.addWidget(self._connect_btn)
        btn_layout.addWidget(self._disconnect_btn)
        layout.addLayout(btn_layout, 0, 5, 1, 1)

        self._refresh_ports()
        return grp

    def _build_metrics_panel(self) -> QGroupBox:
        grp = QGroupBox("Metrics")
        layout = QGridLayout(grp)

        labels = [
            ("Overshoot:", "_os_label"),
            ("Rise time:", "_tr_label"),
            ("Settling time:", "_ts_label"),
            ("SSE:", "_sse_label"),
            ("Steps detected:", "_steps_label"),
        ]
        for row, (text, attr) in enumerate(labels):
            layout.addWidget(QLabel(text), row, 0)
            lbl = QLabel("--")
            lbl.setFont(_MONO)
            setattr(self, attr, lbl)
            layout.addWidget(lbl, row, 1)

        layout.setColumnStretch(1, 1)

        self._save_data_btn = QPushButton("Save Data\u2026")
        self._save_data_btn.setEnabled(False)
        next_row = len(labels)
        layout.addWidget(self._save_data_btn, next_row, 0, 1, 2)

        return grp

    # ── Worker Setup ──────────────────────────────────────────────────

    def _start_worker(self) -> None:
        self._worker = SessionWorker()
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker_thread.start()

    def _connect_signals(self) -> None:
        # Connection panel
        self._refresh_ports_btn.clicked.connect(self._refresh_ports)
        self._elf_browse.clicked.connect(self._browse_elf)
        self._params_browse.clicked.connect(self._browse_params)
        self._connect_btn.clicked.connect(self._on_connect)
        self._disconnect_btn.clicked.connect(self._on_disconnect)

        # Current loop tab → worker
        ct = self._current_tab
        ct.read_gains_requested.connect(self._on_read_gains)
        ct.set_gains_requested.connect(self._on_set_gains)
        ct.enter_test_requested.connect(self._on_enter_test)
        ct.exit_test_requested.connect(self._on_exit_test)
        ct.start_perturbation_requested.connect(self._on_start_perturbation)
        ct.stop_perturbation_requested.connect(self._on_stop_perturbation)

        # Velocity loop tab → worker
        vt = self._velocity_tab
        vt.read_gains_requested.connect(self._on_vel_read_gains)
        vt.set_gains_requested.connect(self._on_vel_set_gains)
        vt.set_velocity_requested.connect(self._on_vel_set_command)
        vt.enter_test_requested.connect(self._on_vel_enter_test)
        vt.exit_test_requested.connect(self._on_exit_test)
        vt.start_perturbation_requested.connect(self._on_vel_start_perturbation)
        vt.stop_perturbation_requested.connect(self._on_vel_stop_perturbation)

        # Open loop tab → worker
        ol = self._openloop_tab
        ol.enter_force_voltage_requested.connect(self._on_ol_enter_voltage)
        ol.enter_force_current_requested.connect(
            lambda: self._on_enter_test("force_current", 0.0),
        )
        ol.exit_test_requested.connect(self._on_exit_test)
        ol.set_overrides_requested.connect(self._on_ol_set_overrides)
        ol.set_commutation_freq_requested.connect(self._on_ol_set_omega)
        ol.set_dq_current_requested.connect(self._on_ol_set_dq_current)
        ol.set_dq_voltage_requested.connect(self._on_ol_set_dq_voltage)
        ol.force_state_requested.connect(self._on_ol_force_state)
        ol.read_status_requested.connect(self._on_ol_read_status)

        # Scope panel → worker
        sp = self._scope_panel
        sp.capture_single_requested.connect(self._on_scope_single)
        sp.continuous_start_requested.connect(self._on_scope_continuous_start)
        sp.stop_requested.connect(self._on_stop)
        sp.view_changed.connect(self._on_view_switched)

        # Save data
        self._save_data_btn.clicked.connect(self._on_save_data)

        # Worker results → current tab
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.gains_read.connect(ct.on_gains_read)
        self._worker.gains_set.connect(ct.on_gains_set)
        self._worker.test_mode_entered.connect(ct.on_test_mode_entered)
        self._worker.test_mode_exited.connect(ct.on_test_mode_exited)
        self._worker.perturbation_started.connect(ct.on_perturbation_started)
        self._worker.perturbation_stopped.connect(ct.on_perturbation_stopped)

        # Worker results → velocity tab
        self._worker.velocity_gains_read.connect(vt.on_gains_read)
        self._worker.velocity_gains_set.connect(vt.on_gains_set)
        self._worker.test_mode_entered.connect(vt.on_test_mode_entered)
        self._worker.test_mode_exited.connect(vt.on_test_mode_exited)
        self._worker.velocity_perturbation_started.connect(vt.on_perturbation_started)
        self._worker.velocity_perturbation_stopped.connect(vt.on_perturbation_stopped)

        # Worker results → open loop tab
        self._worker.test_mode_entered.connect(ol.on_test_mode_entered)
        self._worker.test_mode_exited.connect(ol.on_test_mode_exited)
        self._worker.force_voltage_entered.connect(ol.on_test_mode_entered)
        self._worker.harness_status_read.connect(ol.on_status_read)

        # Worker capture lifecycle → scope panel
        self._worker.capture_done.connect(self._on_capture_done)
        self._worker.capture_started.connect(self._on_capture_started)
        self._worker.capture_cancelled.connect(self._on_capture_cancelled)
        self._worker.continuous_started.connect(sp.on_continuous_started)
        self._worker.continuous_stopped.connect(sp.on_continuous_stopped)

        # Speed readback → all tabs
        self._worker.measured_speed_read.connect(ct.on_speed_read)
        self._worker.measured_speed_read.connect(vt.on_speed_read)
        self._worker.measured_speed_read.connect(ol.on_speed_read)

        self._worker.error.connect(self._on_error)
        self._worker.connection_lost.connect(self._on_connection_lost)
        self._worker.status.connect(self._status_bar.showMessage)
        self._worker.busy_changed.connect(self._on_busy_changed)

        # Wizard panel
        self._wizard_toggle_btn.toggled.connect(self._on_wizard_toggled)
        self._wizard_panel.close_requested.connect(
            lambda: self._wizard_toggle_btn.setChecked(False),
        )
        self._wizard_panel.set_worker(self._worker)
        self._wizard_panel.engine.status_message.connect(
            self._status_bar.showMessage,
        )

    # ── UI State ──────────────────────────────────────────────────────

    def _set_ui_state(self, connected: bool) -> None:
        self._port_combo.setEnabled(not connected)
        self._baud_spin.setEnabled(not connected)
        self._elf_edit.setEnabled(not connected)
        self._elf_browse.setEnabled(not connected)
        self._params_edit.setEnabled(not connected)
        self._params_browse.setEnabled(not connected)
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)

        self._current_tab.set_connected(connected)
        self._velocity_tab.set_connected(connected)
        self._openloop_tab.set_connected(connected)
        self._scope_panel.set_connected(connected)

    # ── Slots: Wizard ─────────────────────────────────────────────────

    def _on_wizard_toggled(self, checked: bool) -> None:
        self._wizard_panel.setVisible(checked)
        if checked:
            self._splitter.setSizes([340, 360, 740])
        else:
            sizes = self._splitter.sizes()
            sizes[0] = 0
            self._splitter.setSizes(sizes)

    # ── Slots: Connection ─────────────────────────────────────────────

    def _refresh_ports(self) -> None:
        self._port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in sorted(ports, key=lambda x: x.device):
            desc = (
                f"{p.device}"
                if not p.description or p.description == "n/a"
                else f"{p.device} - {p.description}"
            )
            self._port_combo.addItem(desc, p.device)

    def _browse_elf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ELF File", "",
            "ELF Files (*.elf);;All Files (*)",
        )
        if path:
            self._elf_edit.setText(path)

    def _browse_params(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select parameters.json", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self._params_edit.setText(path)

    def _on_connect(self) -> None:
        port = self._port_combo.currentData() or self._port_combo.currentText()
        elf = self._elf_edit.text().strip()
        if not port or not elf:
            QMessageBox.warning(
                self, "Missing fields", "Port and ELF file are required.",
            )
            return
        params = self._params_edit.text().strip() or None
        self._connect_btn.setEnabled(False)
        self._worker.submit(
            Command.CONNECT,
            port=port, elf_file=elf,
            baud_rate=self._baud_spin.value(),
            parameters_json=params,
        )

    def _on_disconnect(self) -> None:
        self._worker.request_stop_continuous()
        self._worker.cancel_capture()
        self._worker.submit(Command.EXIT_TEST_MODE)
        self._worker.submit(Command.DISCONNECT)

    def _on_connected(self, session) -> None:
        self._session = session
        self._set_ui_state(connected=True)
        self._current_tab.on_connected(session)
        self._velocity_tab.on_connected(session)
        self._openloop_tab.on_connected(session)
        self._scope_panel.on_connected(session)
        self._wizard_panel.set_connected(True)

        self._worker.submit(Command.STOP_PERTURBATION)
        self._worker.submit(Command.EXIT_TEST_MODE)
        self._worker.submit(
            Command.READ_GAINS,
            axis=self._current_tab.current_axis(),
        )
        self._worker.submit(Command.READ_VELOCITY_GAINS)
        self._speed_timer.start()

    def _on_disconnected(self) -> None:
        self._speed_timer.stop()
        self._session = None
        self._view_cache.clear()
        self._set_ui_state(connected=False)
        self._current_tab.on_disconnected()
        self._velocity_tab.on_disconnected()
        self._openloop_tab.on_disconnected()
        self._scope_panel.on_disconnected()
        self._wizard_panel.set_connected(False)

    def _poll_speed(self) -> None:
        if self._session is not None:
            self._worker.submit(Command.READ_MEASURED_SPEED)

    # ── Slots: routed from CurrentLoopTab ─────────────────────────────

    def _on_read_gains(self, axis: str) -> None:
        self._worker.submit(Command.READ_GAINS, axis=axis)

    def _on_set_gains(self, kp: float, ki: float) -> None:
        self._worker.submit(Command.SET_GAINS, kp=kp, ki=ki)

    def _on_enter_test(self, mode: str, velocity_rpm: float) -> None:
        if mode == "velocity_override":
            self._worker.submit(
                Command.ENTER_VELOCITY_OVERRIDE_MODE,
                velocity_rpm=velocity_rpm,
            )
        else:
            self._worker.submit(Command.ENTER_TEST_MODE)

    def _on_exit_test(self) -> None:
        self._worker.submit(Command.EXIT_TEST_MODE)

    def _on_start_perturbation(self, axis: str, amplitude: float,
                               halfperiod: float) -> None:
        view = f"current_{axis}"
        self._scope_panel.set_view(view)
        sp = self._scope_panel
        self._worker.submit(
            Command.CONFIGURE_SCOPE, view=view,
            sample_time=sp.sample_time(),
            trigger=sp.trigger_enabled(),
            trigger_level=sp.trigger_level_q15(),
        )
        self._worker.submit(
            Command.START_PERTURBATION,
            axis=axis, amplitude=amplitude, halfperiod=halfperiod,
        )

    def _on_stop_perturbation(self) -> None:
        self._worker.submit(Command.STOP_PERTURBATION)

    # ── Slots: routed from VelocityLoopTab ──────────────────────────

    def _on_vel_read_gains(self) -> None:
        self._worker.submit(Command.READ_VELOCITY_GAINS)

    def _on_vel_set_gains(self, kp: float, ki: float) -> None:
        self._worker.submit(Command.SET_VELOCITY_GAINS, kp=kp, ki=ki)

    def _on_vel_set_command(self, rpm: float) -> None:
        self._worker.submit(Command.SET_VELOCITY_COMMAND, rpm=rpm)

    def _on_vel_enter_test(self, velocity_rpm: float) -> None:
        self._worker.submit(
            Command.ENTER_VELOCITY_OVERRIDE_MODE,
            velocity_rpm=velocity_rpm,
        )

    def _on_vel_start_perturbation(self, amplitude_rpm: float,
                                   halfperiod_ms: float) -> None:
        self._scope_panel.set_view("velocity")
        sp = self._scope_panel
        self._worker.submit(
            Command.CONFIGURE_SCOPE, view="velocity",
            sample_time=sp.sample_time(),
            trigger=sp.trigger_enabled(),
            trigger_level=sp.trigger_level_q15(),
        )
        self._worker.submit(
            Command.START_VELOCITY_PERTURBATION,
            amplitude_rpm=amplitude_rpm, halfperiod_ms=halfperiod_ms,
        )

    def _on_vel_stop_perturbation(self) -> None:
        self._worker.submit(Command.STOP_VELOCITY_PERTURBATION)

    # ── Slots: routed from OpenLoopTab ──────────────────────────────

    def _on_ol_enter_voltage(self) -> None:
        self._worker.submit(Command.ENTER_FORCE_VOLTAGE_MODE)

    def _on_ol_set_overrides(self, flags: dict) -> None:
        self._worker.submit(Command.SET_OVERRIDES, flags=flags)

    def _on_ol_set_omega(self, rpm: float) -> None:
        self._worker.submit(Command.SET_COMMUTATION_FREQ, rpm=rpm)

    def _on_ol_set_dq_current(self, d: float, q: float) -> None:
        self._worker.submit(Command.SET_DQ_CURRENT, d=d, q=q)

    def _on_ol_set_dq_voltage(self, d: float, q: float) -> None:
        self._worker.submit(Command.SET_DQ_VOLTAGE, d=d, q=q)

    def _on_ol_force_state(self, transition: int) -> None:
        self._worker.submit(Command.FORCE_STATE, transition=transition)

    def _on_ol_read_status(self) -> None:
        self._worker.submit(Command.READ_HARNESS_STATUS)

    # ── Slots: routed from ScopePanel ───────────────────────────────

    def _on_scope_single(self) -> None:
        sp = self._scope_panel
        self._worker.submit(
            Command.CONFIGURE_SCOPE,
            view=sp.current_view(),
            sample_time=sp.sample_time(),
            trigger=sp.trigger_enabled(),
            trigger_level=sp.trigger_level_q15(),
        )
        self._worker.submit(Command.CAPTURE, timeout=10.0)

    def _on_scope_continuous_start(self) -> None:
        self._plot.clear()
        sp = self._scope_panel
        self._worker.submit(
            Command.CONFIGURE_SCOPE,
            view=sp.current_view(),
            sample_time=sp.sample_time(),
            trigger=sp.trigger_enabled(),
            trigger_level=sp.trigger_level_q15(),
        )
        self._worker.submit(Command.CAPTURE_CONTINUOUS_START, timeout=10.0)

    def _on_stop(self) -> None:
        self._worker.request_stop_continuous()
        self._worker.cancel_capture()

    # ── Slots: data export ────────────────────────────────────────────

    def _on_save_data(self) -> None:
        view = self._scope_panel.current_view()
        cached = self._view_cache.get(view)
        if cached is None:
            QMessageBox.information(
                self, "No Data",
                "No captured data for the current view.",
            )
            return

        response, metrics = cached
        default_name = f"mctoolbox_{view}"
        filters = (
            "CSV Files (*.csv);;"
            "NumPy Archive (*.npz);;"
            "JSON (*.json)"
        )
        path, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Capture Data", default_name, filters,
        )
        if not path:
            return

        try:
            if path.endswith(".npz"):
                self._write_npz(path, response, metrics, view)
            elif path.endswith(".json"):
                self._write_json(path, response, metrics, view)
            else:
                if not path.endswith(".csv"):
                    path += ".csv"
                self._write_csv(path, response, metrics, view)
            self._status_bar.showMessage(f"Data saved to {path}")
        except OSError as exc:
            QMessageBox.critical(
                self, "Save Failed", f"Could not write file:\n\n{exc}",
            )

    @staticmethod
    def _build_metadata(response, metrics, view: str) -> dict:
        meta = {
            "view": view,
            "loop_type": response.loop_type,
            "axis": response.axis,
            "sample_time": response.sample_time,
            "control_period_us": response.control_period_us,
            "reference_units": response.reference_units or response.current_units,
            "measured_units": response.measured_units or response.current_units,
            "output_units": response.output_units or response.voltage_units,
        }
        if response.gains:
            meta["gains"] = dict(response.gains)
        if metrics is not None and metrics.n_steps > 0:
            meta["metrics"] = {
                "overshoot": float(metrics.overshoot),
                "rise_time_us": float(metrics.rise_time_us),
                "settling_time_us": float(metrics.settling_time_us),
                "steady_state_error": float(metrics.steady_state_error),
                "n_steps": int(metrics.n_steps),
            }
        return meta

    @staticmethod
    def _write_csv(path: str, response, metrics, view: str) -> None:
        import csv

        meta = MainWindow._build_metadata(response, metrics, view)

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)

            for key, val in meta.items():
                if isinstance(val, dict):
                    for k2, v2 in val.items():
                        writer.writerow([f"# {key}.{k2}", v2])
                else:
                    writer.writerow([f"# {key}", val])

            writer.writerow([
                "time_us",
                f"reference ({meta['reference_units']})",
                f"measured ({meta['measured_units']})",
                f"output ({meta['output_units']})",
            ])

            for i in range(len(response.time_us)):
                writer.writerow([
                    f"{response.time_us[i]:.2f}",
                    f"{response.reference[i]:.6g}",
                    f"{response.measured[i]:.6g}",
                    f"{response.voltage[i]:.6g}",
                ])

    @staticmethod
    def _write_npz(path: str, response, metrics, view: str) -> None:
        import json as _json
        meta = MainWindow._build_metadata(response, metrics, view)
        np.savez(
            path,
            time_us=response.time_us,
            reference=response.reference,
            measured=response.measured,
            output=response.voltage,
            metadata=_json.dumps(meta),
        )

    @staticmethod
    def _write_json(path: str, response, metrics, view: str) -> None:
        import json as _json
        meta = MainWindow._build_metadata(response, metrics, view)
        data = {
            **meta,
            "time_us": response.time_us.tolist(),
            "reference": response.reference.tolist(),
            "measured": response.measured.tolist(),
            "output": response.voltage.tolist(),
        }
        with open(path, "w") as f:
            _json.dump(data, f, indent=2)

    # ── Slots: capture lifecycle ──────────────────────────────────────

    def _on_capture_started(self) -> None:
        self._scope_panel.on_capture_started()
        self._plot.show_waiting()

    def _on_capture_cancelled(self) -> None:
        self._scope_panel.on_capture_cancelled()
        self._plot.hide_waiting()

    def _on_capture_done(self, response, metrics) -> None:
        self._plot.hide_waiting()
        self._plot.update_plot(response, metrics)
        self._scope_panel.on_capture_done()

        view = self._scope_panel.current_view()
        self._view_cache[view] = (response, metrics)
        self._update_metrics(metrics)
        self._save_data_btn.setEnabled(True)

    def _on_view_switched(self, view_id: str) -> None:
        """Restore cached plot/metrics when the user switches views."""
        cached = self._view_cache.get(view_id)
        if cached is not None:
            response, metrics = cached
            self._plot.clear()
            self._plot.update_plot(response, metrics)
            self._update_metrics(metrics)
            self._save_data_btn.setEnabled(True)
        else:
            self._plot.clear()
            self._clear_metrics()
            self._save_data_btn.setEnabled(False)

    def _update_metrics(self, metrics) -> None:
        if metrics.n_steps > 0:
            self._os_label.setText(f"{metrics.overshoot:.1%}")
            self._tr_label.setText(f"{metrics.rise_time_us:.0f} \u00b5s")
            self._ts_label.setText(f"{metrics.settling_time_us:.0f} \u00b5s")
            self._sse_label.setText(f"{metrics.steady_state_error:.3f}")
            self._steps_label.setText(str(metrics.n_steps))
        else:
            self._clear_metrics()

    def _clear_metrics(self) -> None:
        for lbl in (
            self._os_label, self._tr_label, self._ts_label,
            self._sse_label, self._steps_label,
        ):
            lbl.setText("--")

    # ── Connection Loss / Error / Busy ────────────────────────────────

    def _on_connection_lost(self, message: str) -> None:
        """Handle unexpected loss of communication with the board."""
        if self._session is None:
            return
        self._speed_timer.stop()
        self._worker.request_stop_continuous()
        self._worker.cancel_capture()
        self._on_disconnected()
        QMessageBox.warning(
            self, "Connection Lost",
            "Communication with the board was lost.\n\n"
            "Check the USB connection and click Connect to reconnect.",
        )

    def _on_error(self, cmd_name: str, message: str) -> None:
        self._status_bar.showMessage(f"Error: {cmd_name}")
        self._set_ui_state(connected=self._session is not None)
        QMessageBox.critical(self, f"Error: {cmd_name}", message)

    def _on_busy_changed(self, busy: bool) -> None:
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    # ── Settings Persistence ─────────────────────────────────────────

    def _save_settings(self) -> None:
        s = self._settings
        s.setValue("port", self._port_combo.currentData() or self._port_combo.currentText())
        s.setValue("elf_file", self._elf_edit.text())
        s.setValue("params_json", self._params_edit.text())
        s.setValue("baud_rate", self._baud_spin.value())
        s.setValue("geometry", self.saveGeometry())
        s.setValue("splitter", self._splitter.saveState() if hasattr(self, "_splitter") else None)
        self._current_tab.save_settings(s)
        self._velocity_tab.save_settings(s)
        self._scope_panel.save_settings(s)

    def _restore_settings(self) -> None:
        s = self._settings

        port = s.value("port", "")
        if port:
            idx = self._port_combo.findData(port)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)
            else:
                self._port_combo.setEditText(port)

        elf = s.value("elf_file", "")
        if elf:
            self._elf_edit.setText(elf)

        params = s.value("params_json", "")
        if params:
            self._params_edit.setText(params)

        baud = s.value("baud_rate", type=int)
        if baud:
            self._baud_spin.setValue(baud)

        # Legacy settings migration (pre-tab era)
        axis = s.value("axis", "")
        if axis and not s.value("current/axis", ""):
            s.setValue("current/axis", axis)
        amp = s.value("amplitude", type=float)
        if amp and not s.value("current/amplitude", type=float):
            s.setValue("current/amplitude", amp)
        hp = s.value("halfperiod", type=float)
        if hp and not s.value("current/halfperiod", type=float):
            s.setValue("current/halfperiod", hp)

        self._current_tab.restore_settings(s)
        self._velocity_tab.restore_settings(s)
        self._scope_panel.restore_settings(s)

        geom = s.value("geometry")
        if geom:
            self.restoreGeometry(geom)

        splitter_state = s.value("splitter")
        if splitter_state and hasattr(self, "_splitter"):
            self._splitter.restoreState(splitter_state)

    # ── Window Close ──────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._save_settings()
        self._speed_timer.stop()
        self._worker.request_stop_continuous()
        self._worker.cancel_capture()
        if self._session is not None:
            self._worker.submit(Command.EXIT_TEST_MODE)
            self._worker.submit(Command.DISCONNECT)
        self._worker.stop()
        self._worker_thread.quit()
        self._worker_thread.wait(5000)
        super().closeEvent(event)
