// V7 adapter: AskDB's tenant guardrail (@askdb/core, Apache-2.0), called as published.
// Reads JSON lines {id, sql, tenant_tables: [...], tenant} on stdin; writes {id, passed, codes}.
// Policy per table set: one root "Tenant" whose id column is tenant_id, every tenant table
// scoped through its own tenant_id column. Tables are declared in schema "public" because the
// harness runs unqualified SQL with search_path set to the BIRD schema.
import { pathToFileURL } from "node:url";
import path from "node:path";
// ASKDB_DIR selects an installed version under versions/<ver>; default is the pinned one.
const dir = process.env.ASKDB_DIR ? path.resolve(process.env.ASKDB_DIR) : path.resolve("node_modules/@askdb/core");
const core = await import(pathToFileURL(path.join(dir, "dist/index.js")).href);
// Before 1.0.0-beta.43 placeholderForTenantRoot was not exported; the naming rule was the same.
const placeholderFor = core.placeholderForTenantRoot ??
  ((root) => `:tenant_${root.label.toLowerCase().replace(/[^a-z0-9]+/g, "_")}_ids`);
const NEW_API = typeof core.placeholderForTenantRoot === "function";
import readline from "node:readline";

const cache = new Map();
function policyFor(tables) {
  const key = tables.join(",");
  if (cache.has(key)) return cache.get(key);
  const [root, ...rest] = tables;
  const id = (t) => `table:public.${t}`;
  const lines = [
    "---", "schemaId: tenantbench", "enforcement: warn", "roots:",
    `  - id: ${id(root)}`, `    tenantIdColumn: ${id(root)}#tenant_id`, "    label: Tenant",
    "scopedTables:",
    ...rest.flatMap((t) => [`  - id: ${id(t)}`, "    scopeThrough:", `      - root: ${id(root)}`,
                            `        column: ${id(t)}#tenant_id`]),
    "globalTables: []", "---", "# Tenant Policy", "",
  ];
  const parsed = core.parseTenantPolicyMarkdown(lines.join("\n"));
  const physical = new Set(tables.map(id));
  const owners = new Map(tables.map((t) => [`${id(t)}#tenant_id`, id(t)]));
  const third = NEW_API ? owners : new Set(owners.keys());
  const policy = core.normalizeTenantPolicy(parsed, physical, third);
  const ph = placeholderFor(policy.roots[0]);
  const v = { policy, ph, rootId: id(root) };
  cache.set(key, v);
  return v;
}

const rl = readline.createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  const job = JSON.parse(line);
  const { policy, ph, rootId } = policyFor(job.tenant_tables);
  const scope = { access: { kind: "ids", tenantRoot: rootId, ids: [String(job.tenant)] } };
  let out;
  try {
    const r = core.validateTenantGuardrails(job.sql_placeholder.replaceAll("{PH}", ph), policy, scope,
      { dialect: { id: "postgres", backslashEscapes: false } });
    out = { id: job.id, passed: r.passed, codes: [...new Set(r.warnings.map((w) => w.code ?? w.rule ?? w.kind))] };
  } catch (e) {
    out = { id: job.id, passed: false, codes: ["THREW:" + (e.code || e.name)] };
  }
  process.stdout.write(JSON.stringify(out) + "\n");
}
