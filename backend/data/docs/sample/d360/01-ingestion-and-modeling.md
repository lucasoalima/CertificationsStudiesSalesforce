# Data 360: ingestion and modeling (study notes)

## Data streams
A data stream brings data from a source into Data 360. Common connectors include the Salesforce CRM connector, Marketing Cloud, Amazon S3, Google Cloud Storage, the Ingestion API and the Web and Mobile SDKs. Each data stream has a category (Profile, Engagement or Other) that defines how the records are treated later. Engagement data must have an event date-time field.

## Data lake objects (DLO)
When a data stream is created, the raw records land in a data lake object (DLO). The DLO keeps the data in the shape of the source, before any mapping. It is the right place to keep the original record exactly as it was received.

## Data model objects (DMO) and harmonization
Data model objects are the canonical model of Data 360 (for example Individual, Contact Point Email, Contact Point Phone, Party Identification, Sales Order). Mapping fields from DLOs to DMOs is called harmonization: different sources that call a person "user", "contact" or "subscriber" all map to the Individual DMO. A standard DMO can receive custom attributes when a needed field does not exist in the standard model, so you do not need a custom DMO just for one extra field.

## Relationships and cardinality
DMOs are related through relationships with a cardinality. If one vehicle belongs to only one individual but an individual can own many vehicles, the relationship from Vehicle to Individual is many-to-one (N:1). A custom DMO only appears as related attributes in segmentation if it has a relationship path to the segmented entity.

## Transforms and formulas
Formula fields in a data stream handle simple row-level logic such as string cleanup or arithmetic. Batch data transforms handle heavy, multi-step logic such as joins and aggregations on a schedule. Streaming data transforms process records continuously as they arrive.

## Zero copy and federation
Zero copy data federation lets Data 360 read data that lives in an external platform (such as Snowflake, Databricks, BigQuery or Redshift) without copying it into Data 360 storage. Live query federation pushes the query to the external system every time. Federation with acceleration (caching) keeps a refreshed copy for repeated queries with no real-time need, balancing performance and cost.
