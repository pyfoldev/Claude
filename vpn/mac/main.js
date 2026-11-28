const { app, BrowserWindow, ipcMain } = require('electron');
const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');

const CONF = () => path.join(app.getPath('userData'), 'veil.conf');
const PATHS = ['/opt/homebrew/bin', '/usr/local/bin'];
const wgQuick = () => PATHS.map(p => path.join(p, 'wg-quick')).find(p => fs.existsSync(p));

function parseInput(text) {
  let t = (text || '').trim();
  if (t.startsWith('vpn://')) {
    t = Buffer.from(t.slice(6).replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
  }
  if (!/\[Interface\]/i.test(t) || !/\[Peer\]/i.test(t) || !/PrivateKey/i.test(t)) throw new Error('Неверная конфигурация');
  return t.replace(/\r/g, '').trim() + '\n';
}
function endpoint() {
  try {
    const m = fs.readFileSync(CONF(), 'utf8').match(/^\s*Endpoint\s*=\s*(\S+)/mi);
    return m ? m[1].replace(/:\d+$/, '') : null;
  } catch { return null; }
}
const isUp = () => fs.existsSync('/var/run/wireguard/veil.name');

function admin(cmd) {
  return new Promise((resolve, reject) => {
    const script = `do shell script ${JSON.stringify(cmd)} with administrator privileges`;
    execFile('/usr/bin/osascript', ['-e', script], (err, out, stderr) => {
      if (err) reject(new Error((stderr || err.message).replace(/^.*execution error: /, '').trim())); else resolve(out);
    });
  });
}

ipcMain.handle('state', () => ({ endpoint: endpoint(), up: isUp() }));
ipcMain.handle('save', (_e, text) => {
  fs.mkdirSync(app.getPath('userData'), { recursive: true });
  fs.writeFileSync(CONF(), parseInput(text), { mode: 0o600 });
  return endpoint();
});
ipcMain.handle('toggle', async () => {
  const wg = wgQuick();
  if (!wg) throw new Error('Установите WireGuard: brew install wireguard-tools');
  if (!fs.existsSync(CONF())) throw new Error('Сначала добавьте сервер');
  const env = `PATH=${PATHS.join(':')}:/usr/bin:/bin:/usr/sbin:/sbin`;
  const up = isUp();
  await admin(`${env} ${JSON.stringify(wg)} ${up ? 'down' : 'up'} ${JSON.stringify(CONF())}`);
  return isUp();
});

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 420, height: 760, resizable: false, backgroundColor: '#000000',
    titleBarStyle: 'hiddenInset', fullscreenable: false,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true }
  });
  win.loadFile('index.html');
});
app.on('window-all-closed', () => app.quit());
