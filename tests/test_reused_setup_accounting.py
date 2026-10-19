from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import launch_benchmark_mission as mission


def test_external_reused_call_sources_are_exported_once_with_legacy_sources(tmp_path):
    root=tmp_path/'repository';root.mkdir()
    legacy=root/'artifacts/current-action-transport-01';legacy.mkdir(parents=True)
    transport=tmp_path/'other-checkout/current-action-transport-12';transport.mkdir(parents=True)
    latency=tmp_path/'other-checkout/current-latency-calibration-12';latency.mkdir()
    diagnostic=root/'artifacts/current-hallucination-11';diagnostic.mkdir()
    paths=dict(transport=transport,latency=latency,hallucination=diagnostic)
    assert mission.setup_sources(root,paths)==[legacy,transport,latency,diagnostic]
    paths['transport']=legacy
    assert mission.setup_sources(root,paths)==[legacy,latency,diagnostic]
