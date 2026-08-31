int helper_chain_inner(int value)
{
    return value + 1;
}

int helper_chain_outer(int value)
{
    return helper_chain_inner(value) + 1;
}

/*@
  requires -1000000 <= value <= 1000000;
  assigns \nothing;
  ensures \result == value + 2;
*/
int entry(int value)
{
    return helper_chain_outer(value);
}
