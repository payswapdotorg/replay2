/**
 * Lab persistence — a Prisma-compatible subset over a durable JSON file.
 *
 * Restored stand-in for the original Prisma client (the schema, generated
 * client and prisma deps were never committed with the lab console tree).
 * The lab API routes use a small, regular surface: create / findUnique /
 * findFirst / findMany / update with equality and { in } filters, a
 * single-field orderBy asc/desc, and take. Rows carry Date objects for
 * timestamp fields; ids are auto-generated; every mutation is write-through
 * persisted to the DATABASE_URL file (default <repo>/data/lab-db.json).
 *
 * Server-only: imported exclusively by API routes.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

import fs from "node:fs";
import path from "node:path";

type Row = Record<string, any>;

interface Store {
  labRun: Row[];
  labRecommendation: Row[];
  labBridgeEntry: Row[];
  labCalibrationObservation: Row[];
}

const TABLES = [
  "labRun",
  "labRecommendation",
  "labBridgeEntry",
  "labCalibrationObservation",
] as const;

type TableName = (typeof TABLES)[number];

/** Fields stored as ISO strings but surfaced as Date objects on rows. */
const DATE_FIELDS = new Set([
  "createdAt",
  "updatedAt",
  "submittedAt",
  "observedAt",
]);

/** Create-time column defaults per model (Prisma @default semantics). */
function modelDefaults(table: TableName, now: Date): Row {
  switch (table) {
    case "labBridgeEntry":
      return {
        createdAt: now,
        updatedAt: now,
        submittedAt: now,
        observedAt: null,
        observation: null,
      };
    default:
      return { createdAt: now, updatedAt: now };
  }
}

function emptyStore(): Store {
  return {
    labRun: [],
    labRecommendation: [],
    labBridgeEntry: [],
    labCalibrationObservation: [],
  };
}

function dbFilePath(): string {
  const url = process.env.DATABASE_URL?.trim();
  if (url && url.startsWith("file:")) {
    const raw = decodeURIComponent(url.slice("file:".length));
    if (path.isAbsolute(raw)) return raw;
    return path.join(process.cwd(), raw);
  }
  return path.join(process.cwd(), "data", "lab-db.json");
}

function loadStore(): Store {
  const file = dbFilePath();
  try {
    const raw = fs.readFileSync(file, "utf8");
    const parsed = JSON.parse(raw) as Partial<Store>;
    const store = emptyStore();
    for (const table of TABLES) {
      const rows = parsed[table];
      if (Array.isArray(rows)) {
        store[table] = rows.filter(
          (row) => typeof row === "object" && row !== null,
        ) as Row[];
      }
    }
    return store;
  } catch {
    return emptyStore();
  }
}

