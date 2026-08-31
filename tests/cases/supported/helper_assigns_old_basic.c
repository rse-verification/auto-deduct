int helper_total;

void helper_add_total(int delta)
{
    helper_total = helper_total + delta;
}

/*@
  requires 0 <= helper_total <= 1000;
  requires 0 <= delta <= 1000;
  assigns helper_total;
  ensures helper_total == \old(helper_total) + delta;
*/
void entry(int delta)
{
    helper_add_total(delta);
}
