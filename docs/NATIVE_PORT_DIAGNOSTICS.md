# Native port topology diagnostics

Starting with v0.1.2, each physical Cisco Catalyst port child device exposes two additional diagnostic sensors in Home Assistant. They mirror switch facts already collected by the coordinator for dashboard use, so they do not add SNMP polling.

## Network mode

The **network mode** diagnostic sensor reports one of:

- `access` when the switch explicitly reports a non-trunk port;
- `trunk` when the switch explicitly reports trunk operation;
- `unknown` when the relevant optional Cisco MIB data is unavailable or does not establish the mode.

When available, attributes include:

- `access_vlan`
- `native_vlan`
- `allowed_vlans_count`
- `allowed_vlans`
- `allowed_vlans_truncated`
- `cdp_neighbor_count`
- `lldp_neighbor_count`
- `neighbor_discovered`

The allowed-VLAN list is unrecorded and capped at 128 entries. `allowed_vlans_count` retains the full current count and `allowed_vlans_truncated` indicates whether the displayed list was capped.

## Learned MACs

The **learned MACs** diagnostic sensor uses the current learned-MAC count as its state. This is switch forwarding-table visibility downstream of the port; it does **not** prove that every learned MAC is directly cabled to that port.

When present, attributes include:

- `mac_addresses`
- `mac_addresses_truncated`
- `learned_ip_count`
- `ip_addresses`
- `ip_addresses_truncated`

MAC and IP address lists are unrecorded and capped at 64 entries each. The entity state remains the full learned-MAC count even when the displayed list is capped.

## Optional data

Optional MIB absence does not fail the integration. Unsupported VLAN values are omitted from attributes, and network mode remains `unknown` when the switch data does not establish access or trunk operation.
