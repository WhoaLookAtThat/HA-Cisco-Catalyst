# VLAN Management (upcoming release)

[Documentation home](../README.md) / **VLAN Management**

[Quick Start](USER_GUIDE.md) · [SNMP setup](SNMP_SETUP.md) · [Entities](ENTITIES.md) · [Troubleshooting](TROUBLESHOOTING.md)

> This is release-candidate documentation. The VLAN Management feature is not available in older published Integration releases. Check the installed Integration version and the coordinated release notes before using these instructions.

## Open VLAN Management

Home Assistant administrators can open the panel by appending `/cisco-catalyst-vlan` to their Home Assistant URL. For example: `https://ha.example.com/cisco-catalyst-vlan`. The panel does not need to appear in the Home Assistant sidebar.

## Viewing and managing VLANs

The Existing VLANs list shows switch-reported VLAN IDs and names, detected access-port counts, protection settings and a Details action. Details describes observed access ports from the most recent Home Assistant snapshot, not necessarily a fresh switch query. Trunks and dependencies beyond the detected access ports may not be represented.

Use **Create VLAN** to enter a permitted unused VLAN ID and a name of 1–32 letters, digits, underscores or hyphens. Use **Rename** to change the name of an eligible VLAN; its VLAN ID is read-only and its existing name is prefilled. The switch and Integration independently validate requests and verify results.

The **Protected** checkbox controls the Integration's management policy. It is not a Cisco switch VLAN property. Protected VLANs cannot be renamed or deleted through the Integration. A checkbox saves asynchronously: related actions are disabled during Saving and enabled after a verified unprotect. Default and reserved VLANs retain their own restrictions.

## Moving access ports

**Move ports** lets administrators choose eligible access interfaces and an operational destination VLAN. Verify interface identities and connected equipment first: VLAN reassignment can interrupt connectivity. The Integration checks the current switch configuration and permissions before executing writes. Native per-port Access VLAN controls and the companion Dashboard Port Overview also offer eligible ordinary VLAN changes.

## Deleting VLANs

Only eligible unprotected VLANs may be deleted. A displayed zero access-port count is a cached observation and does not itself authorize a deletion. The Integration performs additional checks of the actual switch state. Follow the panel's exact confirmation instructions (for example, `DELETE 20` when deleting VLAN 20), inspect the effects, and never assume deletion automatically moves connected ports. If an operation is rejected or uncertain, verify the switch state before trying again.

## Recovering an inactive access VLAN

A port can retain an access VLAN assignment after that VLAN has been removed on the switch. The Integration marks the assignment inactive, disables normal access-VLAN selection and offers a dedicated **Review recovery** action under Inactive VLAN assignments.

Review the exact interface, its inactive source VLAN and an eligible operational destination. Type the destination-specific confirmation shown in the panel, for example `RECOVER TO 20` for a destination of VLAN 20. A successfully verified recovery closes its form and leaves a success message. If verification fails or is uncertain, inspect the switch before retrying.

Only one management activity (Create, Rename, Delete, Move, Details or Recovery) is intended to remain open at once. This frontend behavior does not replace switch-side validation or backend authorization.

## Permissions and refresh behavior

Monitoring can operate with read-only SNMP credentials. Changing VLANs or port assignments requires appropriately configured read/write SNMP permissions and Home Assistant administrator authorization. Capabilities differ by switch model, VTP state and IOS/IOS XE version.

Home Assistant typically polls every 300 seconds; a notification or Refresh data may update its observations earlier. On-screen inventory is a cached observation, while write handlers must validate switch state before and after a change.

For prerequisites, see [SNMP setup](SNMP_SETUP.md); for entity behavior, see [Entities](ENTITIES.md).
