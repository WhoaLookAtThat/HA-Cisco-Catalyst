# SNMP Notifications on Catalyst 3650

This document records the notification configuration and live validation baseline for the Home Assistant Cisco Catalyst integration.

## Validated platform

The notification work described here has been validated on:

- Cisco Catalyst **WS-C3650-48FS-S**
- Cisco IOS XE Software **16.06.08**
- IOS XE Everest **16.6.8 (fc3)**
- `CAT3K_CAA-UNIVERSALK9`
- INSTALL mode (`flash:packages.conf`)
- single-member switch with 48 PoE access ports plus 4 additional Gigabit Ethernet interfaces

Other Catalyst models and IOS/IOS-XE releases should be treated as unvalidated until separately tested.

## Authority model

SNMP traps/informs are **low-latency hints and refresh accelerators**. They are not the authoritative source of mutable switch state.

The intended flow is:

1. receive and decode the notification;
2. classify and deduplicate/rate-limit it;
3. request the smallest appropriate authoritative coordinator refresh;
4. re-read switch state over SNMP;
5. update Home Assistant entities and, when useful, emit a stable semantic HA event/diagnostic.

The normal 300-second poll remains enabled as reconciliation and fallback if a notification is lost.

## Home Assistant receiver

Notification reception is optional and disabled by default. When enabled, the integration listens on UDP **1162** by default and fires the raw diagnostic event:

`cisco_catalyst_snmp_notification`

The current receiver then requests an immediate coordinator refresh.

UDP 1162 is used instead of privileged UDP 162. The switch destination must therefore explicitly target UDP 1162 unless the network performs deliberate port forwarding.

## Validated switch-side notification families

The following Phase 1 families are enabled on the live 3650 validation switch:

```text
snmp-server enable traps snmp authentication coldstart warmstart
snmp-server enable traps cpu threshold
snmp-server enable traps flash insertion removal lowspace
snmp-server enable traps power-ethernet group 1
snmp-server enable traps power-ethernet police
snmp-server enable traps entity
snmp-server enable traps envmon fan shutdown supply temperature status
snmp-server enable traps errdisable notification-rate 2
snmp-server enable traps transceiver all
```

`fru-ctrl` is deliberately excluded from the 3650 Phase 1 target because Cisco's Catalyst 3650 IOS XE 16.6.x documentation notes that the keyword may appear in CLI help but is not supported on this device family.

StackWise and stack-power notifications are also excluded from this phase; those belong to future stack support.

## Notification destination

The production validation path uses **SNMPv3 authPriv** to the Home Assistant host on UDP 1162.

Use the actual Home Assistant IP and configured SNMPv3 username when applying the switch configuration. Do not place real credentials in documentation, diagnostics, screenshots, or issue comments.

Generic form:

```text
snmp-server host <HA_IP> traps version 3 priv <SNMPV3_USERNAME> udp-port 1162
```

SNMPv2c was also validated temporarily for compatibility testing:

```text
snmp-server host <HA_IP> traps version 2c <COMMUNITY> udp-port 1162
```

After v2c validation completed, that temporary destination was removed. SNMPv3 authPriv is the production validation configuration.

## PoE live validation

PoE notification delivery was validated on a deliberately selected non-critical PoE access port.

The POWER-ETHERNET-MIB notification received by Home Assistant was:

```text
1.3.6.1.2.1.105.0.1
```

For the selected test PSE port, the accompanying detection-status OID was:

```text
1.3.6.1.2.1.105.1.1.1.6.1.38
```

On the validated single-member switch, the PSE index mapped consistently to the intended physical test port.

Observed values during testing:

- `1` when PoE was disabled;
- `3` when the port returned to `deliveringPower`.

Both transitions were validated over **SNMPv2c** and **SNMPv3 authPriv**.

### Reconciliation result

On PoE disable, the notification arrived and the native Home Assistant port state changed effectively immediately from the user's perspective. The authoritative refresh showed:

- PoE disabled;
- powered device: no;
- consumption: 0 W;
- link down;
- speed unavailable because the port was down;
- learned MAC count dropping to 0.

On recovery, the `deliveringPower` notification arrived, then the camera completed its normal boot sequence without a manual refresh. The port returned to:

