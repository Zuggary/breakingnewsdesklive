const B = require('../lib.js'), assert = require('assert');
const now = Date.parse('2026-11-14T12:00:00Z');
const ev = [{type:'earthquake',region:'Asia',time:'2026-11-14T11:00:00Z'},{type:'weather',region:'Americas',time:'2026-11-12T11:00:00Z'}];
assert.strictEqual(B.filterEvents(ev,{type:'all',region:'all',day:true},now).length,1);
assert.strictEqual(B.filterEvents(ev,{type:'weather'},now).length,1);
assert.strictEqual(B.filterEvents(ev,{region:'Asia'},now).length,1);
assert.strictEqual(B.ago('2026-11-14T11:30:00Z',now),'30m ago');
assert.strictEqual(B.safeUrl('javascript:alert(1)'),null);
assert.ok(B.safeUrl('https://usgs.gov/x'));
assert.strictEqual(B.filterEvents(ev,{hours:6},now).length,1);
assert.strictEqual(B.filterEvents(ev,{type:'g:hazards'},now).length,2);
assert.strictEqual(B.filterEvents(ev,{type:'g:transport'},now).length,0);
console.log('lib.js ok');

var sevEv=[{type:'earthquake',severity:'extreme',time:new Date(now).toISOString(),region:'Asia'},{type:'weather',severity:'severe',time:new Date(now).toISOString(),region:'Americas'},{type:'flood',severity:'moderate',time:new Date(now).toISOString(),region:'Asia'},{type:'storm',severity:'minor',time:new Date(now).toISOString(),region:'Asia'}];
assert.strictEqual(B.filterEvents(sevEv,{sev:'extreme'},now).length,1);
assert.strictEqual(B.filterEvents(sevEv,{sev:'severe'},now).length,2);
assert.strictEqual(B.filterEvents(sevEv,{sev:'moderate'},now).length,3);
assert.strictEqual(B.filterEvents(sevEv,{sev:''},now).length,4);
console.log('severity filter ok');

const first = { id: 'a', type: 'aviation', title: 'Ash advisory', severity: 'severe' };
const otherType = { id: 'b', type: 'weather', title: 'Ash advisory', severity: 'severe' };
const duplicate = { ...first, id: 'c' };
const otherPlace = { ...first, id: 'e', place: 'Another county' };
const otherSeverity = { ...first, id: 'f', severity: 'extreme' };
const otherTitle = { ...first, id: 'd', title: 'Wind advisory' };
assert.deepStrictEqual(B.groupEvents([first, otherType, duplicate, otherTitle]), [
  { ev: first, members: [first, duplicate] },
  { ev: otherType, members: [otherType] },
  { ev: otherTitle, members: [otherTitle] },
]);
assert.strictEqual(B.groupEvents([first, otherPlace, otherSeverity]).length, 3); // different place or severity never collapses
assert.deepStrictEqual(B.groupEvents([]), []);
console.log('feed grouping ok');

const generated = '2026-11-18T19:53:36Z';
const buildTime = Date.parse(generated);
const status = { time: '2026-11-18T19:48:36Z', first_seen: new Date(2026, 10, 18, 1, 5).toISOString() };
assert.strictEqual(B.eventAge(status, generated, buildTime), 'since 1:05 am');
assert.strictEqual(B.eventAge({ ...status, first_seen: new Date(2026, 10, 17, 13, 5).toISOString() }, generated, buildTime), 'since yesterday 1:05 pm');
assert.strictEqual(B.eventAge({ ...status, first_seen: '2026-11-18T19:38:36Z' }, generated, buildTime), '5m ago');
assert.strictEqual(B.eventAge({ time: status.time }, generated, buildTime), '5m ago');
assert.strictEqual(B.eventAge({ ...status, time: '2026-11-18T19:37:36Z' }, generated, buildTime), '16m ago');

const fresh = { id: 'fresh', severity: 'moderate', time: generated };
const stale = { id: 'stale', severity: 'severe', time: new Date(buildTime - 25 * 36e5).toISOString() };
const extreme = { ...stale, id: 'extreme', severity: 'extreme' };
const cutoff = { ...stale, id: 'cutoff', time: new Date(buildTime - 72 * 36e5).toISOString() };
const old = { ...cutoff, id: 'old', time: new Date(Date.parse(cutoff.time) - 1).toISOString() };
const updated = { ...old, id: 'updated', updated: generated };
const ages = [stale, old, fresh, extreme, cutoff, updated];
assert.deepStrictEqual(B.filterEvents(ages, {}, buildTime), [extreme, fresh, updated, stale, cutoff]);
assert.deepStrictEqual(B.filterEvents(ages, { hours: 0 }, buildTime), [extreme, fresh, updated, stale, old, cutoff]);
assert.deepStrictEqual(B.filterEvents(ages, { hours: 24 }, buildTime), [fresh, updated]);

