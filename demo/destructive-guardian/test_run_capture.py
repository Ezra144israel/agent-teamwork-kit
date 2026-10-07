#!/usr/bin/env python3
"""Harmless process-group lifecycle tests for the sterile capture harness."""

import errno
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock


HARNESS = Path(__file__).with_name("run_capture.py")
spec = importlib.util.spec_from_file_location("run_capture", HARNESS)
run_capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_capture)


@unittest.skipUnless(hasattr(os, "killpg"), "process groups require POSIX")
class ProcessGroupCleanupTests(unittest.TestCase):
    def start_sleeping_descendant(self, leader_program=None):
        child_program = "import time; time.sleep(60)"
        if leader_program is None:
            leader_program = (
                "import subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-c', sys.argv[1]], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
                "stderr=subprocess.DEVNULL); "
                "print(child.pid, flush=True)"
            )
        leader = subprocess.Popen(
            [sys.executable, "-c", leader_program, child_program],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        child_pid = None
        try:
            stdout, stderr = leader.communicate(timeout=5)
            self.assertEqual(leader.returncode, 0, stderr)
            child_pid = int(stdout.strip())
            self.assertEqual(os.getpgid(child_pid), leader.pid)
            self.assertNotEqual(leader.pid, os.getpgrp())
            return leader, child_pid
        except BaseException:
            self.cleanup_live_leader_group(leader)
            if child_pid is not None:
                self.cleanup_descendant(leader, child_pid)
            raise

    def assert_process_exits(self, process_id: int, expected_group: int) -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                current_group = os.getpgid(process_id)
            except ProcessLookupError:
                return
            if current_group != expected_group:
                return
            time.sleep(0.05)
        self.fail(f"owned descendant {process_id} remained in group {expected_group}")

    def cleanup_descendant(self, leader, child_pid: int) -> None:
        if leader.poll() is None:
            leader.kill()
            leader.wait(timeout=5)
        try:
            group_id = os.getpgid(child_pid)
        except ProcessLookupError:
            return
        if group_id == leader.pid and group_id != os.getpgrp():
            os.killpg(group_id, signal.SIGKILL)

    def cleanup_live_leader_group(self, leader) -> None:
        if leader.poll() is not None:
            return
        try:
            group_id = os.getpgid(leader.pid)
        except ProcessLookupError:
            return
        self.assertEqual(group_id, leader.pid)
        self.assertNotEqual(group_id, os.getpgrp())
        os.killpg(group_id, signal.SIGKILL)
        leader.communicate(timeout=5)
        self.assert_process_group_exits(group_id)

    def assert_process_group_exits(self, group_id: int) -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(group_id, 0)
            except ProcessLookupError:
                return
            except PermissionError as error:
                if error.errno != errno.EPERM:
                    raise
                # A denied probe is not proof of either presence or absence.
                listing = subprocess.run(
                    ["ps", "-axo", "pgid="],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                groups = {int(value) for value in listing.stdout.split()}
                if os.getpgrp() not in groups:
                    raise RuntimeError("process listing omitted the test's own group")
                if group_id not in groups:
                    return
            time.sleep(0.05)
        self.fail(f"owned process group {group_id} did not exit")

    def test_assert_process_group_exits_checks_listing_after_permission_error(self):
        group_id = 12345
        listing = subprocess.CompletedProcess(
            ["ps", "-axo", "pgid="], 0, " 456\n 789\n", ""
        )
        with mock.patch.object(
            os, "killpg", side_effect=PermissionError(errno.EPERM, "denied")
        ) as killpg, mock.patch.object(
            subprocess, "run", return_value=listing
        ) as run, mock.patch.object(os, "getpgrp", return_value=456):
            self.assert_process_group_exits(group_id)

        killpg.assert_called_once_with(group_id, 0)
        run.assert_called_once_with(
            ["ps", "-axo", "pgid="],
            check=True,
            capture_output=True,
            text=True,
            timeout=1,
        )

    def test_assert_process_group_exits_rejects_present_group_after_denied_probe(self):
        group_id = 12345
        listing = subprocess.CompletedProcess(
            ["ps", "-axo", "pgid="], 0, f" {group_id}\n {os.getpgrp()}\n", ""
        )
        with mock.patch.object(
            os, "killpg", side_effect=PermissionError(errno.EPERM, "denied")
        ) as killpg, mock.patch.object(
            subprocess, "run", return_value=listing
        ), mock.patch.object(
            time, "monotonic", side_effect=[0, 0, 3]
        ), mock.patch.object(time, "sleep"):
            with self.assertRaisesRegex(AssertionError, "did not exit"):
                self.assert_process_group_exits(group_id)

        killpg.assert_called_once_with(group_id, 0)

    def test_assert_process_group_exits_rejects_unverifiable_listing(self):
        for output, error_type in (
            ("", RuntimeError),
            (" 123\n", RuntimeError),
            ("not-a-group\n", ValueError),
        ):
            listing = subprocess.CompletedProcess(["ps"], 0, output, "")
            with self.subTest(output=output), mock.patch.object(
                os, "killpg", side_effect=PermissionError(errno.EPERM, "denied")
            ), mock.patch.object(
                subprocess, "run", return_value=listing
            ), mock.patch.object(os, "getpgrp", return_value=456):
                with self.assertRaises(error_type):
                    self.assert_process_group_exits(12345)

    def test_assert_process_group_exits_propagates_listing_failures(self):
        for error in (
            subprocess.CalledProcessError(1, ["ps"]),
            subprocess.TimeoutExpired(["ps"], 1),
        ):
            with self.subTest(error=type(error).__name__), mock.patch.object(
                os, "killpg", side_effect=PermissionError(errno.EPERM, "denied")
            ), mock.patch.object(subprocess, "run", side_effect=error):
                with self.assertRaises(type(error)):
                    self.assert_process_group_exits(12345)

    def test_assert_process_group_exits_propagates_other_permission_errors(self):
        with mock.patch.object(
            os, "killpg", side_effect=PermissionError(errno.EACCES, "denied")
        ), mock.patch.object(subprocess, "run") as run:
            with self.assertRaises(PermissionError) as caught:
                self.assert_process_group_exits(12345)

        self.assertEqual(caught.exception.errno, errno.EACCES)
        run.assert_not_called()

    def test_assert_process_group_exits_does_not_list_after_absent_probe(self):
        with mock.patch.object(
            os, "killpg", side_effect=ProcessLookupError(errno.ESRCH, "absent")
        ), mock.patch.object(subprocess, "run") as run:
            self.assert_process_group_exits(12345)

        run.assert_not_called()

    def test_cleanup_live_leader_group_ignores_collected_leader(self):
        leader = subprocess.Popen([sys.executable, "-c", "pass"])
        leader.wait(timeout=5)

        with mock.patch.object(os, "getpgid") as getpgid, mock.patch.object(
            os,
            "killpg",
        ) as killpg:
            self.cleanup_live_leader_group(leader)

        getpgid.assert_not_called()
        killpg.assert_not_called()

    def test_start_sleeping_descendant_cleans_up_handshake_timeout(self):
        leader_program = (
            "import subprocess, sys, time; "
            "subprocess.Popen([sys.executable, '-c', sys.argv[1]], "
            "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
            "stderr=subprocess.DEVNULL); "
            "time.sleep(60)"
        )
        leaders = []
        original_popen = subprocess.Popen

        def tracked_popen(*args, **kwargs):
            leader = original_popen(*args, **kwargs)
            if kwargs.get("start_new_session"):
                leaders.append(leader)
            return leader

        try:
            with mock.patch.object(subprocess, "Popen", side_effect=tracked_popen):
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.start_sleeping_descendant(leader_program)
            self.assertEqual(len(leaders), 1)
            leader = leaders[0]
            self.assertIsNotNone(leader.poll())
            self.assert_process_group_exits(leader.pid)
        finally:
            if leaders:
                self.cleanup_live_leader_group(leaders[0])

    def test_stop_process_group_stops_owned_descendant(self):
        leader, child_pid = self.start_sleeping_descendant()
        killpg_calls = []
        original_killpg = run_capture.os.killpg

        def tracked_killpg(group_id, signal_number):
            killpg_calls.append((group_id, signal_number))
            return original_killpg(group_id, signal_number)

        try:
            with mock.patch.object(run_capture.os, "killpg", side_effect=tracked_killpg):
                try:
                    run_capture.stop_process_group(leader.pid)
                except PermissionError as error:
                    if error.errno != errno.EPERM:
                        raise
                    self.assertNotIn(
                        (leader.pid, signal.SIGKILL),
                        killpg_calls,
                    )
            self.assertEqual(leader.returncode, 0)
            self.assert_process_exits(child_pid, leader.pid)
        finally:
            self.cleanup_descendant(leader, child_pid)

    def test_stop_process_group_does_not_kill_after_probe_permission_error(self):
        leader, child_pid = self.start_sleeping_descendant()
        killpg_calls = []
        original_killpg = run_capture.os.killpg

        def probe_permission_error(group_id, signal_number):
            killpg_calls.append((group_id, signal_number))
            if signal_number == 0:
                raise PermissionError(errno.EPERM, "Operation not permitted")
            return original_killpg(group_id, signal_number)

        try:
            with mock.patch.object(
                run_capture.os,
                "killpg",
                side_effect=probe_permission_error,
            ):
                try:
                    run_capture.stop_process_group(leader.pid)
                except PermissionError as error:
                    if error.errno != errno.EPERM:
                        raise
                else:
                    self.fail("injected probe permission error was not raised")
            self.assertEqual(
                killpg_calls,
                [
                    (leader.pid, signal.SIGTERM),
                    (leader.pid, 0),
                ],
            )
            self.assertEqual(leader.returncode, 0)
            self.assert_process_exits(child_pid, leader.pid)
        finally:
            self.cleanup_descendant(leader, child_pid)


if __name__ == "__main__":
    unittest.main()
