# DeviceDataHub AI flow

End-to-end Wi-Fi anomaly detection running as Kubernetes workloads:

```text
MQTT over ngrok -> consumer -> TimescaleDB -> Grafana
                                      ^
                         train_1000.json -> train.py -> model.pkl
                                                        |
                                      inference.py -> MQTT alerts
Kubernetes pod logs -> Fluent Bit -> Splunk HEC -> Splunk Web
MQTT message audit -> TimescaleDB -> MQTT monitor :5000
Telemetry records -> TimescaleDB -> Records monitor :6080 / Grafana
```

## Start On Linux

Open a terminal in any existing checkout of the repository and run:

```bash
cd /path/to/devicedatahub-end-to-end
chmod +x scripts/start_cloud.sh
./scripts/start_cloud.sh
```

The launcher supports native Linux and Ubuntu on WSL2. Windows users should
follow the Windows/WSL path in [workshop_prerequistes.md](workshop_prerequistes.md);
native Linux users can follow its separate Ubuntu/Debian path, then continue at
the common setup section.

The launcher finds the project root from its own location, runs
`git pull --ff-only`, and keeps the virtual environment, downloaded Kubernetes
tools, and runtime files inside that checkout. The checkout can be located
anywhere; the launcher does not clone the repository. For a first-time setup,
clone the repository yourself, then run the commands above from that checkout.

`scripts/start_cloud.sh` performs the complete startup sequence:

1. Installs Docker Engine on Ubuntu/Debian if missing and starts it when stopped; other Linux distributions need Docker installed before launch.
2. Creates `.venv` if it does not exist.
3. Activates the virtual environment.
4. Installs `requirements.txt` only when it is new or has changed since the previous launch.
5. Asks whether to enable the local MQTT simulator.
6. Runs `scripts/startup.py` with `values.simulate.yaml` only when enabled.
7. Creates or reuses the `devicedatahub` kind cluster.
8. Builds `devicedatahub-ai-flow:latest`.
9. Loads the image into the kind nodes.
10. Installs or upgrades the `helm/ai-flow` chart.
11. Starts TimescaleDB, Grafana, Splunk, Fluent Bit, the MQTT consumer, and inference pods.
12. Trains the model from `data/train_1000.json` in the inference pod init container.
13. Starts `inference.py` only after training and database readiness succeed.
14. Starts Grafana, TimescaleDB, Splunk, and monitor UI port-forwards.

On first startup, review and explicitly accept the Splunk license and current
General Terms when prompted. After reviewing and accepting them, you can skip
the prompt in an automated run with
`ACCEPT_SPLUNK_TERMS=true ./scripts/start_cloud.sh`. This is an explicit opt-in;
the default remains interactive. Splunk signs in with username `admin` and
password `admin123`. The HEC token is generated and credentials are stored in
`.runtime/splunk-values.json` with owner-only permissions. Keep this file
private; it is ignored by Git and reused for later Helm upgrades.

The launcher prints the Grafana and Splunk URLs, plus `kubectl logs` commands.
Splunk Web is forwarded from local port `4000` to container port `8000`; sign in
as `admin` with password `admin123`.
The provisioned **DeviceDataHub Live Pod Logs** dashboard is available at
`http://localhost:4000/en-US/app/device_datahub_monitor/pod_logs`. It has a Kubernetes
pod filter, defaults to the last 15 minutes, and refreshes the log table every
10 seconds.
The Splunk Enterprise image is resource intensive; a 16 GB RAM laptop and at
least 30 GB free disk space are recommended.
The first startup can take several minutes while large container images are
downloaded and Splunk initializes. Repeat starts skip Python dependency
installation when `requirements.txt` is unchanged; Helm still waits for all
workloads to become ready.

For a quicker rerun when application source has not changed and the local image
already exists, use `SKIP_IMAGE_BUILD=true ./scripts/start_cloud.sh`. Do not use
this after changing application source or the Docker build inputs; a normal run
rebuilds the image.
`admin123` is a weak workshop password; use it only for a local, trusted
development environment and do not expose Splunk outside the laptop. If Splunk
was already initialized with the previous generated password, changing the
local values file does not necessarily change the password in its persistent
data. Sign in with the existing password and change the account password in
Splunk Web to `admin123`.

The startup output also prints two application monitor URLs:

