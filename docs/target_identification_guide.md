# Target Identification & Field Tradecraft Guide

Signal Scout operates by passively sniffing 802.11 Wi-Fi management frames and Bluetooth Low Energy (BLE) advertisements. However, an unassigned MAC address is just a string of hexadecimal bytes. Turning raw radio frequency (RF) packets into actionable intelligence requires understanding vendor signatures, baseline collection strategies, and visual confirmation.

---

## 1. Ubiquitous Default Signatures

When bootstrapping a new Signal Scout deployment, several common vendor signatures serve as the foundation for your Include Definitions.

### A. Axon Enterprise (`00:25:DF`) — High Confidence
* **Hardware:** Body-worn cameras (Axon Body 2/3/4), in-car video systems (Axon Fleet), Axon Signal vehicle modules, and docking stations.
* **Why it matters:** Unlike general networking equipment, Axon hardware is sold almost exclusively to law enforcement, corrections, and high-security government entities.
* **False Positive Risk:** **Extremely Low.** If an edge watcher detects an `00:25:DF` OUI or an Axon BLE advertisement, it is almost certainly a law enforcement vehicle, officer, or station.

### B. Cradlepoint (`00:30:44`) — Medium Confidence
* **Hardware:** Ruggedized cellular IoT routers (IBR series, R1900, COR, AER) mounted inside vehicles to provide mobile Wi-Fi, CAD connectivity, and telemetry backhaul.
* **Why it matters:** Cradlepoint is the dominant in-vehicle gateway for police cruisers, fire apparatus, and ambulances across North America.
* **False Positive Risk:** **High.** Cradlepoint routers are also widely deployed in:
  * Public transit buses and light rail
  * Utility company service trucks
  * Construction vehicles and heavy equipment
  * Stationary infrastructure (ATMs, digital highway billboards, traffic sensor cabinets)
* **Strategy:** Treat raw Cradlepoint detections as a starting pool, not definitive proof of an emergency vehicle.

### C. Generic SSID & BLE Broadcast Names
Many agencies deploy Wi-Fi networks or Bluetooth peripherals with default or semi-descriptive broadcast identifiers. Adding these to **Definition Names** catches vehicles that might be using third-party modems (e.g., Sierra Wireless, Pepwave) rather than Cradlepoint:
* `"Police"` / `"Sheriff"` / `"StateTrooper"` / `"HighwayPatrol"`
* `"EMS"` / `"Medic"` / `"Ambulance"`
* `"Fire"` / `"Engine"` / `"Rescue"`
* `"K9"` / `"Tactical"` / `"PublicSafety"`

---

## 2. Methodology: How to Build Your Target Database

There are two primary approaches to establishing accurate target identification:

```
┌─────────────────────────────────────────────────────────────┐
│                       Approach 1:                           │
│               Passive Wardriving & Legwork                  │
│  • Upfront survey around stations & patrol corridors        │
│  • Exact MAC identification & vehicle correlation           │
│  • Zero-noise, high-accuracy database from Day 1            │
└─────────────────────────────────────────────────────────────┘
                              OR
┌─────────────────────────────────────────────────────────────┐
│                       Approach 2:                           │
│                 "Cast a Wide Net" Funnel                    │
│  • Enable broad Cradlepoint OUI & generic names             │
│  • Collect all ambient fleet signals for 1–2 weeks          │
│  • Filter stationary noise and transit patterns             │
│  • Whittle down results into verified targets               │
└─────────────────────────────────────────────────────────────┘
```

---

### Approach 1: Passive Wardriving & Upfront Legwork

If you require high accuracy from the outset without flooding your map with unverified hits, you must conduct initial field reconnaissance.

#### What is Passive Wardriving?
Wardriving is the practice of mapping wireless networks while moving through a geographic area. **Passive wardriving** means your receiver only listens (promiscuous / monitor mode); it **never transmits packets, probes, or associates** with nearby access points.

#### Field Reconnaissance Steps:
1. **Target Gathering Areas:** Conduct slow, passive collection drives past public safety stations, municipal motor pools, courthouse parking areas, or common speed-monitoring locations.
2. **Log & Timestamp:** Record RF logs with accurate timestamps and GPS locations (using tools like Kismet, Wireshark, a mobile Signal Scout watcher, or a GPS-enabled laptop).
3. **Isolate Clustered Signatures:** When driving past a police substation, you will observe clusters of identical Cradlepoint OUIs (`00:30:44`), Sierra Wireless OUIs, and Axon device beacons (`00:25:DF`).
4. **Direct Target Assignment:** Take those identified MAC addresses and create formal **Tracked Target** records in the Signal Scout Admin panel (e.g., *Alias: "County Sheriff Unit"*, bound to a specific `DeviceMAC`).

---

### Approach 2: The "Cast a Wide Net" Funnel

If upfront field surveys are not feasible, you can let your deployed watcher nodes do the discovery:

1. **Enable Broad Rules:** 
   * Create an Include Definition for **Cradlepoint** (`00:30:44`) with **VMAC Expansion enabled**.
   * Set Confidence to **Low** or **Medium**.
2. **Collect Ambient Data (1–2 Weeks):**
   * Allow your stationary watchers to ingest all matching beacons.
3. **Analyze the Patterns in the Target Log:**
   * **Stationary False Positives:** Look for MAC addresses that appear continuously 24/7 at a single watcher location with consistent signal strength. These are almost always fixed commercial installations (bank ATMs, vending kiosks, construction site cameras, or digital signs).
   * **Public Transit False Positives:** Look for MAC addresses that trigger periodic alerts on predictable, clockwork schedules (e.g., municipal transit buses passing a stop every 30 or 60 minutes).
   * **True Mobile Targets:** Look for MAC addresses that appear transiently, move across multiple Deployment Locations, or show burst activity during known local emergency responses.
4. **Prune the Noise:**
   * Add identified ATMs, billboards, and transit buses to the **False Positive Filter** by exact MAC or OUI.
   * Promote the remaining mobile, corroborated devices into confirmed **Tracked Targets**.

---

## 3. Visual Observation: The Essential Human-in-the-Loop Filter

Regardless of the approach you choose, **visual confirmation is mandatory** to achieve 100% confidence.

```
[Watcher Alert Triggered]
        │
        ├─ Timestamp: 14:22:05
        ├─ Location: Main St & 3rd Ave
        └─ MAC: 00:30:44:xx:xx:xx
        │
[Visual Field Observation]
        │
        ├─ Cruiser spotted at intersection at 14:22
        ├─ Agency: Local Municipal PD
        ├─ Car Number: #14
        └─ License Plate: State Exempt 8821-X
        │
[Promote to Verified Tracked Target]
        ▼
• Alias: "Municipal PD Car 14"
• Car Number: "14"
• License Plate: "8821-X"
• Bound MAC: 00:30:44:xx:xx:xx (Cradlepoint)
• Confidence: High
```

### Why Visual Observation is Critical:
1. **Radio signals penetrate walls and tree lines:** A watcher may alert on a Cradlepoint router located inside a commercial delivery van parked three driveways down out of sight.
2. **Attribution requires ground truth:** Seeing car markings, unit numbers, and agency emblems allows you to bind a faceless MAC address to a specific patrol vehicle.
3. **Closing the Loop:** Once a vehicle has been visually tied to a MAC address:
   * It moves from being an ambiguous generic detection into a permanent **TrackedTarget**.
   * Future alerts across your entire watcher network will display the vehicle's operator on the live map and keep it distinct from other vehicles used by the same operator.
