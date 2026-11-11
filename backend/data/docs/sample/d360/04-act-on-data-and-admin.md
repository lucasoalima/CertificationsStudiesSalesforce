# Data 360: acting on data and administration (study notes)

## Activations
An activation publishes a segment to an activation target such as Marketing Cloud Engagement, an advertising platform or a cloud storage bucket (Amazon S3). Besides contact points, an activation can include related attributes; filters on those related attributes (for example orders from the last 30 days) are applied inside the activation, otherwise all related records are sent. For an S3 target, the exported file name is composed from the segment and activation names.

## Data actions
Data actions send events to targets such as Salesforce Platform Events, webhooks or Marketing Cloud when a condition on a DMO record or a streaming insight is met. They are the way to update CRM as soon as a record changes in Data 360.

## Enrichments in CRM
Related list enrichment shows Data 360 records (for example all cases or orders of the unified individual) as a related list on Contact, Lead or Account. Copy field enrichment copies selected Data 360 fields, including calculated insights, onto a CRM record.

## Data sharing
Data sharing (zero copy outbound) shares Data 360 objects with external platforms such as Snowflake or Databricks so they can query unified data read-only and in near real time, without export pipelines.

## Data spaces and permissions
Data spaces logically separate data, metadata and processes inside one Data 360 org, for example by brand or business unit. Objects must be added to a data space before they can be mapped and used there. Standard permission sets follow least privilege: admins configure everything, while marketing-focused sets allow segmentation and activation without changing data model mappings or identity resolution.

## Consent and privacy
Consent status (for example email opt-in) should be used as a filter in segments so people who did not consent are excluded. Right to be forgotten requests are submitted for Individual profiles; processing removes the individual and related records according to the platform rules.

## Sandboxes
Data 360 in a sandbox carries metadata such as data streams definitions and mappings, not the ingested production data. After a refresh, data must be ingested again.
