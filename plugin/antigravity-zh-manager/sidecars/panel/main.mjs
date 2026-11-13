// 汉化管理 sidecar：检测汉化状态（asar 里的引擎标记）、一键重新汉化/恢复英文。
//
// 状态检测是无状态的：上游汉化工具注入的引擎带有独特标记字符串
// __AGY_ZH_ACTIVE__（官方原版没有）→ asar 里扫到它 = 已汉化。
// 不需要记录哈希，跨版本/跨更新都不会失灵。
//
// 一键汉化 = 通过 explorer.exe 派发一个 .vbs（脱离 IDE 的 Job Object，
// IDE 被杀时脚本存活）：关 IDE → localize.py apply --yes → 重启 IDE。
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync, spawn } from 'node:child_process';
import { createServer } from 'node:http';

const HERE = dirname(fileURLToPath(import.meta.url));
const SETTINGS = join(HERE, 'settings.json');
const HOME = process.env.USERPROFILE || process.env.HOME || '';
// sidecar 环境里 LOCALAPPDATA 偶尔不可用 → 双兜底（HOME 拼装优先探测）
function resolveLocal() {
  const c1 = process.env.LOCALAPPDATA || '';
  if (c1 && existsSync(join(c1, 'Programs', 'antigravity'))) return c1;
  return join(HOME, 'AppData', 'Local');
}
const LOCAL_DIR = resolveLocal();
const ASAR = join(LOCAL_DIR, 'Programs', 'antigravity', 'resources', 'app.asar');
const IDE_EXE = join(LOCAL_DIR, 'Programs', 'antigravity', 'Antigravity.exe');
const MARKER = '__AGY_ZH_ACTIVE__';
const APPLY_LOCK_MS = 90000;

function readSettings() { try { return JSON.parse(readFileSync(SETTINGS, 'utf8')); } catch { return {}; } }
function writeSettings(s) { writeFileSync(SETTINGS, JSON.stringify(s, null, 2)); }

// ---------- 工具目录（localize.py）定位 ----------
function looksLikeToolDir(dir) { return existsSync(join(dir, 'localize.py')); }
function* walkDirs(root, depth) {
  if (depth < 0) return;
  let es = []; try { es = readdirSync(root, { withFileTypes: true }); } catch { return; }
  for (const e of es) {
    if (!e.isDirectory()) continue;
    if (/^(node_modules|\$RECYCLE\.BIN|System Volume Information|AppData|Windows)$/i.test(e.name)) continue;
    yield join(root, e.name);
    yield* walkDirs(join(root, e.name), depth - 1);
  }
}
function detectToolDir() {
  const roots = [['C:\\agh', 4], [join(HOME, 'Desktop'), 2], [join(HOME, 'Downloads'), 2], [join(HOME, 'Documents'), 2], [HOME, 2]];
  for (const [root, maxDepth] of roots) {
    if (!existsSync(root)) continue;
    if (looksLikeToolDir(root)) return root;
    for (const d of walkDirs(root, maxDepth)) if (looksLikeToolDir(d)) return d;
  }
  return null;
}
// 找到可用的 python。
//
// 注意：`where` 输出走**控制台代码页**（zh-CN 上是 GBK/936），按 UTF-8 解码会把
// 中文用户名打成乱码（实测 "C:\Users\胡天泽\..." → "C:\Users\������\..."），
// 写进 apply.vbs 后路径直接失效 → 一键汉化按钮无反应。
// 优先用文件系统探测（Node 直接给 Unicode 路径，不经过文本解码）；
// 实在要读 `where` 的输出时按 GBK 解码（ASCII 路径在 GBK/UTF-8 下等价，安全）。
function decodeConsole(buf) {
  try { return new TextDecoder('gbk').decode(buf); }
  catch { return buf.toString('utf8'); }
}
function findPython() {
  // 1) pyenv 装在用户目录下的版本（最常见的本机布局）
  try {
    const base = join(HOME, '.pyenv', 'pyenv-win', 'versions');
    for (const v of readdirSync(base)) {
      const p = join(base, v, 'python.exe');
      if (existsSync(p)) return p;
    }
  } catch { }
  // 2) 官方安装版（%LOCALAPPDATA%\Programs\Python\Python*\python.exe）
  try {
    const base = join(LOCAL_DIR, 'Programs', 'Python');
    for (const v of readdirSync(base)) {
      const p = join(base, v, 'python.exe');
      if (existsSync(p)) return p;
    }
  } catch { }
  // 3) PATH 上的 python（输出按控制台代码页解码）
  try {
    const raw = execFileSync('where', ['python'], { encoding: 'buffer', timeout: 15000 });
    const s = decodeConsole(raw).split(/\r?\n/)[0].trim();
    if (s) return s;
  } catch { }
  return null;
}

