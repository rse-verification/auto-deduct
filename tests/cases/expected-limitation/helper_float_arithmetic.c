float helper_scale_float(float value)
{
    return value * 2.0f;
}

/*@
  assigns \nothing;
  ensures \result == value * 2.0f;
*/
float entry(float value)
{
    return helper_scale_float(value);
}
