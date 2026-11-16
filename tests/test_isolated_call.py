import multiprocessing
import time
import unittest

from pia_runtime.isolated_call import isolated_call
from pia_runtime.stage_policy import StageTimeout


def blocked():
    time.sleep(30)
    return "late"


def add(left, right):
    return left + right


class IsolatedCallTest(unittest.TestCase):
    def test_result_and_blocked_process_cleanup(self):
        self.assertEqual(isolated_call(add, (2, 3), timeout=3), 5)
        with self.assertRaises(StageTimeout):
            isolated_call(blocked, timeout=0.15)
        self.assertFalse(multiprocessing.active_children())

    def test_cancel_cleans_child(self):
        def cancel():
            raise RuntimeError("cancelled")
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            isolated_call(blocked, timeout=3, check=cancel)
        self.assertFalse(multiprocessing.active_children())
