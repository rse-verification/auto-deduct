"""Regression coverage for inputs that reach WP but are not fully proved."""

import unittest

from integration_support import (
    DockerPipelineTestCase,
    INTEGRATION_SKIP_REASON,
    RUN_INTEGRATION,
)


@unittest.skipUnless(RUN_INTEGRATION, INTEGRATION_SKIP_REASON)
class ExpectedIncompleteWpIntegrationTests(DockerPipelineTestCase):
    """Ensure known incomplete proof cases remain explicit and non-silent."""

    def test_loop_without_invariant_reaches_incomplete_wp(self):
        """Require the loop case to reach WP and report an incomplete proof."""
        run = self.run_autodeduct(
            "tests/cases/expected-incomplete-wp/helper_loop_without_invariant.c",
            "entry",
            frama_c_options=("-lib-entry",),
        )
        self.assert_expected_failure(run, "wp", "WP proved")
        stages = {stage["name"]: stage for stage in run.report["stages"]}
        self.assertEqual(stages["contract_check"]["status"], "passed")

    def test_local_static_state_reports_missing_contract_and_incomplete_wp(self):
        """Require persistent local state to remain a visible V1 boundary."""
        run = self.run_autodeduct(
            "tests/cases/expected-incomplete-wp/local_static_helper_persistence.c",
            "entry",
            frama_c_options=("-lib-entry",),
        )
        self.assert_expected_failure(run, "wp", "WP proved")
        self.assertEqual(run.report["contract_report"]["missing_contracts"], ["next_count"])
