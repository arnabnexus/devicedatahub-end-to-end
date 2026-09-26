#!/usr/bin/env python3
"""Serve local MQTT history and TimescaleDB record monitoring pages."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

LOGGER = logging.getLogger("device-data-monitor")
DB_OPTIONS = {
    "host": os.getenv("DB_HOST", "ai-flow-timescaledb"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "telemetry"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "postgres"),
    "connect_timeout": 4,
}
TIME_PRESETS = {"5", "15", "60", "1440", "all"}
PAGE_SIZE = 500

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ | DeviceDataHub</title><style>
:root{color-scheme:light;--ink:#17242b;--muted:#64747c;--line:#d7e0e2;--paper:#f3f6f4;--white:#fff;--teal:#087e78;--lime:#d7f36b;--red:#b63f39;--blue:#d9edf3}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}header{background:#13292d;color:#f4f8f3;padding:22px clamp(18px,4vw,56px);display:flex;justify-content:space-between;align-items:center;gap:20px;border-bottom:4px solid var(--lime)}header strong{font-size:18px}header small{color:#b5c8c4;display:block}nav{display:flex;gap:8px}nav a{color:#d9e4df;text-decoration:none;padding:8px 12px;border:1px solid #46605d;border-radius:5px}nav a.active{background:var(--lime);color:#192723;border-color:var(--lime)}main{max-width:1500px;margin:auto;padding:28px clamp(14px,3vw,42px)}.title{display:flex;justify-content:space-between;align-items:end;gap:16px;flex-wrap:wrap}.eyebrow{text-transform:uppercase;color:var(--teal);font-weight:700;font-size:11px}h1{font-size:28px;line-height:1.15;margin:5px 0}.lede{color:var(--muted);margin:6px 0 0}.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:22px 0 14px}.controls select,.controls button{height:38px;border:1px solid var(--line);border-radius:4px;background:#fff;color:var(--ink);padding:0 12px;font:inherit}.controls button{background:var(--teal);color:white;border-color:var(--teal);font-weight:650;cursor:pointer}.status{margin-left:auto;color:var(--muted);font-size:12px}.bar{display:flex;gap:18px;align-items:center;padding:10px 12px;background:#e4ece8;border:1px solid var(--line);border-bottom:0;color:#41565b;font-size:12px}.dot{width:8px;height:8px;background:#37a36b;border-radius:50%;display:inline-block;margin-right:6px}.wrap{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:0 0 5px 5px}table{border-collapse:collapse;width:100%;min-width:900px}th{text-align:left;background:#f7faf8;color:#52656a;text-transform:uppercase;font-size:10px;letter-spacing:.06em;position:sticky;top:0}td,th{padding:11px 12px;border-bottom:1px solid #e7edeb;vertical-align:top}td{font-size:12px}tbody tr:hover{background:#f4faf8}code,.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px}.payload{max-width:540px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:145px;overflow:auto;background:#f5f8f7;padding:8px;border:1px solid #e2e9e6;border-radius:3px}.pill{display:inline-block;padding:3px 7px;border-radius:10px;background:var(--blue);color:#12526a;font-weight:700;font-size:10px;text-transform:uppercase}.pill.published{background:#f4e4cc;color:#80551a}.pill.failed{background:#f7dedd;color:var(--red)}.empty{padding:38px;text-align:center;color:var(--muted)}.more{display:block;margin:16px auto;background:#fff;border:1px solid var(--line);padding:9px 15px;border-radius:4px;cursor:pointer}.error{color:var(--red)}footer{color:var(--muted);font-size:11px;margin-top:16px}@media(max-width:650px){header{align-items:flex-start;flex-direction:column}h1{font-size:24px}.status{margin-left:0;width:100%}}
</style></head><body>
<header><div><strong>DeviceDataHub</strong><small>Telemetry operations</small></div><nav><a href="http://localhost:5000/mqtt" class="__MQTT_ACTIVE__">MQTT messages</a><a href="http://localhost:6080/telemetry" class="__TELEMETRY_ACTIVE__">TimescaleDB</a></nav></header>
<main><div class="title"><div><div class="eyebrow">Live monitor</div><h1>__TITLE__</h1><p class="lede">__LEDE__</p></div></div>
<div class="controls"><label for="range">Time range</label><select id="range"><option value="5">Last 5 minutes</option><option value="15">Last 15 minutes</option><option value="60">Last 1 hour</option><option value="1440">Last 24 hours</option><option value="all">All time</option></select><button id="refresh">Refresh now</button><span class="status" id="status">Connecting…</span></div>
<div class="bar"><span><i class="dot"></i>Auto-refresh every 30 seconds</span><span id="count">0 rows</span><span>Newest first</span></div>
<div class="wrap"><table><thead><tr id="head"></tr></thead><tbody id="rows"></tbody></table></div><button class="more" id="more">Load older records</button><footer id="note"></footer></main>
<script>
const mode="__MODE__", endpoint=mode==="mqtt"?"/api/messages":"/api/telemetry", fields=mode==="mqtt"?["Time","Direction","Topic","Status","Payload"]:["Time","Device","Radio","Channel","Utilization %","CCA busy %","Avg RSSI dBm","Clients","Retries","Failures"];
const head=document.querySelector("#head"),body=document.querySelector("#rows"),status=document.querySelector("#status"),count=document.querySelector("#count"),range=document.querySelector("#range"),more=document.querySelector("#more");let offset=0,loading=false;
for(const field of fields){const th=document.createElement("th");th.textContent=field;head.append(th)}
function cell(row,value,className){const td=document.createElement("td");if(className){const span=document.createElement("span");span.className=className;span.textContent=value;td.append(span)}else{td.textContent=value??"-"}row.append(td)}
function makeRow(item){const tr=document.createElement("tr");if(mode==="mqtt"){cell(tr,new Date(item.created_at).toLocaleString());cell(tr,item.direction,"pill "+item.direction);cell(tr,item.topic,"mono");cell(tr,item.succeeded?"accepted":"failed",item.succeeded?"pill":"pill failed");const td=document.createElement("td"),pre=document.createElement("pre");pre.className="payload";try{pre.textContent=JSON.stringify(JSON.parse(item.payload),null,2)}catch{pre.textContent=item.payload}td.append(pre);tr.append(td)}else{cell(tr,new Date(item.timestamp).toLocaleString());cell(tr,item.device_id);cell(tr,item.radio);cell(tr,item.channel);cell(tr,item.channel_utilization_pct);cell(tr,item.cca_busy_pct);cell(tr,item.avg_rssi_dbm);cell(tr,item.client_count);cell(tr,item.tx_retries);cell(tr,item.tx_failed)}return tr}
async function load(append=false){if(loading)return;loading=true;status.textContent="Refreshing…";status.className="status";if(!append){offset=0;body.replaceChildren()}try{const q=new URLSearchParams({minutes:range.value,limit:"500",offset:String(offset)});const response=await fetch(endpoint+"?"+q);if(!response.ok)throw new Error(await response.text());const result=await response.json();for(const item of result.rows)body.append(makeRow(item));offset+=result.rows.length;count.textContent=result.total===null?`${offset} rows loaded`:`${result.total} rows`;more.hidden=!result.has_more;if(!result.rows.length&&!offset){const tr=document.createElement("tr"),td=document.createElement("td");td.colSpan=fields.length;td.className="empty";td.textContent=mode==="mqtt"?"No MQTT messages recorded in this time range.":"No telemetry records found in this time range.";tr.append(td);body.append(tr)}status.textContent="Updated "+new Date().toLocaleTimeString()}catch(error){status.textContent="Data source unavailable: "+error.message;status.className="status error"}finally{loading=false}}
document.querySelector("#refresh").addEventListener("click",()=>load());range.addEventListener("change",()=>load());more.addEventListener("click",()=>load(true));more.hidden=true;load();setInterval(()=>load(),30000);
</script></body></html>"""


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _load_messages(minutes: str, limit: int, offset: int):
    query = "SELECT id, created_at, direction, topic, payload, succeeded FROM public.mqtt_messages"
    timed_query = query + " WHERE created_at >= NOW() - (%s * INTERVAL '1 minute')"
    order = " ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s"
    with psycopg2.connect(**DB_OPTIONS, cursor_factory=RealDictCursor) as connection:
        with connection.cursor() as cursor:
            if minutes == "all":
                cursor.execute(query + order, (limit + 1, offset))
            else:
                cursor.execute(timed_query + order, (int(minutes), limit + 1, offset))
            return cursor.fetchall()


