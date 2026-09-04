# -*- coding: utf-8 -*-
"""管理层：Qt 后台线程池通用模板。

职责：
- 提供标准 WorkerSignals（progress / finished / error 信号集）
- 提供 BaseWorker(QRunnable) 基类，子类只需实现 run_task()
- 提供 progress_cb 适配器，兼容现有 (message: str) -> None 签名
- 维护全局 QThreadPool 单例，统一管理并发

设计原则（Ponytail）：
- 最小可用模板，不引入任务队列、依赖注入等过度抽象
- 进度信号统一 (percent:int, message:str)，UI 直接驱动 QProgressBar
- 错误信号统一 str（异常文本），UI 弹框即可

典型用法（M4-S2/S3 复制此模板）：

    from worker_pool import BaseWorker, WorkerSignals, thread_pool

    class BackupWorker(BaseWorker):
        def __init__(self, dir_path, zip_path):
            super().__init__()
            self.dir_path = dir_path
            self.zip_path = zip_path

        def run_task(self):
            # progress_cb 兼容旧签名 (message: str) -> None
            cb = self.make_progress_cb()
            result = backup_coordinator.do_backup(
                self.dir_path, os.path.dirname(self.zip_path), progress_cb=cb
            )
            self.emit_finished(result)

    # UI 端：
    worker = BackupWorker(dir_path, zip_path)
    worker.signals.progress.connect(self._on_progress)   # (percent, msg)
    worker.signals.finished.connect(self._on_finished)    # (result)
    worker.signals.error.connect(self._on_error)           # (err_str)
    thread_pool().start(worker)
"""
from PySide6.QtCore import QObject, Signal, QRunnable
from PySide6.QtWidgets import QApplication

# 默认并发上限（Qt 默认常为 CPU 核数，此处明确封顶以保护磁盘 IO）
_MAX_CONCURRENT = 2


class WorkerSignals(QObject):
    """后台 Worker 信号集。

    - progress(int, str): (0-100 百分比, 进度描述)
    - finished(object): 任务最终结果，类型由子类决定
    - error(str): 异常文本（已转为字符串）
    """
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)


class BaseWorker(QRunnable):
    """后台任务基类。子类实现 run_task()，并通过 emit_* 上报状态。

    自带异常捕获：run_task() 抛出的异常会被捕获并通过 error 信号上报。
    """

    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()
        # 任务完成后自动删除，防止 QRunnable 内存泄漏
        self.setAutoDelete(True)

    # ---- 子类必须实现 ----
    def run_task(self):
        """子类实现具体业务逻辑。可调用 self.emit_progress / self.emit_finished。"""
        raise NotImplementedError('子类必须实现 run_task()')

    # ---- Qt 调度入口（不要重写）----
    def run(self):
        try:
            self.run_task()
        except Exception as e:
            self.signals.error.emit(f'{type(e).__name__}: {e}')

    #---- 子类使用的助手 ----
    def emit_progress(self, percent: int, message: str = ''):
        """发射进度信号。percent 限制在 0-100。"""
        percent = max(0, min(100, int(percent)))
        self.signals.progress.emit(percent, message)

    def emit_finished(self, result=None):
        """发射完成信号。result 类型由子类决定。"""
        self.signals.finished.emit(result)

    def make_progress_cb(self):
        """返回兼容旧签名 (message: str) -> None 的进度回调。

        调用方只能给出文本消息时使用，percent 自动估算（基于调用次数）。
        若能精确计算百分比，请直接调用 self.emit_progress(percent, msg)。
        """
        state = {'count': 0}

        def _cb(message: str):
            state['count'] += 1
            # 简易估算：前 5 次 10%-50%，之后逐步逼近 95%，留 5% 给收尾
            percent = min(95, 10 + state['count'] * 8)
            self.emit_progress(percent, message or '')

        return _cb


#---- 全局线程池单例 ----
_pool_instance = None


def thread_pool():
    """获取全局 QThreadPool 单例。"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = QApplication.instance().threadPool() if QApplication.instance() else None
        if _pool_instance is None:
            from PySide6.QtCore import QThreadPool
            _pool_instance = QThreadPool.globalInstance()
        _pool_instance.setMaxThreadCount(_MAX_CONCURRENT)
    return _pool_instance


def run_worker(worker: BaseWorker):
    """便捷启动：将 worker 提交到全局线程池。"""
    thread_pool().start(worker)
