# Sharing and Visibility: implications of the security model and Apex (study notes)

## Sharing keywords in Apex
Classes declared "with sharing" enforce the running user's record access; "without sharing" ignores it; "inherited sharing" takes the mode of the caller. A method in a without sharing class runs without sharing even when it is called from a with sharing class, because the sharing mode belongs to the class where the method is defined.

## Enforcing CRUD and FLS in code
Sharing keywords do not enforce object and field permissions. Use user mode database operations (WITH USER_MODE in SOQL, Database methods with AccessLevel.USER_MODE) or Security.stripInaccessible to respect CRUD and field-level security in Apex.

## Performance and large data volumes
Large numbers of share records, deep role hierarchies and frequent ownership changes cause sharing recalculation and group membership locks. Data skew happens when one user owns more than about 10,000 records of an object or one parent has more than 10,000 children; it slows sharing calculations and causes record locking. Spread ownership and avoid placing integration users that own many records at the top of the hierarchy.

## Defer sharing calculations
Deferring sharing calculations lets admins suspend recalculation during large changes (such as a role hierarchy redesign) and run it later in a maintenance window.
