int file_missing_case(int input)
{
#ifndef TEST
    int value = input + 5;
#else
    int value = 50;
#endif

    return value;
}
