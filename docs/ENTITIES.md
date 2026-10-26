# Cisco Catalyst — Entities and Home Automation

[Start: User Guide](USER_GUIDE.md) · [Install / configure](../README.md#installation)

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
| **MAC movement anomalies** · sensor | Count of detected noteworthy MAC-address movement events. | Investigate a device unexpectedly moving between ports; treat it as an investigation clue, not automatic proof of a security attack. |
| **Dashboard contract** · diagnostic sensor | Schema/metadata marker used by the companion dashboard to discover stable Catalyst entity roles. | Troubleshoot dashboard compatibility; normally not useful as a household automation trigger. |
| **Refresh data** · button | Requests a new Integration poll. It **does not reset the switch** or perform an SNMP write. | Press after moving a cable or editing settings directly at the switch to update Home Assistant's readings. |

For alerts, use suitable time conditions and handle `unknown` or `unavailable` separately from actual fault values. Hardware-specific sensors may not exist on every Catalyst.

## Port devices — state, counters, and diagnostics

| Entity / domain | What it reports | Example home-lab use |
| --- | --- | --- |
| **<port> link** · binary sensor | Physical operational link is up/down, not whether the administrative control is enabled. Its attributes can include port mode, VLAN and discovered endpoint/neighbor information. | Alert when the cable link for an always-on access point goes down for several minutes. |
| **<port> RX bytes** · sensor | Cumulative received byte counter (64-bit when available). | Plot receive traffic rate using a derivative/rate helper; raw bytes are a counter, **not instantaneous Mbps**. |
| **<port> TX bytes** · sensor | Cumulative transmitted byte counter. | Compare outbound traffic trends between uplinks and end-device ports. |
| **<port> speed** · diagnostic sensor | Reported interface speed. | Spot a device negotiating at 100 Mbps rather than its expected 1 Gbps. |
| **<port> errors** · diagnostic sensor | Interface error counter from the switch. | Look for increasing errors after changing a cable; use the change over time rather than a nonzero total alone. |
| **<port> RX discards** · diagnostic sensor | Cumulative received packets discarded. | Check persistent increases when investigating congestion or device/network problems. |
| **<port> TX discards** · diagnostic sensor | Cumulative transmitted packets discarded. | Investigate drops on a busy uplink or oversubscribed port. |
| **<port> network mode** · diagnostic sensor | Access/trunk and related operational network/VLAN facts where reported. | Confirm an AP uplink is a trunk before investigating VLAN availability. |
| **<port> learned MACs** · diagnostic sensor | Learned endpoint MAC/address details, to the extent available from switch tables. | Find the port to which a particular wired device appears connected. |
| **<port> PoE power** · diagnostic sensor | Per-PoE-port measured draw or power-related detail, where supported. | Confirm a powered camera or access point is drawing power. |

Port link attributes may also contain learned IP/MAC addresses, CDP/LLDP neighbor details, access VLAN, native VLAN and allowed VLANs where the switch reports them. These are **attributes**, not separate controls. A trunk's allowed VLAN list is observational; the Integration is not promising a trunk-edit selector.

An example automation could trigger when `binary_sensor.gi1_0_3_link` remains `off` for five minutes and send a mobile notification. Replace the illustrative ID with the one Home Assistant actually created. If you intentionally turn off that port, the link-down notification is expected.

## Port controls — actions that can change switch configuration

| Entity / domain | What you can do | Home-lab example and caution |
| --- | --- | --- |
| **<port> port enabled** · switch | Administratively enable or disable Ethernet operation on a port; different from PoE power. | Temporarily isolate a lab machine. Disabling an uplink or the port used for switch management could interrupt access. |
| **<port> PoE** · switch | Enable or disable switch PoE power to a supported device. | Power-cycle a PoE camera or AP without turning off the Ethernet administrative port; first confirm this is the intended port. |
| **<port> description** · text | Read/edit the switch interface description (`ifAlias`), where write access permits. | Label a jack `Garage-Camera` so devices and dashboards have useful names. |
| **<port> access VLAN** · select | Choose among switch-reported eligible operational access VLANs for a supported static access port. | Move a test device to an isolated VLAN after you have created the destination VLAN. This is not for trunk ports. |

**Read-only access:** Measurements still work with supported read-only SNMP credentials, while configuration-changing features may be unavailable, not actionable, or blocked. Switch and PoE controls may remain visible as observations, depending on the entity. Read/write capability is not a blanket permission to change a protected port; the Integration and switch both enforce their own restrictions.

The Integration's source also contains a legacy numeric access-VLAN implementation (`number` domain). The current supported access-VLAN experience is the **select** entity; do not treat a historic `number.<port>_access_vlan` and a `select.<port>_access_vlan` as two independent current controls.

## Practical automation patterns

**Network availability.** Monitor important port *link* sensors for sustained down periods, preferably with a delay that excludes normal cable moves or device restarts. This tests the Ethernet connection, not whether the connected application is healthy.

**PoE device recovery.** A user-created script can turn a PoE switch off and on when a camera or access point is unresponsive. This is a **real power interruption**; use an appropriate delay and avoid loops that repeatedly reboot an unhealthy device. Do not base the action only on the port being down.

**Capacity tracking.** Take a derivative or rate of RX/TX byte counters to observe throughput over time. Keep units straight (bytes/s versus bits/s) and account for counter resets or device restarts.

**Environmental awareness.** Combine CPU, memory, chassis temperature, fan and supply status in a household maintenance dashboard. Define your own baseline and alert durations; a second power supply listed as Off may simply not be installed.

**Port labeling.** Use the description text control to document connected equipment. Its configured value is read from the switch; changes are not merely cosmetic dashboard labels.

**VLAN assignments.** Use supported per-port access-VLAN selectors to change a single eligible port; avoid treating a trunk/native VLAN attribute as an editable access VLAN.

## Data freshness and safety

Most observations come from the last successful Integration poll, **not an instantaneous live query** each time you open an entity. The **Refresh data** button asks for another poll. A missing sensor or unavailable configuration control does not necessarily indicate an Integration defect: the switch may not expose the requisite MIB data, the interface may not be an eligible access port, the entity may be hidden, or credentials may be read-only. Check the device's entity list, last update, the SNMP status, and the switch configuration.

For all switch-changing controls, test with noncritical ports first. An action on a port can interrupt its connected equipment or network path. You do not need an enterprise procedure to run your home lab, but you do need to know which port you are controlling.