const titles = [{ id: 'lead', title: 'Story', confidence: 'Reported' }, { id: 'other', title: 'Story', confidence: 'Reported' }, { id: 'third', title: 'Different' }];
assert.deepStrictEqual(B.withoutLead(titles, { id: 'lead', headline: 'Different' }), titles.slice(1));
assert.deepStrictEqual(B.withoutLead(titles, { headline: 'Story' }), titles.slice(2));
assert.deepStrictEqual(B.withoutLead(titles, null), titles);

const replay = require('./fixtures/replay-1118.json');
const rows = B.groupEvents(B.filterEvents(replay.events, {}, Date.parse(replay.generated)));
assert.ok(!rows.slice(0, 10).some(({ ev }) => ev.id === 'usgs-us7000tymu'));
assert.ok(!rows.some(({ ev }) => ev.id === 'volcano-311120'));
assert.ok(B.filterEvents(replay.events, { hours: 0 }, Date.parse(replay.generated)).some(e => e.id === 'volcano-311120'));
const groundStops = replay.events.filter(e => e.source_id === 'atd-faa' && e.title.startsWith('Ground stop'));
assert.ok(groundStops.length);
for (const event of groundStops) {
  assert.match(B.eventAge(event, replay.generated, Date.parse(replay.generated)), /^since \d{1,2}:\d{2} [ap]m$/);
}
console.log('routine and stale item helpers ok');

{
  const fixed = Date.parse('2026-11-18T20:00:00Z');
  const oldExtreme = { id: 'old-x', type: 'weather', title: 'Blizzard Warning', severity: 'extreme', time: new Date(fixed - 80 * 36e5).toISOString() };
  const oldModerate = { ...oldExtreme, id: 'old-m', severity: 'moderate' };
  for (const f of [{}, { hours: 72 }]) assert.deepStrictEqual(B.filterEvents([oldExtreme, oldModerate], f, fixed).map(e => e.id), ['old-x']); // the app default is hours 72
  assert.strictEqual(B.eventAge({ ...status, first_seen: new Date(2026, 10, 15, 13, 5).toISOString() }, generated, buildTime), 'since Nov 15 1:05 pm');
  const advisory = { id: 'adv', title: 'Lead headline', severity: 'extreme' };
  const newsRow = { id: 'n1', title: 'Lead headline', confidence: 'Corroborated' };
  assert.deepStrictEqual(B.withoutLead([advisory, newsRow], { headline: 'Lead headline' }).map(e => e.id), ['adv']); // no lead id: only the news row goes
  console.log('review fixes ok');
}

