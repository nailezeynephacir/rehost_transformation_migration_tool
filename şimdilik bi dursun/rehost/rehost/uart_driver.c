#include "stdio.h"
#include "string.h"
#include <stdbool.h>
#include <windows.h>
#include "shared_memory.h"

#include "uart_driver.h"

s_test test = {
	FALSE,
	"",
	""
};

static SharedMemory *shm = NULL;

// teker teker byteları alıp birleştiriyor, rehost kısmında buna gerek yok.
void uartReceive(char data){
	
}

// shmyi al, oluşturulmadıysa oluştur, oluşamazsa hata yazdır.
void uartInit()
{
    shm = shm_get();

    if (shm == NULL){
        shm = shm_init();
    }

    if (shm == NULL){
        printf("Shared memory couldn't start. (uart sends that error)");
        return;
    }

	test.newStringReceived = FALSE;
}

// shm'ye yaz texti
void sendText(){
    if (shm == NULL)
        return false;

    strncpy(shm->last_json,
            test.txString,
            sizeof(shm->last_json)-1);

    shm->last_json[sizeof(shm->last_json)-1] = '\0';

    shm->command_ack_req++;
    
}

// shm'den oku texti
bool receiveText(char* data, int maxNumChars){
	if (shm == NULL)
        return false;

    if (shm->command_req != shm->command_ack_req){
        strncpy(data, shm->command, maxNumChars);
        shm->command_ack_req = shm->command_req;
        return true;
    }

    return false;
}

