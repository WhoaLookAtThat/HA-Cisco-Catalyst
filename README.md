# Cisco Catalyst for Home Assistant

A custom Home Assistant integration for monitoring and controlling Cisco Catalyst switches over SNMP.

The first release is being developed against a **Cisco Catalyst 3650 48-port PoE+ switch**. It supports SNMPv2c and SNMPv3 authPriv, with optional SNMP trap/inform reception for immediate reconciliation.

## Features

- Represents the Catalyst switch as a single Home Assistant device.
- Discovers physical Ethernet interfaces from IF-MIB, including the primary front-panel group and additional/module ports.
- Creates link-state binary sensors for discovered access interfaces.
- Creates 64-bit RX/TX byte counters from IF-MIB.
- Shows interface speed and interface diagnostics.
- Exposes the Cisco interface description (`ifAlias`) as a Home Assistant text entity whose current value remains readable even when the configured SNMP credentials cannot write.
- Creates a per-port administrative enable/disable switch using `ifAdminStatus`; its observed state remains visible with read-only credentials.
- Discovers learned MAC addresses and correlates known IP addresses to physical ports when the switch tables provide enough information.
- Exposes CDP and LLDP neighbor information as port attributes when available.
- Exposes access VLAN and operational trunk/native/allowed VLAN information when the relevant Cisco MIBs are available.
- Discovers Cisco PoE ports through CISCO-POWER-ETHERNET-EXT-MIB.
- Creates per-port PoE switches only when the Cisco ENTITY-MIB mapping resolves to a discovered access interface; observed PoE state remains visible with read-only credentials.
- Keeps Ethernet administrative state and PoE administrative state as separate controls.
- Uses one coordinated poll rather than independent polling for every Home Assistant entity.
- Exposes chassis identity, temperature, fan, power-supply, CPU, memory, and PoE power telemetry when supported.
- Supports configurable polling, diagnostics download, SNMPv3 authPriv, and optional trap/inform-triggered refreshes.
- Treats optional MIBs as capabilities: an unavailable optional table omits that feature instead of failing the integration.

On the development Catalyst 3650, the `Gi1/1/x` uplink/module interfaces are exposed as additional physical-port child devices.

### Dashboard contract

The integration exposes an explicit frontend contract so dashboards do not need to parse user-editable names, entity IDs, or private `unique_id` conventions.

Each physical-port entity exposes `cisco_catalyst_role` plus stable interface metadata including `interface_id`, `interface_name`, `if_index`, `is_physical`, `physical_group`, `physical_position`, and structured `member` / `slot` / `port` coordinates. The existing `physical_member`, `physical_slot`, and `physical_port` aliases are retained for compatibility.

Contract-v1 port roles are `link`, `speed`, `rx_bytes`, `tx_bytes`, `errors`, `admin`, `description`, and `poe`. Role identifiers are stable lowercase API values and are not translated.

A parent-device diagnostic sensor named **Dashboard contract** advertises `dashboard_contract_version: 1`, `cisco_catalyst_role: switch`, and `is_cisco_catalyst_switch: true`. This lets dashboards recognize a Catalyst parent device without using PoE support as a proxy.

The contract metadata is exposed as Home Assistant entity state attributes because Home Assistant's device registry does not provide a supported integration-defined arbitrary metadata field. Parent/child device-registry relationships remain authoritative for grouping. Existing live link/VLAN/neighbor/PoE attribute payloads remain unchanged in contract v1.

## Required switch configuration: persistent IF-MIB indexes

> **IMPORTANT — REQUIRED BEFORE ADDING THE SWITCH TO HOME ASSISTANT**
>
> This integration uses the IF-MIB `ifIndex` as part of each interface entity's stable Home Assistant identity. **Configure Cisco ifIndex persistence before adding the integration.** Without persistence, Cisco IOS/IOS-XE may assign different `ifIndex` values after a switch reboot, which can cause Home Assistant interface entities to be duplicated, missing, or associated with a different physical port.

On supported Cisco IOS/IOS-XE Catalyst switches, enable global ifIndex persistence with:

```text
configure terminal
snmp-server ifindex persist
end
write memory
```

Verify the running configuration contains the setting before configuring Cisco Catalyst in Home Assistant:

