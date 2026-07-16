#include "shared_memory.h"

#include <windows.h>
#include <stdio.h>
#include <stdbool.h>
#include <string.h>

static HANDLE shm_handle = NULL;
static SharedMemory* shm = NULL;

SharedMemory* shm_init(void){
    bool alreadyExists = false;

    shm_handle = CreateFileMappingA(
        INVALID_HANDLE_VALUE,
        NULL,
        PAGE_READWRITE,
        0,
        sizeof(SharedMemory),
        SHM_NAME
    );

    if (shm_handle == NULL)
    {
        printf("CreateFileMappingA failed. Error: %lu \n", GetLastError());
        return NULL;
    }

    if(GetLastError() == ERROR_ALREADY_EXISTS){
        alreadyExists = true;
    }

    shm = (SharedMemory*)MapViewOfFile(
        shm_handle,
        FILE_MAP_ALL_ACCESS,
        0, 
        0,
        sizeof(SharedMemory)
    );

    if (shm == NULL)
    {
        printf("MapViewOfFile failed. Error: %lu \n", GetLastError());
        CloseHandle(shm_handle);
        shm_handle = NULL;
        return NULL;
    }

    if (!alreadyExists)
    {
        //default values
        memset(shm, 0, sizeof(SharedMemory));
        shm->magic = SHM_MAGIC;

        shm->BME_on = 1;
        shm->BMI_on = 1;
        shm->TMP_on = 0;
        shm->OPT_on = 1;
        
        // //Sensor Status Variables
        // bool BME_on = true;
        // bool BMI_on = true;
        // bool TMP_on = false;
        // bool OPT_on = true;

        shm->dominant = 0;

        //input output seq?
    }
    
    return shm;
}

void shm_cleanup(){
    if (shm != NULL)
    {
        UnmapViewOfFile(shm);
        shm = NULL;
    }

    if (shm_handle != NULL)
    {
        CloseHandle(shm_handle);
        shm_handle = NULL;
    }

}

SharedMemory* shm_get(void){
    return shm;
}


#include <stdint.h>

// main.c'nin derlenmesi için gerekli sahte (mock) fonksiyonlar
int32_t bmi160_initialize_sensor(void) {
    // Rehost ortamında sensör başlatma başarılı kabul edilir
    return 0; 
}

int32_t bmi160_config_running_mode(void) {
    return 0;
}

void bme280_data_readout_template(void) {
    // Burası normalde döngüde çalışır, şimdilik içi boş kalabilir
    // İleride buraya shared memory'den veri çekme mantığı da kurulabilir
}