{
  // GD11 + Editorial Front Page helper tests
  assert.strictEqual(B.cleanDc('Briefing in Washington, D.C. today'), 'Briefing in DC today');
  assert.strictEqual(B.cleanDc('District of Columbia alert'), 'DC alert');
  assert.strictEqual(B.cleanDc('Washington State flood warning'), 'Washington State flood warning');
  assert.strictEqual(B.cleanDc('Miguel &#xC1;ngel Asturias &amp; team'), 'Miguel \u00c1ngel Asturias & team');

  assert.strictEqual(B.formatCoord(null, -77.0), null);
  assert.strictEqual(B.formatCoord(38.9, -77.0), '38.9\u00b0N 77.0\u00b0W');

  assert.strictEqual(B.verificationTag({ type: 'headline', status: 'UNVERIFIED', confidence: 'Corroborated' }).code, 'CORROBORATED');
  assert.strictEqual(B.verificationTag({ type: 'headline', status: 'UNVERIFIED' }).code, 'UNVERIFIED');
  assert.strictEqual(B.verificationTag({ type: 'statement', status: 'UNVERIFIED' }).code, 'UNVERIFIED');
  assert.strictEqual(B.verificationTag({ type: 'earthquake', status: 'DEVELOPING', confidence: 'Official single source' }).code, 'DEVELOPING');
  assert.strictEqual(B.verificationTag({ type: 'earthquake', status: '', confidence: 'Official single source' }).code, 'OFFICIAL SINGLE SOURCE');
  assert.strictEqual(B.verificationTag({ type: 'outage', source_id: 'probes', detail: { lane: 'probes', open: true } }).code, 'UNVERIFIED');
  assert.strictEqual(B.verificationTag({ type: 'outage', source_id: 'probes', detail: { lane: 'probes', open: false } }).code, 'RESOLVED');

  assert.strictEqual(
    B.whatChangedLine({
      time: '2026-11-17T12:00:00Z',
      updated: '2026-11-17T14:05:00Z',
      history: [{ t: '2026-11-17T14:05:00Z', from: 'Unverified lead', to: 'Corroborated' }]
    }),
    'Updated 14:05 UTC: label raised from Unverified lead to Corroborated'
  );
  assert.strictEqual(
    B.whatChangedLine({
      time: '2026-11-17T12:00:00Z',
      history: [{ t: '2026-11-17T13:10:00Z', why: 'notice from Airline disappeared (not a resolution)' }]
    }),
    'Updated 13:10 UTC: notice from Airline disappeared (not a resolution)'
  );
  assert.strictEqual(
    B.whatChangedLine({ time: '2026-11-17T12:00:00Z', updated: '2026-11-17T13:30:00Z' }),
    'Updated 13:30 UTC: bulletin revised since 12:00 UTC'
  );
  assert.strictEqual(
    B.whatChangedLine({ type: 'outage', time: '2026-11-18T18:56:15Z', detail: { measured_at: '1:56 PM ET' } }),
    'Measured by the desk: first failing probe at 1:56 PM ET (no service resolution statement)'
  );
  assert.strictEqual(
    B.whatChangedLine({ time: '2026-11-17T12:00:00Z' }),
    'No changes since first published at 12:00 UTC.'
  );

  const sampleEvents = [
    { id: 'h1', type: 'headline', title: 'Outlet rumor', place: 'World', time: '2026-11-18T12:00:00Z', severity: 'minor', source: 'GDELT', summary: 'Summary one.' },
    { id: 'q1', type: 'earthquake', title: 'M 6.1 earthquake', place: 'Ridge', time: '2026-11-18T11:00:00Z', severity: 'severe', source: 'USGS', source_url: 'https://earthquake.usgs.gov/', summary: 'Quake recorded. Depth 10 km.' },
    { id: 'c1', type: 'security', title: 'Curated outage report', place: 'United States', time: '2026-11-18T10:00:00Z', severity: 'moderate', confidence: 'Corroborated', curated: true, detail: { lane: 'curated', sources: [{ source: 'AP' }, { source: 'Reuters' }], reported_line: 'Reported by AP and Reuters' }, links: [{ label: 'AP', url: 'https://apnews.com/1' }], summary: 'First sentence. Second sentence. Third sentence.' },
    { id: 'p1', type: 'outage', source_id: 'probes', title: 'Bank login probe failing', place: 'United States', time: '2026-11-18T09:00:00Z', severity: 'moderate', detail: { lane: 'probes', open: true, services_failing: 2 }, summary: 'Probe failed.' },
    { id: 'f1', type: 'transport', source_id: 'atd-faa', title: 'Delays at SFO', place: 'San Francisco', time: '2026-11-18T08:00:00Z', severity: 'moderate', summary: 'Delays.' }
  ];
  const derived = B.deriveLeadStory(sampleEvents, '2026-11-18T12:05:00Z');
  assert.strictEqual(derived.lead.id, 'c1');
  assert.strictEqual(derived.lead.summary, 'First sentence. Second sentence.');
  const recap = B.buildRecapItems(sampleEvents, sampleEvents[2]);
  assert.strictEqual(recap.primary.id, 'c1');
  assert.strictEqual(recap.secondary.id, 'q1');
  assert.strictEqual(B.streamFocusId([sampleEvents[0], sampleEvents[1]], { id: 'h1' }), 'q1');
  assert.strictEqual(B.streamFocusId(sampleEvents, derived.lead), 'c1');

  const ops = B.opsCounts(sampleEvents, { sources: [{ id: 'a', ok: true, freshness: 'fresh' }, { id: 'b', ok: true, freshness: 'stale' }] });
  assert.strictEqual(ops.total, 5);
  assert.strictEqual(ops.severeHazards, 1);
  assert.strictEqual(ops.probeFailing, 2);
  assert.strictEqual(ops.airspace, 1);
  assert.strictEqual(ops.feedsFresh, 1);
  assert.strictEqual(ops.feedsStale, 1);

  assert.ok(B.validatedCommonsImage({
    image: {
      src: 'https://commons.wikimedia.org/wiki/Special:FilePath/Example.jpg',
      author: 'Jane Doe',
      license: 'CC BY 4.0',
      credit_url: 'https://commons.wikimedia.org/wiki/File:Example.jpg'
    }
  }));
  assert.strictEqual(B.validatedCommonsImage({
    image: {
      src: 'https://commons.wikimedia.org/wiki/Special:FilePath/Example.jpg',
      author: '',
      license: 'CC BY 4.0',
      credit_url: 'https://commons.wikimedia.org/wiki/File:Example.jpg'
    }
  }), null);
  assert.strictEqual(B.validatedCommonsImage({
    image: {
      src: 'https://commons.wikimedia.org/wiki/Special:FilePath/Example.jpg',
      author: 'Jane Doe',
      license: 'CC BY 4.0',
      credit_url: 'https://example.org/not-commons'
    }
  }), null);
  console.log('gd11 editorial front-page helpers ok');
}

