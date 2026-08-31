"""Regression matrix for public cases that currently pass the whole pipeline."""

import unittest

from integration_support import (
    DockerPipelineTestCase,
    INTEGRATION_SKIP_REASON,
    RUN_INTEGRATION,
)


@unittest.skipUnless(RUN_INTEGRATION, INTEGRATION_SKIP_REASON)
class PublicMicrotestIntegrationTests(DockerPipelineTestCase):
    """Ensure previously supported public patterns remain fully provable."""

    def assert_supported_case(self, case: str) -> None:
        """Run one strict helper-inference source with its documented profile."""
        run = self.run_autodeduct(
            f"tests/cases/supported/{case}",
            "entry",
            frama_c_options=("-lib-entry",),
        )
        self.assert_complete_verification(run)

    def test_int_if_helper(self):
        """Preserve basic integer branch inference."""
        self.assert_supported_case("int_if_helper.c")

    def test_struct_basic(self):
        """Preserve basic struct-field inference."""
        self.assert_supported_case("helper_struct_basic.c")

    def test_assigns_old_basic(self):
        """Preserve the selected assigns-and-old-state pattern."""
        self.assert_supported_case("helper_assigns_old_basic.c")

    def test_two_level_call_chain(self):
        """Preserve inference across two helper levels."""
        self.assert_supported_case("helper_two_level_call_chain.c")

    def test_multiple_call_contexts(self):
        """Preserve repeated helper inference across call contexts."""
        self.assert_supported_case("helper_multiple_call_contexts.c")

    def test_struct_return_whole(self):
        """Preserve simple whole-struct return inference."""
        self.assert_supported_case("helper_struct_return_whole.c")
