enum SimpleChoice {
    SIMPLE_CHOICE_LOW = 0,
    SIMPLE_CHOICE_HIGH = 1
};

int helper_enum_score(enum SimpleChoice choice)
{
    switch (choice) {
    case SIMPLE_CHOICE_LOW:
        return 10;
    case SIMPLE_CHOICE_HIGH:
        return 20;
    default:
        return 0;
    }
}

/*@
  requires choice == SIMPLE_CHOICE_LOW || choice == SIMPLE_CHOICE_HIGH;
  assigns \nothing;
  ensures choice == SIMPLE_CHOICE_LOW ==> \result == 10;
  ensures choice == SIMPLE_CHOICE_HIGH ==> \result == 20;
*/
int entry(enum SimpleChoice choice)
{
    return helper_enum_score(choice);
}