```text
show running-config | include snmp-server ifindex persist
```

Expected output:

```text
snmp-server ifindex persist
```

This is a **supported-configuration requirement**, not an optional recommendation. If a particular Catalyst/IOS-XE release uses different Cisco syntax for ifIndex persistence, configure the equivalent Cisco-supported persistence mechanism and verify it before adding the integration.

## SNMP configuration

The integration supports either SNMPv2c or SNMPv3.

For SNMPv2c, configure separate read-only and read-write communities and restrict them with an ACL so only the Home Assistant host can reach them. SNMPv2c community strings are not encrypted.

For SNMPv3, the configuration flow supports authenticated and encrypted USM access (authPriv) with SHA/SHA-256 authentication and AES-128 privacy. Use an IOS/IOS-XE SNMPv3 user whose views/permissions allow the MIB objects required by the features you intend to use.

Optional trap/inform reception is disabled by default. When enabled in integration options, Home Assistant listens on UDP port 1162 by default, fires a `cisco_catalyst_snmp_notification` event, and requests an immediate authoritative poll. Port 1162 avoids the privileged-port requirement of UDP 162; configure the switch notification destination or network forwarding accordingly. Periodic polling remains enabled as reconciliation/fallback.

## Read-only vs write access

The integration asks you to declare the effective permission level of the configured SNMP credentials:

- **Read-only** — Home Assistant may poll and display switch state, but the integration blocks supported SET operations locally.
- **Read/write** — Home Assistant allows supported SET operations in addition to polling.

This declaration is necessary because Home Assistant can safely verify that SNMP reads work, but it cannot reliably discover write permission without attempting a SET and therefore changing switch state. The **Credential access** field in Add Integration and Reconfigure is the user's statement of the permissions already configured on the Cisco switch.

When read access succeeds, Home Assistant keeps showing the current observed values for configuration-related entities such as port administrative state, PoE administrative state, and interface description. Those entities are **not marked unavailable merely because Credential access is Read-only**. In this integration, `unavailable` is reserved for cases where the entity's state cannot be read or its underlying coordinator/device data is unavailable.

Configuration-related entities keep their normal Home Assistant entity types so their observed state remains visible:

- port administrative state remains a `switch`;
- PoE administrative state remains a `switch`;
- interface description remains a `text` entity.

If Credential access is **Read-only**, attempts to use those controls are rejected by the integration before any SNMP SET is sent. Reconfigure the entry as **Read/write** only after the switch credentials actually permit writes.

SNMP-specific details:

- **SNMPv2c:** polling uses the configured read community and supported SET operations use the configured write community. Selecting Read/write requires both a nonblank read community and a nonblank write community. Selecting **Read-only** deliberately clears any saved write community and any saved SNMPv3 credentials when the form is submitted. This prevents inactive write credentials or credentials from another SNMP version from remaining stored. If you later switch back to Read/write or SNMPv3, you must enter those credentials again. A nonblank write community still does not prove that Cisco grants SET permission, so the declaration must match the switch configuration.
- **SNMPv3:** the same authPriv user is used for reads and supported SET operations. Username, authentication key, and privacy key are required. Saving SNMPv3 deliberately clears any saved SNMPv2c read/write communities; switching back to SNMPv2c requires entering the communities again. The Cisco SNMPv3 group/view permissions determine whether that user actually has write access. The declared Credential access must match those permissions.
- If Credential access is Read/write but Cisco still rejects a SET, Home Assistant reports the write failure and the integration returns to the authoritative state read from the switch.

The setup and Reconfigure forms provide a short explanation, while the help text for **Credential access** explains why Home Assistant asks the question. The integration's **?** documentation link points directly to this section.

## Installation

There are two installation methods. **HACS is the easier method once this repository has a usable release.** Manual installation is useful during development and testing.

### Manual installation

Manual installation means downloading the integration's actual files from this repository and placing them in Home Assistant. The text `custom_components/cisco_catalyst/` below is a directory path, not something to paste into Home Assistant.

1. Download or clone this GitHub repository. For a published release, use the release/tag you intend to install; use a development branch only when deliberately testing unreleased code.
2. In the downloaded repository, locate this directory:

   ```text
   custom_components/cisco_catalyst/
   ```

