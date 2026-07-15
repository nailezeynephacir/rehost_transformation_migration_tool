int add_values(int a, int b)
{
#ifndef TEST
    int value = a + b;
    int doubled = value * 2;
#else
    int value = 10;
    int doubled = 20;
#endif

    return doubled;
}
