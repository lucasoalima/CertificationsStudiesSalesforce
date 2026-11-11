# Data 360: segmentation and insights (study notes)

## Segments
A segment selects records of a target entity, usually Unified Individual, using direct attributes (fields on the target), related attributes (fields reached through relationships, such as Sales Order) and calculated insights. Segments refresh on a schedule; rapid publish segments refresh more often for time-sensitive use cases.

## Containers and logic
Attributes inside the same container are evaluated on the same related record. To find people who bought black pants, product color and product type go in a single container so both conditions apply to the same order line. Two separate containers joined by AND only require that the person has some record matching each condition, possibly different records. Exclusion criteria remove records, for example customers who purchased in the last week from a "purchased in the last six months" segment.

## Nested segments
A nested segment reuses another segment as a filter. It is the efficient way to say "members of the Platinum Loyalty segment OR people who spent more than 5,000".

## Calculated insights
Calculated insights are multidimensional metrics defined in SQL over DMOs, such as lifetime value or RFM scores. They are made of measures (metrics) and dimensions, run in batch on a schedule, and their metrics can be used as segment filters and as activation attributes. Reports on calculated insights reflect the last time the insight was processed.

## Streaming insights
Streaming insights aggregate engagement events in near real time over time windows, for example page views in the last 15 minutes from the Web or Mobile SDK. They can trigger data actions. They are not used as filters in the segment canvas.

## Einstein Studio models
Einstein Studio supports building predictive models (regression for numeric outcomes such as time to close, binary and multiclass classification) and bringing your own model hosted on platforms such as Amazon SageMaker or Databricks without copying the data out. Predictions are stored as attributes on a DMO and can be used in segmentation, flows and predict jobs.
