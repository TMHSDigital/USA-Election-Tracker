import { t } from '../i18n';
import type { Office, RaceSummary } from './data';

const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');

/** Prefix an internal path with the site base. Paths must start with "/". */
export const url = (p: string): string => `${BASE}${p}`;

export const raceUrl = (raceId: string) => url(`/races/${raceId}/`);
export const stateUrl = (po: string) => url(`/states/${po.toLowerCase()}/`);
export const sourceUrl = (sourceId: string) => url(`/sources/#${sourceAnchor(sourceId)}`);
export const sourceAnchor = (sourceId: string) => `src-${sourceId.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
export const dataUrl = (p: string) => url(`/data/${p}`);

export function officeName(o: Office): string {
  return t(`office.${o}` as 'office.house');
}

export function raceTitle(r: Pick<RaceSummary, 'office' | 'state_po' | 'state_name' | 'district' | 'special'>): string {
  if (r.office === 'house') {
    if (r.state_po === 'DC') return t('race.title.houseDelegate');
    if (r.district === 0) return t('race.title.houseAtLarge', { state: r.state_name });
    return t('race.title.house', { state: r.state_name, district: r.district ?? '' });
  }
  if (r.office === 'senate') {
    return t(r.special ? 'race.title.senateSpecial' : 'race.title.senate', { state: r.state_name });
  }
  return t('race.title.governor', { state: r.state_name });
}

export function raceHeading(r: Parameters<typeof raceTitle>[0]): string {
  return t('race.heading', { office: officeName(r.office), title: raceTitle(r) });
}

export function voteGovUrl(stateName: string): string {
  return `https://vote.gov/register/${stateName.toLowerCase().replace(/\s+/g, '-')}`;
}
