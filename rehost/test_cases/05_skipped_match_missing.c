int calculate_missing_match(int input)
{
#ifndef TEST
    int first = input + 1;
    int second = input + 2;
#else
    int first = 10;
    int second = 20;
#endif

    return first + second;
}
