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


def _reverse_list(serial: str, port: int) -> bool:
    """查询该设备 reverse 表里是否已有 <port> 映射（true=在位）。

    adb reverse 规则会因拔插 USB / 手机重连 / adb server 重启被整表清除，
    所以不能只做「处理过一次就跳过」的标记——必须每轮真实核验。
    """
    out = _run(['adb', '-s', serial, 'reverse', '--list'])
    if not out:
        return False
    marker = 'tcp:%d' % port
    return any(line.split()[0] == marker
               for line in out.splitlines() if line.strip())


def ensure_reverse(port: int) -> list:
    """核验式 reverse：设备在线但映射缺失（被 adb 清掉）→ 重新建立。

    返回本轮新建立映射的序列号列表（供日志去重，状态变化才打日志）。
    """
    processed = []
    for serial in list_adb_devices():
        if _reverse_list(serial, port):
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


def auto_reverse(port: int, already_done: set = None) -> list:
    """对在线设备执行 adb reverse（已处理过的跳过）。

    .. deprecated:: v23.11 改用 [ensure_reverse]——本函数的一次性标记式去重
       在 reverse 表被 adb 清除（拔插 USB / adb 重启）后永不重建，导致
       USB 同步通道静默失效。保留仅为兼容旧调用方。
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
