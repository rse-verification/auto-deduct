int helper_context_increment(int value)
{
    return value + 1;
}

/*@
  assigns \nothing;
  ensures \result == 5;
*/
int entry(void)
{
    int first = helper_context_increment(1);
    int second = helper_context_increment(2);
    return first + second;
}
