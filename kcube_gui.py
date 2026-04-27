"""
KCube Motor Controller - GUI Application

Tkinter GUI for a Thorlabs Z812 linear actuator driven by a KDC101
KCube DC Servo Motor Controller.

Features:
  - Serial number entry with USB device scan
  - Live position display with auto-polling
  - Home button
  - Jog forward / reverse with configurable step
  - Move to absolute position
  - Named preset buttons (retrieval, dropping, retraction)
  - Motion parameter configuration (velocity, acceleration, jog step, backlash)
  - Status bar with last action

Run standalone:
    python kcube_gui.py [serial_number]
"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from kcube_controller import KCubeController


# =============================================================================
# Connection Frame
# =============================================================================

class ConnectionFrame(ttk.LabelFrame):
    """Serial number entry, USB scan, connect / disconnect."""

    def __init__(self, parent, on_connect, on_disconnect):
        super().__init__(parent, text="Connection", padding=8)
        self.on_connect    = on_connect
        self.on_disconnect = on_disconnect
        self._build()

    def _build(self):
        ttk.Label(self, text="Serial number:").grid(
            row=0, column=0, sticky="e", padx=4, pady=6)
        self.sn_var = tk.StringVar(value="27006288")
        self.sn_combo = ttk.Combobox(self, textvariable=self.sn_var, width=16)
        self.sn_combo.grid(row=0, column=1, sticky="w", padx=4, pady=6)

        self.scan_btn = ttk.Button(self, text="Scan USB", command=self._scan)
        self.scan_btn.grid(row=0, column=2, padx=4, pady=6)

        self.connect_btn = ttk.Button(self, text="Connect", command=self._connect)
        self.connect_btn.grid(row=0, column=3, padx=4, pady=6)

        self.disconnect_btn = ttk.Button(
            self, text="Disconnect", command=self._disconnect, state="disabled")
        self.disconnect_btn.grid(row=0, column=4, padx=4, pady=6)

        self.status_lbl = ttk.Label(self, text="Not connected", foreground="red")
        self.status_lbl.grid(row=0, column=5, padx=12, pady=6, sticky="w")
        self.columnconfigure(5, weight=1)

    def _scan(self):
        self.scan_btn.config(state="disabled")
        self.status_lbl.config(text="Scanning...", foreground="orange")
        self.update()

        def do_scan():
            devices = KCubeController.list_devices()
            self.after(0, lambda: self._scan_done(devices))

        threading.Thread(target=do_scan, daemon=True).start()

    def _scan_done(self, devices: list[str]):
        self.scan_btn.config(state="normal")
        if devices:
            self.sn_combo["values"] = devices
            self.sn_combo.set(devices[0])
            self.status_lbl.config(
                text=f"Found: {', '.join(devices)}", foreground="blue")
        else:
            self.sn_combo["values"] = []
            self.status_lbl.config(text="No Kinesis devices found", foreground="red")

    def _connect(self):
        sn = self.sn_var.get().strip()
        if not sn:
            messagebox.showwarning("No Serial Number", "Enter a serial number first.")
            return
        self.status_lbl.config(text="Connecting…", foreground="orange")
        self.update()
        if self.on_connect(sn):
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            self.sn_combo.config(state="disabled")
            self.scan_btn.config(state="disabled")
            self.status_lbl.config(text=f"Connected  S/N {sn}", foreground="green")
        else:
            self.status_lbl.config(text="Connection failed", foreground="red")

    def _disconnect(self):
        self.on_disconnect()
        self.connect_btn.config(state="normal")
        self.disconnect_btn.config(state="disabled")
        self.sn_combo.config(state="normal")
        self.scan_btn.config(state="normal")
        self.status_lbl.config(text="Disconnected", foreground="red")


# =============================================================================
# Status Panel
# =============================================================================

class StatusPanel(ttk.LabelFrame):
    """Live position, homed flag, and moving indicator."""

    def __init__(self, parent, controller_getter):
        super().__init__(parent, text="Status", padding=10)
        self.get_ctrl = controller_getter
        self._polling = False
        self._build()

    def _build(self):
        font_pos = ("TkFixedFont", 22, "bold")

        ttk.Label(self, text="Position").grid(row=0, column=0, sticky="w", padx=8)
        self.pos_var = tk.StringVar(value="--- mm")
        ttk.Label(self, textvariable=self.pos_var, font=font_pos,
                  foreground="#1a6ebd", width=12, anchor="e").grid(
            row=1, column=0, padx=8, pady=4)

        ttk.Separator(self, orient="vertical").grid(
            row=0, column=1, rowspan=2, fill="y", padx=10)

        info_frm = ttk.Frame(self)
        info_frm.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=4)

        ttk.Label(info_frm, text="Homed:").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        self.homed_var = tk.StringVar(value="—")
        self.homed_lbl = ttk.Label(info_frm, textvariable=self.homed_var,
                                    font=("TkDefaultFont", 11, "bold"), foreground="gray")
        self.homed_lbl.grid(row=0, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(info_frm, text="Moving:").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        self.moving_var = tk.StringVar(value="—")
        self.moving_lbl = ttk.Label(info_frm, textvariable=self.moving_var,
                                     font=("TkDefaultFont", 11, "bold"), foreground="gray")
        self.moving_lbl.grid(row=1, column=1, sticky="w", padx=4, pady=3)

        ttk.Label(self, text="(auto-updates every 0.5 s)",
                  foreground="gray", font=("TkDefaultFont", 8)).grid(
            row=2, column=0, columnspan=3, pady=(4, 0))

    def start_polling(self):
        if self._polling:
            return
        self._polling = True
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def stop_polling(self):
        self._polling = False

    def _poll_loop(self):
        while self._polling:
            ctrl = self.get_ctrl()
            if ctrl and ctrl.is_connected:
                try:
                    s = ctrl.get_status()
                    self.after(0, self._update, s)
                except Exception:
                    pass
            time.sleep(0.5)

    def _update(self, s: dict):
        pos = s.get("position_mm")
        self.pos_var.set(f"{pos:.4f} mm" if pos is not None else "--- mm")

        homed = s.get("is_homed", False)
        self.homed_var.set("YES" if homed else "NO")
        self.homed_lbl.config(foreground="#16a34a" if homed else "#dc2626")

        moving = s.get("is_moving", False)
        self.moving_var.set("YES" if moving else "no")
        self.moving_lbl.config(foreground="#d97706" if moving else "gray")

    def reset(self):
        self.pos_var.set("--- mm")
        self.homed_var.set("—")
        self.homed_lbl.config(foreground="gray")
        self.moving_var.set("—")
        self.moving_lbl.config(foreground="gray")


# =============================================================================
# Motion Control Panel
# =============================================================================

class MotionPanel(ttk.Frame):
    """Home, move-to, jog, and preset buttons."""

    DEFAULT_PRESETS = {
        "retrieval":  5.0,
        "dropping":   6.5,
        "retraction": 11.0,
    }

    def __init__(self, parent, controller_getter, on_action):
        super().__init__(parent)
        self.get_ctrl  = controller_getter
        self.on_action = on_action   # callback(str) for status bar
        self._build()

    def _build(self):
        # ---- Home ----
        home_frm = ttk.LabelFrame(self, text="Home", padding=8)
        home_frm.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        self.home_btn = ttk.Button(home_frm, text="Home Stage", width=14,
                                    command=self._home)
        self.home_btn.pack(padx=4, pady=4)
        ttk.Label(home_frm, text="(moves to 0 mm)", foreground="gray",
                  font=("TkDefaultFont", 8)).pack()

        # ---- Move to ----
        move_frm = ttk.LabelFrame(self, text="Move to absolute position", padding=8)
        move_frm.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        ttk.Label(move_frm, text="Position (mm):").grid(
            row=0, column=0, sticky="e", padx=4, pady=4)
        self.move_var = tk.StringVar(value="6.5")
        ttk.Entry(move_frm, textvariable=self.move_var, width=8).grid(
            row=0, column=1, padx=4, pady=4)
        self.move_btn = ttk.Button(move_frm, text="Move", width=8,
                                    command=self._move_to)
        self.move_btn.grid(row=0, column=2, padx=4)

        # ---- Jog ----
        jog_frm = ttk.LabelFrame(self, text="Jog", padding=8)
        jog_frm.grid(row=0, column=2, sticky="nsew", padx=6, pady=6)

        ttk.Label(jog_frm, text="Step (mm):").grid(
            row=0, column=0, sticky="e", padx=4, pady=4)
        self.jog_step_var = tk.StringVar(value="0.1")
        ttk.Entry(jog_frm, textvariable=self.jog_step_var, width=7).grid(
            row=0, column=1, padx=4, pady=4)

        btn_row = ttk.Frame(jog_frm)
        btn_row.grid(row=1, column=0, columnspan=2, pady=4)
        self.jog_rev_btn = ttk.Button(btn_row, text="◀ Reverse", width=10,
                                       command=lambda: self._jog("reverse"))
        self.jog_rev_btn.pack(side="left", padx=3)
        self.jog_fwd_btn = ttk.Button(btn_row, text="Forward ▶", width=10,
                                       command=lambda: self._jog("forward"))
        self.jog_fwd_btn.pack(side="left", padx=3)

        # ---- Presets ----
        preset_frm = ttk.LabelFrame(self, text="Named presets", padding=8)
        preset_frm.grid(row=1, column=0, columnspan=3, sticky="ew", padx=6, pady=6)

        for col, (name, mm) in enumerate(self.DEFAULT_PRESETS.items()):
            ttk.Button(
                preset_frm,
                text=f"{name.capitalize()}\n({mm} mm)",
                width=14,
                command=lambda n=name: self._move_to_preset(n),
            ).grid(row=0, column=col, padx=8, pady=4)

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

    def set_all_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for w in (self.home_btn, self.move_btn,
                  self.jog_fwd_btn, self.jog_rev_btn):
            w.config(state=state)
        for child in self.winfo_children():
            if isinstance(child, ttk.LabelFrame) and child.cget("text") == "Named presets":
                for btn in child.winfo_children():
                    if isinstance(btn, ttk.Button):
                        btn.config(state=state)

    def _ctrl(self):
        ctrl = self.get_ctrl()
        if ctrl is None or not ctrl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the stage first.")
            return None
        return ctrl

    def _run(self, fn, *args, label="…"):
        """Run a blocking motor command in a daemon thread."""
        self.set_all_enabled(False)
        self.on_action(label)

        def worker():
            try:
                result = fn(*args)
                self.after(0, lambda: self.on_action(f"Done: {result:.4f} mm"))
            except Exception as exc:
                self.after(0, lambda: self.on_action(f"Error: {exc}"))
            finally:
                self.after(0, lambda: self.set_all_enabled(True))

        threading.Thread(target=worker, daemon=True).start()

    def _home(self):
        ctrl = self._ctrl()
        if ctrl:
            self._run(ctrl.home, label="Homing…")

    def _move_to(self):
        ctrl = self._ctrl()
        if ctrl is None:
            return
        try:
            target = float(self.move_var.get())
        except ValueError:
            messagebox.showerror("Invalid", "Enter a valid position in mm.")
            return
        self._run(ctrl.move_to, target, label=f"Moving to {target:.2f} mm…")

    def _jog(self, direction: str):
        ctrl = self._ctrl()
        if ctrl is None:
            return
        try:
            step = float(self.jog_step_var.get())
        except ValueError:
            messagebox.showerror("Invalid", "Enter a valid jog step in mm.")
            return
        self._run(ctrl.jog, direction, step,
                  label=f"Jogging {direction} {step:.3f} mm…")

    def _move_to_preset(self, name: str):
        ctrl = self._ctrl()
        if ctrl is None:
            return
        mm = self.DEFAULT_PRESETS[name]
        self._run(ctrl.move_to, mm, label=f"Moving to {name} ({mm} mm)…")


# =============================================================================
# Motion Parameters Panel
# =============================================================================

class ParamsPanel(ttk.LabelFrame):
    """Velocity, acceleration, jog step, and backlash configuration."""

    def __init__(self, parent, controller_getter, on_action):
        super().__init__(parent, text="Motion Parameters", padding=8)
        self.get_ctrl  = controller_getter
        self.on_action = on_action
        self._build()

    def _build(self):
        fields = [
            ("Velocity (mm/s):",     "vel_var",  "1.0"),
            ("Acceleration (mm/s²):", "acc_var",  "1.0"),
            ("Jog step (mm):",        "jog_var",  "0.1"),
            ("Backlash (mm):",        "blsh_var", "0.0"),
        ]
        for col, (label, attr, default) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=0, column=col*2, sticky="e", padx=(8, 2))
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(self, textvariable=var, width=7).grid(
                row=0, column=col*2 + 1, sticky="w", padx=(0, 8))

        ttk.Button(self, text="Apply", command=self._apply).grid(
            row=0, column=len(fields)*2, padx=8)
        ttk.Label(self, text="(0.0 = keep device value)", foreground="gray",
                  font=("TkDefaultFont", 8)).grid(
            row=0, column=len(fields)*2 + 1, padx=4)

    def _apply(self):
        ctrl = self.get_ctrl()
        if ctrl is None or not ctrl.is_connected:
            messagebox.showwarning("Not Connected", "Connect to the stage first.")
            return
        try:
            vel  = float(self.vel_var.get())
            acc  = float(self.acc_var.get())
            jog  = float(self.jog_var.get())
            blsh = float(self.blsh_var.get())
        except ValueError:
            messagebox.showerror("Invalid", "All parameters must be numeric.")
            return

        def worker():
            try:
                ctrl.apply_motion_params(
                    velocity=vel, acceleration=acc, jog_step=jog, backlash=blsh)
                self.after(0, lambda: self.on_action("Motion parameters applied."))
            except Exception as exc:
                self.after(0, lambda: self.on_action(f"Error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()


# =============================================================================
# Main Application
# =============================================================================

class KCubeApp(tk.Tk):
    """Main application window for the KCube motor controller."""

    def __init__(self, default_sn: Optional[str] = None):
        super().__init__()
        self.title("KCube Motor Controller  (Thorlabs Z812 / KDC101)")
        self.resizable(True, False)
        self.controller: Optional[KCubeController] = None
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if default_sn:
            self.conn_frm.sn_var.set(default_sn)

    def _build(self):
        self.conn_frm = ConnectionFrame(self, self._on_connect, self._on_disconnect)
        self.conn_frm.pack(fill="x", padx=10, pady=6)

        self.status_panel = StatusPanel(self, self._get_ctrl)
        self.status_panel.pack(fill="x", padx=10, pady=4)

        self.motion_panel = MotionPanel(self, self._get_ctrl, self._set_status)
        self.motion_panel.pack(fill="x", padx=10, pady=4)
        self.motion_panel.set_all_enabled(False)

        self.params_panel = ParamsPanel(self, self._get_ctrl, self._set_status)
        self.params_panel.pack(fill="x", padx=10, pady=4)

        self.status_var = tk.StringVar(value="Ready — not connected")
        ttk.Label(self, textvariable=self.status_var,
                  relief="sunken", anchor="w").pack(
            fill="x", side="bottom", padx=2, pady=2)

    def _get_ctrl(self) -> Optional[KCubeController]:
        return self.controller

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    def _on_connect(self, sn: str) -> bool:
        ctrl = KCubeController(sn)
        if ctrl.connect():
            self.controller = ctrl
            self.status_panel.start_polling()
            self.motion_panel.set_all_enabled(True)
            self._set_status(f"Connected to KDC101  S/N {sn}")
            return True
        self._set_status("Connection failed — check serial number and USB/Kinesis")
        return False

    def _on_disconnect(self):
        self.status_panel.stop_polling()
        self.motion_panel.set_all_enabled(False)
        if self.controller:
            self.controller.disconnect()
            self.controller = None
        self.status_panel.reset()
        self._set_status("Disconnected")

    def _on_close(self):
        self.status_panel.stop_polling()
        if self.controller and self.controller.is_connected:
            self.controller.disconnect()
        self.destroy()


# =============================================================================
# Entry point
# =============================================================================

def main():
    import sys
    sn = sys.argv[1] if len(sys.argv) > 1 else None
    app = KCubeApp(default_sn=sn)
    app.mainloop()


if __name__ == "__main__":
    main()
