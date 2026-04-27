"""
KCube Motor Controller - Connection Layer

Low-level connection to a Thorlabs KDC101 KCube DC Servo Motor Controller
via the pylablib wrapper for the Kinesis SDK.

The KDC101 communicates over USB-serial.  Rapid open/close cycles can leave
stale bytes in the OS buffer that are then mis-read as the start of the next
response message, producing a "message sync error".  The SETTLE_DELAY_S sleep
after opening gives the driver time to drain any residual data before the
first command is sent.

Scale note
----------
The Z812 linear actuator has 34304 encoder steps per millimetre.
Passing scale=34304 to KinesisMotor tells pylablib to express all positions
in mm rather than in raw encoder counts.  Do NOT use scale="Z812" — in
pylablib ≥ 1.4 this returns positions in metres (34304E3 steps/m), giving
readings ~1000× too small.

Dependencies
------------
  pip install pylablib
  Thorlabs Kinesis software (provides backend DLLs):
  https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=Motion_Control
"""

from __future__ import annotations

import time
from typing import Optional

try:
    from pylablib.devices import Thorlabs
    PYLABLIB_AVAILABLE = True
except ImportError:
    PYLABLIB_AVAILABLE = False


class KCubeConnection:
    """
    Manages an open connection to a KDC101 KCube DC Servo Motor Controller.

    Wraps pylablib's KinesisMotor, exposing connect / disconnect and the
    underlying motor object for use by KCubeController.
    """

    SETTLE_DELAY_S = 0.5  # drain stale USB-serial bytes after opening

    def __init__(self, serial_number: str, scale: int = 34304):
        """
        Parameters
        ----------
        serial_number : str
            KDC101 serial number as printed on the controller label (e.g. "27006288").
        scale : int
            Encoder steps per millimetre.  Use 34304 for the Z812 actuator.
        """
        self._serial_number = serial_number
        self._scale         = scale
        self._motor         = None
        self._connected     = False

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def serial_number(self) -> str:
        return self._serial_number

    @property
    def motor(self):
        """The underlying pylablib KinesisMotor, or None if not connected."""
        return self._motor

    # =========================================================================
    # Device discovery
    # =========================================================================

    @staticmethod
    def list_devices() -> list[str]:
        """Return serial numbers of all Kinesis devices detected via USB."""
        if not PYLABLIB_AVAILABLE:
            return []
        try:
            return [str(sn) for sn in Thorlabs.list_kinesis_devices()]
        except Exception:
            return []

    # =========================================================================
    # Connection management
    # =========================================================================

    def connect(self) -> bool:
        """
        Open a connection to the KDC101.

        Returns
        -------
        bool
            True on success.

        Raises
        ------
        RuntimeError
            If pylablib is not installed.
        Exception
            On any Kinesis / USB communication error.
        """
        if not PYLABLIB_AVAILABLE:
            raise RuntimeError(
                "pylablib not installed.  Run: pip install pylablib\n"
                "Also ensure Thorlabs Kinesis is installed."
            )
        if self._connected:
            return True

        motor = Thorlabs.KinesisMotor(self._serial_number, scale=self._scale)
        motor.open()
        time.sleep(self.SETTLE_DELAY_S)
        self._motor     = motor
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Close the connection to the KDC101."""
        if self._motor is not None:
            try:
                self._motor.close()
            except Exception:
                pass
            self._motor = None
        self._connected = False

    # =========================================================================
    # Context manager
    # =========================================================================

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.disconnect()

    def __del__(self):
        try:
            if self._connected:
                self.disconnect()
        except Exception:
            pass
