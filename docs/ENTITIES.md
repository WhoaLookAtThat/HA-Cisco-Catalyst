# Cisco Catalyst — Entities and Home Automation

[Documentation home](../README.md) / **Entity reference**

[Quick Start](USER_GUIDE.md) · [SNMP setup](SNMP_SETUP.md) · [Entity reference](ENTITIES.md) · [Automations and events](AUTOMATIONS.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Documentation index](DOCUMENTATION_INDEX.md)

## On this page

- [Example states, values, units, and unavailable readings](#example-states-values-units-and-unavailable-readings)
- [Why diagnostic-only entities exist](#why-these-diagnostic-entities-exist)
- [Interface name examples](#interface-name-examples)
- [What an entity is](#what-an-entity-is)
- [Switch device — monitoring and actions](#switch-device--monitoring-and-actions)
- [Port devices — state, counters, and diagnostics](#port-devices--state-counters-and-diagnostics)
- [Port controls — actions that can change switch configuration](#port-controls--actions-that-can-change-switch-configuration)
- [Practical automation patterns](#practical-automation-patterns)
- [Two worked Home Assistant examples](#two-worked-home-assistant-examples)
- [Data freshness and safety](#data-freshness-and-safety)

## Example states, values, units, and unavailable readings

The following examples illustrate **Home Assistant states** and units, not every raw Cisco SNMP enumeration. `unknown` means a value could not be established; `unavailable` usually indicates an entity/coordinator is not providing valid data. An omitted optional entity is different from either state.

| Entity family | Example state/value | Unit or expected type | Missing data |
| --- | --- | --- | --- |
| Link | `on` / `off` (UI may say Up/Down) | Boolean/binary sensor | `unknown` / `unavailable` |
| Port enabled, PoE enabled | `on` / `off` | Switch state | `unknown` / `unavailable` |
| Port mode attribute | `access`, `trunk` | Text | null/absent if not determined |
| SNMP status | `2c`, `3 (authPriv)` | Text; listener attribute `enabled`/`disabled` | `unavailable` when entry is unavailable |
| Dashboard contract | `1` | Schema version (not a percentage) | `unavailable` if integration is unavailable |
| Access VLAN select | `998`, `20` | VLAN ID, valid operational choices from the switch | Absent/ineligible or `unavailable` |
| RX/TX bytes | `123456789` | Bytes (cumulative) | `unknown` / `unavailable` |
| Errors, discards | `0`, `42` | Packets/events (cumulative counters) | `unknown` / `unavailable` |
| Interface speed | `100`, `1000` | Mbps | `unknown` / `unavailable` |
| CPU, memory | `18`, `65.4` | % (normally 0–100) | `unknown` / `unavailable` |
| PoE draw, total PoE | `7.4`, `125` | W (watts) | `unknown` / `unavailable` |
| Temperature | `38` | °C or °F depending on Home Assistant display units | `unknown` / `unavailable` |
| Uptime | `86400` | Time unit defined on actual entity (check entity details) | `unknown` / `unavailable` |
| Fan / supply | e.g., `Up`, `Off` | Cisco hardware status text, model-dependent | `unknown` / `unavailable` |
| Description | `Garage AP` | Text; may be empty | Empty text or unavailable |
| Learned MACs | `0`, `2` | Count of addresses; details in attributes | `unknown` / `unavailable` |
| MAC movement anomalies | `0`, `1` | Count of noteworthy movement detections | `unknown` / `unavailable` |

For temperature display-unit changes, see [SNMP Setup — Units and missing values](SNMP_SETUP.md#units-and-missing-values). A display unit does **not** change the switch's underlying measurements.

## Why these diagnostic entities exist

For detailed explanations, including fixed versus mobile devices, event behavior, dashboard compatibility, and available versus future features, see [Technical and Compatibility Diagnostics](TECHNICAL_DIAGNOSTICS.md).

### MAC movement anomalies

This is a **nonnegative cumulative count for the current integration/coordinator lifetime**, not an `on`/`off` health flag. A value of `0` means no qualifying anomalies have been observed during the current run; `1` or higher counts qualifying anomalies, and `unknown`/`unavailable` can occur when Home Assistant cannot provide a valid entity state. The count resets when its tracking object is recreated (for example, an integration reload), and should not be interpreted as a lifetime switch total.

A qualifying anomaly occurs when the **same MAC address makes at least three confirmed moves between edge ports in a five-minute window**. A move is confirmed only after two consecutive switch polling observations at the new port. A first sighting, MAC aging/disappearance, transient simultaneous visibility on multiple ports, or a change involving an identified infrastructure/unknown path is **not** counted as an edge-movement anomaly. Infrastructure suppression reduces false alarms but cannot guarantee perfect classification.

The sensor includes `history_scope: coordinator_lifetime`, `recent_movements` (up to 20), and `recent_anomalies` (up to 10) as diagnostic attributes. The integration already emits Home Assistant events `cisco_catalyst_mac_movement` for any confirmed move and `cisco_catalyst_mac_anomaly` for qualifying anomalies. Event data includes `mac`, `old_interface`, `new_interface`, `observed_at`, `edge_move_count`, and `anomaly`. In **Developer Tools → Events**, listen for one of these event types to see the actual data. You can then create a Home Assistant event-triggered notification without installing additional functionality.

If the counter increases, inspect the recorded MAC and ports, consider recent cable changes, intermediary switches, bridges or device behavior, and compare with the switch MAC table. It is a diagnostic clue, **not proof of hostile behavior**, and the integration does not automatically shut ports down or reassign VLANs as a response. A richer movement-history interface may be considered as a future enhancement, but alerting is already possible with existing Home Assistant automations.

### Dashboard contract

This is a **frontend compatibility marker**, not a monitoring metric. Its state is the integer `1` (contract schema version). Attributes include `dashboard_contract_version: 1`, `is_cisco_catalyst_switch: true`, and `cisco_catalyst_role: switch`. The companion dashboard uses this information to recognize the switch independently of user-edited device names or entity IDs.

Most users do not need to open or automate this diagnostic sensor. Its practical troubleshooting purpose is to verify dashboard/integration compatibility if the companion dashboard cannot find the switch. It remains categorized as a Home Assistant **diagnostic entity**, rather than a normal operational sensor. Disabling it outright may interfere with dashboard discovery; it should be kept available to the frontend while being visually deemphasized in ordinary views.


## Interface name examples

In the tables below, `<interface>` means **any discovered supported physical interface**, not only `Gi1/0/x`. Examples: `Gi1/0/2`, `Gi1/1/1`, `Te1/1/1` (and other supported interface prefixes where available). Actual entity names depend on the switch.

## What an entity is

A **device** groups related items in Home Assistant. This Integration creates a device for the Catalyst switch and devices for discovered physical ports. An **entity** is one measurement, condition, button, or control associated with a device. For example, a *link binary sensor* says whether a cable link is up, while a *port enabled switch* tells the switch to administratively enable or disable a port. Those are different signals: a powered-down endpoint can make the link go down even while the port remains enabled.

Home Assistant uses entity domains: `sensor` (measurements or text states), `binary_sensor` (on/off conditions), `switch` (controls), `select` (choose a setting), `text` (edit a string), and `button` (run an action). A diagnostic or configuration entity may be shown in the device's detail view rather than automatically on a dashboard. **Entities called “sensor” are not commands.** The examples below are suggestions for your own automations, not automations the Integration creates automatically.

Names shown below are **display names or patterns**, not guaranteed entity IDs. The entity's actual ID appears in Home Assistant's entity details. A sensor may report `unknown`/`unavailable` if the relevant switch data or poll is missing. Optional sensors/controls appear only when the switch reports enough information.

## Switch device — monitoring and actions

| Entity / domain | What it reports or does | Example home-lab use |
| --- | --- | --- |
| **SNMP status** · sensor | SNMP version/security mode and notification-listener details; not the SNMP password. | Check whether the Integration is running in the expected SNMP mode when diagnosing connectivity. |
| **Uptime** · sensor | Switch uptime reported by the device. | Graph uptime or notice a reset; understand that SNMP uptime is not necessarily identical to how long Home Assistant has been running. |
| **CPU utilization** · sensor | Percentage of switch CPU used. | Alert if utilization remains unusually high for several polls rather than triggering on one transient spike. |
| **Memory used** · sensor | Switch memory consumption as a percentage. | Keep a history graph and flag a sustained increase. |
| **PoE power consumption** · sensor | Total observed power-over-Ethernet usage where supported. | Graph the load of PoE cameras or access points; correlate changes with devices powering up. |
| **Temperature** · sensor(s) | Environmental temperature from switch sensors, when available. | Warn when the switch runs hotter than your usual home-lab baseline. |
| **Fan status** · sensor(s) | Per-fan hardware state, e.g., Up when reported as healthy. | Notify if a fan reports an abnormal state. |
| **Power supply status** · sensor(s) | Per-supply hardware state; an unused or absent second supply may report Off. | Distinguish an expected uninstalled supply from a newly failed supply before alerting. |
| **VLAN review readiness** · diagnostic sensor | Read-only prerequisite check; states `ready_for_review` or `blocked`, with reasons in `blockers`. Never grants write permission or approves a particular port change. | Check snapshot freshness and interface-protection configuration before requesting a VLAN proposal review. |
| **MAC movement anomalies** · sensor | Count of detected noteworthy MAC-address movement events. | Investigate a device unexpectedly moving between ports; treat it as an investigation clue, not automatic proof of a security attack. |
| **Dashboard contract** · diagnostic sensor | Schema/metadata marker used by the companion dashboard to discover stable Catalyst entity roles. | Troubleshoot dashboard compatibility; normally not useful as a household automation trigger. |
| **Refresh data** · button | Requests a new Integration poll. It **does not reset the switch** or perform an SNMP write. | Press after moving a cable or editing settings directly at the switch to update Home Assistant's readings. |

For alerts, use suitable time conditions and handle `unknown` or `unavailable` separately from actual fault values. Hardware-specific sensors may not exist on every Catalyst.

## Port devices — state, counters, and diagnostics

| Entity / domain | What it reports | Example home-lab use |
| --- | --- | --- |
| **`<interface>` link** · binary sensor | Physical operational link is up/down, not whether the administrative control is enabled. Its attributes can include port mode, VLAN and discovered endpoint/neighbor information. | Alert when the cable link for an always-on access point goes down for several minutes. |
| **`<interface>` RX bytes** · sensor | Cumulative received byte counter (64-bit when available). | Plot receive traffic rate using a derivative/rate helper; raw bytes are a counter, **not instantaneous Mbps**. |
| **`<interface>` TX bytes** · sensor | Cumulative transmitted byte counter. | Compare outbound traffic trends between uplinks and end-device ports. |
| **`<interface>` speed** · diagnostic sensor | Reported interface speed. | Spot a device negotiating at 100 Mbps rather than its expected 1 Gbps. |
| **`<interface>` errors** · diagnostic sensor | Interface error counter from the switch. | Look for increasing errors after changing a cable; use the change over time rather than a nonzero total alone. |
| **`<interface>` RX discards** · diagnostic sensor | Cumulative received packets discarded. | Check persistent increases when investigating congestion or device/network problems. |
| **`<interface>` TX discards** · diagnostic sensor | Cumulative transmitted packets discarded. | Investigate drops on a busy uplink or oversubscribed port. |
| **`<interface>` access VLAN status** · diagnostic sensor | State is `operational`, `inactive`, `trunk`, or `unknown`, with attributes including `access_vlan` and `recovery_required`. This sensor is observational, not a control. | Investigate an orphaned access VLAN after switch-side VLAN deletion, then use the VLAN Management recovery flow where available. |
| **`<interface>` network mode** · diagnostic sensor | Access/trunk and related operational network/VLAN facts where reported. | Confirm an AP uplink is a trunk before investigating VLAN availability. |
| **`<interface>` learned MACs** · diagnostic sensor | Learned endpoint MAC/address details, to the extent available from switch tables. | Find the port to which a particular wired device appears connected. |
| **`<interface>` PoE power** · diagnostic sensor | Per-PoE-port measured draw or power-related detail, where supported. | Confirm a powered camera or access point is drawing power. |

Port link attributes may also contain learned IP/MAC addresses, CDP/LLDP neighbor details, access VLAN, native VLAN and allowed VLANs where the switch reports them. These are **attributes**, not separate controls. A trunk's allowed VLAN list is observational; the Integration is not promising a trunk-edit selector.

An example automation could trigger when `binary_sensor.gi1_0_3_link` remains `off` for five minutes and send a mobile notification. Replace the illustrative ID with the one Home Assistant actually created. If you intentionally turn off that port, the link-down notification is expected.

## Port controls — actions that can change switch configuration

| Entity / domain | What you can do | Home-lab example and caution |
| --- | --- | --- |
| **`<interface>` port enabled** · switch | Administratively enable or disable Ethernet operation on a port; different from PoE power. | Temporarily isolate a lab machine. Disabling an uplink or the port used for switch management could interrupt access. |
| **`<interface>` PoE** · switch | Enable or disable switch PoE power to a supported device. | Power-cycle a PoE camera or AP without turning off the Ethernet administrative port; first confirm this is the intended port. |
| **`<interface>` description** · text | Read/edit the switch interface description (`ifAlias`), where write access permits. | Label a jack `Garage-Camera` so devices and dashboards have useful names. |
| **`<interface>` access VLAN** · select | Choose among switch-reported eligible operational access VLANs for a supported static access port. | Move a test device to an isolated VLAN after you have created the destination VLAN. This is not for trunk ports. |

**Access VLAN select eligibility.** A write-enabled integration registers this control for detected static, non-trunk access ports. If the assigned VLAN becomes inactive, the select remains registered but unavailable until recovery. With read-only SNMP access, this control may not be created. The separate access VLAN status sensor can still report the inactive state.

**Description text.** The description entity uses IF-MIB `ifAlias`, allows up to 64 characters, and verifies any authorized change by reading the result.

**Read-only access:** Measurements still work with supported read-only SNMP credentials, while configuration-changing features may be unavailable, not actionable, or blocked. Switch and PoE controls may remain visible as observations, depending on the entity. Read/write capability is not a blanket permission to change a protected port; the Integration and switch both enforce their own restrictions.

The Integration's source also contains a legacy numeric access-VLAN implementation (`number` domain). The current supported access-VLAN experience is the **select** entity; do not treat a historic `number.`<interface>`_access_vlan` and a `select.`<interface>`_access_vlan` as two independent current controls.

## Practical automation patterns

**Network availability.** Monitor important port *link* sensors for sustained down periods, preferably with a delay that excludes normal cable moves or device restarts. This tests the Ethernet connection, not whether the connected application is healthy.

**PoE device recovery.** A user-created script can turn a PoE switch off and on when a camera or access point is unresponsive. This is a **real power interruption**; use an appropriate delay and avoid loops that repeatedly reboot an unhealthy device. Do not base the action only on the port being down.

**Capacity tracking.** Take a derivative or rate of RX/TX byte counters to observe throughput over time. Keep units straight (bytes/s versus bits/s) and account for counter resets or device restarts.

**Environmental awareness.** Combine CPU, memory, chassis temperature, fan and supply status in a household maintenance dashboard. Define your own baseline and alert durations; a second power supply listed as Off may simply not be installed.

**Port labeling.** Use the description text control to document connected equipment. Its configured value is read from the switch; changes are not merely cosmetic dashboard labels.

**VLAN assignments.** Use supported per-port access-VLAN selectors to change a single eligible port; avoid treating a trunk/native VLAN attribute as an editable access VLAN.

## Two worked Home Assistant examples

These are **examples to build yourself**, not automations installed by Cisco Catalyst. Substitute the entity IDs found under **Settings → Devices & services → Cisco Catalyst → your port → Entities**.

### Example 1: Notify when an access point goes offline

Suppose your access point is connected to Gi1/0/3. Use its **link binary sensor**, not its port-enabled switch, for a physical link alarm:

1. In **Settings → Automations & scenes**, create an automation triggered when the Gi1/0/3 link entity becomes **Off** for five minutes.
2. Add a mobile-app notification action, such as “The access point’s Ethernet link has been down for five minutes.”
3. Confirm the trigger using a port and test method you consider appropriate for your network.

This reports the **Ethernet connection state**. It does not prove the access point's Wi-Fi or internet service is working, and an intentionally disconnected or powered-off device can cause an expected alert.

### Example 2: Track or restart a PoE camera

For a supported PoE camera port, add the **PoE power sensor** to a dashboard to see electrical consumption. The **PoE switch entity** is a separate, configuration-changing control: if you choose to create a manual recovery script, that entity can turn power off and then on again. A short off period and a deliberate user command can be useful for a hung camera.

Do not confuse the **port enabled** switch (Ethernet administrative state) with the **PoE** switch (power delivery). Do not automatically power-cycle a device simply because one polling snapshot reports an unknown state. Some switches expose power measurements without an actionable PoE control.

## Data freshness and safety

Most observations come from the last successful Integration poll, **not an instantaneous live query** each time you open an entity. The Integration polls when it starts and on its configured schedule (normally every 300 seconds); a manual refresh or a received notification can request an earlier poll. The **Refresh data** button asks for another poll. A missing sensor or unavailable configuration control does not necessarily indicate an Integration defect: the switch may not expose the requisite MIB data, the interface may not be an eligible access port, the entity may be hidden, or credentials may be read-only. Check the device's entity list, last update, the SNMP status, and the switch configuration.

Changes to port administrative state, PoE, or VLAN assignment can interrupt the devices or network paths connected to the selected port. Review the interface identity and dependencies before applying changes.
