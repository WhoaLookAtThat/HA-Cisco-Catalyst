# Cisco Catalyst — User Guide

**Documentation · 1 of 6 — User Guide**

**1. User Guide (current)** · [2. SNMP Setup](SNMP_SETUP.md) · [3. Entity Reference](ENTITIES.md) · [4. Automations & Events](AUTOMATIONS.md) · [5. Troubleshooting](TROUBLESHOOTING.md) · [6. Documentation Index](DOCUMENTATION_INDEX.md)

Start of guide · [Next: SNMP Setup →](SNMP_SETUP.md) · [All documentation](DOCUMENTATION_INDEX.md)


**Start here: `docs/USER_GUIDE.md`.** This page is the starting point and table of contents for the multi-page Cisco Catalyst Integration documentation. The [repository README](../README.md) explains installation and SNMP setup; it is **not a second competing starting page**. This guide is written for a technically capable homeowner or home-lab administrator.

## On this page

- [Choose what you want to do](#choose-what-you-want-to-do)
- [Suggested first-time reading order](#suggested-first-time-reading-order)
- [What appears in Home Assistant](#what-appears-in-home-assistant)
- [Public and private documentation conventions](#public-and-private-documentation-conventions)

## Choose what you want to do

See also the [complete documentation site list](DOCUMENTATION_INDEX.md).

| Your goal | Read this page |
| --- | --- |
| Understand the Integration and install it | [README — installation and setup](../README.md#installation) |
| Learn what every switch and port entity means, and how it might help in an automation | **[Entities and home-automation examples](ENTITIES.md)** |
| Choose SNMP credentials and decide whether to permit switch changes | [SNMP configuration](../README.md#snmp-configuration) and [read-only versus write access](../README.md#read-only-vs-write-access) |
| Add a visual switch dashboard | [Optional Cisco Catalyst Dashboard](https://github.com/WhoaLookAtThat/HA-Cisco-Catalyst-Dashboard) (separate installation/release) |
| Investigate incorrect or missing entity readings | [Entity reference — data freshness](ENTITIES.md#data-freshness-and-safety), [README features](../README.md#features), and Home Assistant Integration logs |

## Suggested first-time reading order

1. **[Install and configure the Integration](../README.md#installation).** Prepare your switch for SNMP, install from the applicable repository or HACS release, then add Cisco Catalyst under **Settings → Devices & services**.
2. **[Identify your Home Assistant devices and entities](ENTITIES.md#what-an-entity-is).** Look at the switch device and an individual port device; compare what you see with the entity tables.
3. **[Choose a useful home automation](ENTITIES.md#practical-automation-patterns).** For instance, alert when the Ethernet link for an always-on access point has been down for several minutes.
4. **[Consider write controls](ENTITIES.md#port-controls--actions-that-can-change-switch-configuration).** Monitoring does not require enabling port changes, PoE toggles, or VLAN reassignment.
5. **[Customize your dashboard](https://github.com/WhoaLookAtThat/HA-Cisco-Catalyst-Dashboard)** if you want a specialized port map; it is optional.

## What appears in Home Assistant

Under **Settings → Devices & services → Cisco Catalyst**, the Integration creates a *switch device* with overall health information and separate *port devices* with per-interface readings and, where supported, controls. Open a device's **Entities** list. Some diagnostic/configuration entities may not appear on dashboards automatically; they can still appear under entity details.

An **entity** is a Home Assistant measurement, condition, or control, such as a port's link state, receive-byte counter, PoE switch, or description text. An **attribute** is supporting detail on an entity, not a separate control. Entity IDs are assigned by Home Assistant and may differ from examples in this guide.

The reference lists **each entity family implemented by the Integration** with its purpose, availability considerations, and a realistic home-lab use. See **[Entities and home-automation examples](ENTITIES.md)**. Your particular switch may not support every optional entity, and monitoring can remain available even when write access is not configured.

## Public and private documentation conventions

The **public and private copies of the User Guide and entity reference share the same main text and navigation**. The public copy describes released behavior. A private checkout adds clearly identified paragraphs or sections beginning with:

> **PRIVATE DEVELOPMENT DIFFERENCE —** This text describes a private-only feature, version, hardware observation, or behavior that differs from the public release.

Such a note applies to its immediately following paragraph, table, or section, not silently to the entire guide. Private implementation notes do **not** imply that the feature is part of the current public/HACS release. A section with no difference note is intended to match the public guidance.

