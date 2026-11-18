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
assert.strictEqual(B.eventAge({ ...status, first_seen: new Date(2026, 10, 17, 13, 5).toISOString() }, generated, buildTime), 'since 1:05 pm');
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

const titles = [{ id: 'lead', title: 'Story' }, { id: 'other', title: 'Story' }, { id: 'third', title: 'Different' }];
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
  console.log('review fixes ok');
}
