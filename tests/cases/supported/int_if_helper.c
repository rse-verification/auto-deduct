int nonnegative_helper(int value)
{
    if (value < 0) {
        return 0;
    }
    return value;
}

/*@
  assigns \nothing;
  ensures \result >= 0;
*/
int entry(int value)
{
    return nonnegative_helper(value);
}
