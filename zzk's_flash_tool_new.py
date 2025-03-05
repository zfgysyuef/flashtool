import os
import subprocess
import struct
import time
import sys
from pathlib import Path


def check_adb_fastboot():
    """
    检查系统中是否安装了 adb 和 fastboot。
    如果系统中没有安装，则尝试使用脚本目录下的 adb 文件夹中的工具。
    """
    # 默认使用系统环境变量中的 adb 和 fastboot
    adb_cmd = 'adb'
    fastboot_cmd = 'fastboot'

    # 检查系统中是否安装了 adb 和 fastboot
    def check_tool_installed(tool_name):
        try:
            subprocess.run([tool_name, '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except FileNotFoundError:
            return False

    # 如果系统中没有安装 adb 或 fastboot，尝试使用脚本目录下的 adb 文件夹中的工具
    if not check_tool_installed(adb_cmd) or not check_tool_installed(fastboot_cmd):
        print("系统中未找到 adb 或 fastboot，尝试使用脚本目录下的 adb 文件夹中的工具。")
        adb_dir = Path(__file__).parent / "adb"
        if os.name == 'nt':  # Windows 系统
            adb_cmd = str(adb_dir / 'adb.exe')
            fastboot_cmd = str(adb_dir / 'fastboot.exe')
        else:  # Linux/macOS 系统
            adb_cmd = str(adb_dir / 'adb')
            fastboot_cmd = str(adb_dir / 'fastboot')

        # 检查脚本目录下的 adb 文件夹中的工具是否存在
        if not os.path.exists(adb_cmd) or not os.path.exists(fastboot_cmd):
            print(f"错误：{adb_cmd} 或 {fastboot_cmd} 不存在。请确保 adb 文件夹中有正确的工具。")
            sys.exit(1)

    return adb_cmd, fastboot_cmd


# 刷全量包函数，需要已解包，被刷入文件的文件名必须是文件需要被刷入的分区
# 例：boot 的镜像需要命名为 boot.img，recovery 的镜像需要命名为 recovery.img
def flash_images_from_folder(image_dir='image'):
    """
    使用 fastboot 命令刷入指定文件夹下的所有 .img 文件。
    刷入的分区为 img 文件的文件名（不包含文件后缀）。

    :param image_dir: 存放 .img 文件的文件夹路径，默认为 'image'
    """
    # 检查文件夹是否存在
    if not os.path.exists(image_dir):
        print(f"Error: The directory '{image_dir}' does not exist.")
        return

    # 获取 adb 和 fastboot 命令
    adb_cmd, fastboot_cmd = check_adb_fastboot()

    # 检查设备是否连接
    def check_device_connected():
        """检查设备是否连接并处于 fastboot 模式"""
        result = subprocess.run([fastboot_cmd, 'devices'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0 or not result.stdout.decode('utf-8').strip():
            print("未检测到设备，请确保设备已连接并处于 fastboot 模式。")
            return False
        return True

    # 重启设备到 fastbootd 模式
    def reboot_to_fastbootd():
        """通过 adb 重启设备到 fastbootd 模式"""
        print("正在重启设备到 fastbootd 模式...")
        result = subprocess.run([adb_cmd, 'reboot', 'fastboot'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print("无法重启到 fastbootd 模式，请确保设备已连接并启用 USB 调试。")
            return False
        # 等待设备进入 fastbootd 模式
        time.sleep(10)  # 等待设备重启
        return True

    # 检查设备是否连接并处于 fastboot 模式
    if not check_device_connected():
        # 如果设备未连接，尝试通过 adb 重启到 fastboot 模式
        print("尝试通过 adb 重启设备到 fastboot 模式...")
        result = subprocess.run([adb_cmd, 'reboot', 'bootloader'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print("无法重启到 fastboot 模式，请确保设备已连接并启用 USB 调试。")
            return
        # 等待设备进入 fastboot 模式
        time.sleep(10)  # 等待设备重启
        if not check_device_connected():
            print("设备仍未连接，请手动进入 fastboot 模式后重试。")
            return

    # 检查是否需要进入 fastbootd 模式
    print("是否需要刷入动态分区（如 system、vendor 等）？")
    print("如果需要刷入动态分区，请确保设备支持 fastbootd 模式。")
    choice = input("是否重启到 fastbootd 模式？(y/n): ").strip().lower()
    if choice == 'y':
        if not reboot_to_fastbootd():
            return
        # 再次检查设备是否连接
        if not check_device_connected():
            print("设备未连接，无法继续刷入。")
            return

    # 遍历 image 文件夹下的所有文件
    for filename in os.listdir(image_dir):
        # 检查文件是否为 .img 文件
        if filename.endswith('.img'):
            # 获取文件名（不包含后缀）
            partition_name = os.path.splitext(filename)[0]
            # 构建完整的文件路径
            img_path = os.path.join(image_dir, filename)

            # 构建 fastboot 命令
            fastboot_cmd_flash = [fastboot_cmd, 'flash', partition_name, img_path]

            # 执行 fastboot 命令
            print(f"刷入分区 {partition_name} 使用 {img_path}...")
            result = subprocess.run(fastboot_cmd_flash, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # 输出命令执行结果
            if result.returncode == 0:
                print(f"刷入分区 {partition_name} 成功。")
                time.sleep(1)  # 等待 1 秒，避免刷入过快
            else:
                print(f"刷入分区 {partition_name} 失败。错误信息: {result.stderr.decode('utf-8')}")


def unpack_payload(payload_path=None, output_dir=None, dumper_path=None):
    """
    使用 payload-dumper-go 解包 payload.bin 文件。

    :param payload_path: payload.bin 文件的路径，默认为脚本目录下的 pyld/payload.bin
    :param output_dir: 解包输出的目录，默认为脚本目录下的 image
    :param dumper_path: payload-dumper-go 可执行文件的路径，默认为脚本目录下的 payload-dumper-go
    """
    # 设置默认路径
    if payload_path is None:
        payload_path = Path(__file__).parent / "pyld" / "payload.bin"
    if output_dir is None:
        output_dir = Path(__file__).parent / "image"
    if dumper_path is None:
        dumper_path = Path(__file__).parent / "payload-dumper-go.exe"

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 检查 payload.bin 文件是否存在
    if not payload_path.exists():
        print(f"错误：{payload_path} 文件不存在，请把 payload.bin 文件放到 pyld 文件夹中")
        return

    # 检查 payload-dumper-go 可执行文件是否存在
    if not dumper_path.exists():
        print(f"错误：{dumper_path} 可执行文件不存在。")
        return

    # 构建命令
    command = [str(dumper_path), "-o", str(output_dir), str(payload_path)]

    # 打印调试信息
    print(f"运行命令: {' '.join(command)}")

    # 执行命令
    try:
        subprocess.run(command, check=True)
        print(f"解包完成！文件已保存到 {output_dir}")
    except subprocess.CalledProcessError as e:
        print(f"解包过程中发生错误: {e}")
    except FileNotFoundError:
        print("错误：未找到 payload-dumper-go.exe 可执行文件。请确保已正确安装。")


def function1():
    print("你选择了功能 1：解包 payload.bin")
    unpack_payload()


def function2():
    print("你选择了功能 2：刷入全量包")
    flash_images_from_folder()


def function3():
    print("你选择了功能 3：一键 root。")
    print("一键 root 正在开发中。。。")


def exit_program():
    print("退出程序。")
    exit()


def show_menu():
    print("请选择一个功能：")
    print("1. 解包 payload.bin")
    print("2. 刷入全量包")
    print("3. 一键 root")
    print("4. 退出")


def main():
    # 功能映射字典，将数字与对应的函数关联
    functions = {
        1: function1,
        2: function2,
        3: function3,
        4: exit_program
    }

    while True:
        show_menu()  # 显示菜单
        try:
            choice = int(input("请输入你的选择（1-4）："))  # 获取用户输入
            if choice in functions:  # 检查输入是否有效
                functions[choice]()  # 调用对应的函数
            else:
                print("无效的选择，请输入 1 到 4 之间的数字。")
        except ValueError:  # 处理非数字输入
            print("输入无效，请输入一个数字。")


if __name__ == "__main__":
    main()