# -*- coding: utf-8 -*-
"""
rthook_log.py
=============
PyInstaller 运行时钩子：为无控制台的打包版本记录崩溃信息。

背景：--windowed 打包后没有控制台，任何未捕获异常都会静默消失，
      用户只会看到"双击没反应"。本钩子在进程启动时安装全局
      excepthook，把 traceback 追加写入 exe 同目录的 launch_log.txt。

用法（build.bat 已包含）：
    --runtime-hook rthook_log.py

注意：日志文件名刻意使用 ASCII。若改成中文名，必须确认本文件
      以 UTF-8 保存，否则在非 UTF-8 环境下可能写出乱码文件名。
"""

import datetime
import os
import sys
import traceback


def _log_dir() -> str:
    """确定日志目录：打包版写在 exe 旁，源码版写在本文件旁。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


LOG_PATH = os.path.join(_log_dir(), "launch_log.txt")


def _write(text: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        # 日志本身失败不应再抛异常，否则会掩盖真正的错误
        pass


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    lines = [
        "",
        "=" * 70,
        f"time     : {datetime.datetime.now():%Y-%m-%d %H:%M:%S}",
        f"frozen   : {getattr(sys, 'frozen', False)}",
        f"exe      : {getattr(sys, 'executable', 'unknown')}",
        f"python   : {sys.version}",
        "=" * 70,
    ]
    lines.append("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    _write("\n".join(lines))
    try:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    except Exception:
        pass


def _thread_excepthook(args) -> None:
    _excepthook(args.exc_type, args.exc_value, args.exc_traceback)


sys.excepthook = _excepthook

try:
    import threading
    threading.excepthook = _thread_excepthook   # Python 3.8+
except Exception:
    pass

try:
    _write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] runtime hook installed;"
           f" log = {LOG_PATH}\n")
except Exception:
    pass