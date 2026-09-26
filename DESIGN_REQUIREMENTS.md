# DeviceDataHub AI design requirements

## 1. Purpose

Provide an end-to-end Wi-Fi telemetry and anomaly-detection system that can be
started on a Linux workstation, run entirely in Kubernetes pods, expose
Grafana and Splunk interfaces, collect pod logs, and publish actionable anomaly
context over MQTT.

## 2. Functional requirements

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| FR-01 | Consume MQTT telemetry | Consumer connects to the configured ngrok broker and subscribes to `weh-device/network` or the configured topic. |
| FR-02 | Validate Wi-Fi payloads | Invalid JSON and non-Wi-Fi payloads are ignored without terminating the consumer. |
| FR-03 | Persist telemetry | Valid radio rows are normalized and stored in `public.telemetry` in TimescaleDB. |
| FR-04 | Train the model | Inference initialization trains on `data/train_1000.json` and writes `model_artifacts/model.pkl`. |
| FR-05 | Run inference | Inference polls recent telemetry, scores each radio, and applies the configured alert threshold. |
| FR-06 | Explain anomalies | Every published anomaly contains a reason code, scenario, plain-language explanation, and recommended action. |
| FR-07 | Publish alerts | Anomaly, status, and summary payloads are published to the configured MQTT topics. |
| FR-08 | Provision Grafana | Grafana starts with the TimescaleDB datasource and dashboard JSON imported automatically. |
| FR-09 | Expose local access | Linux startup forwards Grafana to `localhost:3000`, TimescaleDB to `localhost:5433`, and Splunk Web to `localhost:4000`. |
| FR-10 | Clean up | `scripts/shutdown.py` stops port-forwards and removes the Helm release, namespace, kind cluster, image, and venv by default. |
| FR-11 | Collect Kubernetes logs | Fluent Bit forwards application pod logs in `devicedatahub` to Splunk HEC with namespace, pod, and container metadata, including simulator pods; it excludes Splunk and itself to avoid feedback. |
| FR-12 | Expose Splunk search | Linux startup forwards Splunk Web to `http://localhost:4000`; events are searchable in the `main` index. |
| FR-13 | Inspect MQTT traffic | A live-refresh UI on `http://localhost:5000` lists incoming messages and published anomaly/status messages from TimescaleDB, newest first, with time filters. |
| FR-14 | Inspect telemetry records | A UI on `http://localhost:6080` lists TimescaleDB telemetry records newest first with time presets and pagination (container port 6000). |

## 3. Non-functional requirements

| ID | Requirement | Acceptance criteria |
| --- | --- | --- |
| NFR-01 | Reproducible startup | `./scripts/start_linux.sh` creates the venv, installs requirements, builds the image, deploys Helm, and starts forwarding. |
| NFR-02 | Kubernetes-only application runtime | Consumer, database, Grafana, training init, and inference run as Kubernetes workloads. |
| NFR-03 | Resilient database startup | Database readiness probes, wait init containers, and inference connection retries handle PostgreSQL startup delays. |
| NFR-04 | Observable operation | Pod status, consumer logs, training logs, inference logs, and port-forward logs are available through documented commands and Splunk searches. |
| NFR-05 | Credential hygiene | Splunk terms are explicitly accepted; generated Splunk credentials are owner-only local values and are not committed. |
| NFR-06 | Single source of truth | Root Docker build files, `src/`, `config/`, `scripts/`, Helm chart, training dataset, and lifecycle scripts define the supported flow. |
| NFR-07 | Shared telemetry visibility | The records UI reads the same `public.telemetry` table used by Grafana; MQTT history is persisted in `public.mqtt_messages`. |

## 4. Operational interfaces

### Grafana

```text
URL: http://localhost:3000
Username: admin
Password: admin by default
```

### TimescaleDB

```text
Host: localhost
Port: 5433
Database: telemetry
User: postgres
Password: postgres by default
Table: public.telemetry
```

### Splunk

```text
URL: http://localhost:4000
Username: admin
Password: admin123 (local workshop default)
Index: main
Example search: index=main kubernetes.namespace_name=devicedatahub
```

### Application monitors

```text
MQTT messages: http://localhost:5000
TimescaleDB records: http://localhost:6080 (container port 6000)
Refresh: every 30 seconds
Time ranges: 5 minutes, 15 minutes, 1 hour, 24 hours, or all time
Ordering: newest first, with load-older pagination
```

The HEC token is stored in the private `.runtime/splunk-values.json` file.

### MQTT output

```text
wifi/alerts/{device_id}/anomaly
wifi/alerts/{device_id}/status
wifi/alerts/summary
```

## 5. Anomaly reason codes

| Code | Scenario | Recommended response |
| --- | --- | --- |
| `SEVERE_CONGESTION` | Severe congestion | Move the radio or clients to a cleaner channel. |
| `SEVERE_INTERFERENCE` | Severe interference | Investigate nearby APs and non-Wi-Fi interference. |
| `CO_CHANNEL_CONGESTION` | Co-channel congestion | Review channel assignments and select a less crowded channel. |
| `WEAK_CLIENTS` | Weak clients | Improve coverage, reposition the AP, or check client obstructions. |
| `HIGH_RETRIES_OR_FAILURES` | High packet retry or failure rate | Investigate signal quality, interference, and channel selection. |
| `HIGH_CLIENT_LOAD` | Too many active clients | Distribute clients across radios or access points. |
| `UNUSUAL_WIFI_CONDITIONS` | Unusual Wi-Fi conditions | Inspect the affected radio metrics and compare nearby APs. |

## 6. Validation checklist

- `bash -n scripts/start_linux.sh` passes.
- `python3 -m py_compile scripts/startup.py scripts/shutdown.py` passes.
- `helm lint helm/ai-flow` passes.
- `helm template ai-flow helm/ai-flow` renders successfully.
- All expected pods reach `Running` and `1/1 Ready`.
- Consumer logs show telemetry rows stored.
- Training logs show `model.pkl` saved.
- Inference logs show database and MQTT connections.
- Grafana loads the dashboard and displays telemetry after selecting a recent time range.
- Fluent Bit becomes ready and Splunk searches return events with pod/container metadata.
- Normal MQTT and simulator deployments both send logs to Splunk.
- MQTT monitor shows incoming and published messages from `public.mqtt_messages`.
- Telemetry monitor shows newest-first `public.telemetry` rows with time filtering and pagination.
- `python3 scripts/shutdown.py` removes runtime resources after validation.
