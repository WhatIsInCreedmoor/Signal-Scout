# Signal Scout: Server Architecture, Design Decisions & Setup Guide

This document outlines the core architectural concepts of the Signal Scout backend, the reasoning behind key design decisions, and the step-by-step procedure for configuring the server once the basic installation is complete.

---

## 1. Post-Installation Setup Workflow

Once Signal Scout is deployed and the Django service is running, follow this recommended sequence to configure your server before deploying hardware:

```
Step 1: Create Admin User (CLI)
   │
Step 2: Create Deployment Locations (Admin)
   │
Step 3: Build Definitions (Includes & Excludes)
   │
Step 4: Commission Watchers (Generate API Keys)
   │
Step 5: Flash Hardware Nodes & Deploy in Field
   │
Step 6: Monitor Live Targets on the Map UI
```

### Initial Superuser Creation
From the Signal Scout directory on the server:
```bash
source ./env/bin/activate
cd /opt/signalscout/signalscout
python manage.py createsuperuser
```
Log in at `https://your-domain.org/admin/`.

---

## 2. System Design Decisions & Concepts

### A. Definitions
Definitions configure the recognition engine on both the server and edge sensor nodes. They define what signals constitute an alert and what signals should be ignored.

```
                      ┌──────────────────────────────────────────────┐
                      │              Definitions Engine              │
                      └───────┬──────────────────────────────┬───────┘
                              │                              │
                              ▼                              ▼
                 ┌─────────────────────────┐   ┌───────────────────────────┐
                 │   Include Definitions   │   │     Exclude Definition    │
                 │       (Discrete)        │   │         (General)         │
                 ├─────────────────────────┤   ├───────────────────────────┤
                 │ • Equipment specific    │   │ • 1 broad noise rule      │
                 │ • Operator attribution  │   │ • Consumer tech OUIs      │
                 │ • Confidence scoring    │   │ • Public Wi-Fi SSIDs      │
                 │ • VMAC expansion        │   │ • Drops packets locally   │
                 └─────────────────────────┘   └───────────────────────────┘
```

#### 1. Discrete Include Definitions
* **Design Decision:** Target equipment should be grouped into separate, discrete definition records (e.g., *"Axon Bodycams"*, *"Flock Safety"*, *"CradlePoint Routers"*, *"LPR Cameras"*).
* **Metadata Attribution:** Each discrete definition allows you to assign:
  * **Operator:** (e.g., `County Sheriff`, `Local PD`, `State Patrol`). When an ESP32 detects an OUI or SSID matching this rule, the server automatically tags the detection with this operator.
  * **Confidence Level:** (`Low`, `Medium`, `High`). Distinguishes high-certainty indicators (unique BLE advertising names or dedicated hardware OUIs) from broader, more ambiguous signatures.
* **Attachments:** You can attach multiple **OUIs** (`XX:XX:XX`) and/or **Names** (Wi-Fi SSID or BLE Advertising Name substrings) to a single Include definition.

#### 2. One General Exclude Definition
* **Design Decision:** Keep exclusions consolidated into **one general rule** rather than creating dozens of individual exclusion categories.
* **Noise Reduction:** Use this rule to list common consumer electronics (e.g., Apple, Samsung, Google, Tesla, TP-Link, printer SSIDs) that operate in the same frequency bands.
* **Sent to the Device:** Both Include and Exclude lists are compiled into the payload sent to watcher nodes (`target_ouis`, `target_names`, `ignore_ouis`, `ignore_names`).

#### 3. Virtual MAC (VMAC) Expansion
* **The Problem:** Modern enterprise routers, vehicle multi-SSID modems (like CradlePoint and Sierra Wireless), and mesh access points broadcast multiple virtual BSSIDs from a single physical radio. The IEEE standard for locally administered virtual MAC addresses modifies the first byte of the hardware OUI.
* **The Math:** In IEEE 802 addressing, the second-least-significant bit of the first byte is the **Universally / Locally Administered (U/L) bit**:
  $$\text{Bit 1 of Byte 0} = 1 \implies \text{Locally Administered Virtual MAC}$$
  This restricts the second hex digit of the first byte to four specific values: `2`, `6`, `A`, or `E`.
* **How It Works:** When **VMAC Expansion** is checked on a `DefinitionOUI` (e.g., `00:11:22`):
  * The server keeps the upper nibble (`0`) and the rest of the OUI (`:11:22`).
  * It automatically synthesizes and distributes the four virtual variations:
    * `02:11:22`
    * `06:11:22`
    * `0a:11:22`
    * `0e:11:22`
  * **Result:** The watcher node catches all virtual access points, guest networks, and secondary BSSIDs transmitted by that vendor's hardware without needing to manually discover every virtual MAC.

#### 4. Edge Distribution & Caching
* Watcher nodes query `/api/definitions/` during boot and at regular background intervals.
* The server hashes the definition payload into an **HTTP MD5 ETag**.
* The node caches definitions to local encrypted storage (`/storage/defs.json` and `/storage/etag.txt`).
* Subsequent checks send `If-None-Match: <etag>`. If unchanged, the server returns **304 Not Modified**, consuming negligible bandwidth and eliminating redundant flash writes.

---

### B. Deployment Locations
Deployment Locations represent physical sites where stationary or mobile watcher nodes are stationed (e.g., *"Intersection 5th & Main"*, *"Highway 10 Overpass"*, *"North Gate"*).

* **Anchor Coordinates:** Each location stores a friendly name, `latitude`, and `longitude`.
* **Automatic Coordinate Attribution:** When a watcher node uploads a detection, it inherits the GPS coordinates of its assigned `DeploymentLocation` by default (unless the node itself provides hardware GPS coordinates).
* **Dynamic Geocoding:** If you update the coordinates of a Deployment Location in the admin panel, the live map dynamically re-anchors historical sessions associated with that area name without requiring database migrations.

