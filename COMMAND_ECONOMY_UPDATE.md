# Organization Command, Public Reputation & Property Economy — 3.64.0-command-economy-1

This preview layers three persistent simulation systems onto the existing Living Adventures / World Systems build without changing save schema 21.

## Organization command

Recognized leaders and officers can issue timed assignments from the Group journal to actual members under their authority. Supported assignments include investigation, patrol/defense, supply runs, diplomacy, escort duty, team training, and raids. Independent allies cannot be ordered. A member on a field assignment is temporarily unavailable for local travel and tactical combat until the team returns or is recalled.

Assignments use campaign time, member capability, organization resources, task risk, and relevant headquarters facilities. Results create persistent reports and resource changes. Off-screen assignment failure does not invent a member death. Organization leaders can dedicate an owned property as a base and spend organization supplies on two-day facility projects such as a training hall, infirmary, intelligence office, defenses, storage, quarters, or production floor.

## Public reputation, fame & wanted attention

Public reputation is an application-owned ledger separate from private NPC knowledge. Fame and infamy arise only from recorded public evidence, faction standing, formal bounty/wanted information, or application-owned public outcomes. Private information does not automatically become public notoriety.

Each jurisdiction tracks standing, a readable reputation band, recognition, heat, and wanted state. Heat can cool with time or a confirmed Lay Low activity; faction standing itself does not disappear. New public trouble can raise heat again. Local standing and heat can influence merchant pricing and travel exposure.

## Property, economy & production

Tracked-currency worlds can acquire homes, workshops, shops, warehouses, and other established holdings at their current location. Property and facility actions use the same duration preview -> confirmation -> automatic resolution flow as Living Adventures.

Properties can accumulate local business proceeds as campaign time passes; proceeds remain in that property's treasury until collected there. Facilities have mechanical effects: training halls improve supported training, infirmaries improve ordinary recovery, workshop floors accelerate production, shopfronts improve business proceeds, and organization-specific facilities support delegated assignments.

Known recipes can be started as persistent workshop orders. Production completes with campaign time and the finished reusable product must be claimed at the workshop. Purchases, upgrades, work orders, collection, and claims are revalidated on completion/resume and cannot duplicate rewards.

Local market prices are derived from established conflict pressure, route conditions, and public jurisdiction standing. The displayed shop price and the charged purchase price use the same calculation.

## Reliability rules

- Read-only panels and map views do not create properties, assignments, reputation, income, or rewards.
- Narrator state patches cannot write organization_command, public_reputation, or property_economy.
- Duplicate assignment requests do not create duplicate equivalent active work.
- Delegated members cannot simultaneously accompany local journeys or tactical encounters.
- Failed/off-screen assignments create setbacks, not arbitrary character deaths.
- Property proceeds accrue once when real campaign time advances and require local collection.
- Heat cooling persists across later reputation synchronization when standing is unchanged.
- Save schema remains 21 and existing campaigns remain compatible.
