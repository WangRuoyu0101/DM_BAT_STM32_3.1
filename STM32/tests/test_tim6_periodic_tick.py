from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Tim6PeriodicTickTests(unittest.TestCase):
    def read(self, relative_path):
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def strip_c_comments(self, source):
        return re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.DOTALL)

    def compact(self, source):
        return re.sub(r"\s+", "", source)

    def extract_braced_block(self, source, start_pattern):
        match = re.search(start_pattern, source, re.MULTILINE)
        self.assertIsNotNone(match, f"missing code matching {start_pattern!r}")

        opening_brace = source.find("{", match.end())
        self.assertNotEqual(opening_brace, -1, "matching code has no body")

        depth = 0
        for index in range(opening_brace, len(source)):
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
                if depth == 0:
                    return source[opening_brace + 1:index]

        self.fail("matching code has an unterminated body")

    def test_ioc_defines_2_ms_tim6_interrupt(self):
        ioc = self.read("DM3.1_BAT.ioc")
        self.assertRegex(ioc, r"(?m)^Mcu\.IP\d+=TIM6$")
        self.assertIn("TIM6.Prescaler=8399", ioc)
        self.assertIn("TIM6.Period=19", ioc)
        self.assertIn("NVIC.TIM6_DAC_IRQn=true", ioc)

    def test_tim6_irq_is_routed_through_hal(self):
        interrupts = self.read("Core/Src/stm32f4xx_it.c")
        self.assertIn("extern TIM_HandleTypeDef htim6;", interrupts)
        self.assertIn("void TIM6_DAC_IRQHandler(void)", interrupts)
        self.assertIn("HAL_TIM_IRQHandler(&htim6);", interrupts)

    def test_timer_callback_only_increments_shared_tick(self):
        main = self.read("Core/Src/main.c")
        tick = self.read("Core/Src/app_periodic_tick.c")
        tick_header = self.read("Core/Inc/app_periodic_tick.h")
        makefile = self.read("Makefile")

        self.assertNotIn("volatile uint32_t g_periodic_tick", main)
        self.assertNotIn("HAL_TIM_PeriodElapsedCallback", main)
        self.assertIn("static volatile uint32_t s_periodic_tick = 0U;", tick)
        self.assertIn("uint32_t App_PeriodicTick_Get(void);", tick_header)
        self.assertIn("Core/Src/app_periodic_tick.c", makefile)

        uncommented_tick = self.strip_c_comments(tick)
        callback = self.extract_braced_block(
            uncommented_tick,
            r"\bvoid\s+HAL_TIM_PeriodElapsedCallback\s*"
            r"\(\s*TIM_HandleTypeDef\s*\*\s*htim\s*\)",
        )
        tim6_branch = self.extract_braced_block(
            callback,
            r"\bif\s*\(\s*htim->Instance\s*==\s*TIM6\s*\)",
        )
        self.assertEqual(self.compact(tim6_branch), "s_periodic_tick++;")
        self.assertEqual(
            self.compact(callback),
            "if(htim->Instance==TIM6){s_periodic_tick++;}",
        )

    def test_led_task_runs_from_app_module_every_1000_ms(self):
        main = self.read("Core/Src/main.c")
        led = self.read("Core/Src/app_status_led.c")
        led_header = self.read("Core/Inc/app_status_led.h")
        makefile = self.read("Makefile")

        self.assertIn('#include "app_status_led.h"', main)
        self.assertIn('#include "app_periodic_tick.h"', main)
        self.assertIn("App_StatusLed_Init();", main)
        self.assertIn("#define APP_STATUS_LED_PERIOD_TICKS 500U", led)
        self.assertIn("void App_StatusLed_Init(void);", led_header)
        self.assertIn("void App_StatusLed_Run(uint32_t current_tick);", led_header)
        self.assertIn("Core/Src/app_status_led.c", makefile)

        uncommented_led = self.strip_c_comments(led)
        run_body = self.extract_braced_block(
            uncommented_led,
            r"\bvoid\s+App_StatusLed_Run\s*\(\s*uint32_t\s+current_tick\s*\)",
        )
        led_due_branch = self.extract_braced_block(
            run_body,
            r"\bif\s*\(\s*"
            r"\(uint32_t\)\s*\(\s*current_tick\s*-\s*s_last_tick\s*\)"
            r"\s*>=\s*APP_STATUS_LED_PERIOD_TICKS\s*\)",
        )
        self.assertIn("s_last_tick = current_tick;", led_due_branch)
        self.assertIn(
            "HAL_GPIO_TogglePin(LED_RUN_GPIO_Port, LED_RUN_Pin);",
            led_due_branch,
        )

        uncommented_main = self.strip_c_comments(main)
        main_body = self.extract_braced_block(
            uncommented_main,
            r"\bint\s+main\s*\(\s*void\s*\)",
        )
        main_loop = self.extract_braced_block(main_body, r"\bwhile\s*\(\s*1\s*\)")
        self.assertIn("uint32_t current_tick = App_PeriodicTick_Get();", main_loop)
        self.assertIn("App_StatusLed_Run(current_tick);", main_loop)

    def test_tim6_interrupt_start_failure_is_handled(self):
        main = self.read("Core/Src/main.c")
        main_body = self.extract_braced_block(main, r"\bint\s+main\s*\(\s*void\s*\)")
        failure_branch = self.extract_braced_block(
            main_body,
            r"\bif\s*\(\s*HAL_TIM_Base_Start_IT\s*"
            r"\(\s*&htim6\s*\)\s*!=\s*HAL_OK\s*\)",
        )
        self.assertEqual(failure_branch.strip(), "Error_Handler();")


if __name__ == "__main__":
    unittest.main()
