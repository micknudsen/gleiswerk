"""Tests for controller-independent logical evidence contracts."""

import unittest
from datetime import UTC, datetime, timedelta

from gleiswerk.evidence import (
    DevicePositionEvidence,
    DevicePositionEvidenceOutcome,
    DevicePositionEvidenceResult,
    EvidenceFreshness,
    EvidenceFreshnessBasis,
    EvidenceSourceId,
    EvidenceSourceStatus,
    OccupancyEvidence,
    OccupancyEvidenceOutcome,
    OccupancyEvidenceResult,
    OccupancyState,
)
from gleiswerk.topology import ControlDeviceId, DevicePositionId, OccupancyZoneId

NOW = datetime(2026, 8, 12, 16, 0, tzinfo=UTC)


class LogicalEvidenceContractTest(unittest.TestCase):
    def test_available_evidence_retains_logical_identity_revision_and_observation(
        self,
    ) -> None:
        occupancy = OccupancyEvidence(
            OccupancyZoneId("platform-detector"),
            "topology-abc123",
            EvidenceSourceId("platform-feedback"),
            EvidenceSourceStatus.AVAILABLE,
            NOW,
            OccupancyState.CLEAR,
        )
        device = DevicePositionEvidence(
            ControlDeviceId("platform-turnout"),
            "topology-abc123",
            EvidenceSourceId("platform-turnout-feedback"),
            EvidenceSourceStatus.AVAILABLE,
            NOW,
            DevicePositionId("normal"),
        )

        self.assertIs(occupancy.state, OccupancyState.CLEAR)
        self.assertEqual(device.position_id, "normal")
        self.assertEqual(occupancy.topology_revision, device.topology_revision)

    def test_freshness_is_derived_from_an_explicit_evaluation_basis(self) -> None:
        basis = EvidenceFreshnessBasis(NOW, timedelta(seconds=30))

        self.assertIs(
            basis.qualify(NOW - timedelta(seconds=30)), EvidenceFreshness.FRESH
        )
        self.assertIs(
            basis.qualify(NOW - timedelta(seconds=31)), EvidenceFreshness.STALE
        )

    def test_observations_retain_an_exact_revision_for_mismatch_rejection(self) -> None:
        occupancy = OccupancyEvidence(
            OccupancyZoneId("platform-detector"),
            "topology-previous",
            EvidenceSourceId("platform-feedback"),
            EvidenceSourceStatus.AVAILABLE,
            NOW,
            OccupancyState.CLEAR,
        )

        self.assertNotEqual(occupancy.topology_revision, "topology-active")

    def test_unknown_or_faulted_evidence_cannot_claim_a_known_value(self) -> None:
        for status in (EvidenceSourceStatus.UNKNOWN, EvidenceSourceStatus.FAULTED):
            with self.subTest(status=status):
                with self.assertRaisesRegex(
                    ValueError, "unavailable evidence cannot declare"
                ):
                    OccupancyEvidence(
                        OccupancyZoneId("platform-detector"),
                        "topology-abc123",
                        EvidenceSourceId("platform-feedback"),
                        status,
                        NOW,
                        OccupancyState.CLEAR,
                    )
                with self.assertRaisesRegex(
                    ValueError, "unavailable evidence cannot declare"
                ):
                    DevicePositionEvidence(
                        ControlDeviceId("platform-turnout"),
                        "topology-abc123",
                        EvidenceSourceId("platform-turnout-feedback"),
                        status,
                        NOW,
                        DevicePositionId("normal"),
                    )

    def test_results_express_stable_clear_occupied_and_aligned_outcomes(self) -> None:
        occupancy = OccupancyEvidenceResult(
            OccupancyZoneId("platform-detector"),
            EvidenceSourceId("platform-feedback"),
            OccupancyEvidenceOutcome.OCCUPIED,
        )
        device = DevicePositionEvidenceResult(
            ControlDeviceId("platform-turnout"),
            DevicePositionId("normal"),
            EvidenceSourceId("platform-turnout-feedback"),
            DevicePositionEvidenceOutcome.UNALIGNED,
        )

        self.assertIs(occupancy.outcome, OccupancyEvidenceOutcome.OCCUPIED)
        self.assertIs(device.outcome, DevicePositionEvidenceOutcome.UNALIGNED)

    def test_evidence_times_must_be_timezone_aware(self) -> None:
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            EvidenceFreshnessBasis(NOW.replace(tzinfo=None), timedelta(seconds=30))
