from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.function(*self.args, **self.kwargs)
        except Exception:
            self.signals.failed.emit(traceback.format_exc())
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
