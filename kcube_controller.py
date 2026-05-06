"""
KCube Motor Controller - Controller

High-level API for a Thorlabs Z812 linear actuator driven by a KDC101
KCube DC Servo Motor Controller.  All positions are in millimetres.

Example:
    ctrl = KCubeController("27006288")
    if ctrl.connect():
        ctrl.home()
        ctrl.move_to(6.5)
        print(f"Position: {ctrl.get_position():.4f} mm")
        ctrl.disconnect()

Context manager:
    with KCubeController("27006288") as ctrl:
        ctrl.home()
        ctrl.move_to(6.5)

Motion parameters
-----------------
The KDC101 stores velocity, acceleration, jog step, and backlash in
non-volatile memory.  Passing None to setup_velocity / setup_jog preserves
whatever is already in the device, so you only need to change what you want
to tune.  Typical values: velocity 1 mm/s, acceleration 1 mm/s².

Named preset positions
----------------------
Presets are a convenience layer on top of move_to().  Pass a dict mapping
names → mm values:
    presets = {"retrieval": 5.0, "dropping": 6.5, "retraction": 11.0}
    ctrl.move_to_preset("dropping", presets)
"""

from __future__ import annotations

from typing import Optional

from kcube_connection import KCubeConnection, PYLABLIB_AVAILABLE


# Z812 travel range — used for position validation
_Z812_MIN_MM = 0.0
_Z812_MAX_MM = 12.0


def _validate_position(position_mm: float) -> None:
    if not (_Z812_MIN_MM <= position_mm <= _Z812_MAX_MM):
        raise ValueError(
            f"Position {position_mm:.4f} mm is outside Z812 travel range "
            f"({_Z812_MIN_MM}–{_Z812_MAX_MM} mm)"
        )


