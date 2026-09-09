from setuptools import setup


package_name = "stm32_jetson_serial_comm"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/stm32_serial.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="jetson",
    maintainer_email="jetson@example.com",
    description="Jetson serial communication bridge helpers.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "serial_link = stm32_jetson_serial_comm.serial_link_cli:main",
            "stm32_serial_node = stm32_jetson_serial_comm.stm32_serial_node:main",
            "stm32_bootloader = stm32_jetson_serial_comm.bootloader_cli:main",
            "stm32_gpio = stm32_jetson_serial_comm.gpio_cli:main",
            "stm32_fan = stm32_jetson_serial_comm.fan_cli:main",
            "stm32_rtk = stm32_jetson_serial_comm.rtk_cli:main",
        ],
    },
)
