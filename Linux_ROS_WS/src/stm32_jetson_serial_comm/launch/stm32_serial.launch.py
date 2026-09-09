"""Launch the STM32 UART5 serial node with Jetson defaults."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("device", default_value="/dev/ttyACM0"),
            DeclareLaunchArgument("baudrate", default_value="115200"),
            DeclareLaunchArgument("status_rate_hz", default_value="0.5"),
            DeclareLaunchArgument("gpio_status_rate_hz", default_value="1.0"),
            DeclareLaunchArgument("ultrasonic_rate_hz", default_value="5.0"),
            DeclareLaunchArgument("board_io_rate_hz", default_value="2.0"),
            DeclareLaunchArgument("timeout", default_value="0.2"),
            DeclareLaunchArgument("query_gpio", default_value="true"),
            DeclareLaunchArgument("query_ultrasonic", default_value="true"),
            Node(
                package="stm32_jetson_serial_comm",
                executable="stm32_serial_node",
                name="stm32_serial_node",
                output="screen",
                parameters=[
                    {
                        "device": LaunchConfiguration("device"),
                        "baudrate": LaunchConfiguration("baudrate"),
                        "status_rate_hz": LaunchConfiguration("status_rate_hz"),
                        "gpio_status_rate_hz": LaunchConfiguration("gpio_status_rate_hz"),
                        "ultrasonic_rate_hz": LaunchConfiguration("ultrasonic_rate_hz"),
                        "board_io_rate_hz": LaunchConfiguration("board_io_rate_hz"),
                        "timeout": LaunchConfiguration("timeout"),
                        "query_gpio": LaunchConfiguration("query_gpio"),
                        "query_ultrasonic": LaunchConfiguration("query_ultrasonic"),
                    }
                ],
            ),
        ]
    )
