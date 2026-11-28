"""Regression checks for render child initialization and session cleanup.

Run with: python -m unittest discover -s tests -p 'test_render_pool_regressions.py'
"""
import multiprocessing as mp
import os
import queue
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _probe_resolver_worker(in_q, out_q, cancel_event):
    """Ask the actual worker loop what its freshly spawned process resolves."""
    from htd.engine import core, render_service

    def probe(_request, _progress, _cancel):
        return core.ffmpeg_executable()

    render_service.run_request = probe
    render_service._worker_loop(in_q, out_q, cancel_event)


class RenderPoolRegressions(unittest.TestCase):
    def test_spawned_worker_installs_ffmpeg_resolver(self):
        from htd.engine import ffmpeg_tools

        binary = shutil.which("ffmpeg")
        if not binary:
            try:
                import imageio_ffmpeg
                binary = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                self.skipTest("No working FFmpeg available for the resolver test")
        binary = str(Path(binary).resolve())
        if ffmpeg_tools.probe(Path(binary), "test") is None:
            self.skipTest("FFmpeg candidate is not executable")

        ctx = mp.get_context("spawn")
        in_q, out_q, cancel = ctx.Queue(), ctx.Queue(), ctx.Event()
        # An empty PATH ensures success depends on the explicit resolver, not PATH.
        with mock.patch.dict(os.environ, {"PATH": "", "HTD_FFMPEG": binary}):
            child = ctx.Process(target=_probe_resolver_worker, args=(in_q, out_q, cancel))
            child.start()
            try:
                in_q.put("probe")
                try:
                    kind, result = out_q.get(timeout=45)
                except queue.Empty:
                    self.fail("spawned worker did not respond")
                self.assertEqual((kind, result), ("result", binary))
            finally:
                in_q.put(None)
                child.join(10)
                if child.is_alive():
                    child.terminate()
                    child.join(5)
                in_q.close()
                out_q.close()

    def test_windows_does_not_signal_session_pid(self):
        from htd import config

        with mock.patch.object(config.os, "name", "nt"), mock.patch.object(config.os, "kill") as kill:
            self.assertTrue(config._session_owner_alive("session-123-456"))
            kill.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX signal-zero behavior")
    def test_posix_session_liveness(self):
        from htd import config

        with mock.patch.object(config.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(config._session_owner_alive("session-123-456"))
        with mock.patch.object(config.os, "kill", side_effect=PermissionError):
            self.assertTrue(config._session_owner_alive("session-123-456"))


if __name__ == "__main__":
    unittest.main()
