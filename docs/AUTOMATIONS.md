# Home Assistant Automations and SNMP Events

[Documentation home](../README.md) / **Automations and events**

[Quick Start](USER_GUIDE.md) · [SNMP setup](SNMP_SETUP.md) · [Entity reference](ENTITIES.md) · [Automations and events](AUTOMATIONS.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Documentation index](DOCUMENTATION_INDEX.md)

## On this page

- [Where to find entity-based examples](#where-to-find-entity-based-examples)
- [Monitoring versus changing a port](#monitoring-versus-changing-a-port)
- [Build a link-down notification](#build-a-link-down-notification)
- [Graph bandwidth and environment](#graph-bandwidth-and-environment)
- [SNMP notifications: event and refresh](#snmp-notifications-event-and-refresh)
- [Notification families](#notification-families)

## Where to find entity-based examples

[Entity Reference](ENTITIES.md) explains the meaning, units, and sample data of the Integration's entities. Use the actual entity IDs assigned by your Home Assistant instance.

## Monitoring versus changing a port

Link-state alerts, bandwidth-rate helpers, environmental graphs, and network health checks are observations and do not modify the switch. PoE toggling, port administrative enable/disable, description edits, and access VLAN changes are configuration actions. Decide which monitored ports are important in your own environment.

## Build a link-down notification

In **Settings → Automations & scenes**, create a state trigger using the intended port's link binary sensor. Set the target state to `off` for an appropriate duration (for example, five minutes), then add your mobile notification action. Handle `unknown`/`unavailable` separately to avoid treating missing data as a cable failure. The port name and entity ID vary across Gigabit, TenGigabit and other supported interface types.

## Graph bandwidth and environment

RX/TX byte sensors are cumulative counters, not speeds. Use a Home Assistant derivative helper to calculate bytes per second, or convert to bits per second if needed. Counter resets can create spikes; review chart statistics and helper settings. For the switch, chart temperature, CPU utilization (%), memory used (%), PoE power (W), fan status, and power supply status. The optional companion dashboard currently emphasizes port layout/details rather than providing a dedicated capacity/environment overview.

## SNMP notifications: event and refresh

When enabled, the optional listener receives SNMP notifications on UDP **1162** by default and emits the Home Assistant event `cisco_catalyst_snmp_notification`. It also requests a fresh poll. The event signals that a notification arrived; automation logic should inspect event data and/or wait for refreshed entity state rather than assuming the trap alone proves current conditions.

To inspect events, open **Developer Tools → Events**, listen for `cisco_catalyst_snmp_notification`, and observe received fields in your own system. An automation can use an **Event** trigger with this event type and optionally filter actual observed event data. Avoid copying unverified event-data keys from examples.

## Notification families

Switch notification capabilities depend on Cisco hardware and configuration. Common families include startup/authentication, CPU thresholds, temperature/fans/power supply, PoE, entity/FRU, err-disable, flash, transceiver, link, and MAC change. Enabling a family on the switch is separate from enabling reception in the Integration. Receiving a trap does not imply that Home Assistant provides a dedicated sensor or automatic handling for that family.

See [SNMP Setup](SNMP_SETUP.md) for destination placeholders, and the repository's advanced [SNMP notification technical reference](SNMP_NOTIFICATIONS.md) when available. Treat family coverage and firmware support as switch-dependent.
