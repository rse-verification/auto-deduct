"""Regression coverage for safe, documented functional-inference boundaries."""

import unittest

from integration_support import (
    DockerPipelineTestCase,
    INTEGRATION_SKIP_REASON,
    RUN_INTEGRATION,
)


@unittest.skipUnless(RUN_INTEGRATION, INTEGRATION_SKIP_REASON)
class ExpectedLimitationIntegrationTests(DockerPipelineTestCase):
    """Ensure unsupported forms fail clearly instead of claiming verification."""

    def assert_limitation(self, case: str, diagnostic: str) -> None:
        """Require TriCera's first functional-boundary diagnostic for one case."""
        run = self.run_autodeduct(
            f"tests/cases/expected-limitation/{case}",
            "entry",
            frama_c_options=("-lib-entry",),
        )
        self.assert_expected_failure(run, "saida_tricera", diagnostic)

    def test_float_arithmetic_is_rejected(self):
        """Require the explicit no-floating-point fallback boundary."""
        self.assert_limitation(
            "helper_float_arithmetic.c", "type 'float' is not supported"
        )

    def test_pointer_arithmetic_fails_at_functional_inference(self):
        """Require a clear parser boundary for the direct pointer form."""
        self.assert_limitation(
            "helper_pointer_arithmetic.c", "TriCera reported a syntax error"
        )

    def test_nested_pointer_fails_at_functional_inference(self):
        """Require a clear parser boundary for the direct nested-pointer form."""
        self.assert_limitation(
            "helper_nested_pointer.c", "TriCera reported a syntax error"
        )
