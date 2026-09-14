struct SmallRecord {
    int level;
    int status;
};

struct SmallRecord helper_make_record(int value)
{
    struct SmallRecord record;
    record.level = value;
    record.status = value + 1;
    return record;
}

/*@
  requires -1000000 <= value <= 1000000;
  assigns \nothing;
  ensures \result.level == value;
  ensures \result.status == value + 1;
*/
struct SmallRecord entry(int value)
{
    return helper_make_record(value);
}
