int mixed_apply(int input)
{
#ifndef TEST
    int base = input + 1;
    int result = base * 2;
#else
    int base = 10;
    int result = 20;
#endif

    return result;
}

int mixed_missing(int input)
{
#ifndef TEST
    int first = input + 3;
    int second = input + 4;
#else
    int first = 30;
    int second = 40;
#endif

    return first + second;
}

int mixed_already(int input)
{
#ifndef TEST
    int result = input + 5;
#else
    int result = 50;
#endif

    return result;
}

int mixed_multiple(int input)
{
    int value = input;

#ifndef TEST
    value += 2;
    value *= 3;
#else
    value += 20;
    value *= 30;
#endif

    return value;
}
