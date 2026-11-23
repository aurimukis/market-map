const { squarify } = require("../site/layout.js");
const sizes = [50, 30, 20, 10, 5, 5, 2, 1];
const r = squarify(sizes, 0, 0, 16, 8);
const area = r.reduce((a, [, , w, h]) => a + w * h, 0);
if (r.length !== sizes.length || Math.abs(area - 128) > 1e-6) { console.error("layout area wrong", area); process.exit(1); }
for (const [x, y, w, h] of r) if (x < -1e-9 || y < -1e-9 || x + w > 16 + 1e-9 || y + h > 8 + 1e-9 || w <= 0 || h <= 0) { console.error("out of bounds"); process.exit(1); }
console.log("layout ok");
