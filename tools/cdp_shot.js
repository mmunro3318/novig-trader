// Headless screenshot via Chrome DevTools Protocol (works when `chrome --screenshot` hangs on polling pages).
// usage: node --experimental-websocket tools/cdp_shot.js <url> <out.png> [width] [height] [waitMs] [mobile 0|1] [jsBeforeShot] [fullPage 0|1]
// needs: google-chrome-stable --headless=new --remote-debugging-port=9333 running
const [url, out, W = 1440, H = 1000, wait = 6000, mobile = 0, js = '', fullPage = 0] = process.argv.slice(2);
(async () => {
  const t = await (await fetch('http://localhost:9333/json/new?about:blank', {method: 'PUT'})).json();
  const ws = new WebSocket(t.webSocketDebuggerUrl); let id = 0; const pend = {}; const logs = [];
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({id: i, method, params})) });
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && pend[d.id]) { pend[d.id](d.result || d); delete pend[d.id] }
    if (d.method == 'Runtime.exceptionThrown') logs.push('EXC ' + JSON.stringify(d.params.exceptionDetails).slice(0, 400));
    if (d.method == 'Runtime.consoleAPICalled' && d.params.type == 'error') logs.push('ERR ' + JSON.stringify(d.params.args).slice(0, 300)) };
  await new Promise(r => ws.onopen = r);
  await send('Runtime.enable'); await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: +W, height: +H, deviceScaleFactor: 1, mobile: !!+mobile});
  await send('Page.navigate', {url}); await new Promise(r => setTimeout(r, +wait));
  if (js) { const r = await send('Runtime.evaluate', {expression: js, awaitPromise: true}); await new Promise(r => setTimeout(r, 2500)); }
  const full = await send('Runtime.evaluate', {expression: 'Math.max(document.documentElement.scrollHeight, innerHeight)', returnByValue: true});
  if (+fullPage) { await send('Emulation.setDeviceMetricsOverride', {width: +W, height: Math.min(6000, full.result.value), deviceScaleFactor: 1, mobile: !!+mobile}); await new Promise(r => setTimeout(r, 1200)) }
  const s = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  require('fs').writeFileSync(out, Buffer.from(s.data, 'base64'));
  console.log('wrote', out, 'pageHeight', full.result && full.result.value, logs.length ? '\n' + logs.join('\n') : '(no JS errors)');
  await fetch('http://localhost:9333/json/close/' + t.id); process.exit(0)
})().catch(e => { console.error(e); process.exit(1) });
