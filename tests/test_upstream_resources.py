"""Owned-resource cleanup boundaries; actual isolated preparation is separate."""
import pytest
from types import SimpleNamespace

from benchmark_runner.upstream_agent_adapter import AdmissionError
from benchmark_runner.upstream_resources import TaskResource, _remove_owned


@pytest.mark.parametrize('message',['error: no such object: fixture','Error: No such container: fixture'])
def test_explicit_docker_absence_case_is_supported(monkeypatch,message):
    import benchmark_runner.upstream_resources as module
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stderr=message))
    assert module._inspect('fixture') is None


def test_unavailable_daemon_is_not_container_absence(monkeypatch):
    import benchmark_runner.upstream_resources as module
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stderr='error during connect: daemon unavailable'))
    with pytest.raises(AdmissionError,match='inspection failed'):
        module._inspect('fixture')


def test_foreign_container_label_refuses_removal(monkeypatch):
    import benchmark_runner.upstream_resources as module
    monkeypatch.setattr(module,'_inspect',lambda name:['a'*64,'foreign-purpose'])
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:pytest.fail('foreign deletion attempted'))
    with pytest.raises(AdmissionError,match='unowned'):
        _remove_owned('a'*64,'my-purpose')


def test_original_task_event_survives_cleanup_failure():
    resource=object.__new__(TaskResource)
    def fail():raise OSError('synthetic daemon cleanup failure')
    resource.close=fail
    original=RuntimeError('original task failure')
    with pytest.raises(BaseExceptionGroup) as result:
        resource.__exit__(RuntimeError,original,None)
    assert result.value.exceptions[0] is original
    assert 'cleanup failure' in str(result.value.exceptions[1])
