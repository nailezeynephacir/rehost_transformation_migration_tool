#include <msp430.h>
#include "driverlib.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

int add_values(int a, int b)
{
    int value = a + b;
    int doubled = value * 2;

    return doubled;
}
