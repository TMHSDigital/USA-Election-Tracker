# Seed data review checklist (compiled 2026-10-18)

The candidate and election office seeds were compiled from official sources on
2026-10-18. The items below need a human check before or soon after launch.
Tick them off in the commit that edits the seeds, and log any published change in
`data/corrections.yaml`.

## Policy decisions

- [ ] **Write-ins.** Seeds include write-in candidates only where the official
  source calls them "certified" or "qualified" (governor: AK, GA, TX; federal:
  AK, AZ, CO, DE, FL, GA, IN, KY, MD, TX, UT, WI, WV, DC). Lists described as
  "declared", "registered", or "write-in candidate" (governor AZ, FL, ID, ME, WI)
  were left out. Decide whether to include them.
- [ ] **Incumbent rule.** Incumbent means the current holder of the same office;
  for House, the same district number in the same state. Under this rule TX and
  TN members in renumbered maps keep the flag when the number matches, and
  members in FL, CA, and UT running under a new number do not. Confirm.

## States with no official list (fallback in use)

- [ ] **Arkansas governor:** no general election list published; page shows
  "official list not yet compiled". Check a county sample ballot.
- [ ] **Ohio U.S. House:** no statewide certified House list; FEC registrant
  fallback shown. Look for county board certifications or the SOS sample ballot.
- [ ] **Arkansas federal:** built from the SOS filing search (one filer per party
  per seat); ballot names include titles such as "Senator Tom Cotton".
- [ ] **Oklahoma federal:** derived from certified primary and runoff results.

## Weaker source types to confirm in a browser

- [ ] MN (results-system candidate file; the official candidate site is
  captcha-protected), IL (filing search), PA (database), KS, SC, OK, SD, ID, VT,
  WY, TN listings.
- [ ] MI (official listing hosted on mi-boe.entellitrak.com, dated Sept 4).
- [ ] AZ governor section and AL certifications were transcribed by hand from a
  browser view and scanned PDFs.

## Specific rows

- [ ] SC U.S. Senate: state list marks Lindsey Graham "Deceased After Primary"
  and shows Darline Graham as the Republican nominee and current senator.
  Verify against senate.gov and the SC Election Commission.
- [ ] MA-1 Richard E. Neal: party left blank (the source shows none).
- [ ] WI-8: source spells "Weid, Tony"; the ballot reads "Tony Wied". Compose
  warns that the incumbent flag does not match congress-legislators.
- [ ] TX-18 Christian Menefee marked incumbent from house.gov; state data does
  not flag him.
- [ ] TX-38 Alex McMenemy (Green): state record has an inactive flag but he
  appears in every county ballot-order report.
- [ ] FL CD10 Maxwell Frost: status "Unopposed"; under Florida law unopposed
  candidates usually do not appear on the ballot.
- [ ] FL U.S. Senate set to special (remainder of term); the list says only
  "United States Senator".
- [ ] ID U.S. Senate: Democrat David Roth withdrew 9/1/2026 and is excluded; he
  may still be printed on ballots.
- [ ] GA U.S. Senate: no Libertarian on the official list.
- [ ] MT: Daines shown as withdrawn by the source. ME Democratic Senate nominee
  is Troy Jackson (replacement). Confirm both.
- [ ] RI governor: close Republican primary; check recount status.
- [ ] NH governor list dated 9/17; review the post-primary vacancies document.
- [ ] NM governor: four independents disqualified; check for litigation.
- [ ] NJ Senate: amended certification links returned 404.
- [ ] NY: "Vote Affordable" line name joined from two PDF lines.
- [ ] MA governor: ballot gives surnames only; first names missing for the
  Independent ticket.
- [ ] CT: "Matt Corey" (ballot) vs "Matthew Corey" (voter guide).

## FEC finance matching

Compose reports ambiguous matches (finance hidden until resolved through
`data/seeds/fec-id-overrides.csv`):

- [ ] IN-02 William Eric Henry, LA-05 Antonio Wilson, MI-10 Mike Saliba, MO-01
  Paul Berry III, NC-04 Mahesh Aychut Ganorkar, NC-08 Mark Everette Harris,
  UT-02 Carlton E. Bowen, UT-03 Michael R. Stoddard.

## State election office seed

- [ ] Office names were written from general knowledge, not copied from each
  official site. Check exact wording (for example Maine, Pennsylvania).
- [ ] Results URLs on vendor domains: AR (tally-enr.com), CT (tgstg.net), TX
  (civixapps.com), CO, SC, WV (Clarity). Confirm each is linked from the
  official state site.
- [ ] Results landing pages to replace with the live 2026 general pages when
  posted: AL, CA, MI, OK, OR, MD, ME, MS, WI, WY, IL, MA, NH, HI, DE.
- [ ] `results_platform` values for GA, ID, UT, WA, RI ("enhanced-voting") and
  IA ("clarity") are inferred from URL patterns.