- PoE enabled;
- powered device: yes;
- link up;
- negotiated speed 100M;
- learned MAC count 1;
- approximately 2 W steady-state consumption.

This proves the notification receiver plus immediate authoritative-refresh path can update Home Assistant far sooner than the normal 300-second poll.

## Multiple notifications close together

During live testing, an independent PoE notification for another PSE port arrived close to the test-port recovery event.

Future semantic classification and deduplication must therefore key on at least the notification type and indexed object/port. Temporal proximity alone must never be used to merge or infer causality between switch events.

## Phase 1 validation status

Live validation on the 3650 now confirms:

- PoE notification delivery and immediate authoritative reconciliation over both SNMPv2c and SNMPv3 authPriv;
- SNMP authentication-failure delivery and semantic classification over the production SNMPv3 path.

Additional controlled tests produced useful platform-specific results:

- a `gbic-invalid` err-disable condition was generated on an unused uplink with err-disable notifications enabled, but the switch's `Trap PDUs` counter did not increase, so the switch did not transmit an err-disable notification for that condition;
- a temporary 1% total-CPU threshold generated `%SYS-1-CPURISINGTHRESHOLD`, but the `Trap PDUs` counter did not increase and Home Assistant received no CPU-threshold notification;
- an unsupported Dell optic was rejected before it entered transceiver inventory, so it could not be used to validate ENTITY/transceiver inventory notifications.

The remaining hardware/environmental families (fan, supply, temperature, flash/storage, supported transceiver health, and similar fault conditions) remain implementation/unit-test targets but will not be deliberately fault-injected where doing so would be intrusive or risky. They can be live-validated when a safe representative event or naturally occurring condition is available.

Stable classification is implemented for the Phase 1 notification OIDs currently known from Cisco MIB definitions. Immediate duplicates are suppressed and per-type notification storms are bounded before Home Assistant events and refresh requests are emitted. Polling remains authoritative.

## Phase 2

Phase 2 classification is implemented but still requires live acceptance on the validation switch.

The receiver recognizes standard SNMP `linkDown` (`1.3.6.1.6.3.1.1.5.3`) and `linkUp` (`1.3.6.1.6.3.1.1.5.4`) notifications as refresh hints. When the standard IF-MIB `ifIndex` varbind is present, the diagnostic event includes that index.

For Catalyst MAC notifications, Cisco's CISCO-MAC-NOTIFICATION-MIB defines:

- `cmnMacChangedNotification`: `1.3.6.1.4.1.9.9.215.2.0.1`;
- `cmnMacMoveNotification`: `1.3.6.1.4.1.9.9.215.2.0.2`.

The integration classifies these as `mac_table_change_hint` and `mac_move_hint`. A MAC-move hint may include the reported MAC address, VLAN, and source/destination bridge-port identifiers, but those fields are diagnostic input only. The notification never directly fires the integration's confirmed MAC-movement/anomaly event. It requests an authoritative coordinator refresh, after which the existing topology-aware movement tracker applies its normal confirmation and infrastructure filtering.

Cisco's Catalyst 3650 IOS XE 16.6 documentation uses `snmp-server enable traps snmp linkup linkdown` for standard link notifications and `snmp-server enable traps mac-notification move` together with `mac address-table notification mac-move` for MAC-move notifications. These commands are not yet recorded here as live-validated configuration until the Phase 2 acceptance test is performed on the WS-C3650-48FS-S.


### MAC move bridge-port resolution

CISCO-MAC-NOTIFICATION-MIB reports `from`/`to` values as IEEE 802.1D bridge-port identifiers, not physical Catalyst port numbers. The integration preserves those raw bridge-port IDs for diagnostics and resolves them through BRIDGE-MIB `dot1dBasePortIfIndex` using the latest authoritative poll. When the mapping is available, `cisco_catalyst_snmp_notification` also includes:

- `from_if_index` / `to_if_index`
- `from_interface` / `to_interface`
- `from_interface_description` / `to_interface_description` when IF-MIB `ifAlias` is populated

For example, a raw bridge-port value of `13` must not be rendered as `Gi1/0/13` unless the BRIDGE-MIB mapping actually resolves it there. Human-facing output should prefer the resolved interface name plus full `ifAlias` where space permits.
