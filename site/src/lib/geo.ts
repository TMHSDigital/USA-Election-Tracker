// Build-time projection of district GeoJSON to static SVG paths.
// Equirectangular with cos(latitude) scaling: adequate for a single state.
import type { GeoJSON } from './data';

type Ring = number[][];

function rings(geom: GeoJSON['features'][number]['geometry']): Ring[] {
  if (geom.type === 'Polygon') return geom.coordinates as Ring[];
  return (geom.coordinates as Ring[][]).flat();
}

function lon(x: number): number {
  // Alaska's Aleutians cross the antimeridian.
  return x > 0 ? x - 360 : x;
}

export interface SvgShape {
  key: string;
  d: string;
  props: Record<string, unknown>;
}

export function bboxOf(d: string): [number, number, number, number] {
  const nums = d.match(/-?\d+/g)?.map(Number) ?? [];
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (let i = 0; i + 1 < nums.length; i += 2) {
    x0 = Math.min(x0, nums[i]); x1 = Math.max(x1, nums[i]);
    y0 = Math.min(y0, nums[i + 1]); y1 = Math.max(y1, nums[i + 1]);
  }
  return [x0, y0, x1, y1];
}

/** True if a path's bounding box overlaps a "x y w h" viewBox. */
export function intersects(d: string, viewBox: string): boolean {
  const [vx, vy, vw, vh] = viewBox.split(' ').map(Number);
  const [x0, y0, x1, y1] = bboxOf(d);
  return x1 >= vx && x0 <= vx + vw && y1 >= vy && y0 <= vy + vh;
}

/** viewBox framing one shape with padding, clamped to the full extent. */
export function focusViewBox(full: string, d: string, pad = 0.6): string {
  const [, , W, H] = full.split(' ').map(Number);
  const nums = d.match(/-?\d+/g)?.map(Number) ?? [];
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (let i = 0; i + 1 < nums.length; i += 2) {
    x0 = Math.min(x0, nums[i]); x1 = Math.max(x1, nums[i]);
    y0 = Math.min(y0, nums[i + 1]); y1 = Math.max(y1, nums[i + 1]);
  }
  if (!isFinite(x0)) return full;
  const size = Math.max(x1 - x0, y1 - y0, 40) * (1 + pad);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const vx = Math.max(0, Math.min(W - size, cx - size / 2));
  const vy = Math.max(0, Math.min(H - size, cy - size / 2));
  if (size >= W && size >= H) return full;
  return `${Math.round(vx)} ${Math.round(vy)} ${Math.round(Math.min(size, W))} ${Math.round(Math.min(size, H))}`;
}

export function projectFeatures(geo: GeoJSON, width = 600): { viewBox: string; shapes: SvgShape[] } {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const f of geo.features)
    for (const r of rings(f.geometry))
      for (const [x, y] of r) {
        const lx = lon(x);
        if (lx < minX) minX = lx;
        if (lx > maxX) maxX = lx;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
  const k = Math.cos((((minY + maxY) / 2) * Math.PI) / 180);
  const spanX = (maxX - minX) * k || 1;
  const spanY = maxY - minY || 1;
  const scale = width / spanX;
  const height = Math.round(spanY * scale);
  // Integer coordinates at 600 units wide are finer than any rendered size.
  const px = (x: number) => Math.round((lon(x) - minX) * k * scale);
  const py = (y: number) => Math.round((maxY - y) * scale);
  const ringPath = (r: Ring) => {
    const pts: string[] = [];
    let last = '';
    for (const [x, y] of r) {
      const p = `${px(x)} ${py(y)}`;
      if (p !== last) pts.push(p);
      last = p;
    }
    return pts.length > 2 ? 'M' + pts.join('L') + 'Z' : '';
  };
  const shapes = geo.features.map((f, i) => {
    const d = rings(f.geometry).map(ringPath).join('');
    return { key: String(f.properties.district ?? f.properties.state_po ?? i), d, props: f.properties };
  });
  return { viewBox: `0 0 ${width} ${height}`, shapes };
}
