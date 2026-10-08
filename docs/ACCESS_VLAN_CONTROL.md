# Access VLAN write development notes

This document is private development material. Publish only sanitized behavior and generic examples.

## Scope

The first VLAN write implementation supports only a single static access VLAN through
CISCO-VLAN-MEMBERSHIP-MIB:

- `vmVlanType.<ifIndex>` — membership type
- `vmVlan.<ifIndex>` — single VLAN ID

The control is created only when all of these are true:

- the Home Assistant config entry declares Credential access = Read/write;
- `vmVlan` is present for the physical interface;
- `vmVlanType == static(1)`;
- the coordinator has positively identified the interface as non-trunk;
- the current and requested VLAN IDs are present as operational VLANs in CISCO-VTP-MIB.

The control refuses dynamic, multiVlan, unknown-mode, trunk, missing-table, nonexistent-VLAN,
and non-operational-VLAN cases. It never uses a port-membership SET as a way to create a VLAN.

## Authority and write transaction

The existing serialized write helper is used:

1. serialize against other writes and coordinator I/O;
2. send one INTEGER SET to the exact `vmVlan.<ifIndex>` OID;
3. GET the exact same OID until the returned value matches;
4. publish the exact-OID verified value;
5. request a full coordinator refresh for related state;
6. retain polling as the long-term source of truth.

A successful SET response by itself is never treated as success.

## VLAN range

The Home Assistant control accepts integer VLAN IDs 1 through 4094, except Cisco's
legacy FDDI/Token Ring VLAN IDs 1002 through 1005.

VLAN 0 is intentionally rejected for this first implementation because static membership
must remain assigned to a VLAN. The integration does not create VLANs, and the switch
remains authoritative for platform-specific/internal VLAN restrictions.

## Explicitly out of scope

- changing `vmVlanType`;
- dynamic VMPS membership;
- multiVlan membership and `vmVlans*` bitmaps;
- trunk native VLAN writes;
- trunk allowed-VLAN writes;
- VLAN create/delete;
- automatically creating a missing VLAN.

## First live acceptance gate

Use a deliberately selected unused static access port whose current VLAN is already known.

The first live write should be a no-op: set the access VLAN to its current VLAN value.
Acceptance requires:

- Home Assistant service/entity write returns successfully;
- exact-OID readback is accepted by the integration;
- the entity remains at the expected VLAN;
- switch CLI still reports the same access VLAN and no unexpected configuration changes;
- no unrelated interface or VLAN state changes.

Only after this no-op gate is proven should a reversible change to a different existing
test VLAN be considered.


## Migration from the temporary number entity

Development builds briefly exposed access VLAN as a Home Assistant `number` entity.
The current implementation uses a `select` entity so only existing operational VLANs
can be chosen.

On integration setup, the integration removes its own stale legacy access-VLAN
`number` registry entries automatically. The replacement `select` entity is preserved.

After updating and restarting Home Assistant:

1. Open the physical port device page.
2. Confirm the access-VLAN control is a dropdown/select and contains only VLANs that
   currently exist and are operational on the switch.
3. Confirm the prior unavailable access-VLAN number entity is gone.
4. If a stale legacy number entity remains unexpectedly, remove only that unavailable
   entity from Home Assistant's entity settings; do not remove the replacement select
   entity.
5. For live validation, choose the port's current VLAN first so the initial SET is a
   no-op, then verify the switch state from IOS.
