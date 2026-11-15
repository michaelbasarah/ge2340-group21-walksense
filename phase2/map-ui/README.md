# Wayfind — indoor navigation prototype

A local, offline-capable interface for the GE2340 project. Select a room or landmark, choose Directions, type a starting point, and preview a route across floors 4 and 5. The interface uses a deliberately illustrative floor plan while the real maps, verified locations, distances and sensor model are being prepared.

## Open it

The easiest option is **`dist/Wayfind.html`**. Open that file directly in a modern browser. It contains the HTML, styles, data and application code, and needs no installation or network connection.

For development, with Node.js installed:

```sh
npm start
```

If server binding is permitted, open the printed local address, normally `http://127.0.0.1:4173`. There are no npm dependencies to install. Optional server arguments are `node server.mjs --host 127.0.0.1 --port 4173`. Hosting is local; nothing was published. The current execution sandbox blocks listening sockets (EPERM), so HTTP readiness could not be verified here. The standalone file is the supported handoff when a server cannot start.

## Try the main flows

1. Search for `Y5302` or tap its room on the map. Choose **Directions**.
2. Type a starting point, choosing the suggestion with the correct floor. Exit 5 and escalator names exist on both floors, so a floor-qualified suggestion avoids ambiguity.
3. For a cross-floor example, open Directions and choose **Try Exit 5 → Y4052**. The route uses the down escalator. Swap the route to test the up escalator.
4. Tap direction steps or the floor buttons to see the relevant floor. **Preview steps** moves through instructions; it does not track your physical position.
5. **Use current location** explains the pending sensor connection. **Try demo location** explicitly places the preview at Exit 5 on 5F; it is not a detected location.
6. Select a landmark and use its camera button to add a recognition photo. Add a photo of the actual doorway, vending machine or escalator landing when available.
7. In **Map setup**, add a floor-plan background. This only replaces the background image: room positions, corridor connections, map scale and north orientation must still be calibrated against that plan.

The `Rooms` and `Essentials` filters narrow the place list. Search spans both floors. Drag the map to pan; use +/− to zoom, and the fit button to show the whole floor. Ctrl/Command + mouse wheel also zooms. Press `/` to focus search. Map rooms and place buttons are keyboard selectable.

## Photos and map images

PNG, JPEG and WebP files up to 25 MB are accepted. Display copies are resized to at most 1,600 pixels and stored as JPEG in this browser's IndexedDB. Files are not uploaded to a service or written into the project. If storage is unavailable or full, the image remains available in the current session and the app explains the limit. Each photo and floor image can be removed.

The standalone file and the HTTP development preview have separate browser storage origins. Images added in one do not automatically appear in the other. Browser storage may also be cleared by the browser or private browsing mode. Keep your original photos separately.

## Source structure

- `dist/index.html`, `styles.css`, `app.mjs`: interface, interaction and local media storage.
- `dist/map-data.mjs`: replaceable physical place IDs, room/corridor polygons and graph edges. This is not the sensor recording-label table.
- `dist/route-engine.mjs`: shortest-path routing, floor segments and human-readable instructions. See [ROUTING.md](ROUTING.md).
- `dist/Wayfind.html`: generated standalone file.
- `server.mjs`: dependency-free local static server.
- `build.mjs`: dependency-free standalone bundler.
- `tests/routing.test.mjs`: routing checks.
- `tests/dom-qa.mjs`, `qa/dom-report.json`: 108 DOM interaction checks using the locally available optional jsdom package. This test dependency is not needed to run the app.
- `BUILD_LOG.md`: implementation decisions, checks and remaining integration work.
- `qa/QA.md`: verification evidence and browser/native-media limitations.

The optional DOM check can be rerun here with `node --experimental-vm-modules tests/dom-qa.mjs`; it uses the existing local jsdom installation documented in that file.

Rebuild and check with:

```sh
npm test
npm run build
python3 package.py
```

The packaging command creates `../wayfind-prototype.zip`, including source and the standalone file. It does not include the private sensor/chat export or browser-local photos.

## Connect the future location model

The app exposes a small adapter:

```js
window.Wayfind.setPosition({
  placeId: 'f4-y4052',
  source: 'sensor-model',
  confidence: 0.8 // optional model output; the current UI does not invent confidence
});
```

The position must reference a known `MAP_DATA.places` ID. The adapter fills the route starting point and redraws an existing route to the destination. It is an integration boundary, not an implemented classifier. `Wayfind.clearPosition()`, `setDestination(placeId)`, `route(startPlaceId, endPlaceId)` and `getState()` support integration and local checks.

The browser's general geolocation is not presented as room-level indoor positioning. The current application does not request GPS, Wi-Fi credentials, microphone or camera access.

## What remains

- Confirm the actual room/landmark names from the relabeled recordings.
- Replace the schematic with an authorized floor-plan image or layout; align place and corridor coordinates, north, graph connections and measured distances.
- Attach the user's actual landmark photos.
- Connect and validate the indoor positioning model. Decide whether its sensor collection runs in a native companion or another supported client; the front end currently receives position estimates through the adapter.
- Test on an actual desktop and phone browser. DOM interactions were checked at desktop/mobile width configurations, but jsdom does not render layout. Native browser rendering, image decoding and persistent media storage remain unverified here because Chromium/WebKit and server sockets are restricted; see the build log.

The prototype does not claim a campus-accurate map, measured travel time/distance, live detection or accessible-route coverage. Up/down escalator direction is enforced in the illustrative routing graph. No existing sensor values or acquisition labels were modified.
