# Wayfind implementation log

This log records software implementation steps separately from sensor processing. Add later decisions and verified results here. The sensor processing log links to this file; no sensor CSV is edited by the app.

## 1. Scope and data boundary

The user requested building the software interface while teammates correct the data labels: clickable rooms, typed-origin or detected-origin directions, indoor maps to be replaced later, and photos at major spots. The prototype is built locally for review under the workspace instruction requiring the user's decision before publication.

The existing acquisition files and candidate location labels are kept separate. The application uses 24 illustrative physical POIs on floors 4 and 5, not a guessed assignment of the 26 sensor recordings.

## 2. Interface

Created a map-first responsive layout with a searchable place list, room/amenity filters, floor selector, pan/zoom, place cards and a directions panel. Used static HTML/CSS/JavaScript with inline SVG icons and no external assets, fonts or dependency installation. Map room labels and place controls work by click/tap and keyboard.

Desktop uses a persistent sidebar and large floor map. Mobile puts the map above a scrollable panel, enlarges touch controls, initially zooms the schematic, and centers a selected place. A fit control restores the full map view. The selected place's photo control remains accessible in the mobile card.

## 3. Routing integration

Integrated the routing worker's pure Dijkstra implementation and replaceable graph. Places have stable physical IDs. Manual origin/destination inputs include floor-qualified suggestions; ambiguous bare names such as Exit 5 are rejected until a floor is selected. Search normalizes case and spacing, so `Y5302` finds `Y5 302`.

Same-floor and cross-floor paths draw per-floor polylines. Up and down escalator edges are directional. Direction steps switch the visible floor. Same-place arrival and invalid input have explicit states. The route preview can step through instructions; it does not claim live navigation. Graph costs are illustrative map units, and metric distance remains unavailable until calibrated.

## 4. Detection boundary

Added the detected-origin interaction with a clear pending-model explanation and explicit demo-location action. The demo is labeled on the map and in the origin note. No browser GPS reading is substituted for indoor room recognition. Exposed `window.Wayfind` methods for a future sensor-model adapter.

## 5. Photos and floor images

Implemented local file selection, image decoding, bounded resizing and browser-local IndexedDB storage. Storage-unavailable/full cases keep session data and give a status message. Photo and floor-background removal are supported. Imported floor images are backgrounds only, with a calibration note. Existing chat photos were not used because they were not verified landmark or floor-plan images.

## 6. Standalone and local development

Created a dependency-free local static server and a build command that generates one self-contained `dist/Wayfind.html`. The standalone file opens without a server or internet. Added source/standalone ZIP packaging and README instructions. No source was committed, pushed, deployed or published.

## 7. Verification

- JavaScript syntax checks passed for the interface and server.
- Standalone build passed and removed external module/style references.
- Routing tests pass; see the routing worker's test file and report for path/direction, invalid-input and graph-cost coverage.
- Separate QA passed 108 DOM checks across actual ES modules and the standalone bundle, using 1440px and 390px width configurations. Checked typed routes in both directions, swap/clear, same-place/invalid/ambiguous input, normalized search, room keyboard selection, zoom/fit, demo location/adapter, map setup, photo picker and invalid-file rejection. jsdom does not verify rendered layout, native image decoding or real IndexedDB persistence.
- Local server binding also fails with EPERM; the CLI gives a direct-file fallback rather than an unhandled error.
- Chromium/WebKit execution is restricted by this workspace's sandbox (EPERM). No visual screenshot or actual device-layout verification is claimed. No browser installation or permission escalation was attempted.

## Remaining integration

Verified floor maps and names, metric distances, landmark photos and a validated indoor positioning model remain pending. The existing data-label reconciliation is not silently resolved by the demo UI. Actual browser and phone rendering needs user/device confirmation when browser execution is available.

## Future entries

Append subsequent verified changes and tests here.


### Final integration check

After mobile control sizing, normalized search, floor-card reset, same-place clear controls, SVG group accessibility and the standalone rebuild, the QA worker reran 108 DOM checks. All passed. The QA report records source/bundle checksums and verifies sources did not change during that run. JavaScript syntax checks and the standalone build pass; routing checks remain green. The app and source are packaged in `../wayfind-prototype.zip`. Native image decode/persistent storage, rendered screenshots and HTTP readiness still require an unrestricted browser/device environment.
