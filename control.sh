#!/bin/bash

# 脚本名称: gunicorn_control.sh
# 功能: 启动、关闭、重启 Gunicorn 服务
# 使用方法: ./gunicorn_control.sh {start|stop|restart|status}

# 配置
APP_NAME="start_back_end"  # 应用名称
GUNICORN_CMD="/home/narada/ems_simulate/venv/bin/gunicorn"  # Gunicorn 路径
APP_DIR="/home/narada/ems_simulate"  # 项目目录
APP_MODULE="start_back_end:app"  # Gunicorn 应用模块
BIND_ADDRESS="0.0.0.0:8888"  # 绑定地址
WORKERS=4  # Worker 数量
PID_FILE="/tmp/gunicorn_${APP_NAME}.pid"  # PID 文件路径
LOG_FILE="/tmp/gunicorn_${APP_NAME}.log"  # 日志文件路径

# 启动 Gunicorn
start() {
    if [ -f "$PID_FILE" ]; then
        echo "Gunicorn 已经在运行 (PID: $(cat $PID_FILE))"
        exit 1
    fi

    echo "启动 Gunicorn..."
    cd $APP_DIR || exit 1
    $GUNICORN_CMD -b $BIND_ADDRESS -w $WORKERS --pid $PID_FILE --log-file $LOG_FILE $APP_MODULE &
    echo "Gunicorn 已启动 (PID: $(cat $PID_FILE))"
}

# 关闭 Gunicorn
stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "Gunicorn 未运行"
        exit 1
    fi

    echo "关闭 Gunicorn..."
    kill -9 "$(cat $PID_FILE)"
    rm -f $PID_FILE
    echo "Gunicorn 已关闭"
}

# 重启 Gunicorn
restart() {
    stop
    sleep 2
    start
}

# 查看状态
status() {
    if [ -f "$PID_FILE" ]; then
        echo "Gunicorn 正在运行 (PID: $(cat $PID_FILE))"
    else
        echo "Gunicorn 未运行"
    fi
}

# 脚本入口
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    *)
        echo "使用方法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
