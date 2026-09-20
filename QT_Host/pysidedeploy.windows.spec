[app]

title = DM3.1 STM32 Debug Host
project_dir = .
input_file = main.py
exec_directory = dist
project_file =
icon =

[python]

python_path =
packages = Nuitka==4.2.1
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]

qml_files =
excluded_qml_plugins =
modules = Charts,Core,Gui,Widgets
plugins =

[android]

wheel_pyside =
wheel_shiboken =
plugins =

[nuitka]

macos.permissions =
mode = onefile
extra_args = --quiet --noinclude-qt-translations --zig --assume-yes-for-downloads --experimental=force-pkg-resources-metadata

[buildozer]

mode = debug
recipe_dir =
jars_dir =
ndk_path =
sdk_path =
local_libs =
arch =
