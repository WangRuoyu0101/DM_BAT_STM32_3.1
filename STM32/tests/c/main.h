#ifndef TEST_MAIN_H
#define TEST_MAIN_H

#include <stdint.h>

typedef struct
{
  volatile uint32_t DEMCR;
} CoreDebug_Type;

typedef struct
{
  volatile uint32_t CTRL;
  volatile uint32_t CYCCNT;
} DWT_Type;

typedef struct
{
  volatile uint32_t BSRR;
} GPIO_TypeDef;

extern CoreDebug_Type mock_core_debug;
extern DWT_Type mock_dwt;
extern GPIO_TypeDef mock_gpio;
extern uint32_t SystemCoreClock;

uint32_t mock_rgb_cycle_now(void);
void mock_rgb_write(uint32_t value);
uint32_t mock_get_primask(void);
void mock_disable_irq(void);
void mock_enable_irq(void);

#define CoreDebug (&mock_core_debug)
#define DWT (&mock_dwt)
#define RGB_GPIO_Port (&mock_gpio)
#define RGB_Pin (1U << 13U)
#define CoreDebug_DEMCR_TRCENA_Msk (1U << 24U)
#define DWT_CTRL_CYCCNTENA_Msk 1U
#define __get_PRIMASK() mock_get_primask()
#define __disable_irq() mock_disable_irq()
#define __enable_irq() mock_enable_irq()
#define APP_RGB_LED_CYCLE_NOW() mock_rgb_cycle_now()
#define APP_RGB_LED_WRITE_PIN(value) mock_rgb_write(value)

#endif
