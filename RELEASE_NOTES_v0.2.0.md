# Cisco Catalyst Integration v0.2.0 — Public Beta

This is the first **coordinated public beta milestone** for the Cisco Catalyst Integration and its companion Dashboard, not the first published version of either repository. The Integration and Dashboard are versioned together at **v0.2.0** for this milestone.

## Highlights

- Discover a compatible Cisco Catalyst switch and its physical interfaces as native Home Assistant devices and entities using SNMP.
- Monitor port link and administrative state, negotiated speed, RX/TX traffic and discard/error counters, interface descriptions, and operational VLAN information.
- Observe learned MAC addresses and source-distinguished IPv4 information: **learned endpoint IPs** from MAC/ARP correlation, **CDP neighbor IPs** advertised by connected devices, and **observed port IPs** as a deduplicated union. Address lists and additional provenance are available in entity attributes.
- Inspect CDP/LLDP neighbor diagnostics and supported PoE consumption, allocated, available and maximum-observed power entities.
- Where supported and explicitly enabled, use Home Assistant controls for port administrative status, PoE, interface descriptions, and access VLANs. VLAN management includes guarded review/confirmation and protection policies; controls are not suitable for arbitrary unmanaged switch changes.
- Expanded [Quick Start](docs/USER_GUIDE.md), [entity reference](docs/ENTITIES.md), [SNMP setup](docs/SNMP_SETUP.md), [automation examples](docs/AUTOMATIONS.md), and [VLAN management](docs/VLAN_MANAGEMENT.md) documentation.

## Companion Dashboard and compatibility

Use with [Cisco Catalyst Dashboard v0.2.0](https://github.com/WhoaLookAtThat/HA-Cisco-Catalyst-Dashboard/releases) for the coordinated interface. The companion Dashboard stable card type is `custom:cisco-catalyst-switch-card` (not the private development `-dev` type).

Live acceptance has been performed primarily against a Cisco Catalyst 3650 with Home Assistant Core 2026.11.1. Other switch models, firmware releases, and network layouts require their own validation; broad compatibility is **not** guaranteed.

## Installation and upgrade

Use the [Quick Start](docs/USER_GUIDE.md) and [public repository](https://github.com/WhoaLookAtThat/HA-Cisco-Catalyst) for Marketplace/HACS or manual installation. If the repository is not catalog-listed, follow the documented **custom repository** procedure. Take a normal Home Assistant backup before migrating from private builds or removing/re-adding the Integration: uninstall/re-add may reset configuration entries or device bindings. Do not remove an existing working configuration entry solely to upgrade files. Restart Home Assistant Core after installing or upgrading Python integration code.

Start with read-only SNMP access; enable any switch-write capability only after confirming switch mapping, permission settings and protection configuration.

## Known limitations

- Native Home Assistant IPv4 discovery sensors report address **counts** as their states; the associated IPv4 address lists are available through entity **attributes**, rather than as separate address-valued sensor states.
- Discard and error counters are cumulative switch observations. A high total does not, on its own, establish a current fault or a current rate of packet loss; no automated health-alert assessment is included.
- IP address discovery is IPv4-focused. It depends on the switch's available MAC/ARP and CDP data, so some connected devices will have no correlated endpoint IP address. This release does not provide IPv6 endpoint/neighbor correlation or optional external inventory enrichment.
- Switch-write operations are restricted by supported functionality, configured SNMP permissions and safeguards. The Integration cannot guarantee that a particular switch or firmware supports every command.
- Live validation has primarily used one Catalyst 3650 environment; compatibility with other Cisco platforms and firmware versions has not been broadly verified. This is a public beta, not a statement of production readiness.

**Beta guidance:** Monitor and validate behavior on your switch before relying on any write controls. Report issues with Home Assistant version, switch model/firmware, read-only diagnostics and reproducible observations—never post SNMP credentials.
