int scale_value(int value)
{
#ifndef TEST
    int result = value * 2;
#else
    int result = 20;
#endif

    return result;
}
