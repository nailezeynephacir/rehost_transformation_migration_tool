#ifndef SHARED_MEMORY_H
#define SHARED_MEMORY_H

#include "shm_layout.h"

// shared memory alanı yoksa açar ve pointerını döndürür.
// zaten varsa olanın pointerını döndürür.
SharedMemory* shm_init(void);

//temizler
void shm_cleanup();

SharedMemory* shm_get(void);

#endif
