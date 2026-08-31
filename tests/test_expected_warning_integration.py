"""Regression coverage for warnings that still allow complete verification."""

import unittest

from integration_support import (
    DockerPipelineTestCase,
    INTEGRATION_SKIP_REASON,
    RUN_INTEGRATION,
)


@unittest.skipUnless(RUN_INTEGRATION, INTEGRATION_SKIP_REASON)
class ExpectedWarningIntegrationTests(DockerPipelineTestCase):
    """Keep non-fatal diagnostics visible without discarding valid proofs."""

    def test_enum_switch_reports_isp_warning_and_proves(self):
        """Accept ISP-W002 only because downstream contract checking and WP pass."""
        run = self.run_autodeduct(
            "tests/cases/expected-warning/helper_enum_switch_basic.c",
            "entry",
            frama_c_options=("-lib-entry",),
        )
        self.assert_verified_with_warning(run, "isp_eva", "ISP-W002")
