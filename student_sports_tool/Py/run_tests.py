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
20 个测试文件，233 passed / 0 failed（test_db_snapshot_scope.py 单独运行收集为 0，属预期）。
基线变更时请同步更新本注释与 EXPECTED_TOTAL。

2026-09-13 校正说明
-------------------
原注释写「17 个文件 / 204 passed」而 EXPECTED_TOTAL=213，两个数互相对不上、也都与实测不符，
根因是本文件曾把「拿不到汇总行」当成 passed=0/failed=0 报 OK（静默假绿），
于是基线被算小。本次实跑逐文件核对后统一为 233。

⚠️ 若本机存在「批量删除拦截」（安全软件 / 沙箱 / 代理环境的 safe-delete 钩子），
被测代码自身的清理逻辑（如 backup_cleaner 删旧自动备份）会被 SystemExit 打断，
表现为 sync_receiver / schedule_autodetect 之类的假失败。这类失败与本文件的
临时目录回收无关时，请先确认拦截规则，不要改测试去迁就。
"""
import os
import subprocess
import sys
import re
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) in ('Py', 'py') else HERE

# 期望基线（passed 数）；用于快速判断是否引入回归
EXPECTED_TOTAL = 233


def discover_tests() -> list:
    names = [f for f in os.listdir(ROOT)
             if f.startswith('test_') and f.endswith('.py')]
    return sorted(names)


LOG_DIR = os.path.join(tempfile.gettempdir(), 'smty_test_logs')


def run_one(name: str):
    """运行单个测试文件，返回 (passed, failed, raw_tail)。

    注意：配置文件 pytest.ini 已含 `-q`，此处再加 `-q` 会变成 `-qq`
    从而抑制汇总行。改用 `-p no:cacheprovider` 显式单 q，并解析汇总行数字。

    2026-09-13 改：子进程输出**落盘**而非管道捕获。
    原实现用 capture_output 管道，一旦输出丢失（进程被中断/崩溃）就只拿到空串，
    于是 passed=0/failed=0 报 `[OK]`——静默假绿。实测本机沙箱批量删临时文件被拦时
    会杀掉 pytest，正是这种「看着全绿其实没跑完」。
    现改为：无汇总行一律计 1 个失败，并打印日志路径供排查。
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, name + '.log')
    with open(log_path, 'w', encoding='utf-8', errors='replace') as fh:
        subprocess.run(
            [sys.executable, '-m', 'pytest', name,
             '-o', 'addopts=',            # 清空 pytest.ini 的 addopts，避免与下方 -q 叠加成 -qq
             # 关闭 pytest 的 tmp_path 历史回收：默认只保留最近 3 个会话目录，
             # 每个文件跑完都会**批量删**旧目录；遇到系统/安全软件的批量删除拦截时
             # pytest 会在打印汇总行之前被杀掉，跑出来的「失败」全是假的。
             '-o', 'tmp_path_retention_count=1000',
             '-q', '--tb=short', '-p', 'no:cacheprovider'],
            cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    with open(log_path, encoding='utf-8', errors='replace') as fh:
        out = fh.read()
    passed = sum(int(m) for m in re.findall(r'(\d+) passed', out))
    failed = sum(int(m) for m in re.findall(r'(\d+) failed', out))
    errors = sum(int(m) for m in re.findall(r'(\d+) error', out))
    # 汇总行形如 "7 passed in 0.68s"
    summary = ''
    for line in reversed(out.strip().splitlines()):
        if 'passed' in line or 'failed' in line or 'error' in line or 'no tests ran' in line:
            summary = line.strip()
            break
    if not summary:
        return passed, failed + errors + 1, f'(无汇总行，计为失败；日志 {log_path})'
    return passed, failed + errors, summary


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
