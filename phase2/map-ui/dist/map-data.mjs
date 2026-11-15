// Illustrative geometry only. Replace with a calibrated floor plan and verified POIs.
export const MAP_DATA = (() => {
  const places = [];
  const nodes = [];
  const edges = [];
  const palette = {
    room: '#e5edf1', study: '#f2ebdc', restroom: '#eae5f1',
    exit: '#e1eee6', food: '#f3e3dc', vending: '#f3e8c9',
    escalator: '#e0eaf0', entrance: '#e1eee6',
  };
  const rectangle = (x1, y1, x2, y2) => [[x1, y1], [x2, y1], [x2, y2], [x1, y2]];
  const floorSpecs = [
    {
      id: '5', label: '5F', level: 5,
      rooms: [
        ['exit-5', 'Exit 5', 'exit', 130, 185, 'top', [70, 115, 190, 255]],
        ['men-toilet', "Men’s toilet", 'restroom', 260, 185, 'top', [205, 115, 315, 255]],
        ['y5302', 'Y5 302', 'room', 410, 185, 'top', [330, 115, 490, 255]],
        ['study-11', 'Study room 11', 'study', 570, 185, 'top', [505, 115, 635, 255]],
        ['study-10', 'Study room 10', 'study', 710, 185, 'top', [650, 115, 765, 255]],
        ['study-9', 'Study room 9', 'study', 850, 185, 'top', [780, 115, 930, 255]],
        ['study-8', 'Study room 8', 'study', 180, 525, 'bottom', [80, 465, 280, 600]],
        ['women-toilet', "Women’s toilet", 'restroom', 345, 525, 'bottom', [295, 465, 395, 600]],
        ['exit-10', 'Exit 10', 'exit', 470, 525, 'bottom', [410, 465, 530, 600]],
        ['canteen', 'Canteen', 'food', 650, 525, 'bottom', [545, 465, 745, 600]],
        ['vending-1', 'Vending machine 1', 'vending', 595, 360, 'top', [570, 335, 620, 385]],
        ['vending-2', 'Vending machine 2', 'vending', 670, 360, 'top', [645, 335, 695, 385]],
        ['down-escalator', 'Down escalator', 'escalator', 805, 525, 'bottom', [760, 465, 850, 600]],
        ['up-escalator', 'Up escalator', 'escalator', 900, 525, 'bottom', [865, 465, 940, 600]],
      ],
    },
    {
      id: '4', label: '4F', level: 4,
      rooms: [
        ['exit-5', 'Exit 5', 'exit', 130, 185, 'top', [70, 115, 190, 255]],
        ['lt2a', 'LT 2A', 'room', 300, 185, 'top', [205, 115, 395, 255]],
        ['lt2b', 'LT 2B', 'room', 490, 185, 'top', [410, 115, 580, 255]],
        ['lt1a', 'LT 1A', 'room', 680, 185, 'top', [595, 115, 765, 255]],
        ['lt1b', 'LT 1B', 'room', 850, 185, 'top', [780, 115, 930, 255]],
        ['main-entrance', 'Main entrance', 'entrance', 180, 525, 'bottom', [80, 465, 280, 600]],
        ['exit-10', 'Exit 10', 'exit', 380, 525, 'bottom', [295, 465, 455, 600]],
        ['y4052', 'Y4052', 'room', 630, 525, 'bottom', [470, 465, 745, 600]],
        ['down-escalator', 'Down escalator', 'escalator', 805, 525, 'bottom', [760, 465, 850, 600]],
        ['up-escalator', 'Up escalator', 'escalator', 900, 525, 'bottom', [865, 465, 940, 600]],
      ],
    },
  ];
  const addEdge = (from, to, type = 'walk', bidirectional = true, extras = {}) => {
    const a = nodes.find(node => node.id === from);
    const b = nodes.find(node => node.id === to);
    edges.push({ from, to, type, bidirectional,
      cost: Math.hypot(a.x - b.x, a.y - b.y), distanceMeters: null, ...extras });
  };
  const floors = floorSpecs.map(spec => {
    const xs = [...new Set([120, 500, 900, ...spec.rooms.map(room => room[3])])].sort((a, b) => a - b);
    for (const [side, y] of [['top', 295], ['bottom', 425]]) {
      for (const x of xs) nodes.push({ id: `${spec.id}:${side}:${x}`, floorId: spec.id, x, y, type: 'corridor' });
      for (let i = 1; i < xs.length; i++) addEdge(`${spec.id}:${side}:${xs[i - 1]}`, `${spec.id}:${side}:${xs[i]}`);
    }
    for (const x of [120, 500, 900]) addEdge(`${spec.id}:top:${x}`, `${spec.id}:bottom:${x}`);
    const rooms = spec.rooms.map(([suffix, name, category, x, y, anchor, bounds]) => {
      const id = `f${spec.id}-${suffix}`;
      const nodeId = `node:${id}`;
      const floorDescription = category === 'escalator'
        ? `${suffix.startsWith('down') ? 'Downward' : 'Upward'} escalator landing · Floor ${spec.id}`
        : `${name} · Floor ${spec.id}`;
      nodes.push({ id: nodeId, floorId: spec.id, x, y, type: 'place', placeId: id });
      places.push({ id, name, floorId: spec.id, category, x, y, nodeId,
        description: floorDescription, photo: null, layoutStatus: 'illustrative' });
      addEdge(nodeId, `${spec.id}:${anchor}:${x}`);
      return { placeId: id, polygon: rectangle(...bounds), labelX: x, labelY: y,
        category, color: palette[category] };
    });
    return { id: spec.id, label: spec.label, level: spec.level,
      name: `Floor ${spec.id}`, rooms,
      bounds: { x: 65, y: 95, width: 885, height: 520 },
      corridors: [rectangle(100, 275, 920, 315), rectangle(100, 405, 920, 445),
        rectangle(100, 275, 140, 445), rectangle(880, 275, 920, 445), rectangle(480, 275, 520, 445)],
      annotations: [{ x: 300, y: 365, text: 'ACADEMIC BUILDING' }],
    };
  });
  addEdge('node:f5-down-escalator', 'node:f4-down-escalator', 'escalator', false,
    { direction: 'down', cost: 180 });
  addEdge('node:f4-up-escalator', 'node:f5-up-escalator', 'escalator', false,
    { direction: 'up', cost: 180 });
  return {
    id: 'ge2340-illustrative-map', title: 'Campus navigator', isDemo: true,
    viewBox: [0, 0, 1000, 700], north: 0, calibrated: false,
    distanceUnit: 'layout units',
    description: 'Illustrative floor layouts. Room positions, corridor geometry and routing weights await verified plans.',
    floors, places, nodes, edges,
  };
})();
