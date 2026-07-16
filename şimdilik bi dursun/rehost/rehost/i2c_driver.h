#include <stdbool.h>
#include <stdint.h>

#ifndef _I2C_DRIVER_REHOST_H_
#define _I2C_DRIVER_REHOST_H_

typedef enum {
	eUSCI_IDLE = 0,
	eUSCI_SUCCESS = 0,
	eUSCI_BUSY = 1,
	eUSCI_NACK = 2,
	eUSCI_STOP,
	eUSCI_START
} eUSCI_status;

extern void initI2C(void);

extern bool writeI2C(uint8_t ui8Addr, uint8_t ui8Reg, uint8_t *Data, uint8_t ui8ByteCount);
extern bool readI2C(uint8_t ui8Addr, uint8_t ui8Reg, uint8_t *Data, uint8_t ui8ByteCount);
extern bool readBurstI2C(uint8_t ui8Addr, uint8_t ui8Reg, uint8_t *Data, uint32_t ui32ByteCount);
#endif /* _I2C_DRIVER_REHOSTH_ */
