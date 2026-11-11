# Data 360: identity resolution (study notes)

## Purpose
Identity resolution matches and reconciles source profiles from many systems into a unified profile (Unified Individual). It is configured through rulesets, and each ruleset has match rules and reconciliation rules.

## Match rules
Match rules decide which source profiles belong to the same person. They can use exact or fuzzy matching on name, and exact matching on contact points such as email (Contact Point Email), phone (Contact Point Phone) or address. To match on a custom identifier such as a Loyalty ID, the identifier is mapped to the Party Identification DMO and used in an exact match rule.

## Avoiding over-matching
Family members often share an address or a phone number. Rules that match only on a shared contact point merge different people into one profile. A more restrictive design combines a contact point with an individual attribute (for example email plus first name) so shared households stay separate. When changing rules in production, a safe approach is to create a new ruleset with stricter criteria, compare its results with the current one, and switch only after approval.

## Reconciliation rules
Reconciliation rules decide which value wins for each attribute in the unified profile when sources disagree. Options include last updated, most frequent and source sequence. Source sequence sets a priority order of data sources for an attribute, for example CRM first for first name and last name. The "ignore empty value" setting skips empty values so an empty field from a higher-priority source does not erase a filled one.

## Unified link objects
Unified Link Individual connects each source Individual to its Unified Individual. Calculations that roll data up to the unified profile, such as lifetime value from Sales Order, join Unified Individual to Unified Link Individual and then to the source records.

## Processing
Identity resolution runs incrementally: only source profiles that changed since the last run are processed again, which is why a run can process fewer profiles than the total.
