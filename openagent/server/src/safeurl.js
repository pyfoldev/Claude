// Защита от SSRF для инструментов http_request / web_fetch у НЕ-владельцев: только публичные http(s)-адреса.
import dns from 'node:dns/promises';
import net from 'node:net';

function privateIp(ip) {
  if (net.isIPv6(ip)) {
    const s = ip.toLowerCase();
    if (s.startsWith('::ffff:')) return privateIp(s.slice(7));
    return s === '::1' || s === '::' || s.startsWith('fc') || s.startsWith('fd') || s.startsWith('fe8') || s.startsWith('fe9') || s.startsWith('fea') || s.startsWith('feb');
  }
  const [a, b] = ip.split('.').map(Number);
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || a >= 224;
}

/** Бросает ошибку, если адрес не http(s) или ведёт на внутреннюю сеть/loopback/метаданные облака. */
export async function assertPublicUrl(raw) {
  let u; try { u = new URL(String(raw)); } catch { throw new Error('Некорректный URL'); }
  if (!/^https?:$/.test(u.protocol)) throw new Error('Разрешены только http(s)-адреса');
  const host = u.hostname.replace(/^\[|\]$/g, '');
  if (/^(localhost|.*\.local|.*\.internal)$/i.test(host)) throw new Error('Внутренние адреса запрещены');
  const ips = net.isIP(host) ? [host] : (await dns.lookup(host, { all: true })).map((x) => x.address);
  if (!ips.length || ips.some(privateIp)) throw new Error('Внутренние адреса запрещены');
  return u;
}

/** fetch с ручной проверкой каждого редиректа (до 4). */
export async function safeFetch(url, init = {}) {
  let cur = String(url);
  for (let i = 0; i < 5; i++) {
    await assertPublicUrl(cur);
    const r = await fetch(cur, { ...init, redirect: 'manual' });
    if (r.status >= 300 && r.status < 400 && r.headers.get('location')) { cur = new URL(r.headers.get('location'), cur).toString(); continue; }
    return r;
  }
  throw new Error('Слишком много перенаправлений');
}
