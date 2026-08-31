"""Regression matrix for public cases that currently pass the whole pipeline."""

import unittest

from integration_support import (
    DockerPipelineTestCase,
    INTEGRATION_SKIP_REASON,
    RUN_INTEGRATION,
)


SUPPORTED_CASES = (
    "int_if_helper.c",
    "helper_struct_basic.c",
    "helper_enum_switch_basic.c",
    "helper_assigns_old_basic.c",
    "helper_two_level_call_chain.c",
    "helper_multiple_call_contexts.c",
    "helper_struct_return_whole.c",
)


@unittest.skipUnless(RUN_INTEGRATION, INTEGRATION_SKIP_REASON)
class PublicMicrotestIntegrationTests(DockerPipelineTestCase):
    """Ensure previously supported public patterns remain fully provable."""

    def test_supported_microtests_prove_end_to_end(self):
        """Run each strict helper-inference source with its documented profile."""
        for case in SUPPORTED_CASES:
            with self.subTest(case=case):
                report = self.run_autodeduct(
                    f"tests/cases/supported/{case}",
                    "entry",
                    frama_c_options=("-lib-entry",),
                )
                self.assert_complete_verification(report)