def _load_telemetry(minutes: str, limit: int, offset: int):
    columns = (
        "timestamp, device_id, radio, channel, channel_utilization_pct, cca_busy_pct, "
        "avg_rssi_dbm, client_count, tx_retries, tx_failed"
    )
    query = f"SELECT {columns} FROM public.telemetry"
    order = " ORDER BY timestamp DESC, device_id, radio LIMIT %s OFFSET %s"
    with psycopg2.connect(**DB_OPTIONS, cursor_factory=RealDictCursor) as connection:
        with connection.cursor() as cursor:
            if minutes == "all":
                cursor.execute(query + order, (limit + 1, offset))
            else:
                cursor.execute(
                    query + " WHERE timestamp >= NOW() - (%s * INTERVAL '1 minute')" + order,
                    (int(minutes), limit + 1, offset),
                )
            return cursor.fetchall()


class MonitorHandler(BaseHTTPRequestHandler):
    def log_message(self, format_string: str, *args) -> None:
        LOGGER.info("%s - %s", self.address_string(), format_string % args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, default=_json_value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path)
        page_type = "mqtt" if self.server.server_port == 5000 else "telemetry"
        if path.path in ("/", "/mqtt", "/telemetry"):
            page = PAGE.replace("__TITLE__", "MQTT messages" if page_type == "mqtt" else "TimescaleDB records")
            page = page.replace("__LEDE__", "Incoming telemetry and published anomaly events" if page_type == "mqtt" else "Stored Wi-Fi telemetry records from PostgreSQL/TimescaleDB")
            page = page.replace("__MODE__", page_type)
            page = page.replace("__MQTT_ACTIVE__", "active" if page_type == "mqtt" else "")
            page = page.replace("__TELEMETRY_ACTIVE__", "active" if page_type == "telemetry" else "")
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if path.path not in ("/api/messages", "/api/telemetry"):
            self._json(404, {"error": "not found"})
            return

        params = parse_qs(path.query)
        minutes = params.get("minutes", ["5"])[0]
        if minutes not in TIME_PRESETS:
            self._json(400, {"error": "invalid time range"})
            return
        try:
            limit = min(max(int(params.get("limit", [str(PAGE_SIZE)])[0]), 1), PAGE_SIZE)
            offset = max(int(params.get("offset", ["0"])[0]), 0)
            loader = _load_messages if path.path == "/api/messages" else _load_telemetry
            rows = loader(minutes, limit, offset)
            has_more = len(rows) > limit
            rows = rows[:limit]
            self._json(200, {"rows": rows, "has_more": has_more, "total": None})
        except Exception:
            LOGGER.exception("Monitor query failed")
            self._json(503, {"error": "TimescaleDB query failed; check database and table readiness"})


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    servers = [ThreadingHTTPServer(("0.0.0.0", port), MonitorHandler) for port in (5000, 6000)]
    LOGGER.info("MQTT monitor listening on :5000; telemetry viewer listening on :6000")
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for server in servers:
            server.shutdown()


if __name__ == "__main__":
    main()
