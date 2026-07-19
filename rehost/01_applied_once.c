#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#include "bmi160_support.h"
#include "bme280_support.h"
#include "tmp007.h"
#include "opt3001.h"
#include "demo_sysctl.h"
#include "i2c_driver.h"
#include "uart_driver.h"

#ifdef REHOST_MODE
	#include <msp430.h>
	#include "driverlib.h"
    #include "windows.h"
	
#endif

int add_values(int a, int b)
{
#ifndef TEST
    int gaipten_gelen_bazı_şeyler = 11;
    int bi_tane_daha = 44;
#endif

    int value = a + b;
    int doubled = value * 2;
    return doubled;
}
