#ifndef SHM_LAYOUT_H
#define SHM_LAYOUT_H

#include <stdint.h>

#define SHM_NAME "MSP430_SHM"
#define SHM_MAGIC 0xABCD1234 //değişebilir

typedef struct{
    uint16_t X;
    uint16_t Y;
    uint16_t Z;
} SensorStruct16;

typedef struct{
    uint32_t X;
    uint32_t Y;
    uint32_t Z;
} SensorStruct32;

typedef struct{
    uint32_t magic;

    // I2C REQUEST FROM C
    uint8_t i2c_addr;
    uint8_t i2c_reg;
    uint8_t i2c_len;
    uint8_t i2c_write;

    uint8_t i2c_tx[16];
    uint8_t i2c_rx[16];

    uint32_t i2c_req;
    uint32_t i2c_ack;

    // BMI160
    SensorStruct16 s_gyroXYZ;
    SensorStruct16 s_accelXYZ;
    SensorStruct32 s_magcompXYZ;

    // BME280
    int32_t temperature;
    uint32_t pressure;
    uint32_t humidity;

    // OPT3001
    uint16_t OPTrawData;
    float    convertedLux;

    /// TMP007
    uint16_t TMPrawTemp;
    uint16_t TMPrawObjTemp;
    float    TMPtObjTemp;
    float    TMPtObjAmb;

    //Sensor Status Variables
    uint8_t BME_on;
    uint8_t BMI_on;
    uint8_t TMP_on;
    uint8_t OPT_on;

    // output from c
    int32_t dominant;
    char last_json[256];

    // commands coming to c
    char command [64];
    uint32_t command_req;
    uint32_t command_ack_req;

    //input output seq?

} SharedMemory;

#endif
