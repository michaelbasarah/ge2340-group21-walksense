// Pure routing functions. Costs are graph weights, not automatically metres.
function routeEmpty(status, extras = {}) {
  return { status, nodeIds: [], edges: [], totalCost: 0, distanceMeters: null,
    floorChanges: 0, floorSegments: [], steps: [], ...extras };
}

export function validateMapData(data) {
  const errors = [];
  if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.places) || !Array.isArray(data.edges)) {
    return { valid: false, errors: ['Map must contain nodes, places and edges arrays.'] };
  }
  const nodes = new Map();
  for (const node of data.nodes) {
    if (!node.id || nodes.has(node.id)) errors.push(`Missing or duplicate node ID: ${node.id}`);
    if (![node.x, node.y].every(Number.isFinite) || typeof node.floorId !== 'string') errors.push(`Invalid coordinates or floor for ${node.id}`);
    nodes.set(node.id, node);
  }
  const placeIds = new Set();
  for (const place of data.places) {
    if (!place.id || placeIds.has(place.id)) errors.push(`Missing or duplicate place ID: ${place.id}`);
    placeIds.add(place.id);
    const node = nodes.get(place.nodeId);
    if (!node || node.floorId !== place.floorId) errors.push(`Missing or mismatched place node for ${place.id}`);
  }
  for (const edge of data.edges) {
    if (!nodes.has(edge.from) || !nodes.has(edge.to)) errors.push(`Unknown edge endpoint: ${edge.from} → ${edge.to}`);
    if (!Number.isFinite(edge.cost) || edge.cost < 0) errors.push(`Invalid nonnegative cost for ${edge.from} → ${edge.to}`);
    if (edge.distanceMeters != null && (!Number.isFinite(edge.distanceMeters) || edge.distanceMeters < 0)) errors.push(`Invalid distance for ${edge.from} → ${edge.to}`);
  }
  return { valid: errors.length === 0, errors };
}

function routeSegments(nodeIds, nodeMap) {
  const segments = [];
  for (const id of nodeIds) {
    const node = nodeMap.get(id);
    let segment = segments.at(-1);
    if (!segment || segment.floorId !== node.floorId) {
      segment = { floorId: node.floorId, nodeIds: [], points: [] };
      segments.push(segment);
    }
    segment.nodeIds.push(id);
    segment.points.push([node.x, node.y]);
  }
  return segments;
}

export function findRoute(data, startPlaceId, endPlaceId) {
  const validation = validateMapData(data);
  if (!validation.valid) return routeEmpty('invalid', { errors: validation.errors });
  const start = data.places.find(place => place.id === startPlaceId);
  const destination = data.places.find(place => place.id === endPlaceId);
  if (!start || !destination) return routeEmpty('invalid', { errors: ['Choose a valid starting point and destination.'] });
  const nodeMap = new Map(data.nodes.map(node => [node.id, node]));
  if (start.nodeId === destination.nodeId) {
    const route = routeEmpty('same', { startPlaceId, endPlaceId, nodeIds: [start.nodeId],
      distanceMeters: 0, floorSegments: routeSegments([start.nodeId], nodeMap) });
    route.steps = buildInstructions(data, route);
    return route;
  }
  const adjacency = new Map(data.nodes.map(node => [node.id, []]));
  data.edges.forEach((edge, index) => {
    adjacency.get(edge.from).push({ ...edge, edgeIndex: index, reversed: false });
    if (edge.bidirectional) adjacency.get(edge.to).push({ ...edge, from: edge.to, to: edge.from, edgeIndex: index, reversed: true });
  });
  const distances = new Map([[start.nodeId, 0]]);
  const previous = new Map();
  const settled = new Set();
  while (true) {
    let current = null;
    let best = Infinity;
    for (const [id, distance] of distances) {
      if (!settled.has(id) && distance < best) { current = id; best = distance; }
    }
    if (current === null || current === destination.nodeId) break;
    settled.add(current);
    for (const edge of adjacency.get(current)) {
      const distance = best + edge.cost;
      if (distance < (distances.get(edge.to) ?? Infinity)) {
        distances.set(edge.to, distance);
        previous.set(edge.to, edge);
      }
    }
  }
  if (!distances.has(destination.nodeId)) return routeEmpty('unreachable', { startPlaceId, endPlaceId });
  const edges = [];
  let cursor = destination.nodeId;
  while (cursor !== start.nodeId) {
    const edge = previous.get(cursor);
    if (!edge) return routeEmpty('unreachable', { startPlaceId, endPlaceId });
    edges.unshift(edge); cursor = edge.from;
  }
  const nodeIds = [start.nodeId, ...edges.map(edge => edge.to)];
  const route = {
    status: 'ok', startPlaceId, endPlaceId, nodeIds, edges,
    totalCost: distances.get(destination.nodeId),
    distanceMeters: edges.every(edge => Number.isFinite(edge.distanceMeters))
      ? edges.reduce((sum, edge) => sum + edge.distanceMeters, 0) : null,
    floorChanges: edges.filter(edge => nodeMap.get(edge.from).floorId !== nodeMap.get(edge.to).floorId).length,
    floorSegments: routeSegments(nodeIds, nodeMap), steps: [],
  };
  route.steps = buildInstructions(data, route);
  return route;
}

