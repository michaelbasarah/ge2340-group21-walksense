import test from 'node:test';
import assert from 'node:assert/strict';
import { MAP_DATA } from '../dist/map-data.mjs';
import { findRoute, buildInstructions, validateMapData } from '../dist/route-engine.mjs';

test('illustrative map has valid unique graph references and both floors', () => {
  assert.deepEqual(validateMapData(MAP_DATA), { valid: true, errors: [] });
  assert.equal(MAP_DATA.isDemo, true);
  assert.equal(MAP_DATA.calibrated, false);
  assert.deepEqual(MAP_DATA.floors.map(floor => floor.id), ['5', '4']);
  assert.equal(MAP_DATA.places.filter(place => place.name === 'Y5 302').length, 1);
  assert.equal(MAP_DATA.places.length, 24);
});

test('all 24 places can reach every other place through legal graph edges', () => {
  for (const start of MAP_DATA.places) for (const end of MAP_DATA.places) {
    const route = findRoute(MAP_DATA, start.id, end.id);
    assert.equal(route.status, start.id === end.id ? 'same' : 'ok', `${start.id} -> ${end.id}`);
    assert.equal(route.nodeIds[0], start.nodeId);
    assert.equal(route.nodeIds.at(-1), end.nodeId);
    assert.ok(route.edges.every(edge => MAP_DATA.edges.some(original =>
      original.from === edge.from && original.to === edge.to ||
      original.bidirectional && original.to === edge.from && original.from === edge.to)));
  }
});

test('5F to 4F travels down the down escalator, never backwards on the up escalator', () => {
  const route = findRoute(MAP_DATA, 'f5-exit-5', 'f4-y4052');
  const connectors = route.edges.filter(edge => edge.type === 'escalator');
  assert.equal(connectors.length, 1);
  assert.equal(connectors[0].from, 'node:f5-down-escalator');
  assert.equal(connectors[0].to, 'node:f4-down-escalator');
  assert.equal(route.floorChanges, 1);
  assert.deepEqual(route.floorSegments.map(segment => segment.floorId), ['5', '4']);
  assert.ok(route.steps.some(step => step.type === 'floor-change' && step.direction === 'down' && step.nextFloorId === '4'));
});

test('4F to 5F travels up the up escalator, never backwards on the down escalator', () => {
  const route = findRoute(MAP_DATA, 'f4-y4052', 'f5-y5302');
  const connectors = route.edges.filter(edge => edge.type === 'escalator');
  assert.equal(connectors.length, 1);
  assert.equal(connectors[0].from, 'node:f4-up-escalator');
  assert.equal(connectors[0].to, 'node:f5-up-escalator');
  assert.deepEqual(route.floorSegments.map(segment => segment.floorId), ['4', '5']);
});

test('same-floor routes remain on their floor and use corridor anchors', () => {
  const route = findRoute(MAP_DATA, 'f5-study-11', 'f5-study-8');
  assert.equal(route.floorChanges, 0);
  assert.ok(route.nodeIds.some(id => id.includes(':top:')));
  assert.ok(route.nodeIds.some(id => id.includes(':bottom:')));
});

test('starting at destination produces a useful zero-distance arrival', () => {
  const route = findRoute(MAP_DATA, 'f4-y4052', 'f4-y4052');
  assert.equal(route.status, 'same');
  assert.equal(route.totalCost, 0);
  assert.equal(route.distanceMeters, 0);
  assert.equal(route.edges.length, 0);
  assert.match(route.steps[0].text, /already at Y4052/);
});

test('unknown places and malformed/negative graph costs produce invalid results', () => {
  assert.equal(findRoute(MAP_DATA, 'unknown', 'f5-y5302').status, 'invalid');
  assert.equal(findRoute({}, 'a', 'b').status, 'invalid');
  const broken = { ...MAP_DATA, edges: [{ ...MAP_DATA.edges[0], cost: -1 }] };
  assert.equal(findRoute(broken, 'f5-exit-5', 'f4-y4052').status, 'invalid');
});

function fixture(edges) {
  return { nodes: [
    { id: 'a', floorId: '5', x: 0, y: 0 },
    { id: 'b', floorId: '5', x: 10, y: 0 },
    { id: 'c', floorId: '5', x: 20, y: 0 },
  ], places: ['a', 'b', 'c'].map(id => ({ id, name: id.toUpperCase(), floorId: '5', nodeId: id })), edges };
}

test('disconnected destination reports unreachable and has no invented path', () => {
  const map = fixture([{ from: 'a', to: 'b', cost: 1, bidirectional: true }]);
  const route = findRoute(map, 'a', 'c');
  assert.equal(route.status, 'unreachable');
  assert.deepEqual(route.nodeIds, []);
  assert.deepEqual(buildInstructions(map, route), []);
});

test('routing chooses the lowest legal total cost rather than fewest edges', () => {
  const map = fixture([
    { from: 'a', to: 'c', cost: 10 },
    { from: 'a', to: 'b', cost: 2 },
    { from: 'b', to: 'c', cost: 3 },
  ]);
  const route = findRoute(map, 'a', 'c');
  assert.deepEqual(route.nodeIds, ['a', 'b', 'c']);
  assert.equal(route.totalCost, 5);
  assert.equal(findRoute(map, 'c', 'a').status, 'unreachable');
});

test('layout costs never become pretend metres; complete real weights can be summed', () => {
  assert.equal(findRoute(MAP_DATA, 'f5-exit-5', 'f4-y4052').distanceMeters, null);
  const map = fixture([
    { from: 'a', to: 'b', cost: 2, distanceMeters: 4.5 },
    { from: 'b', to: 'c', cost: 3, distanceMeters: 7.5 },
  ]);
  assert.equal(findRoute(map, 'a', 'c').distanceMeters, 12);
  map.edges[1].distanceMeters = null;
  assert.equal(findRoute(map, 'a', 'c').distanceMeters, null);
});

test('floor-segment endpoints and instruction nodes faithfully follow the route', () => {
  const route = findRoute(MAP_DATA, 'f5-canteen', 'f4-lt2a');
  assert.deepEqual(route.floorSegments.flatMap(segment => segment.nodeIds), route.nodeIds);
  for (const step of route.steps) assert.ok(step.nodeIds.every(id => route.nodeIds.includes(id)));
  assert.ok(route.steps.every(step => !/\b\d+\s*(?:m|metres|minutes)\b/.test(step.text)));
});