// ---------- 上游工具 / 词典信息 ----------
// 面板要回答两个问题：① 用的哪个版本的汉化工具、② 词典里有多少条 ——
// 官方更新后词典落后是"界面又冒出英文"的头号原因。
let toolInfoCache = { at: 0, v: null };
function toolInfo() {
  const now = Date.now();
  if (now - toolInfoCache.at < 30000 && toolInfoCache.v) return toolInfoCache.v;
  const settings = readSettings();
  const toolDir = settings.toolDir || detectToolDir();
  const out = { dir: toolDir || '', version: null, dictVersion: null, entries: 0 };
  if (toolDir) {
    try {
      const py = readFileSync(join(toolDir, 'localize.py'), 'utf8');
      const m = py.match(/^TOOL_VERSION\s*=\s*["']([^"']+)["']/m);
      if (m) out.version = m[1];
    } catch { }
    try {
      const d = JSON.parse(readFileSync(join(toolDir, 'zh_data.json'), 'utf8'));
      out.dictVersion = d.version || null;
      out.entries = Object.keys(d.exact || {}).length;
    } catch { }
  }
  toolInfoCache = { at: now, v: out };
  return out;
}

// ---------- 状态检测 ----------
// asar 的读取必须走 PowerShell 子进程：sidecar 的 fs 被宿主 loader 钩成
// 虚拟 asar 文件系统 —— statSync(app.asar) 返回 size 0、readFileSync 报
// "ENOENT, not found in ..."。PowerShell 子进程看到的是真实文件。
let psCache = { at: 0, v: null };
function asarStatus() {
  const now = Date.now();
  if (now - psCache.at < 20000 && psCache.v) return psCache.v;
  const cmd =
    '$p = ' + JSON.stringify(ASAR) + ';' +
    '$f = Get-Item -LiteralPath $p -ErrorAction SilentlyContinue;' +
    'if (-not $f) { "0|0|False"; exit };' +
    '$b = [IO.File]::ReadAllBytes($p);' +
    '$s = [Text.Encoding]::ASCII.GetString($b);' +
    '"{0}|{1}|{2}" -f $f.Length, $f.LastWriteTime.ToFileTime(), $s.Contains("' + MARKER + '")';
  try {
    const out = execFileSync('powershell', ['-NoProfile', '-Command', cmd], { encoding: 'utf8', timeout: 60000 }).trim();
    const [size, ft, loc] = out.split('|');
    psCache = { at: now, v: { size: Number(size) || 0, mtimeMs: Number(ft) / 10000 - 11644473600000, localized: loc === 'True' } };
  } catch (e) { /* 保持上一次结果 */ }
  return psCache.v;
}
function isLocalized() { const v = asarStatus(); return v ? v.localized : null; }
let verCache = { at: 0, v: null };
function ideVersion() {
  if (!existsSync(IDE_EXE)) return null;
  const now = Date.now();
  if (now - verCache.at < 300000) return verCache.v;
  try {
    verCache.v = execFileSync('powershell', ['-NoProfile', '-Command',
      '(Get-Item -LiteralPath ' + JSON.stringify(IDE_EXE) + ').VersionInfo.ProductVersion'],
      { encoding: 'utf8', timeout: 30000 }).trim() || null;
    verCache.at = now;
  } catch { }
  return verCache.v;
}
function ideRunning() {
  try {
    return /Antigravity\.exe/i.test(execFileSync('tasklist', ['/FI', 'IMAGENAME eq Antigravity.exe', '/NH'],
      { encoding: 'utf8', timeout: 15000 }));
  } catch { return false; }
}
let runCache = { at: 0, v: null };
function ideRunningCached() {
  const now = Date.now();
  if (now - runCache.at < 4000) return runCache.v;
  runCache = { at: now, v: ideRunning() };
  return runCache.v;
}
function asarInfo() { const v = asarStatus(); return { size: v.size, mtimeMs: v.mtimeMs }; }

// ---------- 一键执行 ----------
function writeApplyVbs(settings, mode) {
  const python = settings.python || findPython();
  const tool = settings.toolDir;
  const launch = settings.launchCmd || (existsSync('C:\\ABP\\launch.cmd') ? 'C:\\ABP\\launch.cmd' : '');
  const verb = mode === 'restore' ? 'restore' : 'apply';
  const pyLine = `sh.Run """${python}"" ""${tool}\\localize.py"" ${verb} --yes", 0, True`;
  const launchLine = launch
    ? `sh.Run """${launch}""", 0, False`
    : `sh.Run """${IDE_EXE}""", 0, False`;
  // 以 UTF-16 LE + BOM 保存（路径含中文），WScript 支持
  const vbs = [
    'Set sh = CreateObject("WScript.Shell")',
    'WScript.Sleep 2000',
    'sh.Run "taskkill /F /IM Antigravity.exe", 0, True',
    'WScript.Sleep 3000',
    pyLine,
    'WScript.Sleep 2000',
    launchLine,
  ].join('\r\n');
  const vbsPath = join(HERE, 'apply.vbs');
  writeFileSync(vbsPath, '\uFEFF' + vbs, 'utf16le');
  return { vbsPath, launch };
}

