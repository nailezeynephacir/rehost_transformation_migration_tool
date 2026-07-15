int mixed_apply(int input)
{
    int base = input + 1;
    int result = base * 2;

    int bonus = 1;
    return result + bonus;
}

int mixed_missing(int input)
{
    int first = input + 3;
    int inserted = input * 10;
    int second = input + 4;

    return first + second + inserted;
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

    value += 2;
    value *= 3;

    value += 2;
    value *= 3;

    return value;
}
