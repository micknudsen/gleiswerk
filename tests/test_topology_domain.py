"""Tests for schema-version 3 controller-independent topology values."""

import unittest
from typing import cast

from gleiswerk.topology import (
    Connection,
    ConnectionId,
    ConnectionMovement,
    ControlDevice,
    ControlDeviceId,
    DevicePositionId,
    DeviceRequirement,
    Junction,
    JunctionId,
    JunctionPassage,
    JunctionPassageId,
    JunctionPort,
    JunctionResource,
    OccupancyCoverage,
    OccupancyExtent,
    OccupancyZone,
    OccupancyZoneId,
    PortId,
    ProtectionZone,
    ProtectionZoneId,
    TrackSection,
    TrackSectionId,
    TrackSectionMovement,
    TrackSectionPort,
    TrackSectionResource,
)


class ResourceCompleteTopologyModelTest(unittest.TestCase):
    def test_directed_path_elements_retain_declared_ends_and_requirements(
        self,
    ) -> None:
        west_entry = TrackSection(
            TrackSectionId("west-entry"),
            (PortId("west"), PortId("east")),
            (
                TrackSectionMovement(PortId("west"), PortId("east")),
                TrackSectionMovement(PortId("east"), PortId("west")),
            ),
        )
        west_throat = Junction(
            JunctionId("west-throat"),
            (PortId("west"), PortId("platform")),
        )
        connection = Connection(
            ConnectionId("entry-to-throat"),
            (
                TrackSectionPort(west_entry.id, PortId("east")),
                JunctionPort(west_throat.id, PortId("west")),
            ),
            (
                ConnectionMovement(
                    TrackSectionPort(west_entry.id, PortId("east")),
                    JunctionPort(west_throat.id, PortId("west")),
                ),
            ),
        )
        control_device = ControlDevice(
            ControlDeviceId("west-throat-turnout"),
            (DevicePositionId("normal"), DevicePositionId("reverse")),
        )
        passage = JunctionPassage(
            JunctionPassageId("west-to-platform"),
            west_throat.id,
            PortId("west"),
            PortId("platform"),
            (DeviceRequirement(control_device.id, DevicePositionId("normal")),),
        )
        self.assertEqual(connection.movements[0].from_port.owner_id, west_entry.id)
        self.assertEqual(passage.from_port, PortId("west"))
        self.assertEqual(
            passage.requirements,
            (DeviceRequirement(control_device.id, DevicePositionId("normal")),),
        )

    def test_occupancy_and_protection_values_retain_physical_resource_identities(
        self,
    ) -> None:
        west_entry = TrackSectionResource(TrackSectionId("west-entry"))
        west_throat = JunctionResource(JunctionId("west-throat"))
        occupancy_zone = OccupancyZone(
            OccupancyZoneId("entry-detector"),
            (
                OccupancyCoverage(west_entry, OccupancyExtent.COMPLETE),
                OccupancyCoverage(west_throat, OccupancyExtent.PARTIAL),
            ),
        )
        protection_zone = ProtectionZone(ProtectionZoneId("west-flank"))

        self.assertEqual(occupancy_zone.coverage[0].resource, west_entry)
        self.assertEqual(occupancy_zone.coverage[1].resource, west_throat)
        self.assertEqual(protection_zone.id, "west-flank")

    def test_physical_resource_types_remain_distinct_with_the_same_identifier(
        self,
    ) -> None:
        track_section = TrackSectionResource(TrackSectionId("shared-resource"))
        junction = JunctionResource(JunctionId("shared-resource"))

        self.assertNotEqual(track_section, junction)

    def test_track_section_requires_two_ports_and_declared_distinct_movements(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "exactly two"):
            TrackSection(
                TrackSectionId("entry"),
                cast(tuple[PortId, PortId], (PortId("west"),)),
                (TrackSectionMovement(PortId("west"), PortId("east")),),
            )

        with self.assertRaisesRegex(ValueError, "declared ports"):
            TrackSection(
                TrackSectionId("entry"),
                (PortId("west"), PortId("east")),
                (TrackSectionMovement(PortId("west"), PortId("missing")),),
            )

        with self.assertRaisesRegex(ValueError, "distinct"):
            TrackSectionMovement(PortId("west"), PortId("west"))

    def test_connection_requires_an_unordered_pair_and_matching_movements(self) -> None:
        entry_east = TrackSectionPort(TrackSectionId("entry"), PortId("east"))
        throat_west = JunctionPort(JunctionId("throat"), PortId("west"))
        connection = Connection(
            ConnectionId("entry-to-throat"),
            (entry_east, throat_west),
            (ConnectionMovement(entry_east, throat_west),),
        )

        self.assertEqual(connection.ports, (entry_east, throat_west))

        with self.assertRaisesRegex(ValueError, "two distinct ports"):
            Connection(
                ConnectionId("loop"),
                (entry_east, entry_east),
                (ConnectionMovement(entry_east, throat_west),),
            )

        with self.assertRaisesRegex(ValueError, "connection ports"):
            Connection(
                ConnectionId("entry-to-throat"),
                (entry_east, throat_west),
                (
                    ConnectionMovement(
                        entry_east,
                        JunctionPort(JunctionId("other"), PortId("west")),
                    ),
                ),
            )

    def test_junction_passage_and_device_requirements_are_locally_validated(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "at least two"):
            ControlDevice(ControlDeviceId("turnout"), (DevicePositionId("normal"),))

        with self.assertRaisesRegex(ValueError, "distinct"):
            JunctionPassage(
                JunctionPassageId("invalid"),
                JunctionId("throat"),
                PortId("west"),
                PortId("west"),
            )

        with self.assertRaisesRegex(ValueError, "device requirements"):
            JunctionPassage(
                JunctionPassageId("invalid-requirements"),
                JunctionId("throat"),
                PortId("west"),
                PortId("east"),
                (
                    DeviceRequirement(
                        ControlDeviceId("turnout"), DevicePositionId("normal")
                    ),
                    DeviceRequirement(
                        ControlDeviceId("turnout"), DevicePositionId("reverse")
                    ),
                ),
            )

    def test_occupancy_zone_requires_unique_claimable_resource_coverage(self) -> None:
        entry = TrackSectionResource(TrackSectionId("entry"))
        with self.assertRaisesRegex(ValueError, "nonempty"):
            OccupancyZone(OccupancyZoneId("detector"), ())

        with self.assertRaisesRegex(ValueError, "once"):
            OccupancyZone(
                OccupancyZoneId("detector"),
                (
                    OccupancyCoverage(entry, OccupancyExtent.COMPLETE),
                    OccupancyCoverage(entry, OccupancyExtent.PARTIAL),
                ),
            )