function routeTurnText(previous, current) {
  if (!previous) return 'Follow the corridor';
  const cross = previous[0] * current[1] - previous[1] * current[0];
  const dot = previous[0] * current[0] + previous[1] * current[1];
  const angle = Math.atan2(cross, dot) * 180 / Math.PI;
  if (Math.abs(angle) < 35) return 'Continue straight';
  if (Math.abs(angle) > 145) return 'Turn around';
  return angle > 0 ? 'Turn right' : 'Turn left';
}

export function buildInstructions(data, route) {
  if (!route || !['ok', 'same'].includes(route.status) || !route.nodeIds.length) return [];
  const nodes = new Map(data.nodes.map(node => [node.id, node]));
  const placesByNode = new Map(data.places.map(place => [place.nodeId, place]));
  const start = data.places.find(place => place.id === route.startPlaceId) ?? placesByNode.get(route.nodeIds[0]);
  const destination = data.places.find(place => place.id === route.endPlaceId) ?? placesByNode.get(route.nodeIds.at(-1));
  const steps = [];
  const push = (type, text, floorId, nodeIds, extras = {}) => {
    steps.push({ id: `step-${steps.length + 1}`, type, text, floorId, nodeIds, ...extras });
  };
  if (route.status === 'same') {
    push('arrive', `You are already at ${destination.name}.`, destination.floorId, [destination.nodeId], { placeId: destination.id });
    return steps;
  }
  push('start', `Start at ${start.name} on Floor ${start.floorId}.`, start.floorId, [start.nodeId], { placeId: start.id });
  let previousDirection = null;
  let index = 0;
  while (index < route.edges.length) {
    const edge = route.edges[index];
    const a = nodes.get(edge.from); const b = nodes.get(edge.to);
    if (a.floorId !== b.floorId) {
      const direction = edge.direction ?? (Number(b.floorId) > Number(a.floorId) ? 'up' : 'down');
      push('floor-change', `Take the ${direction} escalator to Floor ${b.floorId}.`, a.floorId,
        [a.id, b.id], { nextFloorId: b.floorId, direction, connectorType: edge.type });
      previousDirection = null; index++; continue;
    }
    const direction = [b.x - a.x, b.y - a.y];
    const groupedNodes = [a.id, b.id];
    let finish = b;
    let nextIndex = index + 1;
    while (nextIndex < route.edges.length) {
      const next = route.edges[nextIndex];
      const c = nodes.get(next.to);
      if (c.floorId !== a.floorId) break;
      const nextDirection = [c.x - finish.x, c.y - finish.y];
      const cross = direction[0] * nextDirection[1] - direction[1] * nextDirection[0];
      const dot = direction[0] * nextDirection[0] + direction[1] * nextDirection[1];
      if (Math.abs(cross) > 0.001 || dot <= 0) break;
      groupedNodes.push(c.id); finish = c; nextIndex++;
    }
    const place = placesByNode.get(finish.id);
    const action = routeTurnText(previousDirection, direction);
    const context = place ? ` towards ${place.name}` : ' along the corridor';
    push('walk', `${action}${action === 'Follow the corridor' && !place ? '' : context}.`, a.floorId, groupedNodes,
      place ? { placeId: place.id } : {});
    previousDirection = direction;
    index = nextIndex;
  }
  push('arrive', `Arrive at ${destination.name} on Floor ${destination.floorId}.`, destination.floorId,
    [destination.nodeId], { placeId: destination.id });
  return steps;
}
