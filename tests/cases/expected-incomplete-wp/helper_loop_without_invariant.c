int helper_count_to_limit(int limit)
{
    int count = 0;
    int index = 0;
    while (index < limit) {
        count = count + 1;
        index = index + 1;
    }
    return count;
}

/*@
  requires 0 <= limit <= 1000;
  assigns \nothing;
  ensures \result == limit;
*/
int entry(int limit)
{
    return helper_count_to_limit(limit);
}
