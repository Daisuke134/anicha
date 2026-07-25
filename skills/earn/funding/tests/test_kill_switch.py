import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.kill_switch import is_killed  # noqa: E402


def test_is_killed_false_when_no_kill_file_present(tmp_path):
    assert is_killed(str(tmp_path)) is False


def test_is_killed_true_when_kill_file_present(tmp_path):
    (tmp_path / "KILL").write_text("halted by operator\n", encoding="utf-8")
    assert is_killed(str(tmp_path)) is True


def test_is_killed_false_for_a_directory_that_does_not_exist():
    assert is_killed(str(tmp_path_for_missing_dir())) is False


def tmp_path_for_missing_dir():
    import tempfile

    d = tempfile.mkdtemp()
    os.rmdir(d)
    return d
