"""Opt-in end-to-end regression test for the shipped public ASE 2024 example."""

import unittest

from integration_support import (
    DockerPipelineTestCase,
    INTEGRATION_SKIP_REASON,
    RUN_INTEGRATION,
)


@unittest.skipUnless(
    RUN_INTEGRATION,
    INTEGRATION_SKIP_REASON,
)
class Ase2024IntegrationTests(DockerPipelineTestCase):
    """Exercise the full shipped pipeline instead of mocked stage orchestration."""

    def test_public_ase_2024_example_proves_end_to_end(self):
        """Require the public example to produce a complete verified report."""
        report = self.run_autodeduct("examples/ase-2024", "main")
        self.assert_complete_verification(report)