- `http://localhost:5000` shows incoming MQTT messages and published anomaly/status messages, newest first.
- `http://localhost:6080` shows telemetry rows stored in TimescaleDB, newest first; this is the same `public.telemetry` table Grafana reads. The container still listens on `6000`; startup forwards the browser to `6080` because Chromium blocks local port `6000`.

Both pages auto-refresh every 30 seconds, support Last 5 minutes, Last 15
minutes, Last 1 hour, Last 24 hours, and All time filters, and provide
load-older pagination. MQTT message history is stored in
`public.mqtt_messages`; telemetry is stored in `public.telemetry`.
The MQTT page presents message direction, topic, status, and payload. The
telemetry page presents device/radio readings including utilization, signal,
client, retry, and failure fields.

When running the optional Docker Compose stack, the same UI ports are published
directly by the `monitor` service:

```bash
docker compose up --build
```

GitHub CLI is not required for this public HTTPS repository. Git can pull it
without `gh auth login`.

The script supports graphical terminals. In WSL or a headless Linux shell it
runs the port-forwards in the background and writes their logs and PIDs under
`.runtime/`.

Answer `Yes` to the simulator prompt to deploy Mosquitto and `simulator.py` as
Kubernetes workloads. The simulator publishes randomized normal and anomaly
telemetry to the same topic consumed by the existing consumer. Answer `No` to
keep the ngrok MQTT flow unchanged. See [README.simulate.md](README.simulate.md)
for simulator settings.

Fluent Bit collects application pod logs from the `devicedatahub` namespace in
both MQTT modes. Splunk and Fluent Bit logs are excluded to prevent a feedback
loop. In Splunk Web, open **Search & Reporting**, set the time range to **Last
15 minutes** (or **All time**), and run one of these searches:

```spl
index=main
```

Filter by workload text:

```spl
index=main "ai-flow-inference"
index=main "ai-flow-consumer"
index=main "ai-flow-simulator"
```

The simulator search returns events when simulation mode is enabled. To filter
by pod metadata, use:

```spl
index=main kubernetes.namespace_name=devicedatahub kubernetes.pod_name="ai-flow-inference*"
```

## Grafana And Database Access

Grafana is available at:

```text
http://localhost:3000
```

Default Grafana credentials:

```text
Username: admin
Password: admin
```

The dashboard is imported from `grafana/dashboard.json` and uses the
provisioned `TimescaleDB` datasource.

TimescaleDB is forwarded to:

```text
Host: localhost
Port: 5433
Database: telemetry
Username: postgres
Password: postgres
```

The equivalent manual commands are:

```bash
kubectl port-forward service/ai-flow-grafana 3000:3000 \
  --namespace=devicedatahub
```

```bash
kubectl port-forward service/ai-flow-timescaledb 5433:5432 \
  --namespace=devicedatahub
```

Forward the monitor pages manually if needed:

```bash
kubectl port-forward service/ai-flow-monitor 5000:5000 6080:6000 \
  --namespace=devicedatahub
```

Keep each command running in its own terminal. In VS Code, configure a
PostgreSQL/TimescaleDB extension with host `localhost`, port `5433`, database
`telemetry`, user `postgres`, and password `postgres`.

Splunk Web is available at `http://localhost:4000`. Use username `admin` and
password `admin123`.

Open the default live pod-log dashboard at
`http://localhost:4000/en-US/app/device_datahub_monitor/pod_logs`. Choose a pod from
the **Kubernetes pod** dropdown or select **All pods**. The dashboard defaults
to the last 15 minutes and refreshes the log table every 10 seconds.

The manual Splunk Web forward is:

```bash
kubectl port-forward service/ai-flow-splunk 4000:8000 --namespace=devicedatahub
```

## Verify The Pods

Use the namespace explicitly:

```bash
kubectl get pods -n devicedatahub -o wide
kubectl get services -n devicedatahub
```

Follow the consumer and inference logs:

```bash
kubectl logs -n devicedatahub deploy/ai-flow-consumer -f
kubectl logs -n devicedatahub deploy/ai-flow-inference -c inference -f
kubectl logs -n devicedatahub deploy/ai-flow-inference -c train-model --tail=200
kubectl logs -n devicedatahub daemonset/ai-flow-fluent-bit -f
```

The expected flow is:

