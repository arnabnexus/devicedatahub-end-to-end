# Local MQTT simulation

The simulation profile is opt-in. It starts Mosquitto inside Kubernetes and a
`simulator.py` pod that publishes randomized normal and anomalous Wi-Fi payloads
to the same topic consumed by `consumer.py`.

Use `./scripts/start_linux.sh` from the repository root and answer `Yes` when asked to enable local simulation.
Answering `No` preserves the normal ngrok MQTT flow.

Simulation resources:

```text
ai-flow-mqtt-broker  MQTT Service on 1883
ai-flow-simulator    Random telemetry publisher
consumer             Existing telemetry consumer
```

The simulator publishes:

```text
weh-device/network
```

The consumer writes those messages to TimescaleDB, and inference publishes
anomaly explanations to:

```text
wifi/alerts/{device_id}/anomaly
wifi/alerts/{device_id}/status
wifi/alerts/summary
```

The same Fluent Bit DaemonSet collects broker, simulator, consumer, inference,
and other application workload logs in the `devicedatahub` namespace and forwards
them to Splunk. Splunk and Fluent Bit logs are excluded to prevent a feedback
loop. Open **Search & Reporting** in Splunk Web at `http://localhost:4000`, set
the time range to **Last 15 minutes** (or **All time**), and search:

```spl
index=main kubernetes.namespace_name=devicedatahub
```

Filter by simulator workload text:

```spl
index=main "ai-flow-simulator"
```

Sign in to Splunk Web as `admin`. Retrieve the generated password from the
repository root with:

```bash
python3 -c 'import json; print(json.load(open(".runtime/splunk-values.json"))["splunk"]["adminPassword"])'
```

To isolate simulated publisher logs, filter by pod:

```spl
index=main kubernetes.namespace_name=devicedatahub kubernetes.pod_name=ai-flow-simulator*
```

Override simulator settings in `helm/ai-flow/values.simulate.yaml`:

```yaml
simulator:
  intervalSeconds: 5
  anomalyRate: 0.35
```

Run `python3 scripts/shutdown.py` to remove the broker, simulator, pods, Helm release,
namespace, kind cluster, image, and port-forward processes. The generated Splunk
credentials in `.runtime/splunk-values.json` are preserved for the next startup.
