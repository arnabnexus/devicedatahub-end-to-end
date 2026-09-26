#!/usr/bin/env python3
"""Bootstrap the complete DeviceDataHub AI flow on a local kind cluster."""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
LOCAL_BIN = ROOT / ".local" / "bin"
KIND_CLUSTER = "devicedatahub"
NAMESPACE = "devicedatahub"
IMAGE = "devicedatahub-ai-flow:latest"


def command_path(name: str) -> str | None:
    local_path = LOCAL_BIN / name
    return str(local_path) if local_path.exists() else shutil.which(name)


def run(
    command: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=check, input=input_text, text=True, env=env)


def output(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def download(url: str, destination: Path) -> None:
    print(f"Downloading {destination.name}...", flush=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_venv() -> None:
    python = VENV / "bin" / "python"
    if not python.exists():
        run([sys.executable, "-m", "venv", str(VENV)])
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "-r", "requirements.txt"])
    print(f"Virtual environment ready: {VENV}", flush=True)
    print(f"Activate it in your shell with: source {VENV}/bin/activate", flush=True)


def ensure_tools() -> dict[str, str]:
    docker = command_path("docker")
    if docker is None:
        raise SystemExit("Docker is required. Install Docker Engine and start it first.")
    if subprocess.run([docker, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise SystemExit("Docker is installed but not running.")

    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    kind = command_path("kind")
    if kind is None:
        kind_path = LOCAL_BIN / "kind"
        download("https://kind.sigs.k8s.io/dl/v0.30.0/kind-linux-amd64", kind_path)
        kind = str(kind_path)

    kubectl = command_path("kubectl")
    if kubectl is None:
        version = urllib.request.urlopen("https://dl.k8s.io/release/stable.txt").read().decode().strip()
        kubectl_path = LOCAL_BIN / "kubectl"
        download(f"https://dl.k8s.io/release/{version}/bin/linux/amd64/kubectl", kubectl_path)
        kubectl = str(kubectl_path)

    helm = command_path("helm")
    if helm is None:
        archive = ROOT / ".helm.tgz"
        download("https://get.helm.sh/helm-v3.19.0-linux-amd64.tar.gz", archive)
        with tarfile.open(archive, "r:gz") as bundle:
            member = bundle.getmember("linux-amd64/helm")
            member.name = "helm"
            bundle.extract(member, LOCAL_BIN)
        archive.unlink()
        helm = str(LOCAL_BIN / "helm")

    return {"docker": docker, "kind": kind, "kubectl": kubectl, "helm": helm}


def cluster_container_running(docker: str) -> bool:
    result = subprocess.run(
        [docker, "inspect", "-f", "{{.State.Running}}", f"{KIND_CLUSTER}-control-plane"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_cluster(kind: str, docker: str) -> None:
    clusters = output([kind, "get", "clusters"]).splitlines()
    if KIND_CLUSTER not in clusters:
        run([kind, "create", "cluster", "--name", KIND_CLUSTER, "--wait", "5m"])
    elif not cluster_container_running(docker):
        print(
            f"Existing kind cluster '{KIND_CLUSTER}' is stopped; recreating it.",
            flush=True,
        )
        run([kind, "delete", "cluster", "--name", KIND_CLUSTER], check=False)
        run([kind, "create", "cluster", "--name", KIND_CLUSTER, "--wait", "5m"])
    else:
        print(f"Using existing kind cluster: {KIND_CLUSTER}", flush=True)


def install_stack(tools: dict[str, str], *, rebuild: bool, values_file: str | None) -> None:
    if rebuild:
        run([tools["docker"], "build", "-t", IMAGE, "."])
    kind_tmp = ROOT / ".runtime" / "kind-tmp"
    kind_tmp.mkdir(parents=True, exist_ok=True)
    kind_env = os.environ.copy()
    kind_env["TMPDIR"] = str(kind_tmp)
    image_archive = kind_tmp / "devicedatahub-ai-flow.tar"
    try:
        run([tools["docker"], "save", "--output", str(image_archive), IMAGE])
        run(
            [tools["kind"], "load", "image-archive", str(image_archive), "--name", KIND_CLUSTER],
            env=kind_env,
        )
    finally:
        image_archive.unlink(missing_ok=True)
    namespace_yaml = subprocess.check_output(
        [tools["kubectl"], "create", "namespace", NAMESPACE, "--dry-run=client", "-o", "yaml"],
        cwd=ROOT,
        text=True,
    )
    run([tools["kubectl"], "apply", "-f", "-"], input_text=namespace_yaml)
    command = [
        tools["helm"],
        "upgrade",
        "--install",
        "ai-flow",
        "helm/ai-flow",
        "--namespace",
        NAMESPACE,
        "--set",
        "image.repository=devicedatahub-ai-flow",
        "--set",
        "image.tag=latest",
        "--wait",
        "--timeout",
        "10m",
    ]
    if values_file:
        command.extend(["--values", values_file])
    run(command)


def show_logs(kubectl: str) -> None:
    run([kubectl, "get", "pods", "-n", NAMESPACE, "-o", "wide"])
    print(f"Grafana: http://localhost:3000 (after port-forwarding is started)", flush=True)
    print("Kubernetes log commands:", flush=True)
    print(f"  {kubectl} logs -n {NAMESPACE} -l app.kubernetes.io/instance=ai-flow --all-containers=true --max-log-requests=20 --prefix --tail=100 -f", flush=True)
    print(f"  {kubectl} logs -n {NAMESPACE} deploy/ai-flow-consumer --all-containers=true --tail=100 -f", flush=True)
    print(f"  {kubectl} logs -n {NAMESPACE} deploy/ai-flow-inference -c inference --tail=100 -f", flush=True)
    print(f"  {kubectl} logs -n {NAMESPACE} deploy/ai-flow-inference -c train-model --tail=200", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the DeviceDataHub AI flow on Kubernetes")
    parser.add_argument("--no-build", action="store_true", help="Reuse the local image")
    parser.add_argument("--values", help="Private Helm values file for broker and database settings")
    parser.add_argument("--delete-cluster", action="store_true", help="Delete the kind cluster and exit")
    args = parser.parse_args()

    ensure_venv()
    tools = ensure_tools()
    if args.delete_cluster:
        if KIND_CLUSTER in output([tools["kind"], "get", "clusters"]).splitlines():
            run([tools["kind"], "delete", "cluster", "--name", KIND_CLUSTER])
        return 0

    ensure_cluster(tools["kind"], tools["docker"])
    install_stack(tools, rebuild=not args.no_build, values_file=args.values)
    show_logs(tools["kubectl"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f"Startup command failed with exit code {error.returncode}.", file=sys.stderr)
        raise SystemExit(error.returncode) from error
