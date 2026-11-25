const chunks = (t = "") =>
  String(t).split(/\n+|(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);

/** Sentence-level diff between two texts: [{type:"same"|"add"|"del", text}] */
export function diffText(a, b) {
  const x = chunks(a), y = chunks(b);
  const dp = Array.from({ length: x.length + 1 }, () => new Array(y.length + 1).fill(0));
  for (let i = x.length - 1; i >= 0; i--)
    for (let j = y.length - 1; j >= 0; j--)
      dp[i][j] = x[i] === y[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out = [];
  let i = 0, j = 0;
  while (i < x.length && j < y.length) {
    if (x[i] === y[j]) { out.push({ type: "same", text: x[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push({ type: "del", text: x[i++] });
    else out.push({ type: "add", text: y[j++] });
  }
  while (i < x.length) out.push({ type: "del", text: x[i++] });
  while (j < y.length) out.push({ type: "add", text: y[j++] });
  return out;
}
