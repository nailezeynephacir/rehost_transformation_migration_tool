#include <msp430.h>
#include "driverlib.h"
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "i2c_driver.h"
#include "demo_sysctl.h"
#include "bmi160_support.h"
#include "bme280_support.h"
#include "tmp007.h"
#include "opt3001.h"
#include "uart_driver.h"

int add_values(int a, int b)
{
    int value = a + b;
    int doubled = value * 2;

    return doubled;
}
