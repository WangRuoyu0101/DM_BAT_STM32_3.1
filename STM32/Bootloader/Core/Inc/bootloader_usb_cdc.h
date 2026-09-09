#ifndef BOOTLOADER_USB_CDC_H
#define BOOTLOADER_USB_CDC_H

#include "bootloader_protocol.h"

#include <stdint.h>

void Bootloader_UsbCdcInit(void);
void Bootloader_UsbCdcDeInit(void);
void Bootloader_UsbCdcHandleData(const uint8_t *data, uint32_t length);
uint8_t Bootloader_UsbCdcPollFrame(Bootloader_Frame *frame);
uint8_t Bootloader_UsbCdcPollError(uint8_t *error_code);
uint8_t Bootloader_UsbCdcSendFrame(uint8_t frame_id, const uint8_t *payload, uint8_t length);

#endif /* BOOTLOADER_USB_CDC_H */