let lastApply = 0;
function doApply(mode) {
  const now = Date.now();
  if (now - lastApply < APPLY_LOCK_MS) return { ok: false, error: '已有一次汉化正在执行，请稍候' };
  const settings = readSettings();
  const toolDir = settings.toolDir || detectToolDir();
  if (!toolDir) return { ok: false, error: '未找到汉化工具（localize.py），请在下方填写工具目录' };
  const python = settings.python || findPython();
  if (!python) return { ok: false, error: '未找到 python' };
  if (!existsSync(ASAR)) return { ok: false, error: '未找到 app.asar' };

  settings.toolDir = toolDir;
  settings.python = python;
  if (!settings.launchCmd) settings.launchCmd = existsSync('C:\\ABP\\launch.cmd') ? 'C:\\ABP\\launch.cmd' : '';
  settings.lastApply = { mode, at: now };
  writeSettings(settings);
  lastApply = now;

  const { vbsPath } = writeApplyVbs(settings, mode);
  // explorer 派发：脱离 IDE 的 Job Object，IDE 被杀时脚本继续跑完
  spawn('explorer.exe', [vbsPath], { detached: true, stdio: 'ignore' }).unref();
  return {
    ok: true,
    note: mode === 'restore'
      ? '正在恢复英文原版：Antigravity 将关闭，约 40 秒后自动重启。'
      : '正在重新汉化：Antigravity 将关闭，约 40 秒后自动重启（带代理）。',
  };
}

// ---------- HTTP ----------
function json(res, code, obj) { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(obj)); }

const server = createServer(async (req, res) => {
  const u = new URL(req.url, 'http://127.0.0.1');
  try {
    if (u.pathname === '/api/status') {
      const settings = readSettings();
      return json(res, 200, {
        localized: isLocalized(),
        asarPath: ASAR,
        ideVersion: ideVersion(),
        ideRunning: ideRunningCached(),
        asar: asarInfo(),
        toolDir: settings.toolDir || detectToolDir() || '',
        python: settings.python || findPython() || '',
        launchCmd: settings.launchCmd || (existsSync('C:\\ABP\\launch.cmd') ? 'C:\\ABP\\launch.cmd' : ''),
        lastApply: settings.lastApply || null,
        tool: toolInfo(),
      });
    }
    if (u.pathname === '/api/debug') {
      const out = { asarPath: ASAR, envLocal: process.env.LOCALAPPDATA || null, envHome: process.env.USERPROFILE || process.env.HOME || null, cwd: process.cwd() };
      try { const st = statSync(ASAR); out.stat = { size: st.size, mtime: st.mtimeMs }; }
      catch (e) { out.statError = String(e.message || e); out.statCode = e.code || null; }
      try { out.exists = existsSync(ASAR); } catch (e) { out.existsErr = String(e.message || e); }
      try { out.marker = readFileSync(ASAR).toString('latin1').includes(MARKER); } catch (e) { out.readErr = String(e.message || e).slice(0, 120); }
      try { out.dirList = readdirSync(join(ASAR, '..')).slice(0, 10); } catch (e) { out.dirErr = String(e.message || e).slice(0, 120); }
      return json(res, 200, out);
    }
    if (u.pathname === '/api/apply' && req.method === 'POST') {
      let body = ''; for await (const c of req) body += c;
      let mode = 'apply';
      try { mode = JSON.parse(body || '{}').mode || 'apply'; } catch { }
      return json(res, 200, doApply(mode === 'restore' ? 'restore' : 'apply'));
    }
    if (u.pathname === '/api/settings' && req.method === 'POST') {
      let body = ''; for await (const c of req) body += c;
      const b = JSON.parse(body || '{}');
      const s = readSettings();
      if (typeof b.toolDir === 'string') s.toolDir = b.toolDir.trim();
      if (typeof b.launchCmd === 'string') s.launchCmd = b.launchCmd.trim();
      writeSettings(s);
      return json(res, 200, { ok: true, settings: s });
    }
    if (u.pathname === '/' || u.pathname === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      return res.end(readFileSync(join(HERE, 'index.html'), 'utf8'));
    }
    res.writeHead(404); res.end();
  } catch (e) {
    json(res, 500, { error: String(e.message || e) });
  }
});

const port = Number(process.env.ANTIGRAVITY_SIDECAR_WEB_PORT) || 0;
server.listen(port, '127.0.0.1', () => console.log(`[zh-manager] http://127.0.0.1:${server.address().port}`));
