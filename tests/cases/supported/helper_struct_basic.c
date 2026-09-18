struct SimpleValue {
    int value;
};

int helper_struct_value(void)
{
    struct SimpleValue item;
    item.value = 7;
    return item.value;
}

/*@
  assigns \nothing;
  ensures \result == 7;
*/
int entry(void)
{
    return helper_struct_value();
}
