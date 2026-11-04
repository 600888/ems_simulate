#!/bin/sh
# 一键部署（在解压后的 packet-analyzer 目录里执行）
#
# 做三件事：
#   1. 检查内置 Python 能否运行
#   2. 跑一遍解析自检，确认代码完整
#   3. 检查抓包权限（libpcap + root/CAP_NET_RAW）
#
# 不修改系统任何文件，不安装到 /usr，只提示怎么用。
set -e

DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"

echo "== 1/3 检查内置 Python =="
if [ ! -x "$DIR/python/bin/python3" ]; then
    echo "  错误：未找到 python/bin/python3" >&2
    exit 1
fi
"$DIR/python/bin/python3" -V
# 注意：-c 里的代码只用 ASCII。老系统 locale 常为 GBK，
# 命令行直接传中文会触发 UnicodeEncodeError（surrogates not allowed）。
"$DIR/python/bin/python3" -c 'import platform; print("  glibc:", platform.libc_ver()[1] or "unknown")'

echo
echo "== 2/3 解析自检 =="
PYTHONPATH="$DIR" "$DIR/python/bin/python3" -m packet_analyzer.cli selftest | tail -6

echo
echo "== 3/3 抓包权限 =="
if [ "$(id -u)" -eq 0 ]; then
    echo "  当前是 root，可直接抓包"
elif sudo -n true 2>/dev/null; then
    echo "  免密 sudo 可用：sudo $DIR/pa.sh capture --iface <网卡>"
else
    echo "  当前用户无 root 且 sudo 需密码；抓包需 root 或 CAP_NET_RAW："
    echo "    sudo setcap cap_net_raw,cap_net_admin=eip $DIR/python/bin/python3"
fi

echo
echo "部署完成。常用命令："
echo "  $DIR/pa.sh ifaces                                    # 列出网卡"
echo "  sudo $DIR/pa.sh capture --iface eth0 --duration 60    # 抓 60 秒"
echo "  sudo $DIR/pa.sh capture --iface eth0 --ip 192.168.1.10 --port 502 --log run.pcap"
echo "  $DIR/pa.sh replay run.pcap --protocol modbus_tcp      # 回放日志"
echo "  $DIR/pa.sh parse 000100000006010300000009            # 解析单帧"
echo
echo "也可以加进 PATH：  echo 'alias pa=$DIR/pa.sh' >> ~/.bashrc"
