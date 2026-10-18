// Small static index the lookup island uses to turn (state, district) into race links.
import type { APIRoute } from 'astro';
import { getRaceIndex, getStates } from '../../lib/data';
import { raceTitle, raceUrl, officeName } from '../../lib/format';

export const GET: APIRoute = () => {
  const races = getRaceIndex();
  const out: Record<string, unknown> = {};
  for (const s of getStates()) {
    const mine = races.filter((r) => r.state_po === s.state_po);
    const link = (r: (typeof races)[number]) => ({ office: officeName(r.office), title: raceTitle(r), url: raceUrl(r.race_id) });
    out[s.state_po] = {
      name: s.state_name,
      voter_info_url: s.office?.voter_info_url ?? s.office?.homepage_url ?? null,
      house: Object.fromEntries(mine.filter((r) => r.office === 'house').map((r) => [String(r.district), link(r)])),
      statewide: mine.filter((r) => r.office !== 'house').map(link),
    };
  }
  return new Response(JSON.stringify(out), { headers: { 'Content-Type': 'application/json' } });
};
