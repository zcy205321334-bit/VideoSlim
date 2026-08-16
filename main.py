#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VideoSlim - A video compression application using x264
Refactored version: v1.8
"""

import logging
import tkinter as tk
from logging.handlers import RotatingFileHandler

from src.controller import Controller
from src.service import init_services
from src.view import View


def setup_logging():
    """
    配置日志记录功能
    该函数用于设置Python的日志记录系统，将日志信息写入到文件中。
    配置包括日志级别、输出文件、文件写入模式以及日志格式。
    使用 RotatingFileHandler 轮转：单文件 5MB，保留 3 个备份。
    """
    handler = RotatingFileHandler(
        "log.txt",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[handler],
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def main():
    """
    应用程序的主入口函数

    该函数会：
    1. 配置日志记录系统
    2. 初始化所有服务（配置、消息、存储、更新）
    3. 创建Tkinter根窗口
    4. 初始化视图和控制器
    5. 启动Tkinter主事件循环
    """
    setup_logging()

    init_services()

    root = tk.Tk()
    app = View(root, Controller())
    root.mainloop()


if __name__ == "__main__":
    main()
