"""Hidden acceptance tests for pathresolve. Every test pinned via PINS."""
from pathresolve import resolve_path

PINS = {
    "test_c01_dot_removed": ["C01"],
    "test_c01_trailing_dot": ["C01"],
    "test_c02_dotdot_pops": ["C02"],
    "test_c02_trailing_dotdot": ["C02"],
    "test_c03_double_slash": ["C03"],
    "test_c03_trailing_slash": ["C03"],
    "test_c03_root_stays": ["C03"],
    "test_c04_leading_dotdot_kept": ["C04"],
    "test_c04_dotdot_beyond_root": ["C04"],
    "test_c04_absolute_leading_dotdot_dropped": ["C04"],
    "test_c05_no_os_path": ["C05"],
    "test_c06_no_empty_segments": ["C06"],
    "test_c07_empty": ["C07"],
    "test_c07_dot": ["C07"],
    "test_c07_dotdot": ["C07"],
}


def test_c01_dot_removed():
    assert resolve_path("a/./b") == "a/b"


def test_c01_trailing_dot():
    assert resolve_path("a/.") == "a"


def test_c02_dotdot_pops():
    assert resolve_path("a/b/../c") == "a/c"


def test_c02_trailing_dotdot():
    assert resolve_path("a/b/..") == "a"


def test_c03_double_slash():
    assert resolve_path("a//b") == "a/b"


def test_c03_trailing_slash():
    assert resolve_path("a/b/") == "a/b"


def test_c03_root_stays():
    assert resolve_path("/") == "/"


def test_c04_leading_dotdot_kept():
    assert resolve_path("../a") == "../a"


def test_c04_dotdot_beyond_root():
    assert resolve_path("a/../../b") == "../b"


def test_c04_absolute_leading_dotdot_dropped():
    assert resolve_path("/../a") == "/a"


def test_c05_no_os_path():
    import pathresolve
    import inspect
    src = inspect.getsource(pathresolve)
    assert "os.path" not in src
    assert "pathlib" not in src


def test_c06_no_empty_segments():
    assert resolve_path("/a//b/") == "/a/b"
    assert resolve_path("a/b/") == "a/b"


def test_c07_empty():
    assert resolve_path("") == "."


def test_c07_dot():
    assert resolve_path(".") == "."


def test_c07_dotdot():
    assert resolve_path("..") == ".."
