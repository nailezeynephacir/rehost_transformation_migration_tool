
#include <stdbool.h>
#include <stdint.h>
#include <Windows.h>
#include "demo_sysctl.h"

// #define DelayMs(ulClockMS) {}
extern uint32_t MCLKValue;
void DelayMs (uint32_t ui32ClockMS)
{
	if (ui32ClockMS != 0)
	{
		Sleep(ui32ClockMS);
	}
}

