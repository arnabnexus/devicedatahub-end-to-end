# DeviceDataHub Workshop Prerequisites

This guide prepares a Windows laptop running Ubuntu on WSL2 to run the
DeviceDataHub AI flow entirely in Kubernetes.

At the end, you will be in a WSL terminal inside the repository and ready to
run:

```bash
./scripts/start_cloud.sh
```

The flow starts an MQTT consumer, TimescaleDB, Grafana, Splunk log search,
live MQTT/telemetry monitor pages, model training, inference, and optional local
MQTT simulation.

## 1. Hardware and Windows prerequisites

### Required hardware

- 64-bit Windows 10 version 2004 or newer, or Windows 11
- CPU virtualization support: Intel VT-x or AMD-V
- At least 16 GB RAM recommended for Splunk Enterprise and the Kubernetes workloads
- At least 30 GB free disk space recommended
- Administrator access to Windows
- Internet access for Windows features, Ubuntu packages, GitHub, and Kubernetes images

### Enable virtualization in BIOS/UEFI

Virtualization must be enabled before WSL2 can run reliably.

1. Save your work and restart the laptop.
2. Enter BIOS/UEFI during boot. Common keys are `F2`, `F10`, `F12`, `Delete`, or `Esc`.
3. Open a menu named **Advanced**, **Security**, **CPU Configuration**, or **Virtualization**.
4. Enable the matching setting:
   - Intel: `Intel Virtualization Technology`, `VT-x`, or `Intel VT-d`
   - AMD: `SVM Mode`, `AMD-V`, or `Secure Virtual Machine`
5. Choose **Save and Exit**.
6. Let Windows boot normally.

The exact menu names depend on the laptop manufacturer. If Windows Task
Manager already shows **Virtualization: Enabled**, this step is complete.

### Verify virtualization in Windows

Open **PowerShell as Administrator** and run:

```powershell
systeminfo.exe
```

Look near the Hyper-V requirements. Virtualization-based requirements should
not be reported as unavailable.

You can also check:

1. Press `Ctrl+Shift+Esc`.
2. Open **Performance**.
3. Select **CPU**.
4. Confirm **Virtualization: Enabled**.

## 2. Enable Windows WSL features

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Restart Windows if prompted.

If WSL is already installed, explicitly enable the required Windows features:

```powershell
 dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
 dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

Restart Windows after enabling the features:

```powershell
Restart-Computer
```

After Windows restarts, set WSL2 as the default:

```powershell
wsl --set-default-version 2
wsl --update
wsl --status
```

Expected output should identify WSL2 as the default version.

## 3. Install Ubuntu for WSL

List available distributions:

```powershell
wsl --list --online
```

Install Ubuntu:

```powershell
wsl --install -d Ubuntu
```

If Ubuntu is already installed, list the installed distributions:

```powershell
wsl --list --verbose
```

The Ubuntu distribution should show:

```text
VERSION 2
```

If it shows version 1, convert it:

```powershell
wsl --set-version Ubuntu 2
```

Launch Ubuntu from the Start menu or PowerShell:

```powershell
wsl -d Ubuntu
```

## 4. Complete the first Ubuntu login

On the first Ubuntu launch, create a Linux username and password.

These credentials are separate from your Windows account. The password is used
for `sudo` commands and will not be displayed while typing.

After login, confirm that you are inside Linux:

```bash
whoami
pwd
cat /etc/os-release
```

You should see Ubuntu details and a Linux home directory similar to:

```text
/home/<your-linux-user>
```

## 5. Prepare Ubuntu packages

The project startup script installs missing Linux prerequisites automatically.
Install the base packages once so the workshop starts predictably:

```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y \
  git \
  curl \
  ca-certificates \
  python3 \
  python3-venv \
  python3-pip \
  docker.io
```

Verify the tools:

```bash
git --version
python3 --version
python3 -m venv --help >/dev/null && echo "python venv support: OK"
docker --version
```

## 6. Configure Docker Engine inside WSL

The workshop runs Ubuntu's Docker Engine directly inside WSL. No Docker Desktop
installation is needed. The launcher installs the `docker.io` package if it is
missing and attempts to start the daemon.

Enable systemd in WSL so Docker starts reliably. In Ubuntu, create or edit
`/etc/wsl.conf`:

```bash
sudo nano /etc/wsl.conf
```

Add:

```ini
[boot]
systemd=true
```

Save with `Ctrl+O`, press Enter, then exit with `Ctrl+X`. Close Ubuntu and run
this from PowerShell:

```powershell
wsl --shutdown
```

Reopen Ubuntu and verify systemd is running:

```bash
ps -p 1 -o comm=
```

Expected output is `systemd`. Start Docker and allow your Linux user to access
the daemon:

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Close and reopen Ubuntu for the group change to take effect. The launcher can
also start Docker automatically on later runs.

## 7. Verify WSL networking and Docker

Run these commands in Ubuntu:

```bash
printf 'Linux user: '; whoami
printf 'Linux home: '; printf '%s\n' "$HOME"
printf 'WSL IP: '; hostname -I
git --version
python3 --version
docker version
docker info >/dev/null && echo "Docker engine: OK"
docker run --rm hello-world
```

The client and server sections should both be present in `docker version`. The
test container confirms that Docker can pull and run images through WSL.

## 8. Configure Git identity

Configure a Git identity for local commits if this laptop will be used for
workshop changes:

```bash
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

