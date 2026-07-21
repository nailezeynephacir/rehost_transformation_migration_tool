#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

#ifdef REHOST_MODE
	#include <msp430.h>
	#include "driverlib.h"
    #include "windows.h"
#endif

int add_values(int a, int b)
{
#ifndef TEST
    // burası function start
    int gaipten_gelen_bazı_şeyler = 11;
    int bi_tane_daha = 44;
#endif

    int value = a + b;
    int doubled = value * 2;

    
#ifndef TEST
    // burası function ortası
    int c = 11;
    int d = 44;
#endif

    return doubled;


#ifndef TEST
    // burası function end
    int a = 11;
    int b = 44;
#endif
}