{
  // Round 2 polish tests: entity decoding, stale labelling, item-boundary ticker, non-truncating callouts
  assert.strictEqual(B.decodeEntities('Miguel &#xC1;ngel Asturias'), 'Miguel \u00c1ngel Asturias');
  assert.strictEqual(B.decodeEntities('Miguel &amp;#xC1;ngel &mdash; &ldquo;test&rdquo; &eacute; &Aacute;'), 'Miguel \u00c1ngel \u2014 \u201ctest\u201d \u00e9 \u00c1');
  assert.strictEqual(B.cleanDc('Briefing for Miguel &#xC1;ngel in Washington, D.C.'), 'Briefing for Miguel \u00c1ngel in DC');

  const dirtyEv = {
    id: 'gdelt-test',
    title: 'Headline: \u201cMiguel &#xC1;ngel Asturias &amp; DC\u201d',
    place: 'Washington, D.C.',
    summary: 'Ceremony for Miguel &#xC1;ngel &rsquo;s team.',
    source: 'Example &amp; Wire',
    detail: { headline: 'Miguel &#xC1;ngel Asturias', sources: [{ source: 'Example &amp; Co' }] },
    links: [{ label: 'site.example', title: 'Miguel &#xC1;ngel Asturias' }],
    history: [{ t: '2026-11-15T00:00:00Z', why: 'Updated for Miguel &#xC1;ngel' }]
  };
  const cleanEv = B.sanitizeEvent(dirtyEv);
  assert.strictEqual(cleanEv.title, 'Headline: \u201cMiguel \u00c1ngel Asturias & DC\u201d');
  assert.strictEqual(cleanEv.place, 'DC');
  assert.strictEqual(cleanEv.detail.headline, 'Miguel \u00c1ngel Asturias');
  assert.strictEqual(cleanEv.links[0].title, 'Miguel \u00c1ngel Asturias');
  assert.strictEqual(cleanEv.history[0].why, 'Updated for Miguel \u00c1ngel');

  const snapGen = '2026-11-15T01:20:04Z';
  const freshNow = Date.parse('2026-11-15T01:30:00Z');
  const staleNow = Date.parse('2026-11-19T02:20:00Z');
  assert.strictEqual(B.isSnapshotFresh(snapGen, freshNow), true);
  assert.strictEqual(B.isSnapshotFresh(snapGen, staleNow), false);

  const oldWarn = { id: 'w1', type: 'weather', time: '2026-11-14T18:54:00Z', first_seen: '2026-11-13T23:59:00Z', source_id: 'nws-alerts' };
  const oldHead = { id: 'h1', type: 'headline', time: '2026-11-15T00:45:00Z', source_id: 'gdelt-doc' };
  assert.strictEqual(B.eventAge(oldWarn, snapGen, staleNow), '4d ago');
  const fw = B.itemFreshness(oldWarn, snapGen, staleNow, { checked: snapGen, ok: true, freshness: 'fresh' });
  assert.strictEqual(fw.stale, false);
  assert.strictEqual(fw.badge, '');
  assert.strictEqual(fw.ageText, '4d ago');
  const fh = B.itemFreshness(oldHead, snapGen, staleNow, null);
  assert.strictEqual(fh.stale, false);
  assert.strictEqual(fh.ageText, '4d ago');

  const staleFeedItem = B.itemFreshness(oldWarn, snapGen, staleNow, { checked: snapGen, ok: false, freshness: 'stale' });
  assert.strictEqual(staleFeedItem.stale, true);
  assert.strictEqual(staleFeedItem.badge, 'SOURCE STALE');

  const freshWarn = { id: 'w2', type: 'weather', time: '2026-11-15T01:10:00Z', source_id: 'nws-alerts' };
  const ff = B.itemFreshness(freshWarn, snapGen, freshNow, { checked: snapGen, ok: true, freshness: 'fresh' });
  assert.strictEqual(ff.stale, false);
  assert.strictEqual(ff.badge, '');
  assert.strictEqual(ff.ageText, '20m ago');

  const opsFresh = B.opsCounts([oldWarn], { sources: [{ id: 'nws-alerts', ok: true, freshness: 'fresh', checked: snapGen }] }, staleNow);
  assert.strictEqual(opsFresh.feedsFresh, 1);
  assert.strictEqual(opsFresh.feedsStale, 0);
  const opsStale = B.opsCounts([oldWarn], { sources: [{ id: 'nws-alerts', ok: false, freshness: 'stale', checked: snapGen }] }, staleNow);
  assert.strictEqual(opsStale.feedsFresh, 0);
  assert.strictEqual(opsStale.feedsStale, 1);

  assert.strictEqual(B.distinctPlace({ title: 'Tropical Cyclone Xavier', place: 'Tropical Cyclone Xavier' }), '');
  assert.strictEqual(B.distinctPlace({ title: 'M 6.1 earthquake', place: 'Pacific-Antarctic Ridge' }), 'Pacific-Antarctic Ridge');
  assert.strictEqual(B.hasRevision({ time: '2026-11-18T10:00:00Z' }), false);
  assert.strictEqual(B.shortChangedTag({ time: '2026-11-18T10:00:00Z' }), '');
  assert.strictEqual(B.hasRevision({ time: '2026-11-18T10:00:00Z', updated: '2026-11-18T12:15:00Z' }), true);
  assert.strictEqual(B.shortChangedTag({ time: '2026-11-18T10:00:00Z', updated: '2026-11-18T12:15:00Z' }), 'Updated 12:15 UTC');
  assert.strictEqual(
    B.shortChangedTag({ time: '2026-11-18T10:00:00Z', history: [{ t: '2026-11-18T14:05:00Z', from: 'Unverified lead', to: 'Corroborated' }] }),
    'Updated 14:05 UTC \u00b7 Corroborated'
  );
  assert.strictEqual(
    B.shortChangedTag({ type: 'outage', time: '2026-11-19T09:36:35Z', detail: { measured_at: '4:36 AM ET' } }),
    'Probe fail 4:36 AM ET'
  );

  assert.strictEqual(B.trimWholeWords('Severe Blizzard Warning across northern Alaska coastal zones', 28), 'Severe Blizzard Warning\u2026');
  assert.deepStrictEqual(B.packTickerItems([140, 160, 200, 120], 340, 20, 0), { indices: [0, 1], overflowSingle: false });
  assert.deepStrictEqual(B.packTickerItems([140, 160, 200, 120], 340, 20, 2), { indices: [2, 3], overflowSingle: false });
  assert.deepStrictEqual(B.packTickerItems([420, 160], 300, 20, 0), { indices: [0], overflowSingle: true });

  assert.strictEqual(B.mapCalloutText({ type: 'volcano', title: 'Great Sitkin volcano', place: 'Alaska Volcano Observatory', detail: { volcano: 'Great Sitkin', alert_level: 'Watch' } }), 'Great Sitkin \u00b7 Watch');
  assert.strictEqual(B.mapCalloutText({ type: 'earthquake', title: 'M 5.8 earthquake', place: '79 km WSW of Changuillo, Peru', detail: { magnitude: 5.8 } }), 'M 5.8 \u00b7 Changuillo, Peru');
  assert.strictEqual(B.mapCalloutText({ type: 'weather', title: 'Blizzard Warning', place: 'Alaska, United States' }), 'Blizzard Warning \u00b7 Alaska');

  const placed = B.placeMapCallouts([
    { id: 'a', rowId: 'a', pinX: 80, pinY: 70, w: 120, h: 24, rank: 0, isSelected: false },
    { id: 'b', rowId: 'b', pinX: 84, pinY: 72, w: 120, h: 24, rank: 1, isSelected: true },
    { id: 'c', rowId: 'c', pinX: 250, pinY: 120, w: 120, h: 24, rank: 2, isSelected: false }
  ], 400, 220, 5);
  assert.strictEqual(placed.length, 3);
  assert.strictEqual(placed[0].id, 'b'); // selected placed first
  for (const box of placed) {
    assert.ok(box.boxX >= 6 && box.boxX + box.w <= 394 && box.boxY >= 6 && box.boxY + box.h <= 214);
  }
  console.log('round 2 polish helpers ok');
}

