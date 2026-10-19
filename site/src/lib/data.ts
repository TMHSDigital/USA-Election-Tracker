// Build-time data access. Reads the bundle produced by `ingest compose`.
// The bundle location is DATA_DIR (default: ../.data/site relative to site/).
import fs from 'node:fs';
import path from 'node:path';
import { load as loadYaml } from 'js-yaml';

export type Office = 'house' | 'senate' | 'governor';
export type ListStatus = 'official' | 'fec_registrants' | 'unavailable';

export interface Finance {
  receipts: number | null;
  disbursements: number | null;
  cash_on_hand: number | null;
  coverage_end_date: string | null;
  source_ids: string[];
}

export interface Candidate {
  candidate_id: string;
  name: string;
  ballot_name: string;
  party_label: string;
  incumbent: boolean;
  ballot_order: number | null;
  write_in: boolean;
  running_mate: string | null;
  fec_candidate_id: string | null;
  fec_match_method: string | null;
  list_status: ListStatus;
  source_ids: string[];
  finance: Finance | null;
}

export interface HistoryEntry {
  year: number;
  special: boolean;
  total_votes: number | null;
  candidates: { name: string; party_label: string; votes: number | null; pct: number | null; writein: boolean }[];
  source_ids: string[];
}

export interface Race {
  race_id: string;
  office: Office;
  state_po: string;
  state_name: string;
  district: number | null;
  special: boolean;
  election_date: string;
  candidate_list: { status: ListStatus; url: string | null; source_ids?: string[] };
  notes: { election_type: string; runoff_date: string | null; source_ids: string[] } | null;
  order_method: 'ballot' | 'alphabetical';
  candidates: Candidate[];
  boundary: {
    boundary_set_id: string;
    enacting_instrument: string;
    enacting_instrument_url: string | null;
    display_path: string;
    source_ids: string[];
  } | null;
  history: HistoryEntry[];
  demographics: {
    available: boolean;
    reason?: string;
    vintage?: string;
    rows: { label: string; variable: string; estimate: number | null; moe: number | null; source_ids: string[] }[];
  } | null;
  official_results_url: string | null;
}

export interface RaceSummary {
  race_id: string;
  office: Office;
  state_po: string;
  state_name: string;
  district: number | null;
  special: boolean;
  candidate_count: number;
  list_status: ListStatus;
}

export interface StateOffice {
  state_po: string;
  state_name: string;
  office_name: string;
  homepage_url: string | null;
  voter_info_url: string | null;
  results_url: string | null;
  results_platform: string | null;
  general_election_date: string;
  notes: string;
  source_ids: string[];
}

export interface StateInfo {
  state_po: string;
  state_name: string;
  state_fips: string;
  house_seats: number;
  office: StateOffice | null;
  race_ids: string[];
  boundary_set: { boundary_set_id: string; enacting_instrument: string; enacting_instrument_url: string | null; source_ids: string[] } | null;
}

export interface Source {
  source_id: string;
  name: string;
  publisher: string;
  url: string;
  license: string;
  retrieved_at: string | null;
  source_published_at: string | null;
  notes: string;
}

export interface AdapterStatus {
  adapter_id: string;
  description: string;
  ok: boolean;
  stale: boolean;
  has_data: boolean;
  last_success_at: string | null;
  last_attempt_at: string | null;
  retrieved_at: string | null;
}

export interface Meta {
  schema_version: number;
  generated_at: string;
  live_enabled: boolean;
  status: { adapters: Record<string, AdapterStatus> };
  warnings: string[];
}

const SITE_ROOT = process.cwd();
export const DATA_DIR = path.resolve(SITE_ROOT, process.env.DATA_DIR ?? '../.data/site');
const REPO_ROOT = path.resolve(SITE_ROOT, '..');

const cache = new Map<string, unknown>();
function readJson<T>(rel: string, fallback: T): T {
  const key = rel;
  if (cache.has(key)) return cache.get(key) as T;
  const p = path.join(DATA_DIR, rel);
  let value: T = fallback;
  if (fs.existsSync(p)) value = JSON.parse(fs.readFileSync(p, 'utf8')) as T;
  cache.set(key, value);
  return value;
}

export const getMeta = (): Meta =>
  readJson<Meta>('meta.json', {
    schema_version: 1,
    generated_at: new Date(0).toISOString(),
    live_enabled: false,
    status: { adapters: {} },
    warnings: ['data bundle missing'],
  });
export const getStates = (): StateInfo[] => readJson<StateInfo[]>('states.json', []);
export const getRaceIndex = (): RaceSummary[] => readJson<RaceSummary[]>('races.json', []);
export const getRace = (id: string): Race => readJson<Race>(`races/${id}.json`, null as unknown as Race);
export const getSources = (): Source[] => readJson<Source[]>('sources.json', []);
export const getDownloads = () =>
  readJson<{ name: string; description: string; rows: number; files: string[]; source_ids: string[]; license: string }[]>(
    'downloads/index.json',
    [],
  );

export function sourceMap(): Map<string, Source> {
  return new Map(getSources().map((s) => [s.source_id, s]));
}

export function readGeo(rel: string): GeoJSON | null {
  return readJson<GeoJSON | null>(`boundaries/${rel}`, null);
}

export interface GeoJSON {
  type: 'FeatureCollection';
  features: { properties: Record<string, unknown>; geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] } }[];
}

export interface Correction {
  id: string;
  date: string;
  pages: string[];
  summary: string;
  details?: string;
}

export function getCorrections(): Correction[] {
  const p = path.join(REPO_ROOT, 'data', 'corrections.yaml');
  if (!fs.existsSync(p)) return [];
  const doc = loadYaml(fs.readFileSync(p, 'utf8')) as { corrections?: Correction[] };
  return (doc?.corrections ?? []).sort((a, b) => b.date.localeCompare(a.date));
}

/** Adapters whose data feeds a given page section, used for "Data last updated". */
export const ADAPTERS_FOR = {
  race: ['candidates_official', 'fec', 'legislators', 'history', 'boundaries', 'acs'],
  state: ['state_offices', 'candidates_official', 'boundaries'],
  home: ['state_offices', 'candidates_official', 'fec', 'legislators', 'history', 'boundaries', 'acs'],
} as const;
