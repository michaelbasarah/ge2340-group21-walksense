# Map data and routing layer

This local prototype uses a deliberately illustrative two-floor schematic. It is not a verified campus floor plan. All 24 physical place nodes, room positions, corridor geometry and layout-unit route costs are examples awaiting the user's confirmed labels, floor plans and distances. Repeated measurements of Y5 302 do not create extra physical rooms. The sensor acquisition tables are not imported or modified.

`dist/map-data.mjs` exports `MAP_DATA`. It holds floors `5` and `4`, room polygons, corridor polygons, places, graph nodes and edges in a `1000 × 700` view box. Room polygons have `placeId`, `polygon`, `labelX`, `labelY`, `category` and `color`. Floor corridor entries are arrays of `[x,y]` polygon points. Place IDs begin `f5-`/`f4-` and retain independent names rather than raw sensor recording IDs.

`dist/route-engine.mjs` exports:

- `validateMapData(data)`: validates node/POI references, unique IDs, floor association, finite coordinates and nonnegative costs/distances.
- `findRoute(data, startPlaceId, endPlaceId)`: runs Dijkstra on directed edges and returns `ok`, `same`, `unreachable` or `invalid`, plus ordered node IDs, oriented edges, total layout cost, nullable metric distance, floor segments and instructions.
- `buildInstructions(data, route)`: groups straight corridor segments, identifies geometric turns, adds floor changes and arrival. Directions follow the illustrative drawing; they are not a phone compass bearing.

Cross-floor edges are directional: **5F down landing → 4F down landing** and **4F up landing → 5F up landing**. Both landings have same-floor corridor connections. A route never reverses an escalator's direction. Cross-floor nodes split route polylines into separate floor segments instead of drawing an impossible line between floors.

`totalCost` uses layout units for graph search. `distanceMeters` remains `null` until every selected edge has a finite, actual metric distance; no time estimate is synthesized. A same-place route has known zero distance. After calibration, the caller should also update edge costs to actual distance or another declared preference rather than confusing map pixels with metres.

Useful example IDs:

```js
findRoute(MAP_DATA, 'f5-exit-5', 'f4-y4052');
findRoute(MAP_DATA, 'f4-main-entrance', 'f5-y5302');
```

Run checks with `node tests/routing.test.mjs`: **11 tests pass**, including all 576 ordered place pairs, both escalator directions, same-floor paths, same-place arrival, malformed/unknown data, unreachable paths, shortest-cost selection, metric-distance provenance and route/instruction geometry. `node --test tests/routing.test.mjs` also succeeds; this host's outer harness reports the file as one test, while the direct command prints the 11 individual checks. No dependencies or network access are required. Browser interaction/layout checks belong to the interface integration.

Completed routing work: created the example floor/graph data, pure route calculation and directions, and meaningful routing checks. No model is connected, no raw data was relabeled, and nothing was committed, uploaded or published.
