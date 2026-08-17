#include <limits.h>

int input;
int result;

int increment(int value) {
    return value + 1;
}

/*@
  requires INT_MIN < input < INT_MAX;
  ensures result == input + 1;
*/
int main(void) {
    result = increment(input);
    return 0;
}
