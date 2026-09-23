# Public Regression Cases

These public, GPLv2-covered C/ACSL sources are copied unchanged from the
`autodeduct-support-microtests` branch at revision
`f5b8de8dbb16e942841c60bff3ec007daad0e4f1`. They contain no Scania or other
proprietary source.

Each folder describes the expected AutoDeduct outcome, not a claim that every
nearby C or ACSL pattern has the same support level:

| Folder | Expected AutoDeduct result | Expected Python regression result |
| --- | --- | --- |
| `supported/` | Complete proof | Pass |
| `expected-warning/` | Warning followed by complete proof | Pass |
| `expected-limitation/` | Clear safe failure at the first unsupported stage | Pass |
| `expected-incomplete-wp/` | WP runs but leaves proof obligations unresolved | Pass |

An expected pipeline failure is a passing regression when it remains explicit,
safe, and correctly classified. Open investigations are intentionally not
included until their expected outcome and owning component are stable.
