# Cisco Catalyst — User Guide

**Start here:** [Project README](../README.md) for what the Integration does, supported hardware, switch SNMP preparation, installation, and initial setup. This **User Guide** is the table of contents for everyday use. It is intended for a technically capable homeowner or home-lab administrator, not an enterprise change-control process.

## Reading order

1. **[README: installation and first setup](../README.md#installation)** — install with HACS or manually, add Cisco Catalyst in Home Assistant under **Settings → Devices & services**, and configure SNMP.
2. **[Entities and automation examples](ENTITIES.md)** — what Home Assistant devices, entities, states and attributes mean, and realistic automations for links, PoE, bandwidth, environmental health, and VLAN controls.
3. **[SNMP configuration and permissions](../README.md#snmp-configuration)** and **[read-only versus write access](../README.md#read-only-vs-write-access)** — choose monitoring only or enable supported switch controls.
4. **[Optional dashboard](https://github.com/WhoaLookAtThat/HA-Cisco-Catalyst-Dashboard)** — the dashboard is a separate project and release, not a prerequisite for Integration entities.
5. **[Troubleshooting and diagnostics](../README.md#features)** — entity and diagnostic explanations start in the entity reference; check the Integration logs, the device's SNMP status, and switch-side connectivity if values are unavailable.

## What appears in Home Assistant

Under **Settings → Devices & services → Cisco Catalyst**, the Integration creates a *switch device* with overall health information and separate *port devices* with per-interface readings and (when configured and supported) controls. Open a device's **Entities** list. Some troubleshooting and configuration entities are hidden from default dashboard views; they still appear in the device/entity details.

An **entity** is a Home Assistant state or control such as `binary_sensor.<port>_link`, `sensor.<port>_rx_bytes`, `switch.<port>_poe`, or `text.<port>_description`. Names and entity IDs are examples; Home Assistant may generate different IDs based on your switch name and registry. An entity can be used in automations, dashboards, history, or scripts. An **attribute** provides additional detail attached to an entity rather than a separate entity.

Entity availability depends on your model, switch-reported MIB data, discovered ports, credentials, and the installed Integration version. Read-only SNMP access permits monitoring; **switch-changing actions require the Integration's configured read/write access and switch permissions**.

## Documentation conventions

The public README and user guide describe publicly available behavior. In a private development checkout, any difference from the public instructions is introduced explicitly with a **PRIVATE DEVELOPMENT DIFFERENCE** label at the specific paragraph. The absence of such a label means the section is intended to be shared. Private development features are not automatically public/HACS features. Do not assume a development version number or a screenshot is available in the public release.

To locate a feature quickly, begin at this index, then follow the appropriate topic link. The entity reference is organized by **switch**, **port**, and **controls** so it can be read without knowing the source-code class names.
