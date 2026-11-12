# Technical and Compatibility Diagnostics

**Reference page · [User Guide](USER_GUIDE.md) · [Entity Reference](ENTITIES.md) · [Complete documentation index](DOCUMENTATION_INDEX.md)**

## On this page

- [Why these diagnostics exist](#why-these-diagnostics-exist)
- [Dashboard contract](#dashboard-contract)
- [MAC movement tracking](#mac-movement-tracking)
- [Which devices may generate noise](#which-devices-may-generate-noise)
- [What Home Assistant can do today](#what-home-assistant-can-do-today)
- [Potential future improvements](#potential-future-improvements)

## Why these diagnostics exist

Some Home Assistant entities exist to support diagnostic tools or interoperability rather than to provide another household measurement. They remain visible in the entity registry so an administrator can inspect them when troubleshooting. They do not need a card on a normal monitoring dashboard.

## Dashboard contract

The **Dashboard contract** diagnostic sensor tells the companion Cisco Catalyst dashboard how to recognize the Integration's switch parent device and the structure of its exposed port metadata. It is not a network-health value, a user command, or a value that normally changes during operation.

| State/attribute | Sample value | Meaning |
| --- | --- | --- |
| Sensor state | `1` | Frontend data contract version |
| `dashboard_contract_version` | `1` | Schema supported by the Integration |
| `is_cisco_catalyst_switch` | `true` | Marks the parent as a Catalyst switch |
| `cisco_catalyst_role` | `switch` | Identifies the entity's structural role |

**Why not remove it?** The dashboard needs a reliable way to discover a switch without depending on a user-renamed device or entity ID. Removing or disabling the sensor without verifying the frontend discovery mechanism could break that relationship. It is already in Home Assistant's diagnostic entity category. There is no normal household automation that requires its state. If the companion card cannot find the switch, inspect this entity as one diagnostic clue.

## MAC movement tracking

The **MAC movement anomalies** sensor is a cumulative numeric count, not an `on/off` detector of whether a device moved. The existing Integration observes learned MAC addresses at switch interfaces. After a new location is seen in **two consecutive polls**, it can emit `cisco_catalyst_mac_movement`. A move is considered an anomaly when the same MAC completes **three or more confirmed edge-to-edge moves within five minutes**; this also emits `cisco_catalyst_mac_anomaly` and increases the counter.

| Observation | Current behavior |
| --- | --- |
| First sighting of a MAC | Establishes baseline; no movement event |
| Confirmed change of switch port | Movement event |
| Three or more confirmed edge-port moves within five minutes | Anomaly event and incremented count |
| MAC disappears or ages out | No movement alert by itself |
| Port is identified as infrastructure or path classification is uncertain | Excluded from edge-flapping anomaly sequence |
| Count is `0` | No qualifying anomalies seen this integration run |
| Count is `1`, `2`, etc. | Cumulative anomalies observed this integration run |

The sensor's `recent_movements` and `recent_anomalies` attributes contain bounded diagnostic history. Its scope is `coordinator_lifetime`: restarting/reloading the Integration can reset its tracking history. This is **not** a permanent inventory of where devices are connected, nor proof of suspicious activity.

## Which devices may generate noise

A **hardwired device** such as a desktop, NAS, wired camera, printer, or fixed access point usually stays attached to one physical connection. If its MAC appears on a different edge port, an owner may want to know even after **one** confirmed move. That is already detectable as a movement event, though the anomaly counter does not increase from a single move.

A **mobile device** moving between Wi-Fi access points can legitimately cause its MAC to be learned through a different switch path. For example, a phone roaming between two APs connected to different access switches or uplinks may appear to move. This can be normal, noisy activity rather than a problem. The tracker deliberately excludes known infrastructure paths from edge-to-edge anomaly detection, but topology information may be incomplete; it is not a reliable per-device fixed-versus-mobile classification system.

Importantly, this Integration currently observes **one configured switch**. It does not independently build a verified network-wide history across multiple switches, identify clients as mobile or stationary, or know whether a device was physically moved versus reachable through a different Layer-2 path.

## What Home Assistant can do today

Home Assistant can already trigger an automation from `cisco_catalyst_mac_movement` (one confirmed change) or `cisco_catalyst_mac_anomaly` (repeated edge movements). Look at the event in **Developer Tools → Events** to inspect `mac`, `old_interface`, `new_interface`, `observed_at`, `edge_move_count`, and `anomaly`. An automation could send a notification for selected MAC addresses. That filtering must currently be configured by the user; there is no built-in device classification or dedicated alert policy UI.

The Integration **does not** automatically disable a port, change VLANs, or declare a device malicious based on these events. A port change may be expected; inspect cabling and connected paths before taking action.

## Potential future improvements

A higher-level feature might offer an owner-maintained **watch list for devices expected to remain on a fixed port**, an ignore list for mobile or infrastructure devices, friendly names, per-device alert policies, movement history and event explanation. Such features are feasible using Home Assistant and switch observations, but robust multi-switch and roaming-aware tracking would require additional topology/source information. These are **ideas, not claims of implemented capabilities**. Development plans belong in a roadmap rather than being advertised as released functionality.