3. Copy the **entire `cisco_catalyst` directory and all files/directories inside it** into your Home Assistant configuration directory so the final layout is:

   ```text
   /config/custom_components/cisco_catalyst/
       __init__.py
       manifest.json
       config_flow.py
       const.py
       coordinator.py
       entity.py
       sensor.py
       binary_sensor.py
       switch.py
       text.py
       button.py
       diagnostics.py
       snmp.py
       trap.py
       write.py
       strings.json
       translations/
           en.json
       brand/
           icon.png
           logo.png
   ```

   If `/config/custom_components/` does not already exist, create it first.

4. Restart **Home Assistant Core** after the files have been copied.
5. In Home Assistant, go to **Settings → Devices & services**.
6. Select **Add Integration**.
7. Search for **Cisco Catalyst**.
8. Enter the switch connection and SNMP credentials, then declare whether those credentials are effectively **Read-only** or **Read/write** on the switch.

If **Cisco Catalyst** does not appear after the restart, first check **Settings → System → Logs** for a custom-component import or manifest error. A browser hard refresh can also be necessary after adding a new custom integration.

#### Manually updating an existing installation

If you originally installed Cisco Catalyst manually, update it by replacing the integration files with the files from the newer repository version. You do **not** normally need to remove the integration from **Settings → Devices & services**, and replacing the Python files does not by itself remove the existing Home Assistant config entry.

1. Download the newer repository version you want to install. For normal updates, use the intended published release/tag; select a development branch only when deliberately testing unreleased code.
2. In the download, locate:

   ```text
   custom_components/cisco_catalyst/
   ```

3. In Home Assistant, locate the existing installation:

   ```text
   /config/custom_components/cisco_catalyst/
   ```

4. Replace the **entire contents** of the existing `/config/custom_components/cisco_catalyst/` directory with the contents of the newer repository's `custom_components/cisco_catalyst/` directory. Make sure new files and subdirectories are copied too.
5. If a file existed in the old integration but has been removed from the newer repository version, remove that obsolete file from the Home Assistant copy as well. The safest approach is to replace the whole `cisco_catalyst` directory rather than copying only changed `.py` files.
6. Restart **Home Assistant Core** so Home Assistant loads the updated Python code.
7. After the restart, open **Settings → System → Logs** and check for `cisco_catalyst` import, setup, or migration errors.
8. Open **Settings → Devices & services → Cisco Catalyst** and confirm the integration and entities still load as expected.

Do not mix manual and HACS installation methods for the same integration. If the integration was installed manually, continue updating it manually unless you intentionally migrate to HACS later.

### HACS installation

HACS (Home Assistant Community Store) can download and update custom integrations for Home Assistant. In these instructions, **"the repository" means this GitHub repository: `WhoaLookAtThat/HA-Cisco-Catalyst`**.

This repository is intended to be installed through HACS as a **custom repository** unless/until it is accepted into HACS's default catalog:

1. Make sure HACS is already installed and configured in Home Assistant.
2. Open **HACS** in Home Assistant.
3. Open the HACS menu and choose **Custom repositories**. Depending on the HACS frontend version, this is normally under the three-dot menu.
4. In **Repository**, copy and paste this exact URL:

   ```text
   https://github.com/WhoaLookAtThat/HA-Cisco-Catalyst
   ```

5. For **Type/Category**, select **Integration**.
6. Add the repository.
7. Open the newly added **Cisco Catalyst** repository in HACS.
8. Select **Download** and choose the version offered by HACS.
9. Restart Home Assistant Core when HACS asks you to, or restart it manually after the download completes.
10. Go to **Settings → Devices & services → Add Integration** and search for **Cisco Catalyst**.
11. Enter the switch connection details, choose SNMPv2c or SNMPv3, provide the credentials for that mode, and declare whether those credentials are effectively Read-only or Read/write.

HACS handles copying the integration into Home Assistant's `custom_components` directory. You should **not** also manually copy a second copy when using the HACS method.

> **Development note:** HACS normally installs tagged GitHub releases. If you intentionally need to test an unreleased development branch, manual installation is the most predictable way to test that exact branch.

