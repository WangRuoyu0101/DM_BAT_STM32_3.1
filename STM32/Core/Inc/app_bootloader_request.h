#ifndef APP_BOOTLOADER_REQUEST_H
#define APP_BOOTLOADER_REQUEST_H

#include <stdint.h>

/* RTC backup register 中保存的应用到 bootloader 跳转魔数，ASCII 为 "BOOT"。 */
#define APP_BOOTLOADER_REQUEST_MAGIC 0x424F4F54U

/* 应用收到合法 UART5 bootloader 请求后置位该标志，再执行软件复位。 */
void App_BootloaderRequest_SetFlag(void);

/* bootloader 启动早期读取该标志，并立即清除，避免之后每次复位都停留在升级态。 */
uint8_t App_BootloaderRequest_ConsumeFlag(void);

#endif /* APP_BOOTLOADER_REQUEST_H */
