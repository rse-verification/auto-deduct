/*
 * AutoDeduct harness for the public CruiseControl example from the paper
 * cited in examples/paper-1046/README.md.
 *
 * The paper source is included unchanged. Renaming its main function lets
 * this file provide the contracted entry point used by AutoDeduct.
 */

#define main paper_cruise_control_main
#include "CC-simple.c"
#undef main

/*@ ensures \result == 0; */
int paper_entry(void)
{
    return paper_cruise_control_main();
}
