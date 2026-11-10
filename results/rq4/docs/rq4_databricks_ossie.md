# RQ4 agent report: Databricks metric views + Apache Ossie (accessed 10 Nov 2026)

## Databricks metric views
- R0: proprietary managed; needs "CAN USE permission on a SQL warehouse or other compute resource running Databricks Runtime 17.3 or above." https://docs.databricks.com/aws/en/uc-semantics/metric-views/create
- R1: (a) YAML `filter`: "A filter in the YAML definition applies to all queries that reference the metric view." https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference ; (b) UC row filters: "To create a row filter, you write a function (UDF) to define the filter policy and then apply it to a table." https://docs.databricks.com/aws/en/data-governance/unity-catalog/filters-and-masks/manually-apply . Row filter on metric view itself: NOT STATED.
- R2: left to UDF; SESSION_USER / IS_ACCOUNT_GROUP_MEMBER "run as the invoker" (manually-apply page). "The metric view owner's privileges are used to resolve the underlying data sources at query time." https://docs.databricks.com/aws/en/data-governance/unity-catalog/securable-objects . Invoker-dependent expressions banned only for materialization https://docs.databricks.com/aws/en/uc-semantics/metric-views/materialization
- R3: "CREATE TABLE and USE SCHEMA privileges in the schema where you want to create the metric view." + "USE CATALOG privilege on the parent catalog." (create page). Row filter: "you must be the table owner, or have both the MANAGE and SELECT privileges on the table."
- R4: Databricks SQL only; PostgreSQL NOT STATED.
- R5: "Supported sources include tables, views, metric views, and SQL queries." (yaml-reference). CTE/UNION NOT STATED; filter applies on output (inference).
- R6: Genie trusted assets: "Parameterized example queries and SQL functions whose exact logic has been verified by an agent author." https://docs.databricks.com/aws/en/genie-agents/concepts
- R7: Genie "convert natural language questions to an equivalent SQL query." "Generated queries are always read-only." "Unity Catalog evaluates data access as the end user's own identity, not the author's." agent mode "Databricks-provided MCP connectors." (concepts). Inference: Genie with base tables bypasses metric-view filter; only table row filters survive.

## Apache Ossie
- R0: Apache-2.0; spec main "Version: 0.3.0.dev0", "DRAFT version — in development, schema may change before 0.3.0 is released." https://raw.githubusercontent.com/apache/ossie/main/core-spec/spec.md ; tag osi-0.1.1-rc1 (19 May 2026). Incubation: "Started: 2026-06-19"; "2026-06-22 Project enters incubation." https://incubator.apache.org/clutch/ossie.html ; announcement post 10 Jul 2026 https://ossie.apache.org/updates/ossie-enters-apache-incubator/  (CORRECTS Kebaruan note "masuk 10 Jul").
- R1: NOT STATED; only "Fields represent row-level attributes that can be used for grouping, filtering, and in metric expressions." (spec.md)
- R2: NOT STATED; "security/access/permission/tenant" absent from spec.md; roadmap plans "Discovery, versioning, and access control for Ossie models" https://raw.githubusercontent.com/apache/ossie/main/ROADMAP.md
- R3: NOT STATED; file format "single JSON- and YAML-based specification that any tool can read and write." https://github.com/apache/ossie
- R4: "OSSIE_SQL_2026 is the only dialect the specification defines; all others are opaque to Ossie." POSTGRES registered token https://raw.githubusercontent.com/apache/ossie/main/extensions/dialects.md ; "Registering a dialect does not mean Ossie supports querying in it" (spec.md)
- R5: dataset source "Reference to underlying physical table/view (e.g., database.schema.table) or query" (spec.md); CTE/UNION/filter NOT STATED.
- R6: none; roadmap "Standard semantic query language (Ossie-native or SQL-extended)".
- R7: "Additional context for AI tools (e.g., synonyms, common terms)" (spec.md); no enforcement point.
