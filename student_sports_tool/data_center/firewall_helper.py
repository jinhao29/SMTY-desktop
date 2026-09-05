# -*- coding: utf-8 -*-
"""工具层：Windows 防火墙入站规则管理（双端同步 LAN 互通）。

背景：
    同一 Wi-Fi 下手机连不上 PC 同步服务，最常见原因是 Windows Defender
    防火墙拦截入站连接（Python / 打包 exe 首次监听时弹窗被点了"取消"，
    或从未弹窗直接默认拦截）。USB（adb reverse）不经过防火墙，
    所以典型症状是「USB 通、Wi-Fi 不通」。

需要放行的入站规则：
    TCP <sync_port>   同步服务（/upload /sync/* /health）
    UDP 9112          在线心跳广播（手机端自动发现）

行为：
    - rule_exists(port) / beacon_rule_exists()：查询规则是否已放行
    - ensure_rules(sync_port)：检测 + 尝试静默添加；无管理员权限时返回提示
    - 非 Windows 平台直接放行（无防火墙墙概念差异，不阻塞主流程）

仅使用标准库 subprocess/ctypes，netsh 失败绝不抛出到调用方 UI。
"""
import ctypes
import logging
import subprocess
import sys

RULE_TCP_NAME = 'SMTY-Sync-TCP'
RULE_UDP_NAME = 'SMTY-Sync-UDP'
UDP_BEACON_PORT = 9112

# netsh 输出重定向到 DEVNULL，避免控制台闪窗
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0


def is_windows() -> bool:
    return sys.platform == 'win32'


def is_admin() -> bool:
    """当前进程是否具有管理员权限（添加防火墙规则需要）。"""
    if not is_windows():
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run_netsh(args: list) -> int:
    """执行 netsh 命令，返回 returncode（异常归一为 -1）。"""
    try:
        proc = subprocess.run(
            ['netsh', 'advfirewall', 'firewall'] + args,
            capture_output=True, text=True, timeout=10,
            creationflags=_CREATE_NO_WINDOW,
        )
        return proc.returncode
    except (OSError, subprocess.TimeoutExpired) as e:
        logging.debug('netsh 执行失败：%s', e)
        return -1


def rule_exists(rule_name: str) -> bool:
    """查询指定名称的防火墙入站规则是否已存在。非 Windows 返回 True。"""
    if not is_windows():
        return True
    return _run_netsh(['show', 'rule', f'name={rule_name}']) == 0


def tcp_rule_exists() -> bool:
    return rule_exists(RULE_TCP_NAME)


def udp_rule_exists() -> bool:
    return rule_exists(RULE_UDP_NAME)


def _add_rule(rule_name: str, protocol: str, port: int) -> bool:
    """添加入站放行规则（需管理员权限）。"""
    rc = _run_netsh([
        'add', 'rule', f'name={rule_name}',
        'dir=in', 'action=allow',
        f'protocol={protocol}', f'localport={port}',
    ])
    if rc != 0:
        logging.debug('防火墙规则添加失败：%s（通常因缺少管理员权限）', rule_name)
    return rc == 0


def ensure_rules(sync_port: int) -> dict:
    """确保同步所需防火墙规则就位。

    返回:
        {
            'tcp_ok': bool,        # TCP sync_port 是否已放行
            'udp_ok': bool,        # UDP 9112 是否已放行
            'added': bool,         # 本次是否实际添加了规则
            'need_admin': bool,    # 是否因缺少管理员权限未能添加
        }
    """
    result = {'tcp_ok': False, 'udp_ok': False, 'added': False, 'need_admin': False}
    if not is_windows():
        result.update(tcp_ok=True, udp_ok=True)
        return result

    result['tcp_ok'] = tcp_rule_exists()
    result['udp_ok'] = udp_rule_exists()
    if result['tcp_ok'] and result['udp_ok']:
        return result

    # 缺规则：尝试静默添加（有管理员权限时一次成功）
    if not result['tcp_ok']:
        if _add_rule(RULE_TCP_NAME, 'TCP', sync_port):
            result['tcp_ok'] = True
            result['added'] = True
    if not result['udp_ok']:
        if _add_rule(RULE_UDP_NAME, 'UDP', UDP_BEACON_PORT):
            result['udp_ok'] = True
            result['added'] = True

    result['need_admin'] = not (result['tcp_ok'] and result['udp_ok'])
    return result