{
  // Round 4 fix tests: non-duplicating briefing, non-truncating callouts, pin avoidance, consistent severity counts
  const leadEv = { id: 'lead-1', type: 'security', title: 'AP and CNN report flooding in Brevard', severity: 'moderate', confidence: 'Corroborated' };
  const probeEv = { id: 'p-1', type: 'outage', title: 'Regions login page responding badly', severity: 'moderate', detail: { lane: 'probes', open: true } };
  const wxEv = { id: 'wx-1', type: 'weather', title: 'Flood Warning', severity: 'severe', confidence: 'Official single source' };
  const secEv = { id: 'sec-2', type: 'security', title: 'Senate hearing update', severity: 'moderate', confidence: 'Corroborated' };
  const brief = B.selectBriefingItems([leadEv, probeEv, wxEv, secEv], 'lead-1', 2);
  assert.strictEqual(brief.length, 2);
  assert.ok(brief.every(e => e.id !== 'lead-1'));
  assert.notStrictEqual(brief[0].type, brief[1].type);

  assert.strictEqual(
    B.mapCalloutText({ type: 'earthquake', title: 'M 5.3 earthquake', place: 'South Georgia Island region', detail: { magnitude: 5.3 } }),
    'M 5.3 \u00b7 South Georgia Island'
  );
  assert.strictEqual(
    B.mapCalloutText({ type: 'transport', title: 'Ground delay program at SFO', place: 'San Francisco International', detail: { airport_code: 'SFO', kind: 'Ground delay program' } }),
    'SFO \u00b7 Ground delay'
  );
  assert.ok(!B.mapCalloutText({ type: 'storm', title: 'Tropical Cyclone Xavier', place: 'Tropical Cyclone Xavier' }).includes('\u2026'));

  const pinObstacles = [
    { x: 100, y: 100, r: 9 },
    { x: 185, y: 100, r: 9 }
  ];
  const pinPlaced = B.placeMapCallouts([
    { id: 'p1', rowId: 'p1', pinX: 100, pinY: 100, w: 96, h: 24, rank: 0, isSelected: false },
    { id: 'p2', rowId: 'p2', pinX: 185, pinY: 100, w: 96, h: 24, rank: 1, isSelected: false }
  ], 420, 220, undefined, pinObstacles);
  assert.strictEqual(pinPlaced.length, 2);
  for (const box of pinPlaced) {
    for (const pin of pinObstacles) {
      const pr = pin.r + 3;
      const hitPin = box.boxX < pin.x + pr + 2 && box.boxX + box.w + 2 > pin.x - pr &&
        box.boxY < pin.y + pr + 2 && box.boxY + box.h + 2 > pin.y - pr;
      assert.strictEqual(hitPin, false, 'callout overlapped pin obstacle');
    }
  }

  const sevSample = [
    { id: '1', type: 'weather', severity: 'severe' },
    { id: '2', type: 'aviation', severity: 'severe' },
    { id: '3', type: 'earthquake', severity: 'moderate' }
  ];
  const counts4 = B.opsCounts(sevSample, { sources: [] });
  assert.strictEqual(counts4.severeTotal, 2);
  assert.strictEqual(counts4.severeHazards, 1);
  assert.strictEqual(counts4.severeAirspace, 1);
  assert.strictEqual(B.formatSevCount(sevSample), '2 severe');
  assert.strictEqual(B.formatSevCount([{ severity: 'extreme' }, ...sevSample]), '1 extreme, 2 severe');
  assert.strictEqual(B.formatSevCount({ extreme: 0, severe: 16, extremeTotal: 3 }), '16 severe');
  console.log('round 4 polish helpers ok');
}
