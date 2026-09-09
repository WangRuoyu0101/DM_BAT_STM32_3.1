#ifndef BOOTLOADER_JUMP_H
#define BOOTLOADER_JUMP_H

#include "bootloader_config.h"

#include <stdint.h>

uint8_t Bootloader_IsApplicationValid(void);
void Bootloader_JumpToApplication(void);

#endif /* BOOTLOADER_JUMP_H */
