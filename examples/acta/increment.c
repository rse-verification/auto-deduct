static int increment(int x)
{
    return x + 1;
}

/*@ requires 0 <= x <= 100;
    ensures \result == x + 1;
*/
int compute(int x)
{
    return increment(x);
}
