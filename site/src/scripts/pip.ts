// Point-in-polygon and distance helpers for GeoJSON (lon/lat degrees).
export type Ring = number[][];
export interface Feature {
  properties: Record<string, unknown>;
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: unknown };
}

export function polygons(f: Feature): Ring[][] {
  return f.geometry.type === 'Polygon' ? [f.geometry.coordinates as Ring[]] : (f.geometry.coordinates as Ring[][]);
}

function inRing(x: number, y: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function contains(f: Feature, x: number, y: number): boolean {
  return polygons(f).some(([outer, ...holes]) => inRing(x, y, outer) && !holes.some((h) => inRing(x, y, h)));
}

/** Approximate distance in meters from a point to the nearest edge of a feature. */
export function edgeDistanceMeters(f: Feature, x: number, y: number): number {
  const k = Math.cos((y * Math.PI) / 180);
  let best = Infinity;
  for (const poly of polygons(f))
    for (const ring of poly)
      for (let i = 1; i < ring.length; i++) {
        const ax = ring[i - 1][0] * k, ay = ring[i - 1][1];
        const bx = ring[i][0] * k, by = ring[i][1];
        const px = x * k, py = y;
        const dx = bx - ax, dy = by - ay;
        const len = dx * dx + dy * dy;
        let tt = len ? ((px - ax) * dx + (py - ay) * dy) / len : 0;
        tt = Math.max(0, Math.min(1, tt));
        const d = Math.hypot(px - (ax + tt * dx), py - (ay + tt * dy));
        if (d < best) best = d;
      }
  return best * 111_320;
}
