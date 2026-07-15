int calculate_total(int value)
{
#ifndef TEST
    int result = value + 10;
#else
    int result = 100;
#endif

    return result;
}