---

### C. False Positive Filter (Server-Side)
The False Positive Filter acts as a server-side safety net to silence stubborn or unexpected alert noise.

```
[Radio Environment]
        │
   (Unfiltered Packet)
        │
        ▼
[ESP32 Watcher Node] ──► Hears false positive, stop listening, connects to Wi-Fi, sends HTTP POST
        │
        ▼
[Signal Scout Server]
   └── False Positive Filter Check:
         ├── Exact MAC Match?  ──► DROP (HTTP 200 "ignored")
         ├── OUI Prefix Match? ──► DROP (HTTP 200 "ignored")
         └── Name Substring?   ──► DROP (HTTP 200 "ignored")
```

#### Key Design Considerations:
1. **Why it is a SECONDARY filter:**
   * It is processed **on the server during ingestion**.
   * It does **not** stop the edge node from triggering on a flase positive, connecting to Wi-Fi, and transmitting the packet.
   * **Rule of Thumb:** Always prefer filtering noise at the **Definition (Exclude)** level so the ESP32 drops the packet in RAM before establishing a network connection. Use the False Positive Filter for fast, emergency suppression of stubborn targets without waiting for a fleet-wide definition sync.
2. **Matching Flexibility:**
   * **Exact MAC:** Blocks a single noisy device (`XX:XX:XX:XX:XX:XX`).
   * **MAC OUI:** Blocks a vendor block (`XX:XX:XX`).
   * **Device Name:** Case-insensitive substring match (e.g., entering `printer` catches `"HP-LaserJet-Printer-12"` and `"Office_Printer"`).
3. **Automatic Loop-Back to Edge:**
   * Active False Positive Filters are automatically appended to the `ignore_ouis` and `ignore_names` lists distributed by `/api/definitions/`. On their next sync cycle, edge nodes pull these rules and begin filtering them locally.

---

### D. Targets & The Live Map
The **Targets** table is the operational core where all accepted detections and alerts are logged.

* **What Appears Here Appears on the Map:**
  * The public/authenticated map UI at `/` polls `/api/targets/` every 5 seconds.
  * Every record in the Targets table from the last 12 hours is rendered as a pin on the Leaflet map and listed in the real-time event table below it.
* **Session Splitting Algorithm:**
  * Rather than cluttering the map with hundreds of raw packets for the same stationary vehicle, the server groups repeated detections into unified **Sessions**:
    * **Time Window:** Detections for the same device within a **5-minute window** are merged into an ongoing session, updating the `last_seen` timestamp.
    * **Geographic Splitting:** If the same target MAC is detected by a watcher in a *different* Deployment Location, the server immediately closes the previous session and starts a new one, producing a distinct breadcrumb trail across the map.

---

### E. Watchers (Node Commissioning & Fleet Health)
The **Watchers** section is your control center for managing the physical fleet.

#### 1. Node Commissioning Workflow
To commission a new watcher node:
1. Navigate to **Admin $\rightarrow$ Watchers $\rightarrow$ Add Watcher**.
2. Select or enter the **Device Type** (e.g., `Seeed XIAO ESP32C6`, `ESP32-S3`).
3. Assign a **Deployment Location**.
4. You can leave `MAC Address` blank if you don't yet have it (the node will auto-populate its hardware MAC on its first connection).
5. Copy the automatically generated **Auth Key** (`auth_key`).
6. Place this key into the device's secrets file (`device-secrets/<MAC>.device_secrets.csv`) and flash the device's NVS partition.

#### 2. Fleet Health Monitoring
* **`Last Seen`:** Updated whenever the device checks in via heartbeat (`/api/heartbeat/`) or refreshes definitions (`/api/definitions/`). Tells you the node is alive and connected to Wi-Fi.
* **`Last Uploaded`:** Updated only when the device successfully transmits a new target detection.
* **Hardware Target:** Automatically reported by the firmware on its first check-in (e.g., `esp32c3`, `esp32c6`, `esp32s3`), ensuring firmware updates deliver the correct chip binary.

#### 3. Over-The-Air (OTA) Firmware Management
* **`Firmware Version`:** Displays the current version running on the hardware.
* **`Auto Update Enabled`:** A per-device toggle. When checked (`True`), the node will download and flash new firmware releases uploaded under **Firmware Releases** that match its `hardware_target`. When unchecked (`False`), the device stays locked to its current firmware.

---

## 3. Summary Reference Table

| Section | Primary Function | Where Processed | Action / Impact |
| :--- | :--- | :---: | :--- |
| **Definitions (Include)** | Identify targets, assign Operator & Confidence | Edge (Detect) + Server (Enrich) | Matches trigger Wi-Fi connect & upload |
| **Definitions (Exclude)** | General noise suppression (OUIs & SSIDs) | Edge | Packets dropped in RAM (zero extra Wi-Fi connects) |
| **VMAC Expansion** | Auto-generate virtual BSSIDs (`02`, `06`, `0A`, `0E`) | Server $\rightarrow$ Edge | Captures multi-SSID vehicle routers |
| **Deployment Locations** | Physical coordinate anchoring | Server | Geocodes detections on the Leaflet map |
| **False Positive Filter** | Emergency secondary filter for stubborn alerts | Server (then synced to Edge) | Drops alerts at ingest before DB write |
| **Targets** | Detection logs & session tracking | Server | Directly feeds the live web map UI |
| **Watchers** | Fleet commissioning, health, & OTA toggles | Server | Controls device API keys, status, & updates |
