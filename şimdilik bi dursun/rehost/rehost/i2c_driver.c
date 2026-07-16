#include <stdbool.h>
#include <stdint.h>
#include <windows.h>
#include <stdio.h>

#include "shared_memory.h"
#include "i2c_driver.h"

static SharedMemory *shm = NULL;

void initI2C(void)
{
    shm = shm_get();

    if (shm == NULL){
        shm = shm_init();
    }

    if (shm == NULL){
        printf("Shared memory couldn't start. (i2c sends that error)");
        return;
    }
	
}


bool writeI2C(uint8_t ui8Addr, uint8_t ui8Reg, uint8_t *Data, uint8_t ui8ByteCount)
{
    if (shm == NULL || Data == NULL || ui8ByteCount == 0){
        return false;
    }

    shm->i2c_addr = ui8Addr;
    shm->i2c_reg  = ui8Reg;
    shm->i2c_len  = ui8ByteCount;


    memcpy(shm->i2c_tx,
           Data,
           ui8ByteCount);


    shm->i2c_write = 1;


    shm->i2c_req++;


    while(shm->i2c_ack != shm->i2c_req)
    {
        Sleep(1);
    }

    return true;
}


bool readI2C(uint8_t ui8Addr, uint8_t ui8Reg, uint8_t *Data, uint8_t ui8ByteCount)
{
    if (shm == NULL || Data == NULL || ui8ByteCount == 0){
        return false;
    }

    shm->i2c_addr = ui8Addr;
    shm->i2c_reg  = ui8Reg;
    shm->i2c_len  = ui8ByteCount;

    shm->i2c_write = 0;

    shm->i2c_req++;

    while(shm->i2c_ack != shm->i2c_req)
    {
        Sleep(1);
    }

    memcpy(Data, 
           shm->i2c_rx,
           ui8ByteCount);


    return true;

}


// mainde kullanılmamış
bool readBurstI2C(uint8_t ui8Addr, uint8_t ui8Reg, uint8_t *Data, uint32_t ui32ByteCount)
{
	return false;
}
