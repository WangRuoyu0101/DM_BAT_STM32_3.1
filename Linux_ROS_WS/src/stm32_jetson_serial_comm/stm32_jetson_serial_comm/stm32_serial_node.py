"""ROS2 node that publishes STM32 USB CDC status through standard topics."""

from __future__ import annotations

import os
import threading

from std_msgs.msg import Bool, Int32, Int32MultiArray, String, UInt8
from std_srvs.srv import SetBool

import rclpy
from rclpy.node import Node

from stm32_jetson_serial_comm.serial_driver import SerialDriver
from stm32_jetson_serial_comm.serial_host import SerialHost
from stm32_jetson_serial_comm.serial_node_core import SerialNodeCore


GPIO_SERVICE_CHANNELS = (
    ("flash_ctr", 0x01, "/stm32/gpio/flash_ctr/set"),
    ("led", 0x02, "/stm32/gpio/led/set"),
    ("bee", 0x03, "/stm32/gpio/bee/set"),
    ("motor", 0x04, "/stm32/gpio/motor/set"),
    ("flash", 0x05, "/stm32/gpio/flash/set"),
    ("sound", 0x06, "/stm32/gpio/sound/set"),
)

GPIO_CONTROL_RESULT_LABELS = {
    0x00: "OK",
    0x01: "INVALID_CHANNEL",
    0x02: "INVALID_LEVEL",
    0x03: "LENGTH_ERROR",
}


def _parameter_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


