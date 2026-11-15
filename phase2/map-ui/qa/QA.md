# Wayfind verification notes

This report distinguishes checks of the actual source/DOM from rendered browser testing. The map is illustrative, with no verified campus geometry or connected indoor-location model.

## Included-image inspection

Four JPEGs from the 14 November WhatsApp export were extracted into `/tmp/ge2340_map_assets` for inspection only:

- `IMG-20261114-WA0038.jpg`: blurred interior photo dominated by a person; no reliable landmark identity.
- `IMG-20261114-WA0039.jpg`, `0040.jpg`, `0041.jpg`: phyphox pressure screenshots.

None is a floor plan or a confirmed landmark photo. They were not copied into the app. Actual landmark photos remain a future user-provided input.

## Browser availability

Existing Playwright packages and cached Chromium/WebKit installations were found. No package or browser was installed or downloaded.

- Chromium headless shell exited before opening a page: `sandbox_host_linux.cc` reported `shutdown: Operation not permitted`.
- Installed full Chromium also exited before opening a page, reporting `setsockopt: Operation not permitted`.
- Installed WebKit 2336 exited while adopting its IPC socket: `Operation not permitted`.

These host restrictions prevent a rendered browser session here. No desktop/mobile screenshot, layout, actual image-decoding or physical touch test is claimed. No approval escalation was attempted.

The parent agent also reported `EPERM` while attempting the optional local HTTP preview. The standalone HTML is the handoff path and does not require a server. This QA worker did not start a server.

## DOM and source checks

**108 DOM behavior checks passed** using the existing jsdom installation at `personal/portfolio/piohub/frontend/node_modules/jsdom`. The test executes the actual application ES modules using Node's VM module loader; it does not reimplement route or UI logic. It also executes the actual inline module in `dist/Wayfind.html`.

Both source-module and standalone-bundle forms were checked with 1440px and 390px width configurations. The only explicit browser-API shim is `matchMedia` for the app's mobile width branch. jsdom does not render CSS; these width configurations verify responsive code paths, **not** viewport layout or visual appearance.

Checked behavior:

- Bootstrap, all 24 destination options, demo-layout disclosure and absent-IndexedDB fallback text.
- Cross-floor search, normalized `Y5302` search for `Y5 302`, result selection, selected-place card and Directions action.
- Typed origins/destinations, 5F → 4F down-escalator route and reverse up-escalator route.
- Floor overlays, endpoint swap, step preview, route clearing, same-place arrival and clearing the same-place result.
- Switching floors hides a selected-place card from the previous floor.
- Ambiguous and invalid room names produce user-facing errors.
- Current-location dialog discloses that physical detection is unconnected; only its explicit demo action sets a demo position.
- Adapter rejects unknown place IDs and omits confidence for demo positions.
- Zoom/fit update the SVG viewBox; keyboard room selection works.
- Map setup explains background-only replacement and pending calibration.
- Photo picker is reachable on both width configurations; unsupported file types produce an error.
- No uncaught jsdom errors during these flows.

Reproduce from `map-ui/`:

```bash
node --experimental-vm-modules tests/dom-qa.mjs
```

On another machine, set `JSDOM_MODULE` to an existing jsdom entry-point path. This is an optional developer test dependency; the standalone user app requires no dependencies. The test script never installs packages. Results are saved in `qa/dom-report.json` with verification limits, SHA-256 hashes of the checked source and bundle, and confirmation that those files stayed unchanged during the checks.

An independent `node --test tests/routing.test.mjs` run also passed. No source fixes were needed for the tested interactions.

The following remain unverified here: rendered desktop/mobile layout, label legibility, physical touch/pan geometry, valid image decoding/canvas conversion, actual IndexedDB persistence and browser-specific `file://` behavior. The source and bundle both pass the DOM flows above, but that is not a replacement for those browser checks.

## Remaining manual browser checks

Open the standalone `dist/Wayfind.html` in a normal browser and check desktop and phone widths:

1. Search/select a room, then open Directions.
2. Enter start/destination; verify drawn route and floor-change instructions in both directions.
3. Swap endpoints, choose the same place twice, and clear the route.
4. Switch floors, zoom/pan/fit the map, and use keyboard focus controls.
5. Open the location dialog; confirm physical location is never claimed and the demo action is explicit.
6. Add/remove a landmark photo and floor-background image, reload, and check persistence/fallback notices.
7. Check mobile selected-place cards, route controls, map labels, dialogs and scrolling for overlap.

The local-only app has not been published. No owned preview server was started or remains running.
