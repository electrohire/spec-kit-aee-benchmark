"""Read-only audit of the immutable, network-disabled benchmark base image."""
import argparse
import json
import subprocess
from pathlib import Path

from benchmark_runner.store import write_json, utc

IMAGE="sha256:adc751293f079d2ed0a459cbeb36e2b746ef8382e23d0b04c1fa282b8cb2a120"
CODE="""
import pathlib,json,os,platform
paths={p:[str(x) for x in pathlib.Path(p).rglob('*')] for p in ('/testbed','/grade','/workflow')}
forbidden=[k for k in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GITHUB_TOKEN','GH_TOKEN') if k in os.environ]
print(json.dumps(dict(paths=paths,forbidden_env_names=forbidden,python=platform.python_version())))
"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    result=subprocess.run(["docker","run","--rm","--network","none","--cap-drop","ALL",
        "--security-opt","no-new-privileges","--memory","256m","--cpus","1",
        "--entrypoint","python",IMAGE,"-c",CODE],capture_output=True,timeout=30)
    if result.returncode:raise RuntimeError("base image audit process failed")
    value=json.loads(result.stdout)
    value.update(image=IMAGE,observed_at=utc(),passed=not any(value["paths"].values()) and not value["forbidden_env_names"])
    write_json(args.output,value,exclusive=True)
    if not value["passed"]:raise RuntimeError("base image contains unexpected solver/grader assets or credentials")
    print(json.dumps(value))


if __name__=="__main__":main()