class Stm32SerialNode(Node):
    def __init__(self):
        super().__init__("stm32_serial_node")

        self.declare_parameter("device", os.environ.get("STM32_SERIAL_DEVICE", "/dev/ttyACM0"))
        self.declare_parameter("baudrate", 115200)
        self.declare_parameter("status_rate_hz", 0.5)
        self.declare_parameter("gpio_status_rate_hz", 1.0)
        self.declare_parameter("ultrasonic_rate_hz", 5.0)
        self.declare_parameter("cs1237_rate_hz", 10.0)
        self.declare_parameter("board_io_rate_hz", 2.0)
        self.declare_parameter("timeout", 0.2)
        self.declare_parameter("query_gpio", True)
        self.declare_parameter("query_ultrasonic", True)

        self._device = self.get_parameter("device").value
        self._baudrate = int(self.get_parameter("baudrate").value)
        self._timeout = float(self.get_parameter("timeout").value)
        status_rate_hz = float(self.get_parameter("status_rate_hz").value)
        gpio_status_rate_hz = float(self.get_parameter("gpio_status_rate_hz").value)
        ultrasonic_rate_hz = float(self.get_parameter("ultrasonic_rate_hz").value)
        cs1237_rate_hz = float(self.get_parameter("cs1237_rate_hz").value)
        board_io_rate_hz = float(self.get_parameter("board_io_rate_hz").value)
        query_gpio = _parameter_bool(self.get_parameter("query_gpio").value)
        query_ultrasonic = _parameter_bool(self.get_parameter("query_ultrasonic").value)

        self._status_pub = self.create_publisher(String, "/stm32/status_text", 10)
        self._gpio_text_pub = self.create_publisher(String, "/stm32/gpio_text", 10)
        self._gpio_pub = self.create_publisher(UInt8, "/stm32/gpio_bitmap", 10)
        self._ultrasonic_text_pub = self.create_publisher(String, "/stm32/ultrasonic_text", 10)
        self._ultrasonic_pub = self.create_publisher(Int32MultiArray, "/stm32/ultrasonic_mm", 10)
        self._cs1237_raw_pub = self.create_publisher(Int32, "/stm32/cs1237_raw", 10)
        self._cs1237_text_pub = self.create_publisher(String, "/stm32/cs1237_text", 10)
        self._fan_rpm_pub = self.create_publisher(Int32MultiArray, "/stm32/fan_rpm", 10)
        self._fan_level_pub = self.create_publisher(UInt8, "/stm32/fan_level", 10)
        self._key_bitmap_pub = self.create_publisher(UInt8, "/stm32/key_bitmap", 10)
        self._board_io_text_pub = self.create_publisher(String, "/stm32/board_io_text", 10)
        self._link_pub = self.create_publisher(Bool, "/stm32/link_ok", 10)

        self._driver = SerialDriver.open(self._device, self._baudrate, self._timeout)
        self._host = SerialHost(self._driver)
        self._serial_lock = threading.Lock()
        self._core = SerialNodeCore(
            self._host,
            timeout_seconds=self._timeout,
            query_gpio=query_gpio,
            query_ultrasonic=query_ultrasonic,
        )
        self._gpio_services = [
            self.create_service(
                SetBool,
                service_name,
                self._make_gpio_service_callback(channel_name, channel_id),
            )
            for channel_name, channel_id, service_name in GPIO_SERVICE_CHANNELS
        ]

        self._status_timer = self.create_timer(
            self._rate_to_period(status_rate_hz, 2.0),
            self._poll_status_once,
        )
        self._gpio_timer = self.create_timer(
            self._rate_to_period(gpio_status_rate_hz, 1.0),
            self._poll_gpio_once,
        )
        self._ultrasonic_timer = self.create_timer(
            self._rate_to_period(ultrasonic_rate_hz, 0.2),
            self._poll_ultrasonic_once,
        )
        self._cs1237_timer = self.create_timer(
            self._rate_to_period(cs1237_rate_hz, 0.1),
            self._poll_cs1237_once,
        )
        self._board_io_timer = self.create_timer(
            self._rate_to_period(board_io_rate_hz, 0.5),
            self._poll_board_io_once,
        )
        self.get_logger().info(
            f"STM32 serial node opened {self._device} at {self._baudrate} baud"
        )

    def destroy_node(self):
        if hasattr(self, "_driver"):
            self._driver.close()
        super().destroy_node()

    @staticmethod
    def _rate_to_period(rate_hz: float, fallback_period: float) -> float:
        return 1.0 / rate_hz if rate_hz > 0.0 else fallback_period

    def _try_poll_lock(self) -> bool:
        return self._serial_lock.acquire(blocking=False)

    def _poll_status_once(self) -> None:
        if not self._try_poll_lock():
            return
        try:
            result = self._core.poll_status()
        finally:
            self._serial_lock.release()
        self._publish_poll_result(result)

    def _poll_gpio_once(self) -> None:
        if not self._try_poll_lock():
            return
        try:
            result = self._core.poll_gpio()
        finally:
            self._serial_lock.release()
        self._publish_poll_result(result)

    def _poll_ultrasonic_once(self) -> None:
        if not self._try_poll_lock():
            return
        try:
            result = self._core.poll_ultrasonic()
        finally:
            self._serial_lock.release()
        self._publish_poll_result(result)

    def _poll_cs1237_once(self) -> None:
        if not self._try_poll_lock():
            return
        try:
            result = self._core.poll_cs1237()
        finally:
            self._serial_lock.release()
        self._publish_poll_result(result)

    def _poll_board_io_once(self) -> None:
        if not self._try_poll_lock():
            return
        try:
            result = self._core.poll_board_io()
        finally:
            self._serial_lock.release()
        self._publish_poll_result(result)

    def _publish_poll_result(self, result) -> None:

        link_msg = Bool()
        link_msg.data = result.link_ok
        self._link_pub.publish(link_msg)

        if not result.link_ok:
            self.get_logger().warn(
                f"STM32 serial poll failed: {result.error_text}; "
                f"timeouts={self._core.timeout_count}"
            )
            return

        if result.status_text is not None:
            status_msg = String()
            status_msg.data = result.status_text
            self._status_pub.publish(status_msg)

        if result.gpio_bitmap is not None:
            gpio_msg = UInt8()
            gpio_msg.data = result.gpio_bitmap
            self._gpio_pub.publish(gpio_msg)

        if result.gpio_text is not None:
            gpio_text_msg = String()
            gpio_text_msg.data = result.gpio_text
            self._gpio_text_pub.publish(gpio_text_msg)

        if result.ultrasonic_mm is not None:
            ultrasonic_msg = Int32MultiArray()
            ultrasonic_msg.data = result.ultrasonic_mm
            self._ultrasonic_pub.publish(ultrasonic_msg)

        if result.ultrasonic_text is not None:
            ultrasonic_text_msg = String()
            ultrasonic_text_msg.data = result.ultrasonic_text
            self._ultrasonic_text_pub.publish(ultrasonic_text_msg)

        if result.cs1237_raw is not None:
            cs1237_raw_msg = Int32()
            cs1237_raw_msg.data = result.cs1237_raw
            self._cs1237_raw_pub.publish(cs1237_raw_msg)

        if result.cs1237_text is not None:
            cs1237_text_msg = String()
            cs1237_text_msg.data = result.cs1237_text
            self._cs1237_text_pub.publish(cs1237_text_msg)

        if result.fan_rpm is not None:
            fan_rpm_msg = Int32MultiArray()
            fan_rpm_msg.data = result.fan_rpm
            self._fan_rpm_pub.publish(fan_rpm_msg)

        if result.fan_level is not None:
            fan_level_msg = UInt8()
            fan_level_msg.data = result.fan_level
            self._fan_level_pub.publish(fan_level_msg)

        if result.key_bitmap is not None:
            key_bitmap_msg = UInt8()
            key_bitmap_msg.data = result.key_bitmap
            self._key_bitmap_pub.publish(key_bitmap_msg)

        if result.board_io_text is not None:
            board_io_text_msg = String()
            board_io_text_msg.data = result.board_io_text
            self._board_io_text_pub.publish(board_io_text_msg)

    @staticmethod
    def _format_gpio_result(result: int) -> str:
        label = GPIO_CONTROL_RESULT_LABELS.get(result, "UNKNOWN")
        return f"{label}(0x{result:02X})"

    def _make_gpio_service_callback(self, channel_name: str, channel_id: int):
        def callback(request, response):
            level = 1 if request.data else 0
            level_text = "ON" if level else "OFF"
            try:
                with self._serial_lock:
                    result = self._host.control_gpio(
                        channel_id=channel_id,
                        level=level,
                        seq=self._core._allocate_seq(),
                        timeout_seconds=self._timeout,
                    )
                response.success = result.result == 0x00
                response.message = (
                    f"GPIO {channel_name} -> {level_text}: "
                    f"{self._format_gpio_result(result.result)}"
                )
            except Exception as exc:
                response.success = False
                response.message = f"GPIO {channel_name} -> {level_text}: {exc}"
                self.get_logger().warn(response.message)
            return response

        return callback


def main(args=None) -> None:
    rclpy.init(args=args)
    node = Stm32SerialNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
