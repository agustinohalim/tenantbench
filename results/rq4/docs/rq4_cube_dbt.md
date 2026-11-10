# RQ4 agent report: Cube + dbt MetricFlow (accessed 10 Nov 2026; quotes via WebFetch summariser, VERIFY before print)

## Cube
- R0: "Cube Backend is Apache 2.0 licensed" / "Cube Client is MIT licensed" https://github.com/cube-js/cube
- R1: query_rewrite "You can use `query_rewrite` to enforce mandatory filters that apply to all queries." https://docs.cube.dev/docs/data-modeling/access-control/context#enforcing-mandatory-filters ; access policies row_level https://docs.cube.dev/docs/data-modeling/access-control/row-level-security ; view default_filters "`default_filters` are enforced on every query against the view, including filter suggestions." https://docs.cube.dev/reference/data-modeling/view
- Context7 (docs.cube.dev/docs/data-modeling/data-access-policies): "Row-level filters in access policies are combined together with filters defined using the query_rewrite configuration option. Both will apply to the request."
- R2: multitenancy example `if (user.id) { query.filters.push(...) } return query` https://docs.cube.dev/embedding/multitenancy (fail-open as written); role example `raise ValueError("No role found in Security Context!")` (context page); "When you define access policies for specific groups, access is automatically denied to all other groups." https://docs.cube.dev/reference/data-modeling/data-access-policies ; missing attribute NOT STATED.
- R3: no write needed for querying; pre-aggregations may need write "depending on your data source, Cube may require write access to the" ... https://docs.cube.dev/docs/pre-aggregations
- R4: many incl. Postgres https://docs.cube.dev/admin/connect-to-data/data-sources
- R5: cube sql "It can be any valid SQL query, but usually it takes the form of a SELECT * FROM my_table query." https://docs.cube.dev/reference/data-modeling/cube ; filter in outer WHERE https://docs.cube.dev/reference/data-modeling/context-variables
- R6: no parameterised saved queries NOT STATED; views; playground explorations.
- R7: Cube MCP hosted, OAuth, runQuery "Cube SQL query (PostgreSQL dialect)" https://docs.cube.dev/docs/integrations/mcp-server ; dev mode: "the SQL API accepts any credentials as well, allowing arbitrary SQL against connected data sources." https://docs.cube.dev/reference/core-data-apis/sql-api ; whether query_rewrite applies to SQL API: NOT STATED -> RUN TEST.

## dbt Semantic Layer / MetricFlow
- R0: "Version 0.209.0 and greater is covered by the Apache 2.0 license." https://github.com/dbt-labs/metricflow ; "The dbt Semantic Layer is proprietary to dbt, however some components of it are open-source." https://docs.getdbt.com/docs/use-dbt-semantic-layer/sl-faqs
- R1: none per-user; metric filter "Consider it as your WHERE clause." https://docs.getdbt.com/docs/build/metrics-overview ; "the credentials you configure when setting up the dbt Semantic Layer are used for every request. Any physical access policies you have tied to your credentials will be respected." (sl-faqs)
- R2: NOT STATED; filter Jinja only Entity/Dimension/TimeDimension/Metric.
- R3: "The Semantic Layer requires read access to the schema(s) containing the dbt models" / "We recommend using 'read-only' credentials." https://docs.getdbt.com/docs/use-dbt-semantic-layer/setup-sl ; cache "lives in your data platform" (sl-faqs)
- R4: "Use Snowflake, BigQuery, Databricks, Redshift, Postgres, or Trino." (setup-sl)
- R5: "Expr ... allows you to put any arbitrary SQL supported by your data platform in any definition of a measure, entity, or dimension." (sl-faqs); "Each semantic model corresponds to a dbt model in your DAG" https://docs.getdbt.com/docs/build/semantic-models
- R6: saved queries https://docs.getdbt.com/docs/build/saved-queries
- R7: dbt MCP "It provides access to private APIs, text-to-SQL, and SQL execution." https://docs.getdbt.com/docs/dbt-ai/about-mcp ; "`execute_sql` doesn't block write statements. What a query can do depends on the permissions of the warehouse credentials it runs with." https://docs.getdbt.com/docs/dbt-ai/mcp-available-tools
