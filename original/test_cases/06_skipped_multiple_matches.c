static int read_first(void)
{
    return 1;
}

static int read_second(void)
{
    return 2;
}

int calculate_multiple_matches(int input)
{
    int value = input;

    value += read_first();
    value += read_second();

    return value;
}
