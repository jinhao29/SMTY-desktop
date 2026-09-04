# -*- coding: utf-8 -*-
"""处理器层：跨平台文件名清洗（Windows 优先，兼容 macOS/Linux）。

职责：
- 替换 Windows 非法字符 \\ / : * ? " < > | 为下划线
- 去除控制字符（ASCII 0-31）与首尾空格
- 去除结尾点号（Windows 不允许文件名以 . 结尾）
- 空名回退为 'unnamed'，过长截断到 120 字符

仅纯逻辑，无状态、无副作用，便于单元测试。
"""
import re

# Windows 保留名（CON/PRN/AUX/NUL/COM1-9/LPT1-9），加扩展名后仍非法
_RESERVED_RE = re.compile(
    r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', re.IGNORECASE
)
# 非法字符：\ / : * ? " < > |
_ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
# 控制字符 0x00-0x1F
_CONTROL_CHARS_RE = re.compile(r'[\x00-\x1f]')
_MAX_LEN = 120


def sanitize_filename(name: str, fallback: str = 'unnamed') -> str:
    """清洗字符串为合法的 Windows 文件名（兼容 macOS/Linux）。

    参数:
        name: 原始字符串（学员名、工作表名等）
        fallback: 清洗后为空时使用的回退名

    返回:
        合法文件名字符串，最长 _MAX_LEN 字符

    示例:
        >>> sanitize_filename('张三')
        '张三'
        >>> sanitize_filename('a/b\\\\c:d*e?f"g<h>i|j')
        'a_b_c_d_e_f_g_h_i_j'
        >>> sanitize_filename('  .')
        'unnamed'
        >>> sanitize_filename('CON.txt')
        'CON_.txt'
    """
    if not isinstance(name, str):
        name = str(name) if name is not None else ''

    # 1. 替换非法字符为下划线
    name = _ILLEGAL_CHARS_RE.sub('_', name)
    # 2. 去除控制字符
    name = _CONTROL_CHARS_RE.sub('', name)
    # 3. 去除首尾空格
    name = name.strip()
    # 4. 去除结尾点号（Windows 禁止）
    name = name.rstrip('.')
    # 5. 处理 Windows 保留名：在末尾追加下划线
    if _RESERVED_RE.match(name):
        # 在扩展名点前插入下划线，例如 'CON.txt' -> 'CON_.txt'
        if '.' in name:
            base, ext = name.split('.', 1)
            name = f'{base}_.{ext}'
        else:
            name = f'{name}_'
    # 6. 空名回退
    if not name:
        return fallback
    # 7. 长度截断（按字符数，避免截断中文字符产生乱码）
    if len(name) > _MAX_LEN:
        name = name[:_MAX_LEN].rstrip('.').rstrip()
        if not name:
            return fallback
    return name


def sanitize_path_segment(segment: str) -> str:
    """清洗路径单段（与 sanitize_filename 等价，语义化命名）。

    用于 zip 解压后跨平台路径归一化场景。
    """
    return sanitize_filename(segment)
