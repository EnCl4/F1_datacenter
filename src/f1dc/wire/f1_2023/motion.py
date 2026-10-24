"""T004 -- PacketMotionData, 1349 bytes.

This layout was verified against a real capture: speed derived from the velocity vector
peaks at 328 km/h, identical to CarTelemetry's independent 328 km/h. It supplies the
g-forces and the X/Z world positions used to draw the circuit map.

Direction vectors are transmitted as int16 and normalised by 32767 here, so the dataclass
holds unit-scale floats.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.registry import register

_DIR_SCALE = 32767.0


@dataclass(frozen=True, slots=True)
class MotionData:
    world_position_x: float
    world_position_y: float
    world_position_z: float
    world_velocity_x: float
    """Metres per second."""
    world_velocity_y: float
    world_velocity_z: float
    world_forward_dir_x: float
    world_forward_dir_y: float
    world_forward_dir_z: float
    world_right_dir_x: float
    world_right_dir_y: float
    world_right_dir_z: float
    g_force_lateral: float
    g_force_longitudinal: float
    g_force_vertical: float
    yaw: float
    """Radians."""
    pitch: float
    """Radians."""
    roll: float
    """Radians."""

    @property
    def speed_kph(self) -> float:
        """Speed from the velocity vector, independent of CarTelemetry's speed field."""
        return (
            math.sqrt(
                self.world_velocity_x**2 + self.world_velocity_y**2 + self.world_velocity_z**2
            )
            * 3.6
        )


@register
class MotionCodec(PerCarCodec):
    packet_id = 0
    wire_size = 1349
    name = "Motion"

    ITEM = struct.Struct(
        "<"
        "3f"  # worldPosition X, Y, Z
        "3f"  # worldVelocity X, Y, Z (m/s)
        "3h"  # worldForwardDir X, Y, Z (normalised by 32767)
        "3h"  # worldRightDir X, Y, Z (normalised by 32767)
        "3f"  # gForce lateral, longitudinal, vertical
        "3f"  # yaw, pitch, roll (radians)
    )

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> MotionData:
        v = cls.unpack_car(buf, index)
        return MotionData(
            *v[0:6],
            *(x / _DIR_SCALE for x in v[6:9]),
            *(x / _DIR_SCALE for x in v[9:12]),
            *v[12:18],
        )
