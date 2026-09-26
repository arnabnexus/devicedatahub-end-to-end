#!/usr/bin/env python3
"""Bootstrap the complete DeviceDataHub AI flow on a local kind cluster."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import uuid
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
    requirements = ROOT / "requirements.txt"
    requirements_hash = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = VENV / ".requirements.sha256"
    if not stamp.exists() or stamp.read_text(encoding="utf-8").strip() != requirements_hash:
        print("Installing Python requirements (manifest changed or environment is new).", flush=True)
        run([str(python), "-m", "pip", "install", "-r", "requirements.txt"])
        stamp.write_text(requirements_hash + "\n", encoding="utf-8")
    else:
        print("Python requirements unchanged; skipping dependency installation.", flush=True)
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


def install_stack(
    tools: dict[str, str],
    *,
    rebuild: bool,
    values_file: str | None,
    splunk_values: Path,
) -> None:
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
        "20m",
    ]
    if values_file:
        command.extend(["--values", values_file])
    command.extend(["--values", str(splunk_values)])
    run(command)


def splunk_values_file(*, accept_terms: bool = False) -> Path:
    values_path = ROOT / ".runtime" / "splunk-values.json"
    values_path.parent.mkdir(parents=True, exist_ok=True)
    if values_path.exists():
        values = json.loads(values_path.read_text(encoding="utf-8"))
        splunk = values.get("splunk", {})
        if splunk.get("acceptLicense") is True and splunk.get("adminPassword") and splunk.get("hecToken"):
            return values_path
        raise SystemExit(f"Incomplete Splunk credentials file: {values_path}")

    if not accept_terms:
        print(
            "Splunk Enterprise requires accepting its license and current General Terms. "
            "Review https://www.splunk.com/en_us/legal/splunk-general-terms.html before continuing.",
            flush=True,
        )
        if not sys.stdin.isatty() or input("Type YES to accept Splunk terms and continue: ").strip() != "YES":
            raise SystemExit("Splunk terms were not accepted; startup cancelled.")
    else:
        print("Splunk terms auto-accept enabled; ensure you reviewed and accept the license and General Terms.", flush=True)

    values = {
        "splunk": {
            "acceptLicense": True,
            "adminPassword": "admin123",
            "hecToken": str(uuid.uuid4()),
        }
    }
    descriptor = os.open(values_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as credentials_file:
        json.dump(values, credentials_file, indent=2)
        credentials_file.write("\n")
    print(f"Saved local Splunk credentials in {values_path} (permissions 600).", flush=True)
    return values_path


def show_logs(kubectl: str) -> None:
    run([kubectl, "get", "pods", "-n", NAMESPACE, "-o", "wide"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the DeviceDataHub AI flow on Kubernetes")
    parser.add_argument("--no-build", action="store_true", help="Reuse the local image")
    parser.add_argument(
        "--accept-splunk-terms",
        action="store_true",
        help="Skip the prompt; use only after reviewing and accepting Splunk terms",
    )
    parser.add_argument("--values", help="Private Helm values file for broker and database settings")
    parser.add_argument("--delete-cluster", action="store_true", help="Delete the kind cluster and exit")
    args = parser.parse_args()

    ensure_venv()
    tools = ensure_tools()
    if args.delete_cluster:
        if KIND_CLUSTER in output([tools["kind"], "get", "clusters"]).splitlines():
            run([tools["kind"], "delete", "cluster", "--name", KIND_CLUSTER])
        return 0

    if args.no_build and subprocess.run(
        [tools["docker"], "image", "inspect", IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        raise SystemExit(f"Cannot use --no-build because local image {IMAGE} is missing. Run once without --no-build.")

    credentials_path = splunk_values_file(accept_terms=args.accept_splunk_terms)
    ensure_cluster(tools["kind"], tools["docker"])
    install_stack(
        tools,
        rebuild=not args.no_build,
        values_file=args.values,
        splunk_values=credentials_path,
    )
    show_logs(tools["kubectl"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f"Startup command failed with exit code {error.returncode}.", file=sys.stderr)
        raise SystemExit(error.returncode) from error
