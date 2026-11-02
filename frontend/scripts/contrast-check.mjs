const themes = {
  Aurora: { bg: '#0b0b1a', surface: '#14142b', border: '#626288', text: '#eef0ff', muted: '#b8bbdf', primary: '#6847e8' },
  'Meta Blue': { bg: '#0a0f1a', surface: '#111a2b', border: '#63718a', text: '#e8eefb', muted: '#b4c2d9', primary: '#0866ff' },
  Daylight: { bg: '#f7f8fc', surface: '#ffffff', border: '#878ca5', text: '#12142b', muted: '#454b68', primary: '#4f46e5' },
};
function luminance(hex) {
  const rgb = hex.slice(1).match(/../g).map((v) => parseInt(v, 16) / 255).map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2];
}
function ratio(a, b) { const values = [luminance(a), luminance(b)].sort((x, y) => y - x); return (values[0] + .05) / (values[1] + .05); }
let failed = false;
console.log('WCAG AA contrast check (text >= 4.5:1; controls/borders >= 3:1)');
for (const [name, t] of Object.entries(themes)) {
  const checks = [
    ['body text / bg', ratio(t.text, t.bg), 4.5],
    ['muted text / bg', ratio(t.muted, t.bg), 4.5],
    ['body text / surface', ratio(t.text, t.surface), 4.5],
    ['border / bg', ratio(t.border, t.bg), 3],
    ['border / surface', ratio(t.border, t.surface), 3],
    ['white button text / primary', ratio('#ffffff', t.primary), 4.5],
  ];
  console.log(`\n${name}`);
  for (const [label, value, threshold] of checks) {
    const ok = value >= threshold;
    failed ||= !ok;
    console.log(`  ${ok ? 'PASS' : 'FAIL'} ${label}: ${value.toFixed(2)}:1 (requires ${threshold}:1)`);
  }
}
if (failed) process.exitCode = 1;
