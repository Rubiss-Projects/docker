import tempfile
import unittest
from pathlib import Path

from snapshot import read, snapshot


class SnapshotTest(unittest.TestCase):
    def test_missing_daemon(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(snapshot(Path(directory))["error"], "daemon_not_found")

    def test_bounded_read_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample"
            path.write_text("x" * 4096)
            self.assertEqual(len(read(path)), 2048)
            self.assertEqual(read(path / "missing"), {"error": "NotADirectoryError"})

    def test_descriptor_paths_without_reading_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory) / "123"
            task = proc / "task" / "124"
            task.mkdir(parents=True)
            (proc / "comm").write_text("transmission-da\n")
            (task / "wchan").write_text("p9_client_rpc")
            (task / "syscall").write_text("74 0x9 0 0 0 0 0")
            (proc / "fd").mkdir()
            (proc / "fd" / "9").symlink_to("/does-not-exist/media.mkv")
            result = snapshot(Path(directory))
            self.assertEqual(result["threads"][0]["syscall"].split()[0], "74")
            self.assertEqual(result["fds"]["9"], "/does-not-exist/media.mkv")
            self.assertEqual(result["threads"][0]["stack"], {"error": "FileNotFoundError"})


if __name__ == "__main__":
    unittest.main()
