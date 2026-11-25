// Evaluates the CORE block of knn_playground.html in Node for the cases in argv[3] (JSON), writes results to argv[4].
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const P = JSON.parse(html.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/)[1]);
const core = html.match(/\/\/ CORE-START[^\n]*\n([\s\S]*?)\/\/ CORE-END/)[1];
const lib = new Function(core + '\nreturn {buildBank, distances, knn, projectPCA};')();
const bank = lib.buildBank(P);
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = cases.map(c => {
  const use = Uint8Array.from(c.use);
  const q = {B: bank.B[c.i], x: bank.x[c.i], y: bank.y[c.i], z: bank.z[c.i],
             Bv: c.tilt ? bank.Bv[c.i] : NaN, Bh: c.tilt ? bank.Bh[c.i] : NaN, floor: bank.floor[c.i]};
  const D = lib.distances(bank, q, c.w, use);
  const r = lib.knn(bank, D, c.k, P.places.length);
  return {pred: r.pred, shares: Array.from(r.shares), order: r.order, pc: lib.projectPCA(P, q)};
});
fs.writeFileSync(process.argv[4], JSON.stringify(out));
