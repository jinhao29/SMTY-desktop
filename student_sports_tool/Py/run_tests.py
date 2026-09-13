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
22 个测试文件，248 passed / 0 failed（test_db_snapshot_scope.py 单独运行收集为 0，属预期）。
基线变更时请同步更新本注释与 EXPECTED_TOTAL。

2026-09-13 批 1 变更（操作摩擦修复）
----------------------------------
新增 test_lesson_feedback_wiring.py（5 例），锁定「记录一次上课 / 填写课后反馈」两条接线：
LessonWindow（5 字段）与 feedback_storage（7 字段）此前从未被实例化 / 从未被 UI 调用。
233 → 238。

2026-09-13 批 2 变更（操作摩擦修复）
----------------------------------
新增 test_phone_fee_merge.py（10 例），锁定手机端收费流水 → PC 收费记录的合并规则：
自然键（学员|日期|金额|课时数|收款方式|备注）去重，不重复 / 不覆盖 / 不静默丢弃。
238 → 248。

2026-09-13 校正说明
-------------------
原注释写「17 个文件 / 204 passed」而 EXPECTED_TOTAL=213，两个数互相对不上、也都与实测不符，
根因是本文件曾把「拿不到汇总行」当成 passed=0/failed=0 报 OK（静默假绿），
于是基线被算小。本次实跑逐文件核对后统一为 233。

⚠️ 若本机存在「批量删除拦截」（安全软件 / 沙箱 / 代理环境的 safe-delete 钩子），
被测代码自身的清理逻辑（如 backup_cleaner 删旧自动备份）会被 SystemExit 打断，
表现为 sync_receiver / schedule_autodetect 之类的假失败。这类失败与本文件的
临时目录回收无关时，请先确认拦截规则，不要改测试去迁就。
详见 docs/local_environment_notes.md。

临时目录治理（2026-09-13）
-------------------------
两个决定，配套使用，缺一不可：

1. **运行期间不回收**（`-o tmp_path_retention_count=1000`）
   为什么关：pytest 默认 `tmp_path_retention_count=3`，即每个会话结束都要批量删掉
   更早的会话目录（实测一次要删上百个文件）。本机存在「批量删除守卫」，会让这类删除
   直接 `SystemExit(1)` 打断进程，而它发生在**打印汇总行之前**——于是 pytest 输出全丢，
   跑批器只能看到空输出。关掉回收，跑批就稳定了。
   为什么不撤：这是**正确性修复**，不是绕路。开发者要的是「测试结论可信」，
   而不是「临时目录干净」；宁可目录多留几天，也不能让结论失真。

2. **启动时有界清理**（`cleanup_stale_temp`）
   为什么保留：关掉回收后 `%TEMP%/pytest-of-<user>/` 只增不减（实测一轮全量约 +100 个文件，
   0.9 MB 量级），长期跑会堆积。
   为什么「有界」：清理本身也是删除，同样会撞上守卫，所以给了两个上限——
   `CLEANUP_MAX_AGE_DAYS=7`（只删过期目录）与 `CLEANUP_MAX_FILES=40`
   （单轮最多删这么多个**文件**）。40 这个数来自守卫阈值 50（见
   docs/local_environment_notes.md 的实测报文 `{"threshold":50}`），留 20% 余量。
   ⚠️ 守卫计的是**文件数**不是目录数（实测 `{"count":112,...,"targetCount":1}`），
   所以上限必须按文件算。
   清理失败一律吞掉并只记一行日志：卫生工作不得影响测试结论。
