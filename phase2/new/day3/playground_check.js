// Evaluates the CORE block of knn_playground.html in Node for the cases in argv[3] (JSON), writes results to argv[4].
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const P = JSON.parse(html.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/)[1]);
const core = html.match(/\/\/ CORE-START[^\n]*\n([\s\S]*?)\/\/ CORE-END/)[1];
const lib = new Function(core + '\nreturn {buildBank, distances, knn, projectPCA, buildMask, phoneSessionMatrix, varianceFeature, placeCells, comparePhones};')();
const bank = lib.buildBank(P);
const mxArg = process.argv[5];                 // optional: 'matrix' -> write the live panel's matrix at the default weights/k
if (mxArg === 'matrix') {
  const m = lib.phoneSessionMatrix(bank, P, P.model.weights, P.model.k);
  fs.writeFileSync(process.argv[4], JSON.stringify(m.cells.map(c => ({mode: c.mode, phone: P.phones[c.phone], col: c.col, cell: c.cell && {
    win: c.cell.win, rec: c.cell.rec, chance: c.cell.chance, ntr: c.cell.ntr, nte: c.cell.nte, cross: c.cell.cross,
    trainPhones: c.cell.trainPhones.map(i => P.phones[i]), per: Object.fromEntries(Object.entries(c.cell.per).map(([t, v]) => [P.places[t], v]))}}))));
  process.exit(0);
}
if (mxArg === 'variance') {            // nested variance decomposition + per-place cell table for the page's own filter logic
  const vc = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  const dims = {nS: P.sessions.length, nPh: P.phones.length};
  fs.writeFileSync(process.argv[4], JSON.stringify(vc.map(c => {
    const use = lib.buildMask(bank, c.filter, true), r = {};
    for (const order of ['session_first', 'phone_first']) {
      r[order] = {};
      for (const [f] of P.vfeats) r[order][f] = lib.varianceFeature(bank, f, use, order, dims);
    }
    return {n: use.reduce((a, b) => a + b, 0), var: r, cells: lib.placeCells(bank, use)};
  })));
  process.exit(0);
}
if (mxArg === 'compare') {             // compare-phones panel: argv[3] = cases [{w, k, o}] (o = the panel's options), result = comparePhones() per case
  const cc = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  fs.writeFileSync(process.argv[4], JSON.stringify(cc.map(c => lib.comparePhones(bank, P, c.w, c.k, c.o))));
  process.exit(0);
}
if (mxArg === 'masks') {               // training mask vs drawn mask for place filters
  const mc = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  fs.writeFileSync(process.argv[4], JSON.stringify(mc.map(f => ({train: Array.from(lib.buildMask(bank, f, false)), draw: Array.from(lib.buildMask(bank, f, true))}))));
  process.exit(0);
}
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = cases.map(c => {
  const use = c.filter ? lib.buildMask(bank, c.filter) : Uint8Array.from(c.use);   // c.filter: the page's own mask logic
  const q = {B: bank.B[c.i], x: bank.x[c.i], y: bank.y[c.i], z: bank.z[c.i],
             Bv: c.tilt ? bank.Bv[c.i] : NaN, Bh: c.tilt ? bank.Bh[c.i] : NaN, floor: bank.floor[c.i]};
  const D = lib.distances(bank, q, c.w, use);
  const r = lib.knn(bank, D, c.k, P.places.length);
  return {use: Array.from(use), pred: r.pred, shares: Array.from(r.shares), order: r.order, pc: lib.projectPCA(P, q)};
});
fs.writeFileSync(process.argv[4], JSON.stringify(out));