function saveStore(store: Store): void {
  const file = dbFilePath();
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const tmp = `${file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(store, null, 2), "utf8");
    fs.renameSync(tmp, file);
  } catch {
    // Persistence failing must not take the API down; rows stay in memory.
  }
}

let idCounter = 0;

function newId(): string {
  idCounter += 1;
  const rand = Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0");
  return `c${Date.now().toString(36)}${idCounter.toString(36)}${rand}`;
}

function serialize(value: unknown): unknown {
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map(serialize);
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) out[key] = serialize(item);
    return out;
  }
  return value;
}

function revive(row: Row): Row {
  const out: Row = { ...row };
  for (const field of DATE_FIELDS) {
    if (typeof out[field] === "string") out[field] = new Date(out[field] as string);
  }
  return out;
}

function matches(row: Row, where?: Row): boolean {
  if (!where || typeof where !== "object") return true;
  for (const [key, condition] of Object.entries(where)) {
    if (condition !== null && typeof condition === "object" && !Array.isArray(condition)) {
      const operators = condition as Record<string, unknown>;
      if ("in" in operators) {
        const list = operators.in;
        if (!Array.isArray(list) || !list.includes(row[key])) return false;
        continue;
      }
      return false; // unsupported operator — matches nothing, loudly visible in tests
    }
    if (row[key] !== condition) return false;
  }
  return true;
}

function sortRows(rows: Row[], orderBy?: Row): Row[] {
  if (!orderBy || typeof orderBy !== "object") return rows;
  const entries = Object.entries(orderBy);
  if (entries.length === 0) return rows;
  const sorted = [...rows];
  for (const [field, direction] of entries) {
    const factor = direction === "desc" ? -1 : 1;
    sorted.sort((a, b) => {
      const av = a[field];
      const bv = b[field];
      if (av === bv) return 0;
      if (av === null || av === undefined) return -1 * factor;
      if (bv === null || bv === undefined) return 1 * factor;
      return av > bv ? factor : -factor;
    });
  }
  return sorted;
}

class Table {
  constructor(
    private readonly store: Store,
    private readonly table: TableName,
  ) {}

  private rows(): Row[] {
    return this.store[this.table];
  }

  // Return types are `any` (not Row): call sites hold the typed view. A
  // string-index signature (Row) cannot satisfy required named members of
  // the route-level RowLike interfaces (TS property-existence semantics),
  // so typing create/findMany as Row breaks every route that pipes rows
  // into the typed summary helpers. Routes own their types (RunRowLike,
  // BridgeEntryRowLike, …) per this file's stand-in contract.
  async create(args: { data: Row }): Promise<any> {
    const now = new Date();
    const row: Row = {
      ...modelDefaults(this.table, now),
      ...(serialize(args.data) as Row),
      id: (args.data as Row).id ?? newId(),
    };
    this.rows().push(row);
    saveStore(this.store);
    return revive(row);
  }

  async findUnique(args: { where: Row }): Promise<any> {
    const found = this.rows().find((row) => matches(row, args.where));
    return found ? revive(found) : null;
  }

  async findFirst(args: { where?: Row; orderBy?: Row } = {}): Promise<any> {
    const filtered = this.rows().filter((row) => matches(row, args.where));
    const ordered = sortRows(filtered, args.orderBy);
    const found = ordered[0] ?? this.rows().find((row) => matches(row, args.where)) ?? null;
    return found ? revive(found) : null;
  }

  async findMany(
    args: { where?: Row; orderBy?: Row; take?: number; skip?: number } = {},
  ): Promise<any[]> {
    const filtered = this.rows().filter((row) => matches(row, args.where));
    const ordered = sortRows(filtered, args.orderBy);
    const start = typeof args.skip === "number" ? Math.max(0, args.skip) : 0;
    const limited =
      typeof args.take === "number" ? ordered.slice(start, start + args.take) : ordered.slice(start);
    return limited.map(revive);
  }

  async update(args: { where: Row; data: Row }): Promise<any> {
    const index = this.rows().findIndex((row) => matches(row, args.where));
    if (index === -1) {
      throw new Error(
        `An operation failed because it depends on one or more records that were not found (${this.table}).`,
      );
    }
    const merged: Row = {
      ...this.rows()[index],
      ...(serialize(args.data) as Row),
      updatedAt: new Date().toISOString(),
    };
    this.rows()[index] = merged;
    saveStore(this.store);
    return revive(merged);
  }
}

// Module-scope singleton that also survives dev-server hot reloads.
const globalRef = globalThis as unknown as { __labDbStore?: Store };
const store = globalRef.__labDbStore ?? loadStore();
globalRef.__labDbStore = store;

export const db: {
  labRun: Table;
  labRecommendation: Table;
  labBridgeEntry: Table;
  labCalibrationObservation: Table;
} = {
  labRun: new Table(store, "labRun"),
  labRecommendation: new Table(store, "labRecommendation"),
  labBridgeEntry: new Table(store, "labBridgeEntry"),
  labCalibrationObservation: new Table(store, "labCalibrationObservation"),
};

export const __labDbFilePath = dbFilePath;