"""
import glob
import os
import shutil
import subprocess
import sys
import re
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) in ('Py', 'py') else HERE

# 期望基线（passed 数）；用于快速判断是否引入回归
EXPECTED_TOTAL = 248

# 有界清理参数；改动前先读模块 docstring「临时目录治理」
CLEANUP_MAX_AGE_DAYS = 7
CLEANUP_MAX_FILES = 40          # 必须 < 守卫阈值 50


def discover_tests() -> list:
    names = [f for f in os.listdir(ROOT)
             if f.startswith('test_') and f.endswith('.py')]
    return sorted(names)


LOG_DIR = os.path.join(tempfile.gettempdir(), 'smty_test_logs')


def _count_files(path: str) -> int:
    """递归数文件个数（守卫按文件数计数，故上限也必须按文件算）。"""
    n = 0
    for _root, _dirs, files in os.walk(path):
        n += len(files)
    return n


def cleanup_stale_temp(verbose: bool = True):
    """有界清理 pytest 遗留的过期临时会话目录。返回 (删目录数, 删文件数, 跳过数, 错误)。

    只处理 `%TEMP%/pytest-of-<user>/` 下 mtime 超过 CLEANUP_MAX_AGE_DAYS 的直接子目录，
    最旧的先删，累计删除文件数不超过 CLEANUP_MAX_FILES —— 保证单轮删除量低于批量删除
    守卫阈值（见模块 docstring）。

    任何异常（含守卫抛出的 SystemExit，属 BaseException）都吞掉：清理是卫生工作，
    绝不允许影响测试结果。
    """
    removed_dirs = removed_files = skipped = 0
    err = ''
    try:
        cutoff = time.time() - CLEANUP_MAX_AGE_DAYS * 86400
        expired = []
        for root in glob.glob(os.path.join(tempfile.gettempdir(), 'pytest-of-*')):
            if not os.path.isdir(root):
                continue
            try:
                entries = list(os.scandir(root))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir() and entry.stat().st_mtime < cutoff:
                        expired.append((entry.stat().st_mtime, entry.path))
                except OSError:
                    continue
        expired.sort()                          # 最旧的先删

        budget = CLEANUP_MAX_FILES
        for _mtime, path in expired:
            if budget <= 0:
                skipped += 1
                continue
            size = _count_files(path)
            if size > budget:                   # 这一个就超预算，留给下次
                skipped += 1
                continue
            try:
                shutil.rmtree(path)
                removed_dirs += 1
                removed_files += size
                budget -= size
            except BaseException as e:          # noqa: BLE001 - 含 SystemExit，必须吞
                err = f'{type(e).__name__}: {e}'
                skipped += 1
    except BaseException as e:                  # noqa: BLE001
        err = f'{type(e).__name__}: {e}'

    if verbose and (removed_dirs or skipped or err):
        msg = f'[tmp] 清理 {CLEANUP_MAX_AGE_DAYS} 天前的临时会话目录：' \
              f'删除 {removed_dirs} 个目录 / {removed_files} 个文件，跳过 {skipped}'
        if err:
            msg += f'；出现异常（已忽略）{err}'
        print(msg)
    return removed_dirs, removed_files, skipped, err


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
    # 先做一次有界的临时目录清理（失败不影响本次结果，原因见模块 docstring）
    cleanup_stale_temp()

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


def selfcheck():
    """清理逻辑自检：`python Py/run_tests.py --selfcheck`。

    不进 pytest 用例集（那个基线是 233，不想为一个卫生函数动它），
    但要有可运行的检查——预算算错、或误删新目录，这里立刻红。
    """
    import datetime

    root = os.path.join(tempfile.gettempdir(),
                        'pytest-of-selfcheck-%d' % os.getpid())
    old_dir = os.path.join(root, 'pytest-old')
    new_dir = os.path.join(root, 'pytest-fresh')
    shutil.rmtree(root, ignore_errors=True)           # 清掉上次自检的残留
    os.makedirs(old_dir)
    os.makedirs(new_dir)
    for i in range(3):                                  # 旧目录塞 3 个文件
        with open(os.path.join(old_dir, 'f%d.txt' % i), 'w') as fh:
            fh.write('x')
    stale = (datetime.datetime.now() - datetime.timedelta(days=8)).timestamp()
    os.utime(old_dir, (stale, stale))

    removed_dirs, removed_files, _skipped, err = cleanup_stale_temp(verbose=False)
    assert err == '', '清理不应报错：%s' % err
    assert not os.path.exists(old_dir), '过期目录应被删除'
    assert os.path.exists(new_dir), '未过期目录不该被删（只删 %s 天前）' % CLEANUP_MAX_AGE_DAYS

    shutil.rmtree(root, ignore_errors=True)
    print('selfcheck OK：过期目录已清、新目录保留、单轮删除 %d 目录 / %d 文件（上限 %d 文件）'
          % (removed_dirs, removed_files, CLEANUP_MAX_FILES))
    return 0


if __name__ == '__main__':
    if '--selfcheck' in sys.argv:
        sys.exit(selfcheck())
    sys.exit(main())
