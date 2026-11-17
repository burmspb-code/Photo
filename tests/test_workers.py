"""Тесты CoreWorker: результат, ошибка, прогресс и отмена."""
from __future__ import annotations

import time

from src.core.progress import check_cancel, maybe_report
from src.ui.workers import CoreWorker
from tests.gui_case import GuiTestCase


class TestCoreWorker(GuiTestCase):
    @staticmethod
    def _connect(worker: CoreWorker) -> dict:
        seen = {"progress": [], "result": None, "error": None, "cancelled": False}
        worker.progress.connect(lambda p, m: seen["progress"].append((p, m)))
        worker.succeeded.connect(lambda r: seen.__setitem__("result", r))
        worker.failed.connect(lambda m: seen.__setitem__("error", m))
        worker.cancelled.connect(lambda: seen.__setitem__("cancelled", True))
        return seen

    def _run(self, func, *, cancel=False) -> dict:
        worker = CoreWorker(func)
        seen = self._connect(worker)
        if cancel:
            worker.cancel()
        worker.start()
        self.assertTrue(worker.wait(5000))
        self.process_events()
        return seen

    def test_success_with_progress(self) -> None:
        def job(progress=None, cancelled=None):
            for step in range(1, 4):
                check_cancel(cancelled)
                maybe_report(progress, step * 25, f"этап {step}")
            return "готово"

        seen = self._run(job)
        self.assertEqual(seen["result"], "готово")
        self.assertEqual([p for p, _ in seen["progress"]], [25, 50, 75])
        self.assertIsNone(seen["error"])
        self.assertFalse(seen["cancelled"])

    def test_failure_is_reported(self) -> None:
        def job(progress=None, cancelled=None):
            raise ValueError("сбой")

        seen = self._run(job)
        self.assertIsNone(seen["result"])
        self.assertEqual(seen["error"], "ValueError: сбой")

    def test_cancel_before_start(self) -> None:
        def job(progress=None, cancelled=None):
            check_cancel(cancelled)
            return "не должно выполниться"

        seen = self._run(job, cancel=True)
        self.assertTrue(seen["cancelled"])
        self.assertIsNone(seen["result"])
        self.assertIsNone(seen["error"])

    def test_cancel_from_progress_slot_stops_loop(self) -> None:
        def job(progress=None, cancelled=None):
            for step in range(200):
                check_cancel(cancelled)
                maybe_report(progress, step, "работа")
                time.sleep(0.01)
            return "цикл завершён"

        worker = CoreWorker(job)
        seen = self._connect(worker)
        worker.progress.connect(lambda _p, _m: worker.cancel())
        worker.start()
        for _ in range(100):
            self.process_events()
            if seen["cancelled"] or seen["result"] or seen["error"]:
                break
            time.sleep(0.01)
        self.assertTrue(worker.wait(5000))
        self.process_events()
        self.assertTrue(seen["cancelled"])
        self.assertIsNone(seen["result"])
        self.assertIsNone(seen["error"])
