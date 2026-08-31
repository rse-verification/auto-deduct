# Supported Public Microtests

These seven C/ACSL sources are copied without modification from the public
`autodeduct-support-microtests` branch of AutoDeduct, revision
`f5b8de8dbb16e942841c60bff3ec007daad0e4f1`, under
`autodeduct-support/micro-tests/`. They are GPLv2-covered public test inputs;
no Scania or other proprietary source is included.

Each source has a contract on `entry` and calls helpers without written helper
contracts. The integration suite runs every case with `--entry-point entry`
and Frama-C's `-lib-entry` option. A passing regression requires complete
Saida/TriCera inference, usable ISP output, no missing reachable helper
contracts, and complete WP verification.

These probes establish support only for their exact input patterns. They do
not turn a source rewrite or a nearby pattern into general C or ACSL support.
