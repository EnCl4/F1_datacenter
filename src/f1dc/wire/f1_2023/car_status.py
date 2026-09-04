"""T017 -- PacketCarStatusData, 1239 bytes.

Supplies tyre compound and age, fuel state and ERS. Tyre compound and age are part of a
lap's comparability context (FR-011, principle VI): a 1:11 on fresh softs is not the
same lap time as a 1:11 on twenty-lap-old hards.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from f1dc.wire.base import PerCarCodec
from f1dc.wire.f1_2023 import enums
from f1dc.wire.registry import register


@dataclass(frozen=True, slots=True)
class CarStatusData:
    traction_control: int
    anti_lock_brakes: int
    fuel_mix: int
    front_brake_bias: int
    pit_limiter_status: int
    fuel_in_tank: float
    fuel_capacity: float
    fuel_remaining_laps: float
    max_rpm: int
    idle_rpm: int
    max_gears: int
    drs_allowed: int
    drs_activation_distance: int
    actual_tyre_compound: int
    visual_tyre_compound: int
    tyres_age_laps: int
    vehicle_fia_flags: int
    engine_power_ice: float
    engine_power_mguk: float
    ers_store_energy: float
    ers_deploy_mode: int
    ers_harvested_this_lap_mguk: float
    ers_harvested_this_lap_mguh: float
    ers_deployed_this_lap: float
    network_paused: int

    @property
    def driver_aids(self) -> dict[str, int]:
        """Traction control and ABS -- which are NOT in the Session packet.

        The Session packet carries steering, braking, gearbox, pit, pit-release, ERS,
        DRS and racing-line assists. Traction control and ABS live only here. Both
        materially change achievable lap times, so constitution principle VI's
        "comparability context" is incomplete without this packet: a session summary
        built from the Session packet alone would report "no assists" for a driver
        running full traction control.

        Found by decoding the reference capture, which reports Session braking assist
        off while CarStatus reports traction control 2 and ABS on.
        """
        return {
            "traction_control": self.traction_control,
            "anti_lock_brakes": self.anti_lock_brakes,
        }

    @property
    def actual_compound_name(self) -> str:
        return enums.actual_compound_name(self.actual_tyre_compound)

    @property
    def visual_compound_name(self) -> str:
        return enums.visual_compound_name(self.visual_tyre_compound)


@register
class CarStatusCodec(PerCarCodec):
    packet_id = 7
    wire_size = 1239
    name = "CarStatus"

    ITEM = struct.Struct(
        "<"
        "BBBBB"  # tractionControl .. pitLimiterStatus
        "fff"  # fuelInTank, fuelCapacity, fuelRemainingLaps
        "HH"  # maxRPM, idleRPM
        "BB"  # maxGears, drsAllowed
        "H"  # drsActivationDistance
        "BBB"  # actualTyreCompound, visualTyreCompound, tyresAgeLaps
        "b"  # vehicleFiaFlags (signed: -1 means invalid)
        "fff"  # enginePowerICE, enginePowerMGUK, ersStoreEnergy
        "B"  # ersDeployMode
        "fff"  # ersHarvestedMGUK, ersHarvestedMGUH, ersDeployed
        "B"  # networkPaused
    )

    @classmethod
    def decode_car(cls, buf: bytes | memoryview, index: int) -> CarStatusData:
        return CarStatusData(*cls.unpack_car(buf, index))
