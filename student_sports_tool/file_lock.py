# -*- coding: utf-8 -*-
"""管理层：跨进程文件互斥锁工具。

职责：
- 封装 portalocker 库，提供上下文管理器风格的文件锁
- 支持 Excel/JSON/ZIP 等任意文件的读写互斥
- 检测到文件被占用时安全等待 1 秒后重试，避免直接报错
- 桌面端与 Android 端备份文件并发读写场景的核心防护

设计原则：
- 单一职责：仅负责锁机制，不关心业务逻辑
- 失败友好：默认重试 3 次，每次间隔 1 秒，超时抛出 LockTimeoutError
- 跨平台：portalocker 在 Windows 使用 LockFileEx，Linux 使用 fcntl
"""
import os
import time
import contextlib
import tempfile

try:
    import portalocker
except ImportError:  # pragma: no cover
    portalocker = None


class LockTimeoutError(RuntimeError):
    """文件锁获取超时异常。"""


@contextlib.contextmanager
def file_lock(file_path: str, mode: str = 'a+', timeout: float = 3.0,
              retry_interval: float = 1.0, fail_when_missing: bool = False):
    """文件互斥锁上下文管理器。

    参数:
        file_path: 被锁定的文件路径（会创建同目录下的 .lock 伴生文件）
        mode: 锁文件的打开模式，默认 'a+'
        timeout: 总超时秒数，超时抛出 LockTimeoutError
        retry_interval: 每次重试间隔秒数
        fail_when_missing: True 时若 portalocker 未安装则直接抛出 ImportError；
                           False 时降级为无锁模式（仅记录警告）

    使用示例:
        with file_lock('学员档案.xlsx'):
            wb = load_workbook('学员档案.xlsx')
            # ... 修改 ...
            wb.save('学员档案.xlsx')

    实现说明:
        - 锁文件路径 = 原文件路径 + '.lock'，避免污染原文件
        - 锁文件在 with 块结束后仅解锁并关闭句柄，不删除：
          删除会造成多进程竞争窗口（A 删锁与 B 建锁交错时互斥失效）
        - portalocker.LOCK_EX 排他锁，LOCK_NB 非阻塞模式配合超时重试
    """
    if portalocker is None:
        if fail_when_missing:
            raise ImportError(
                'portalocker 未安装，无法启用文件锁。'
                '请执行 pip install portalocker 或在 requirements.txt 中添加。'
            )
        # 降级：无锁模式（开发环境/单进程场景）
        yield None
        return

    lock_path = file_path + '.lock'
    # 确保锁文件所在目录存在
    lock_dir = os.path.dirname(lock_path)
    if lock_dir and not os.path.exists(lock_dir):
        os.makedirs(lock_dir, exist_ok=True)

    # 锁文件句柄一律用 'a+' 打开（不存在则自动创建）：
    # mode='r' 时若伴生锁文件不存在，open('r') 会抛 FileNotFoundError。
    # 锁语义由 portalocker 决定（此处始终 LOCK_EX），句柄打开模式不影响互斥正确性。
    lock_file = open(lock_path, 'a+', encoding='utf-8')
    acquired = False
    start_ts = time.time()
    last_err = None
    try:
        while True:
            try:
                portalocker.lock(lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
                acquired = True
                break
            except (portalocker.LockException, OSError, IOError) as e:
                last_err = e
                if time.time() - start_ts >= timeout:
                    raise LockTimeoutError(
                        f'获取文件锁超时（{timeout:.1f}s）：{file_path}\n'
                        f'可能原因：另一进程（如手机端备份）正在写入该文件。\n'
                        f'最后错误：{last_err}'
                    )
                time.sleep(retry_interval)
        yield lock_file
    finally:
        if acquired:
            try:
                portalocker.unlock(lock_file)
            except Exception:
                pass
        lock_file.close()
        # 清理锁文件（失败不影响主流程）
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except OSError:
            pass


def atomic_save_workbook(wb, fpath: str) -> None:
    """openpyxl 工作簿原子写入：先写同目录临时文件，成功后 os.replace 原子覆盖。

    解决 wb.save(fpath) 直写目标路径时，写入中断（崩溃/断电）导致整个 Excel 损坏的问题。
    失败时清理临时文件，原文件保持完好。

    本函数不加锁；跨进程互斥请由调用方配合 file_lock 使用
    （参照 data_center/config_manager.py 的既有模式）。
    """
    dir_name = os.path.dirname(os.path.abspath(fpath)) or '.'
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            wb.save(f)
        os.replace(tmp_path, fpath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def with_retry(func, max_retries: int = 3, retry_interval: float = 1.0,
               exceptions=(OSError, IOError)):
    """带重试的函数调用包装器。

    参数:
        func: 要调用的可调用对象
        max_retries: 最大重试次数（含首次）
        retry_interval: 每次重试间隔秒数
        exceptions: 触发重试的异常类型

    返回:
        func 的返回值

    抛出:
        最后一次重试时的异常
    """
    last_exc = None
    for i in range(max_retries):
        try:
            return func()
        except exceptions as e:
            last_exc = e
            if i < max_retries - 1:
                time.sleep(retry_interval)
    raise last_exc
