// DOM behavior checks, not a rendered-browser/layout test.
// Uses an existing jsdom installation; no dependency or browser is downloaded.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const jsdomPath = process.env.JSDOM_MODULE || '/home/basarah/personal/portfolio/piohub/frontend/node_modules/jsdom/lib/api.js';
const { JSDOM, VirtualConsole } = await import(pathToFileURL(jsdomPath).href);
if (!vm.SourceTextModule) throw new Error('Run with node --experimental-vm-modules tests/dom-qa.mjs');
const results = [];
const tick = () => new Promise(resolve => setTimeout(resolve, 15));
async function sourceHashes() {
  const result = {};
  for (const name of ['index.html', 'styles.css', 'app.mjs', 'map-data.mjs', 'route-engine.mjs', 'Wayfind.html']) {
    result[name] = createHash('sha256').update(await fs.readFile(path.join(root, 'dist', name))).digest('hex');
  }
  return result;
}

async function runScenario(mode, width) {
  const scenario = `${mode}-${width}`;
  const htmlFile = path.join(root, 'dist', mode === 'standalone' ? 'Wayfind.html' : 'index.html');
  const html = await fs.readFile(htmlFile, 'utf8');
  const errors = [];
  const console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(html, { url: 'http://wayfind.test/', runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole: console });
  const window = dom.window;
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
  // jsdom does not implement matchMedia; only the app's explicit width branch is emulated.
  window.matchMedia = query => ({ matches: /max-width\s*:\s*700px/.test(query) && width <= 700,
    media: query, onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true; } });
  const context = dom.getInternalVMContext();
  const cache = new Map();
  async function loadModule(filename) {
    filename = path.resolve(filename);
    if (!filename.startsWith(path.join(root, 'dist') + path.sep)) throw new Error('Unexpected nonlocal module: ' + filename);
    if (!cache.has(filename)) {
      const source = await fs.readFile(filename, 'utf8');
      cache.set(filename, new vm.SourceTextModule(source, { context, identifier: filename,
        initializeImportMeta(meta) { meta.url = pathToFileURL(filename).href; } }));
    }
    return cache.get(filename);
  }
  const entry = mode === 'standalone'
    ? new vm.SourceTextModule(window.document.querySelector('script[type="module"]').textContent, { context, identifier: htmlFile })
    : await loadModule(path.join(root, 'dist', 'app.mjs'));
  await entry.link((specifier, referencing) => loadModule(path.resolve(path.dirname(referencing.identifier), specifier)));
  await entry.evaluate();
  await tick();
  const $ = selector => window.document.querySelector(selector);
  const click = selector => { const element = $(selector); assert.ok(element, selector + ' exists'); element.dispatchEvent(new window.MouseEvent('click', { bubbles: true })); };
  const type = (selector, value) => { $(selector).value = value; $(selector).dispatchEvent(new window.Event('input', { bubbles: true })); };
  const submit = () => $('#route-form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  const check = (name, fn) => { fn(); results.push({ scenario, check: name, passed: true }); };
  try {
    check('app_bootstraps_actual_modules_and_24_destination_options', () => {
      assert.ok(window.Wayfind);
      assert.equal(window.document.querySelectorAll('#place-options option').length, 24);
      assert.ok(window.document.querySelectorAll('#map-svg [data-place]').length > 0);
      assert.equal($('#map-floor-title').textContent, 'Floor 5');
    });
    check('demo_disclosure_and_storage_fallback_visible', () => {
      assert.match($('.demo-badge').textContent, /Demo layout/);
      assert.match($('#storage-note').textContent, /session only/);
      assert.equal(window.Wayfind.getState().position, null);
    });
    type('#explore-search', 'Y4052');
    check('cross_floor_search_returns_matching_place', () => {
      assert.equal(window.document.querySelectorAll('#place-list [data-select-place]').length, 1);
      assert.match($('#place-list').textContent, /Y4052/);
    });
    click('[data-select-place="f4-y4052"]');
    check('selecting_search_result_updates_floor_and_place_card', () => {
      assert.equal(window.Wayfind.getState().floor, '4');
      assert.equal($('#selected-card').hidden, false);
      assert.match($('#selected-card').textContent, /Y4052/);
      assert.ok($('#add-photo'));
    });
    click('#selected-directions');
    check('place_directions_sets_destination_and_opens_panel', () => {
      assert.equal($('#directions-panel').hidden, false);
      assert.equal($('#destination-input').value, 'Y4052 · 4F');
    });
    type('#origin-input', 'Exit 5 · 5F');
    submit();
    check('typed_start_routes_down_from_5F_to_4F', () => {
      assert.equal(window.Wayfind.getState().route.status, 'ok');
      assert.equal(window.Wayfind.getState().route.floorChanges, 1);
      assert.match($('#route-result').textContent, /down escalator to Floor 4/);
      assert.match($('#route-result').textContent, /Distance awaiting map scale/);
      assert.ok($('#map-svg .route-line'));
    });
    click('#floor-4');
    check('floor_switch_draws_destination_floor_route', () => {
      assert.equal(window.Wayfind.getState().floor, '4');
      assert.ok($('#map-svg .route-line'));
    });
    click('#swap-button');
    check('swapped_route_uses_up_escalator', () => {
      assert.equal($('#origin-input').value, 'Y4052 · 4F');
      assert.equal($('#destination-input').value, 'Exit 5 · 5F');
      assert.match($('#route-result').textContent, /up escalator to Floor 5/);
    });
    click('#preview-route');
    check('step_preview_is_explicit_and_marks_active_step', () => {
      assert.ok($('.route-step.active'));
      assert.match($('.preview-status').textContent, /not live navigation/);
    });
    click('#clear-route');
    check('clear_route_removes_overlay_and_restores_empty_state', () => {
      assert.equal(window.Wayfind.getState().route, null);
      assert.equal($('#route-empty').hidden, false);
      assert.equal($('#map-svg .route-line'), null);
    });
    type('#origin-input', 'Y4052 · 4F');
    type('#destination-input', 'Y4052 · 4F');
    submit();
    check('same_start_and_destination_has_arrival_state', () => {
      assert.equal(window.Wayfind.getState().route.status, 'same');
      assert.match($('#route-result').textContent, /already there|already at/i);
    });
    click('#clear-route');
    check('same_place_arrival_can_be_cleared', () => {
      assert.equal(window.Wayfind.getState().route, null);
      assert.equal($('#route-empty').hidden, false);
    });
    type('#origin-input', 'Exit 5');
    submit();
    check('ambiguous_bare_name_requires_floor', () => {
      assert.equal($('#route-error').hidden, false);
      assert.match($('#route-error').textContent, /floor/);
    });
    type('#origin-input', 'unknown room');
    submit();
    check('invalid_start_produces_user_facing_error', () => {
      assert.equal($('#route-error').hidden, false);
      assert.equal(window.Wayfind.getState().route, null);
    });
    click('#locate-button');
    check('location_dialog_discloses_detection_is_unconnected', () => {
      assert.equal($('#location-dialog').hasAttribute('open'), true);
      assert.match($('#location-dialog').textContent, /does not detect your physical location/);
      assert.equal(window.Wayfind.getState().position, null);
    });
    click('#try-demo-location');
    check('only_explicit_demo_action_sets_demo_position', () => {
      assert.equal(window.Wayfind.getState().position.source, 'demo');
      assert.match($('#position-note').textContent, /not your detected location/);
      assert.equal($('#location-dialog').hasAttribute('open'), false);
    });
    check('position_adapter_rejects_unknown_place_and_removes_demo_confidence', () => {
      assert.throws(() => window.Wayfind.setPosition({ placeId: 'invalid' }), /known/);
      window.Wayfind.setPosition({ placeId: 'f5-exit-5', source: 'demo', confidence: 0.99 });
      assert.equal('confidence' in window.Wayfind.getState().position, false);
    });
    const view = $('#map-svg').getAttribute('viewBox');
    click('#zoom-in');
    check('zoom_button_changes_map_view', () => assert.notEqual($('#map-svg').getAttribute('viewBox'), view));
    click('#fit-map');
    check('fit_restores_full_view', () => assert.equal($('#map-svg').getAttribute('viewBox'), '0 0 1000 700'));
    click('#setup-button');
    check('map_setup_discloses_background_only_and_calibration_pending', () => {
      assert.equal($('#setup-dialog').hasAttribute('open'), true);
      assert.match($('#setup-dialog').textContent, /background only/);
      assert.match($('#setup-dialog').textContent, /calibration/);
    });
    click('[data-close-dialog="setup-dialog"]');
    click('#explore-tab');
    type('#explore-search', 'Y5302');
    check('normalized_room_number_search_matches_spaced_name', () => {
      assert.equal(window.document.querySelectorAll('#place-list [data-select-place]').length, 1);
      assert.match($('#place-list').textContent, /Y5 302/);
    });
    type('#explore-search', 'nothing-matches-this');
    check('no_search_matches_has_clear_empty_state', () => assert.match($('#place-list').textContent, /No places found/));
    type('#explore-search', '');
    click('#floor-5');
    const room = $('#map-svg [data-place="f5-study-11"]');
    room.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    check('keyboard_room_selection_and_photo_control_available', () => {
      assert.equal(window.Wayfind.getState().selected, 'f5-study-11');
      assert.ok($('#add-photo'));
      if (width <= 700) assert.notEqual($('#close-selected').parentElement.className, 'selected-photo');
    });
    click('#floor-4');
    check('switching_floor_hides_stale_other_floor_card', () => assert.equal($('#selected-card').hidden, true));
    click('#floor-5');
    $('#map-svg [data-place="f5-study-11"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
    let filePickerRequested = false;
    $('#photo-input').addEventListener('click', () => { filePickerRequested = true; });
    click('#add-photo');
    check('add_photo_requests_picker', () => assert.equal(filePickerRequested, true));
    const file = new window.File(['invalid'], 'invalid.txt', { type: 'text/plain' });
    Object.defineProperty($('#photo-input'), 'files', { value: [file], configurable: true });
    $('#photo-input').dispatchEvent(new window.Event('change', { bubbles: true }));
    await tick();
    check('unsupported_photo_type_has_user_facing_error', () => assert.match($('#toast').textContent, /PNG, JPEG or WebP/));
    check('no_uncaught_dom_errors', () => assert.deepEqual(errors, []));
  } finally {
    window.close();
  }
}

const report = { kind: 'jsdom_behavior_not_rendered_browser', browserLayoutVerified: false,
  emulatedBrowserApi: ['matchMedia width branch; jsdom does not render CSS'],
  unverified: ['desktop/mobile rendered layout', 'touch/pan geometry', 'valid image decoding/canvas conversion', 'IndexedDB persistence', 'real browser file:// security behavior'],
  checks: results };
try {
  report.sourceSha256 = await sourceHashes();
  for (const [mode, width] of [['modules', 1440], ['modules', 390], ['standalone', 1440], ['standalone', 390]]) await runScenario(mode, width);
  assert.deepEqual(await sourceHashes(), report.sourceSha256, 'Application source changed while DOM checks were running');
  report.sourceUnchangedDuringChecks = true;
  report.passed = true;
  report.checkCount = results.length;
  console.log(`${results.length} actual-module DOM behavior checks passed; rendered browser/layout verification unavailable.`);
} catch (error) {
  report.passed = false;
  report.error = error.stack;
  process.exitCode = 1;
  console.error(error);
} finally {
  await fs.mkdir(path.join(root, 'qa'), { recursive: true });
  await fs.writeFile(path.join(root, 'qa', 'dom-report.json'), JSON.stringify(report, null, 2) + '\n');
}