```text
consumer: Connected to broker
consumer: Telemetry table ready
consumer: Stored Wi-Fi telemetry rows
train-model: Model successfully saved to model_artifacts/model.pkl
inference: Model loaded
inference: TimescaleDB connection established
inference: MQTT connected
inference: Published anomaly message
```

Anomaly messages are published to:

```text
wifi/alerts/{device_id}/anomaly
wifi/alerts/{device_id}/status
wifi/alerts/summary
```

Messages include the reason code, training-aligned scenario, layman
explanation, recommended action, metrics, and publish result.

## Container Files At Repository Root

The Docker files intentionally remain at the repository root, which is the
standard Docker build context:

```text
Dockerfile          image definition
.dockerignore       image build exclusions
docker-compose.yml  optional local Compose orchestration
requirements.txt    image dependency manifest
```

Application source is separated under `src/`, operational configuration under
`config/`, and lifecycle scripts under `scripts/`.

## Configuration

Copy the example environment file for reference:

```bash
cp config/.env.example .env
```

For Kubernetes, use a private Helm values file for broker and credential
settings. Do not commit `.env` or private values files.

The main settings are:

```yaml
mqtt:
  host: 0.tcp.in.ngrok.io
  port: 19023
  topic: weh-device/network
alerts:
  host: 0.tcp.in.ngrok.io
  port: 19023
  baseTopic: wifi/alerts
database:
  name: telemetry
  user: postgres
  password: postgres
splunk:
  enabled: true
  storage: 10Gi
```

## Manual Kubernetes Commands

The startup script generates private Splunk password and HEC token values after
explicit terms acceptance. For manual Helm deployment, provide a private values
file with `splunk.acceptLicense: true`, `splunk.adminPassword`, and
`splunk.hecToken`; do not commit that file.

Build and load the image:

```bash
docker build -t devicedatahub-ai-flow:latest .
mkdir -p .runtime/kind-tmp
docker save --output .runtime/kind-tmp/devicedatahub-ai-flow.tar devicedatahub-ai-flow:latest
kind load image-archive .runtime/kind-tmp/devicedatahub-ai-flow.tar --name devicedatahub
rm .runtime/kind-tmp/devicedatahub-ai-flow.tar
```

The monitor UI runs in the `ai-flow-monitor` Deployment using the same
application image and reads the `mqtt_messages` and `telemetry` tables from
TimescaleDB.

Deploy the chart:

```bash
helm upgrade --install ai-flow helm/ai-flow \
  --namespace devicedatahub \
  --create-namespace \
  --set image.repository=devicedatahub-ai-flow \
  --set image.tag=latest \
  --values .runtime/splunk-values.json \
  --wait \
  --timeout 20m
```

## Shutdown

After validation is complete, run the cleanup command:

```bash
python3 scripts/shutdown.py
```

This stops the port-forward processes, uninstalls the Helm release, deletes the
namespace, deletes the kind cluster, removes the local image, and removes the
project virtual environment. The local `.runtime/splunk-values.json` file is
preserved so the generated Splunk login and accepted-terms setting are reused
on the next start.

Preserve selected local resources when needed:

```bash
python3 scripts/shutdown.py --keep-cluster
python3 scripts/shutdown.py --keep-image
python3 scripts/shutdown.py --keep-venv
```

## Project Files

- [src/consumer](src/consumer): MQTT consumer, configuration, storage, and client
- [src/ai](src/ai): training, inference, database access, model I/O, publisher, and simulator
- [config](config): environment and simulator broker configuration
- [data/train_1000.json](data/train_1000.json): canonical training dataset
- [model_artifacts](model_artifacts): trained model storage
- [scripts/start_cloud.sh](scripts/start_cloud.sh): Linux/WSL startup and port forwarding
- [scripts/startup.py](scripts/startup.py): kind, kubectl, Helm, image, and deployment bootstrap
- [scripts/shutdown.py](scripts/shutdown.py): process, Kubernetes, and local cleanup
- [helm/ai-flow](helm/ai-flow): complete Kubernetes chart
- [ARCHITECTURE.md](ARCHITECTURE.md): component and data-flow diagram
- [DESIGN_REQUIREMENTS.md](DESIGN_REQUIREMENTS.md): application requirements and acceptance criteria
- [README.simulate.md](README.simulate.md): local MQTT simulator operation