GitHub CLI is optional. This project uses a public HTTPS repository, so cloning
does not require `gh auth login`.

For private repositories, install and authenticate GitHub CLI separately:

```bash
sudo apt-get install -y gh
gh auth login
```

## 9. Get the repository

Choose any location inside the WSL Linux filesystem, then clone the project
once. The launcher itself does not clone; on each run it pulls the latest
changes from the checkout's configured upstream.

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
```

Clone the repository:

```bash
git clone https://github.com/arnabnexus/devicedatahub-end-to-end.git
cd devicedatahub-end-to-end
```

Verify the repository:

```bash
git remote -v
git status
find src config scripts helm data -maxdepth 2 -type f | sort
```

The important layout is:

```text
Dockerfile
.dockerignore
docker-compose.yml
requirements.txt
src/consumer/
src/ai/
config/
scripts/
helm/ai-flow/
data/
```

Docker files and `requirements.txt` intentionally remain at the repository root
because the repository root is the Docker build context.

## 10. Make the Linux launcher executable

Run:

```bash
chmod +x scripts/start_cloud.sh
```

Confirm the script is executable:

```bash
ls -l scripts/start_cloud.sh
bash -n scripts/start_cloud.sh
```

The mode should contain `x`, for example:

```text
-rwxr-xr-x
```

## 11. Verify the startup dependencies before launch

Run this final preflight:

```bash
command -v git
command -v python3
command -v docker
command -v curl
python3 -m venv --help >/dev/null && echo "venv: OK"
docker info >/dev/null && echo "Docker Engine: OK"
git ls-remote https://github.com/arnabnexus/devicedatahub-end-to-end.git HEAD
```

If the last command prints a commit hash, GitHub access is working.

## 12. Start the workshop flow

You are now in the repository and ready to run:

```bash
./scripts/start_cloud.sh
```

The launcher will:

1. Pull the existing checkout with `git pull --ff-only` (the checkout may be located anywhere).
2. Create and activate `.venv` inside the checkout.
3. Install Python requirements only when the requirements manifest is new or has changed.
4. Install Docker Engine inside Ubuntu if missing and start it if stopped.
5. Download `kind`, `kubectl`, and Helm into `.local/bin` inside the checkout when needed.
6. Ask whether to enable the local MQTT simulator.
7. Create or repair the kind cluster.
8. Build and load the application image.
9. Deploy the Helm release.
10. Train the model in the inference init container.
11. Start Splunk Enterprise and Fluent Bit for namespace pod logs.
12. Start the MQTT/TimescaleDB monitor UI and application workloads.
13. Start local port-forwards: Splunk `4000`, MQTT monitor `5000`, and telemetry monitor host port `6080` to container port `6000`.
14. Print Kubernetes log commands and Splunk searches.

On first startup, read the Splunk license and current General Terms at
https://www.splunk.com/en_us/legal/splunk-general-terms.html. Normally the
installer requires you to type `YES` to confirm acceptance. After reviewing and
accepting the terms, automation can use
`ACCEPT_SPLUNK_TERMS=true ./scripts/start_cloud.sh` to skip the prompt; the
default remains interactive. Splunk login is username `admin`, password
`admin123`. The HEC token is stored in `.runtime/splunk-values.json`; keep this
file private.

At the simulator prompt:

```text
Enable local MQTT simulator and broker? [y/N]:
```

- Enter `y` or `yes` to start Mosquitto and randomized simulated telemetry.
- Press Enter or enter `n` to use the configured ngrok broker.

Grafana will be available at:

```text
http://localhost:3000
```

TimescaleDB will be available to local tools at:

```text
Host: localhost
Port: 5433
Database: telemetry
User: postgres
Password: postgres
```

Splunk Web is available at `http://localhost:4000` with username `admin` and
password `admin123`.
This is a weak local-workshop password: keep the port-forward local and do not
expose the service to an untrusted network. If Splunk was already initialized
with an earlier password, sign in with that existing password and change it in
Splunk Web; the persistent Splunk data volume can retain its previous password.

The provisioned live pod-log dashboard is at
`http://localhost:4000/app/device_datahub_monitor/pod_logs`. Choose a Kubernetes
pod or **All pods** from the pod filter. It defaults to the last 15 minutes and
refreshes the log table every 10 seconds.

