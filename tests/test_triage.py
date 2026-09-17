import json
from pathlib import Path

import pytest

from benchmark_runner.triage import main, run, transform


def csv(tmp_path, rows):
    p = tmp_path/"input.csv"
    p.write_text("asset_id,vibration_mm_s,temperature_c\n"+rows)
    return p


def test_boundaries_and_order(tmp_path):
    source = csv(tmp_path, "z,7.1,79.9\na,7.099,80\nb,0,-20\nc,7.1,80\n")
    before = source.read_bytes()
    target = tmp_path/"out.json"
    run(source, target)
    data = json.loads(target.read_text())
    assert [d["asset_id"] for d in data] == ["a", "b", "c", "z"]
    assert data[0]["reasons"] == ["temperature_c >= 80"]
    assert not data[1]["flagged"]
    assert len(data[2]["reasons"]) == 2
    assert data[3]["reasons"] == ["vibration_mm_s >= 7.1"]
    assert source.read_bytes() == before
    first = target.read_bytes()
    run(source, target)
    assert target.read_bytes() == first


@pytest.mark.parametrize("rows", ["a,1,2\na,2,3\n", ",1,2\n", "a,,2\n", "a,1\n", "a,x,2\n",
                                     "a,nan,2\n", "a,1,inf\n", "a,-1,2\n", "a,1,2,3\n"])
def test_validation_preserves_output(tmp_path, rows):
    source = csv(tmp_path, rows)
    out = tmp_path/"output.json"
    out.write_text("existing")
    assert main([str(source), str(out)]) == 2
    assert out.read_text() == "existing"


def test_header_same_path_and_atomic_failure(tmp_path, monkeypatch):
    source = csv(tmp_path, "a,1,2\n")
    with pytest.raises(ValueError, match="different"):
        run(source, source)
    target = tmp_path/"out.json"
    target.write_text("old")
    def fail(*args):
        raise OSError("simulated replace failure")
    monkeypatch.setattr("benchmark_runner.triage.os.replace", fail)
    with pytest.raises(OSError):
        run(source, target)
    assert target.read_text() == "old"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["input.csv", "out.json"]
    source.write_text("wrong,header\n")
    with pytest.raises(ValueError, match="requires"):
        transform(source)


def test_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    assert "not a validated" in capsys.readouterr().out