## Configuration

The UI configuration flow asks for the switch host, SNMP port, SNMP version, credentials, and the declared **Credential access** level (Read-only or Read/write). Existing config entries can be reconfigured from the integration menu to update the host, credentials, SNMP version, or declared access level without removing and re-adding the entry.

The integration verifies the supplied SNMP credentials by querying `sysName` before creating or reconfiguring the config entry. Polling interval and optional trap/inform reception are configured through integration options.

## Tested Catalyst 3650 interface mapping

On the development Catalyst 3650, IF-MIB reports the 48 access ports as `GigabitEthernet1/0/1` through `GigabitEthernet1/0/48`, with IF-MIB indexes 8 through 55. The four `GigabitEthernet1/1/x` uplinks follow at indexes 56 through 59.

The standard/Cisco PoE tables expose 48 PSE rows indexed `1.1` through `1.48` on this single-member switch. Cisco's PSE-to-ENTITY table maps those rows to ENTITY indexes 1061 through 1108, which ENTITY-MIB identifies as `Gi1/0/1` through `Gi1/0/48`. The integration requires this mapping to resolve before exposing a PoE control.

## PoE control

PoE discovery/control uses `CISCO-POWER-ETHERNET-EXT-MIB`. PoE writes use `cpeExtPsePortEnable`:

- `auto(1)` when a Home Assistant PoE switch is turned on
- `disable(4)` when it is turned off

Ethernet administrative state is controlled separately through IF-MIB `ifAdminStatus`.

## Current status

**0.1.0 is the initial release line.** Development and real-device validation have been performed against a Catalyst 3650 running IOS XE, including SNMPv2c and SNMPv3 authPriv read/write operation, repeated Reconfigure reloads, interface-description and PoE writes, trap/inform reception, dashboard-contract metadata, and stable Home Assistant device/entity identity across protocol changes.

New installations should still begin by verifying read-only discovery before relying on write controls. Confirm that discovered Home Assistant port names correspond to physical switch ports and that PoE controls are either mapped to the correct physical interfaces or omitted. An absent PoE control is preferable to an uncertain ENTITY-MIB mapping.

The Catalyst 3650 has had historical Cisco IOS XE bugs involving PoE SNMP/entity index mapping, so current switch software and verification of the discovered mapping are recommended.

For the first write test on a new switch/model/software combination, use a deliberately chosen non-critical port. Change only its description first, verify the corresponding IOS `description`, then restore it. After that, test Ethernet administrative state and PoE only on a port whose attached device can safely be disconnected or power-cycled. Avoid testing against the Home Assistant host's own network path or any switch uplink.

## Remaining before 0.1 release

- Complete the final release-readiness review of the development branch and Draft PR.
- Choose and add a project license before publishing the first general-use release.
- Protect the `main` branch with a repository ruleset (tracked separately as a GitHub issue).

## License

This project is licensed under the MIT License. See `LICENSE`.

## AI-assisted development

This project was developed with substantial assistance from **OpenAI ChatGPT, GPT-5.6 Sol**.

The AI has been used as an engineering assistant for architecture, Home Assistant/HACS documentation research, implementation, tests, build/CI work, code review, and repository maintenance. Changes are committed to the repository and validated by automated tests/build checks so readers can inspect the resulting source rather than relying on AI-generated claims.

Useful context for evaluating that contribution:

- **Model:** GPT-5.6 Sol.
- **Role:** AI engineering assistant; the project owner directs requirements, architecture boundaries, deployment, and real-device validation.
- **Tool access during development:** repository read/write access through the GitHub integration, current public web/documentation research, and isolated code/tool execution where available.
- **Validation:** automated tests, build/static validation where applicable, and repository CI checks are used to validate changes.
- **Limits:** the model does not independently operate or continuously observe the user's Home Assistant instance or Catalyst switch. Real-device behavior must therefore be validated against the user's Home Assistant environment.
- **Reproducibility:** source, tests, build/validation configuration, and distributable artifacts where applicable are kept in the repository so changes can be reviewed without requiring access to the original ChatGPT conversation.

AI assistance does not imply endorsement, review, or support by OpenAI, Home Assistant, HACS, or Cisco.
