# -*- coding: utf-8 -*-
"""update_dialog"跳过此版本"持久化的最小回归测试（2026-09-09）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from update_dialog import load_skip_version, save_skip_version


def test_skip_version_roundtrip():
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    try:
        os.remove(path)  # 从"文件不存在"开始
        assert load_skip_version(path) == ''
        assert save_skip_version('v1.0.1', path) is True
        assert load_skip_version(path) == 'v1.0.1'
        assert save_skip_version('', path) is True  # 空串 = 清除记录
        assert load_skip_version(path) == ''
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_skip_version_corrupt_file_returns_empty():
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('not json')
        assert load_skip_version(path) == ''
    finally:
        if os.path.exists(path):
            os.remove(path)
