"""Only shell commands cross into fresh network-disabled upstream containers."""
import json
import re
import subprocess
import uuid
import shutil
import tempfile
from pathlib import Path


def docker_args(image, name):
    if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", image):
        raise ValueError("solver image must be pinned by registry digest")
    return ["docker", "run", "-d", "--rm", "--name", name, "--network=none",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=256",
            "--memory=8g", "--cpus=4", "--workdir=/testbed", "--entrypoint=/bin/sh",
            image, "-c", "sleep infinity"]


class DockerSandbox:
    def __init__(self, image):
        self.image = image
        self.name = "aee-bench-" + uuid.uuid4().hex

    def __enter__(self):
        subprocess.run(docker_args(self.image, self.name), check=True, capture_output=True, timeout=120)
        try:
            details = json.loads(subprocess.check_output(["docker", "inspect", self.name], timeout=20))[0]
            if details["Mounts"] or details["HostConfig"]["NetworkMode"] != "none":
                raise RuntimeError("isolation verification failed")
            self.details = {"image_id": details["Image"], "image": self.image,
                            "mounts": [], "network": "none"}
            return self
        except BaseException:
            self.__exit__()
            raise

    def execute(self, command, timeout=60):
        result = subprocess.run(["docker", "exec", self.name, "bash", "-lc", command],
                                capture_output=True, timeout=timeout)
        return {"exit_code": result.returncode,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace")}

    def stage_workflow(self, root):
        """Copy a strict allowlist of pristine core assets, never controller memory."""
        with tempfile.TemporaryDirectory(prefix="workflow-assets-") as folder:
            target = Path(folder)/"workflow"
            for part in ("scripts/python", "templates"):
                shutil.copytree(Path(root)/".specify"/part, target/".specify"/part,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (target/".specify/memory").mkdir()
            shutil.copyfile(target/".specify/templates/constitution-template.md",
                            target/".specify/memory/constitution.md")
            subprocess.run(["docker", "cp", str(target), self.name+":/workflow"],
                           check=True, capture_output=True, timeout=30)
            result = self.execute("cd /workflow && git init -q && mkdir -p specs")
            if result["exit_code"]:
                raise RuntimeError("workflow staging failed")

    def __exit__(self, *exc):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, timeout=30)
