int helper_read_next(int *base)
{
    return *(base + 1);
}

/*@
  requires \valid(base + (0 .. 1));
  assigns \nothing;
  ensures \result == base[1];
*/
int entry(int *base)
{
    return helper_read_next(base);
}
