int next_count(void)
{
    static int counter = 0;
    counter = counter + 1;
    return counter;
}

/*@
  assigns \nothing;
  ensures \result == 3;
*/
int entry(void)
{
    int first = next_count();
    int second = next_count();
    return first + second;
}
