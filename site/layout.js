// Squarified treemap. sizes: positive numbers, largest first. Returns [x, y, w, h] per size,
// which together exactly fill the rectangle.
function squarify(sizes, x, y, w, h) {
  const total = sizes.reduce((a, b) => a + b, 0);
  const areas = sizes.map(s => (s / total) * w * h);
  const rects = [];
  const worst = (row, side) => {
    const sum = row.reduce((a, b) => a + b, 0);
    return Math.max(...row.map(r => Math.max((side * side * r) / (sum * sum), (sum * sum) / (side * side * r))));
  };
  let i = 0;
  while (i < areas.length) {
    const side = Math.min(w, h);
    const row = [areas[i]];
    let j = i + 1;
    while (j < areas.length && worst(row.concat(areas[j]), side) <= worst(row, side)) { row.push(areas[j]); j++; }
    const sum = row.reduce((a, b) => a + b, 0);
    if (w >= h) {
      const cw = sum / h; let yy = y;
      row.forEach(a => { rects.push([x, yy, cw, a / cw]); yy += a / cw; });
      x += cw; w -= cw;
    } else {
      const rh = sum / w; let xx = x;
      row.forEach(a => { rects.push([xx, y, a / rh, rh]); xx += a / rh; });
      y += rh; h -= rh;
    }
    i = j;
  }
  return rects;
}
if (typeof module !== "undefined") module.exports = { squarify };
