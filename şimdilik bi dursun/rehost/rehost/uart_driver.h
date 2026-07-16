#ifndef UART_DRIVER_H_
#define UART_DRIVER_H_

// Global variables
#define MAX_STR_LENGTH 271

#define FALSE 0
#define TRUE  1

typedef struct{
	unsigned char newStringReceived;
	char          txString[MAX_STR_LENGTH];
	char          rxString[MAX_STR_LENGTH];
}s_test;

extern s_test test;

void uartReceive(char data);
void uartInit(void);
void uartSend(char * buf, unsigned char len);
void sendText(void);
bool receiveText(char* data, int maxNumChars);

#endif /* UART_DRIVER_REHOST_H_ */
