int mixed_apply(int input)
{
    int base = input + 1;
    int result = base * 2;

    return result;
}

int mixed_missing(int input)
{
    int first = input + 3;
    int second = input + 4;

    return first + second;
}

int mixed_already(int input)
{
    int result = input + 5;

    return result;
}

int mixed_multiple(int input)
{
    int value = input;

    value += 2;
    value *= 3;

    return value;
}
