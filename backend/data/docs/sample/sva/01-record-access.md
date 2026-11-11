# Sharing and Visibility: access to records (study notes)

## Organization-wide defaults (OWD)
OWD sets the baseline access to records an internal user does not own: Private, Public Read Only, Public Read/Write (and Controlled by Parent for detail objects). External OWD can be equal to or more restrictive than the internal default. Everything else in the sharing model only opens access on top of OWD; nothing in the sharing model can restrict below it.

## Role hierarchy
Users above a record owner in the role hierarchy get the same access as the owner, when "Grant Access Using Hierarchies" is enabled (always on for standard objects). Users at the same level do not see each other's private records through the hierarchy.

## Sharing rules
Owner-based sharing rules share records owned by members of a group, role or territory with another group. Criteria-based sharing rules share records that match field criteria. Sharing rules are the scalable declarative way to open access to records for whole groups of users.

## Teams, manual sharing and Apex managed sharing
Account, opportunity and case teams give access per record. Manual sharing lets owners share a single record. When sharing logic is too complex for rules, Apex managed sharing creates share records (for example AccountShare or a custom object's __Share) with a custom sharing reason; records shared with a custom reason survive owner changes.

## Implicit sharing and master-detail
Detail records in a master-detail relationship inherit access from the master, so the detail object has no OWD of its own. On a junction object with two master-detail parents, a user needs access to both parents to see the junction record.

## Enterprise Territory Management
Territories grant access by account territory assignment (geography, industry, segment) independently of the role hierarchy, which is useful when sales coverage does not follow the reporting structure.