class KCubeController:
    """
    Unified high-level interface to a KDC101 driving a Z812 linear actuator.

    Covers:
    - Connection management   (connect, disconnect)
    - Status                  (get_position, is_homed, is_moving, get_status)
    - Motion parameters       (setup_velocity, setup_jog, set_backlash, apply_motion_params)
    - Motion commands         (home, move_to, move_by, jog, move_to_preset)
    """

    def __init__(self, serial_number: str, scale: int = 34304):
        """
        Parameters
        ----------
        serial_number : str
            KDC101 serial number (e.g. "27006288").
        scale : int
            Encoder steps per millimetre.  Use 34304 for the Z812.
        """
        self._conn = KCubeConnection(serial_number, scale)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        return self._conn.is_connected

    @property
    def serial_number(self) -> str:
        return self._conn.serial_number

    @property
    def is_available(self) -> bool:
        """True if pylablib and the Kinesis SDK are installed."""
        return PYLABLIB_AVAILABLE

    # =========================================================================
    # Device discovery
    # =========================================================================

    @staticmethod
    def list_devices() -> list[str]:
        """Return serial numbers of all detected Kinesis devices."""
        return KCubeConnection.list_devices()

    # =========================================================================
    # Connection
    # =========================================================================

    def connect(self) -> bool:
        """
        Connect to the KDC101.

        Returns
        -------
        bool
            True on success.

        Raises
        ------
        RuntimeError
            If pylablib is not installed.
        Exception
            On any Kinesis / USB communication error (propagated from KCubeConnection).
        """
        return self._conn.connect()

    def disconnect(self) -> None:
        """Close the connection to the KDC101."""
        self._conn.disconnect()

    # =========================================================================
    # Status
    # =========================================================================

    def get_position(self) -> Optional[float]:
        """Return the actual encoder position in mm, or None if not connected.

        Uses get_encoder() (SCC_GetEncoderCounter) rather than get_position()
        (SCC_GetPosition) because get_position() returns the commanded setpoint
        after a move, not the true mechanical position as shown on the KCube
        display.  Falls back to get_position() if get_encoder() is unavailable.
        """
        motor = self._conn.motor
        if motor is None:
            return None
        try:
            return float(motor.get_encoder(scale=True))
        except AttributeError:
            return float(motor.get_position())

    def is_homed(self) -> bool:
        """Return True if the stage has been homed in this session."""
        motor = self._conn.motor
        if motor is None:
            return False
        try:
            return "homed" in motor.get_status()
        except Exception:
            return False

    def is_moving(self) -> bool:
        """Return True if a move is in progress."""
        motor = self._conn.motor
        if motor is None:
            return False
        try:
            return bool(motor.is_moving())
        except Exception:
            return False

    def get_status(self) -> dict:
        """
        Return a snapshot of the stage state.

        Returns
        -------
        dict
            connected   : bool
            position_mm : float  (0.0 if not connected)
            is_homed    : bool
            is_moving   : bool
        """
        pos = self.get_position()
        return {
            "connected":   self.is_connected,
            "position_mm": pos if pos is not None else 0.0,
            "is_homed":    self.is_homed(),
            "is_moving":   self.is_moving(),
        }

    # =========================================================================
    # Motion parameters
    # =========================================================================

    def setup_velocity(self, max_velocity: Optional[float] = None,
                       acceleration: Optional[float] = None) -> None:
        """
        Set velocity and/or acceleration.  None preserves the device value.
        """
        motor = self._conn.motor
        if motor is None:
            return
        if max_velocity is not None or acceleration is not None:
            motor.setup_velocity(max_velocity=max_velocity, acceleration=acceleration)

    def setup_jog(self, step_size: Optional[float] = None) -> None:
        """Set the jog step size in mm.  None is a no-op."""
        motor = self._conn.motor
        if motor is None or step_size is None:
            return
        motor.setup_jog(step_size=step_size)

    def set_backlash(self, backlash_mm: float) -> None:
        """Set backlash compensation in mm.  Values ≤ 0 are ignored."""
        motor = self._conn.motor
        if motor is None or backlash_mm <= 0:
            return
        motor.set_backlash(backlash_mm)

    def apply_motion_params(self, velocity: float = 0.0, acceleration: float = 0.0,
                            jog_step: float = 0.0, backlash: float = 0.0) -> None:
        """
        Apply all motion parameters at once.  Values of 0.0 preserve the
        device's current (non-volatile) setting.
        """
        self.setup_velocity(
            max_velocity=velocity    if velocity    > 0 else None,
            acceleration=acceleration if acceleration > 0 else None,
        )
        if jog_step > 0:
            self.setup_jog(step_size=jog_step)
        if backlash > 0:
            self.set_backlash(backlash)

    # =========================================================================
    # Motion commands
    # =========================================================================

    def home(self, timeout: float = 60.0) -> float:
        """
        Home the stage (blocks until complete).

        Returns
        -------
        float
            Position in mm after homing.

        Raises
        ------
        RuntimeError if not connected.
        """
        motor = self._conn.motor
        if motor is None:
            raise RuntimeError("Not connected")
        motor.home(sync=True, timeout=timeout)
        return float(motor.get_position())

    def move_to(self, position_mm: float, timeout: float = 60.0) -> float:
        """
        Move to an absolute position (blocks until complete).

        Parameters
        ----------
        position_mm : float
            Target position in mm.  Must be within 0–12 mm.
        timeout : float
            Maximum wait time in seconds.

        Returns
        -------
        float
            Actual position after move.

        Raises
        ------
        ValueError   if position_mm is outside the Z812 travel range.
        RuntimeError if not connected.
        """
        motor = self._conn.motor
        if motor is None:
            raise RuntimeError("Not connected")
        _validate_position(position_mm)
        motor.move_to(position_mm)
        motor.wait_move(timeout=timeout)
        return float(motor.get_position())

    def move_by(self, step_mm: float, timeout: float = 30.0) -> float:
        """
        Move by a relative displacement (blocks until complete).

        Parameters
        ----------
        step_mm : float
            Signed displacement in mm (positive = forward, negative = reverse).
        timeout : float
            Maximum wait time in seconds.

        Returns
        -------
        float
            Actual position after move.

        Raises
        ------
        ValueError   if the resulting position would be outside the travel range.
        RuntimeError if not connected.
        """
        motor = self._conn.motor
        if motor is None:
            raise RuntimeError("Not connected")
        current = float(motor.get_position())
        _validate_position(current + step_mm)
        motor.move_by(step_mm)
        motor.wait_move(timeout=timeout)
        return float(motor.get_position())

    def jog(self, direction: str = "forward", step_mm: Optional[float] = None,
            timeout: float = 30.0) -> float:
        """
        Move by one jog step in the given direction.

        Parameters
        ----------
        direction : str
            "forward" or "reverse".
        step_mm : float, optional
            Override the jog step size.  If None, uses the device's stored value.
        timeout : float
            Maximum wait time in seconds.

        Returns
        -------
        float
            Actual position after jog.
        """
        if direction not in ("forward", "reverse"):
            raise ValueError(f"direction must be 'forward' or 'reverse', got {direction!r}")
        if step_mm is not None and step_mm <= 0:
            raise ValueError(f"step_mm must be positive, got {step_mm}")
        signed = (step_mm if step_mm is not None else 0.1) * (1 if direction == "forward" else -1)
        return self.move_by(signed, timeout=timeout)

    def move_to_preset(self, name: str, presets: dict[str, float],
                       timeout: float = 60.0) -> float:
        """
        Move to a named preset position.

        Parameters
        ----------
        name : str
            Preset name (key in *presets*).
        presets : dict
            Mapping of name → position in mm.
        timeout : float
            Maximum wait time in seconds.

        Returns
        -------
        float
            Actual position after move.

        Raises
        ------
        KeyError  if *name* is not in *presets*.
        """
        if name not in presets:
            raise KeyError(f"Unknown preset {name!r}. Available: {list(presets)}")
        return self.move_to(float(presets[name]), timeout=timeout)

    # =========================================================================
    # Convenience
    # =========================================================================

    def print_status(self) -> None:
        """Print a formatted status summary to stdout."""
        s = self.get_status()
        print("\n" + "=" * 48)
        print("KCube Motor Controller Status")
        print("=" * 48)
        print(f"Connected  : {s['connected']}")
        if s["connected"]:
            print(f"S/N        : {self.serial_number}")
            print(f"Position   : {s['position_mm']:.4f} mm")
            print(f"Homed      : {s['is_homed']}")
            print(f"Moving     : {s['is_moving']}")
        print("=" * 48)

    # =========================================================================
    # Context manager
    # =========================================================================

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()
        return False


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    import sys

    sn = sys.argv[1] if len(sys.argv) > 1 else "27006288"
    ctrl = KCubeController(sn)

    print(f"Connecting to KDC101  S/N {sn} ...")
    if ctrl.connect():
        ctrl.print_status()

        print("\nAvailable commands:")
        print("  python kcube_controller.py <sn> home")
        print("  python kcube_controller.py <sn> <position_mm>")

        if len(sys.argv) > 2:
            arg = sys.argv[2]
            if arg == "home":
                pos = ctrl.home()
                print(f"Homed  →  {pos:.4f} mm")
            else:
                try:
                    target = float(arg)
                    pos = ctrl.move_to(target)
                    print(f"Moved to {target} mm  →  actual {pos:.4f} mm")
                except ValueError as exc:
                    print(f"Error: {exc}")

        ctrl.disconnect()
    else:
        print("Connection failed — check serial number and USB cable.")
        sys.exit(1)
