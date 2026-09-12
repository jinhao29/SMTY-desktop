# -*- coding: utf-8 -*-
"""测试运行器：逐文件隔离执行 pytest，规避单进程全套跑 capture 崩溃。

背景
----
PySide6 的 Qt 事件循环与 pytest 的全局 stdout capture 冲突：
单进程一次 collect+run 全部 test_*.py 时，部分用例会触发

    ValueError: I/O operation on closed file.
    （_pytest/capture.py 的 snap() -> tmpfile.seek(0)）

表现为 "no tests ran"，是环境已知问题，不是测试本身失败。

解决方式
--------
本脚本为每个测试文件启动独立子进程，逐个报告结果并汇总。
这样既保留了一键回归的便利，又绕开了 capture 冲突。

用法
----
    python Py/run_tests.py            # 跑全部
    python Py/run_tests.py test_fee_manager.py   # 跑指定文件

期望基线
--------
17 个测试文件，204 passed（test_db_snapshot_scope.py 单独运行收集为 0，属预期）。
基线变更时请同步更新本注释与 README/文档。
"""
import os
import subprocess
import sys
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) in ('Py', 'py') else HERE

# 期望基线（passed 数）；用于快速判断是否引入回归
EXPECTED_TOTAL = 213


def discover_tests() -> list:
    names = [f for f in os.listdir(ROOT)
             if f.startswith('test_') and f.endswith('.py')]
    return sorted(names)


def run_one(name: str):
    """运行单个测试文件，返回 (passed, failed, raw_tail)。

    注意：配置文件 pytest.ini 已含 `-q`，此处再加 `-q` 会变成 `-qq`
    从而抑制汇总行。改用 `-p no:cacheprovider` 显式单 q，并解析汇总行数字。
    """
    proc = subprocess.run(
        [sys.executable, '-m', 'pytest', name,
         '-o', 'addopts=',            # 清空 pytest.ini 的 addopts，避免与下方 -q 叠加成 -qq
         '-q', '--tb=short', '-p', 'no:cacheprovider'],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = (proc.stdout or '') + (proc.stderr or '')
    passed = sum(int(m) for m in re.findall(r'(\d+) passed', out))
    failed = sum(int(m) for m in re.findall(r'(\d+) failed', out))
    errors = sum(int(m) for m in re.findall(r'(\d+) error', out))
    # 汇总行形如 "7 passed in 0.68s"；无汇总行时回退到最后一行
    summary = ''
    for line in reversed(out.strip().splitlines()):
        if 'passed' in line or 'failed' in line or 'error' in line or 'no tests ran' in line:
            summary = line.strip()
            break
    return passed, failed + errors, summary or '(无汇总)'


def main():
    targets = sys.argv[1:] or discover_tests()
    if not targets:
        print('未找到任何 test_*.py')
        return 1

    total_passed = 0
    total_failed = 0
    failed_files = []

    print('=' * 62)
    print('桌面端测试回归 · 逐文件隔离模式')
    print('=' * 62)
    for name in targets:
        passed, failed, tail = run_one(name)
        total_passed += passed
        total_failed += failed
        flag = 'OK ' if failed == 0 else 'FAIL'
        print(f'[{flag}] {name:<34} {tail}')
        if failed:
            failed_files.append(name)

    print('-' * 62)
    print(f'合计: {total_passed} passed, {total_failed} failed')
    print(f'基线: {EXPECTED_TOTAL} passed')
    if total_failed:
        print(f'失败文件: {", ".join(failed_files)}')
        return 1
    if total_passed != EXPECTED_TOTAL:
        print(f'注意: passed 数与基线不一致（期望 {EXPECTED_TOTAL}，实际 {total_passed}），'
              f'若为有意变更请同步更新 EXPECTED_TOTAL。')
    else:
        print('基线一致 ✓')
    return 0


if __name__ == '__main__':
    sys.exit(main())
