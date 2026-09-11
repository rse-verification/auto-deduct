# Roadmap

This is a living document describing the roadmap of the AutoDeduct toolchain
and what the target for each version is.

## Version 1.0.0 "Rubber Duck"

* Reproducable builds of docker image.
  
  * Specific version of WP-solvers
  
    * Z3
    * CVC4
    * Alt-Ergo

  * Specific version of TriCera
  * Specific version of Frama-C
  
    * RTE?
    * RTE-WP
  
  * Specific version of ISP
  * Specific version of Saida
  * (Specific version of Eldarica)

* Clear definition of what subset of C that is supported.
  
  * Support for code with stackpointers is included.
  
* Toolchain delivered in source form as a Dockerfile

* Experimental contract assistant.

  * Detect helper functions that are reachable from contracted functions
    but do not have ACSL contracts.
  * Support scanning individual C files or directories containing `.c` and
    `.h` files.
  * Produce an LLM-ready prompt for draft ACSL suggestions.
  * Provide a small browser UI for running the pre-check and inspecting the
    pipeline status.
  * Provide explicit Frama-C Eva and WP runs from the browser UI and show the
    command output.
  * Keep Frama-C/WP/Eva as the validation step for any suggested contract.

### Acceptance test

It is possible to run the ``STEE`` codebase through the toolchain, and
AutoDeduct delivers a clear result "YES", "NO" or "UNKNOWN".
