void helper_store_nested(int **target, int value)
{
    **target = value;
}

/*@
  requires \valid(target);
  requires \valid(*target);
  assigns **target;
  ensures **target == value;
*/
void entry(int **target, int value)
{
    helper_store_nested(target, value);
}
