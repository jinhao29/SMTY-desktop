# -*- coding: utf-8 -*-
"""工具层：USB 设备自动发现与 adb reverse（USB 通道自动化）。

功能：
- list_adb_devices(): 解析 `adb devices` 输出，返回在线设备序列号列表
- auto_reverse(port, already_done): 对每台在线设备执行
  `adb -s <serial> reverse tcp:<port> tcp:<port>`，已处理过的跳过；
  之后手机端访问 127.0.0.1:<port> 即直达 PC 同步服务

容错：
- adb 不在 PATH / 无设备 / 执行失败 → 一律返回空列表，绝不抛出
- 仅 Windows 主动使用（Android Studio platform-tools 已随开发环境安装）
"""
import logging
import subprocess
import sys

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def _run(args: list, timeout: float = 10.0) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout, creationflags=_CREATE_NO_WINDOW)
        return proc.stdout or ''
    except (OSError, subprocess.TimeoutExpired) as e:
        logging.debug('adb 执行失败：%s', e)
        return ''


def list_adb_devices() -> list:
    """返回当前通过 USB 在线的设备序列号列表（排除 offline/unauthorized）。"""
    out = _run(['adb', 'devices'])
    serials = []
    for line in out.splitlines()[1:]:
        line = line.strip()
        if not line or '\t' not in line:
            continue
        serial, state = line.split('\t', 1)
        if state.strip() == 'device':
            serials.append(serial)
    return serials


def auto_reverse(port: int, already_done: set = None) -> list:
    """对在线设备执行 adb reverse（已处理过的跳过）。

    返回本次新处理成功的序列号列表。
    """
    done = already_done if already_done is not None else set()
    processed = []
    for serial in list_adb_devices():
        if serial in done:
            continue
        out = _run(['adb', '-s', serial, 'reverse',
                    f'tcp:{port}', f'tcp:{port}'])
        # adb reverse 成功时无输出、returncode 0；_run 不暴露 code，
        # 用「无 error 字样」粗判（失败信息以 'error' 开头）
        if out and out.strip().lower().startswith('error'):
            logging.debug('adb reverse 失败 [%s]：%s', serial, out.strip())
            continue
        processed.append(serial)
    return processed