The application monitor pages are:

```text
MQTT incoming and published messages: http://localhost:5000
TimescaleDB telemetry records:         http://localhost:6080 (container port 6000)
```

Both refresh every 30 seconds and provide Last 5 minutes, Last 15 minutes,
Last 1 hour, Last 24 hours, and All time filters. Results are newest-first;
select **Load older records** to page through more rows. MQTT messages are
audited in `public.mqtt_messages`; the records page reads `public.telemetry`,
the same table used by Grafana.

The MQTT page shows direction, topic, delivery status, and payload for incoming
telemetry and published anomaly/status events. The telemetry page shows recent
device/radio measurements such as channel utilization, RSSI, client counts, and
retry/failure counts.

For a quicker rerun when application source has not changed and the local image
already exists, run `SKIP_IMAGE_BUILD=true ./scripts/start_cloud.sh`. Use the
normal command after source or Docker build-input changes so the image is rebuilt.

## 13. Verify after startup

In another WSL terminal:

```bash
cd /path/to/devicedatahub-end-to-end
export PATH="$PWD/.local/bin:$PATH"

kubectl get pods -n devicedatahub -o wide
kubectl get services -n devicedatahub
kubectl logs -n devicedatahub deploy/ai-flow-consumer --tail=50
kubectl logs -n devicedatahub deploy/ai-flow-inference -c inference --tail=50
kubectl logs -n devicedatahub daemonset/ai-flow-fluent-bit --tail=50
```

In Splunk Search & Reporting, choose **Last 15 minutes** or **All time** and
search all project logs with:

```spl
index=main
```

Filter logs by workload text:

```spl
index=main "ai-flow-inference"
index=main "ai-flow-consumer"
index=main "ai-flow-simulator"
```

The simulator search returns events when simulation mode is enabled. You can
also filter by Kubernetes pod metadata:

```spl
index=main kubernetes.namespace_name=devicedatahub kubernetes.pod_name="ai-flow-inference*"
```

Expected pod state:

```text
Running
1/1 Ready
```

Expected log milestones:

```text
Telemetry table ready
Stored wifi telemetry rows
Model loaded
TimescaleDB connection established
MQTT connected
Published anomaly message
```

## 14. Shutdown after the workshop

When validation is complete, stop all local port-forwards and Kubernetes
resources:

```bash
cd /path/to/devicedatahub-end-to-end
python3 scripts/shutdown.py
```

This removes the Helm release, namespace, kind cluster, Docker image, project
virtual environment, simulator resources, and background port-forward
processes. It preserves `.runtime/splunk-values.json`, so your generated Splunk
admin password remains available and the startup terms prompt is not repeated.

## Troubleshooting

### Virtualization is disabled

Return to BIOS/UEFI and enable Intel VT-x or AMD SVM/AMD-V. Then restart
Windows and verify virtualization in Task Manager.

### WSL reports version 1

From PowerShell:

```powershell
wsl --set-default-version 2
wsl --set-version Ubuntu 2
```

### Docker permission denied

Ensure the current Linux user is in the `docker` group:

```bash
sudo usermod -aG docker "$USER"
```

Close and reopen Ubuntu, then verify:

```bash
docker info
```

### Docker daemon cannot start

Check the service and daemon log:

```bash
sudo systemctl status docker --no-pager
cat /tmp/devicedatahub-dockerd.log
```

### Splunk has no events

Check Fluent Bit and Splunk pod status/logs:

```bash
kubectl get pods -n devicedatahub -o wide
kubectl logs -n devicedatahub daemonset/ai-flow-fluent-bit --tail=100
kubectl logs -n devicedatahub deploy/ai-flow-splunk --tail=100
```

Confirm the Fluent Bit pod can reach the Splunk HEC service and that the
namespace filter is `devicedatahub`. In Splunk, select the `main` index.

### Git clone fails

Check connectivity:

```bash
git ls-remote https://github.com/arnabnexus/devicedatahub-end-to-end.git HEAD
```

### Git pull cannot update the checkout

The launcher uses `git pull --ff-only`, so it stops rather than creating a merge
commit if the local branch has diverged. Resolve or commit local changes, then
rerun from any directory containing the project checkout. The launcher must be
run from a Git checkout; it never clones the repository.

```bash
git status
git pull --ff-only
./scripts/start_cloud.sh
```

### Grafana shows no data

Use a recent time range such as **Last 15 minutes**, then inspect:

```bash
kubectl logs -n devicedatahub deploy/ai-flow-consumer --tail=100
kubectl logs -n devicedatahub deploy/ai-flow-grafana --tail=100
```

The Grafana datasource must use:

```text
Host: ai-flow-timescaledb:5432
Database: telemetry
User: postgres
Password: postgres
```
