"""Trusted, offline task preparer for the pinned FeatureBench grader image.

Run only in the trusted controller container, with a read-only /control plan,
exclusive /results and the local Docker socket. The separate actor container
never receives these mounts, this plan, dataset gold or the grader package.
This is preparation, not inference, grading or campaign admission.
"""
from pathlib import Path
import hashlib
import json
import logging
import sysconfig

import docker
from featurebench.infer.models import TaskInstance
from featurebench.infer.runtime import RuntimeHandler


CONTROL = Path('/control')
OUT = Path('/results')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    plan = json.loads((CONTROL/'plan.json').read_text())
    assert digest(Path(__file__)) == plan['preparer_sha256']
    assert digest(CONTROL/'input.json') == plan['input_sha256']
    expected = json.loads((CONTROL/'expected-featurebench-package.json').read_text())
    package = Path(sysconfig.get_paths()['purelib'])/'featurebench'

    def package_hashes():
        return {p.relative_to(package).as_posix(): digest(p)
                for p in package.rglob('*')
                if p.is_file() and '__pycache__' not in p.parts}

    assert len(expected) == 113 and package_hashes() == expected
    with (OUT/'started.json').open('x') as handle:
        json.dump(dict(plan_sha256=digest(CONTROL/'plan.json'), model_calls=0), handle)
    row = json.loads((CONTROL/'input.json').read_text())
    real = docker.from_env()
    actor = real.containers.get(plan['container_id'])
    actor.reload()
    assert actor.id == plan['container_id']
    assert actor.image.id == plan['image_id']
    assert actor.attrs['Config']['Labels']['purpose'] == plan['purpose']
    assert actor.attrs['State']['Running'] and not actor.attrs['Mounts']
    config = actor.attrs['HostConfig']
    assert config['NetworkMode'] == 'none' and config['Privileged'] is False
    assert config['NanoCpus'] == 2_000_000_000 and config['CpusetCpus'] == '0,1'
    assert config['Memory'] == plan['memory_bytes'] and config['PidsLimit'] == 256
    assert 'no-new-privileges' in ' '.join(config['SecurityOpt'])
    # Only a fresh upstream DockerEnvironment sleep container is admissible.
    # Preparation never attaches to a container already running solver commands.
    assert actor.attrs['Path'] == 'sleep'

    def checked(command, user='root'):
        code, raw = actor.exec_run(['/bin/bash', '-lc', command], user=user)
        text = raw.decode('utf-8', errors='replace')
        with (OUT/'preparation.log').open('a') as handle:
            handle.write('\nCOMMAND '+command+'\n'+text+'\nEXIT '+str(code)+'\n')
        if code:
            raise RuntimeError('Task preparation failed; retained original output')
        return text

    class ContainerManager:
        def exec_command(self, container, command, log_file=None):
            assert container.id == actor.id
            code, raw = container.exec_run(['/bin/bash', '-lc', command])
            text = raw.decode('utf-8', errors='replace')
            with (OUT/'upstream-runtime.log').open('a') as handle:
                handle.write('\nCOMMAND '+command+'\n'+text+'\nEXIT '+str(code)+'\n')
            return code, text

        def copy_to_container(self, container, source, target):
            import io
            import tarfile
            assert container.id == actor.id
            raw = Path(source).read_bytes()
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w') as archive:
                item = tarfile.TarInfo(Path(target).name)
                item.mode, item.size = 0o600, len(raw)
                archive.addfile(item, io.BytesIO(raw))
            assert container.put_archive(str(Path(target).parent), stream.getvalue())

    runtime = RuntimeHandler(ContainerManager(), logging.getLogger('upstream-preparation'))
    if plan['kind'] == 'FeatureBench':
        instance = TaskInstance.from_dict(row)
        assert runtime._initialize_level1(actor, instance, OUT/'upstream-runtime.log', white_box=False)
        for name in instance.fail_to_pass:
            assert not any(value in name for value in ('..', '\n', "'"))
            checked("test ! -e '/testbed/"+name+"'")
    elif plan['kind'] == 'SWE-EVO':
        commit = row['base_commit']
        assert len(commit) == 40 and set(commit) <= set('0123456789abcdef')
        checked('set -e; cd /testbed; git archive '+commit+
                ' > /tmp/benchmark-base-source.tar; '
                'find /testbed -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; '
                'tar -xf /tmp/benchmark-base-source.tar -C /testbed; '
                'rm /tmp/benchmark-base-source.tar; '
                'find /testbed -type d -name __pycache__ -prune -exec rm -rf -- {} +; '
                'find /testbed -type f -name "*.pyc" -delete; '
                'git init; git config user.email benchmark@local.invalid; '
                'git config user.name Benchmark; git add -A; '
                'git commit --allow-empty -m "Clean declared source baseline"')
    else:
        raise ValueError('unregistered task kind')
    assert runtime.clear_package_caches(actor, OUT/'upstream-runtime.log')
    checked('set -e; for p in /opt/benchmark-wheelhouse /opt/benchmark-compatible-resources; '
            'do if test -d "$p"; then chmod 700 "$p"; fi; done; '
            'groupadd --system fbagent; '
            'useradd --system --gid fbagent --home-dir /home/fbagent '
            '--create-home --shell /bin/bash fbagent; '
            'chown -R fbagent:fbagent /testbed')
    probe = checked('cd /testbed && test -w . && test ! -r /root && '
                    'test ! -w /opt/miniconda3/envs/testbed/bin/python && '
                    'test ! -w /usr/bin/git && '
                    'test ! -S /var/run/docker.sock && test ! -e /control && test ! -e /results && '
                    'test ! -r /opt/benchmark-wheelhouse && '
                    'test ! -r /opt/benchmark-compatible-resources && '
                    'test $(git rev-list --all --count) -eq 1 && '
                    'test -z "$(git remote)" && test -z "$(git status --porcelain)" && '
                    'git rev-parse HEAD && git rev-parse HEAD^{tree} && '
                    'id -u && grep -E "^(NoNewPrivs|CapEff):" /proc/self/status', user='fbagent')
    assert 'CapEff:\t0000000000000000' in probe and 'NoNewPrivs:\t1' in probe
    if plan['kind'] == 'SWE-EVO':
        end = row['end_version_commit']
        assert len(end) == 40 and set(end) <= set('0123456789abcdef')
        checked('cd /testbed && ! git cat-file -e '+end+'^{commit} 2>/dev/null', user='fbagent')
    assert package_hashes() == expected
    result = dict(prepared=True, model_calls=0, coding_campaign_admitted=False,
                  container_id=actor.id, image_id=actor.image.id, kind=plan['kind'],
                  instance_id=row['instance_id'], baseline_commit=probe.splitlines()[0],
                  baseline_tree=probe.splitlines()[1], observed_uid=999, probe=probe,
                  preparer_sha256=plan['preparer_sha256'], input_sha256=plan['input_sha256'],
                  upstream_package_files_verified=113,
                  scope='Declared base/masked workspace and bounded OS/path controls. '
                        'Not complete gold-absence, transient immutability or protected identity.')
    with (OUT/'prepared.json').open('x') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
