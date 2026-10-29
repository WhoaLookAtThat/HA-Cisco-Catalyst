# SNMP Setup and Permissions

[Documentation home](../README.md) / **SNMP setup**

[Quick Start](USER_GUIDE.md) · [SNMP setup](SNMP_SETUP.md) · [Entity reference](ENTITIES.md) · [Automations and events](AUTOMATIONS.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Documentation index](DOCUMENTATION_INDEX.md)

## On this page

- [Where SNMP is configured](#where-snmp-is-configured)
- [Configuration placeholders](#configuration-placeholders)
- [SNMPv2c permissions and ACLs](#snmpv2c-permissions-and-acls)
- [SNMPv3 views and permissions](#snmpv3-views-and-permissions)
- [Polling versus notifications](#polling-versus-notifications)
- [Units and missing values](#units-and-missing-values)

## Where SNMP is configured

SNMP users, communities, access lists (ACLs), and notification destinations are configured **on the Cisco switch**, not by the Home Assistant Integration. An ACL is **not automatically installed** by the Integration. Whether a switch already has one must be checked in its running configuration. Cisco IOS/IOS XE syntax and available security features depend on the model and software release.

## Configuration placeholders

| Placeholder | Replace with |
| --- | --- |
| `<HA_IP>` | Home Assistant's reachable IP address; for a switch SNMP notification destination, use an IP address rather than assuming `homeassistant.local` resolves |
| `<COMMUNITY>` | SNMPv2c community string configured on the switch |
| `<RO_COMMUNITY>` | Read-only SNMPv2c community string |
| `<RW_COMMUNITY>` | Read/write SNMPv2c community string, if write access is intended |
| `<SNMPV3_USERNAME>` | SNMPv3 user name configured on the switch |
| `<HA_ACL>` | Number or name of a switch ACL allowing the intended Home Assistant source |
| `<SWITCH_IP>` | Management IP address of the Cisco switch |

Never copy angle-bracket placeholders literally into a production configuration.

## SNMPv2c permissions and ACLs

Read-only and read/write community names **can** be separate. Access restrictions using Cisco switch ACLs are recommended but must be explicitly configured; neither the Integration nor Home Assistant creates these switch ACLs.

An *illustrative* IOS-style restriction using a numbered standard ACL is:

```text
configure terminal
access-list 10 permit <HA_IP>
snmp-server community <RO_COMMUNITY> RO 10
! Optional, only when writes are required:
snmp-server community <RW_COMMUNITY> RW 10
end
```

Review existing ACL 10 before using it; never overwrite or extend an ACL blindly. Check the exact command syntax, SNMP views, existing communities, and access path against your Cisco model/software documentation before applying. Use the SNMPv2c read community in Home Assistant; provide the write community and select read/write only when you intend to permit changes.

## SNMPv3 views and permissions

Cisco SNMPv3 group configuration links a user to an SNMP security level and a MIB view. A **read view** must contain the objects needed for polling, and a **write view** must include the specific objects changed by enabled controls (such as interface admin status, PoE state, interface description, or access VLAN). A user may authenticate successfully yet lack access to some MIBs.

To inspect existing settings in Cisco IOS/IOS XE, use the supported commands for your switch, commonly `show snmp user`, `show snmp group`, and `show running-config | include snmp-server view|snmp-server group|snmp-server user`. Some user secrets do not appear in the normal running configuration. Consult the device-specific [Cisco technical documentation](https://www.cisco.com/c/en/us/support/switches/index.html) for SNMPv3 USM users, groups, views, and ACL syntax. Do not give a view broader read/write permissions than necessary.

## Polling versus notifications

The Integration performs an initial read when the entry starts, then scheduled polling at its configured interval (300 seconds is the documented normal/default interval). A manual **Refresh data** action requests an additional poll. A received SNMP trap/inform can request an immediate reconciliation poll when the optional listener is enabled. Changes performed through supported Integration controls are checked against switch state. Opening a Home Assistant dashboard does not by itself guarantee a fresh SNMP read.

## Units and missing values

Home Assistant can convert supported temperature entities between Celsius and Fahrenheit according to the user/system unit settings; change **Settings → System → General → Unit system** (labels vary by Home Assistant version), or use the entity's display-unit setting if offered. Raw SNMP measurements and discrete diagnostic labels are not necessarily converted. An unavailable reading is usually represented by Home Assistant as `unknown` or `unavailable`, not by a universal `N/A` string.
