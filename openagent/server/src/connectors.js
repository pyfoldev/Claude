// Встроенные коннекторы без ключей: погода, Википедия, курсы валют и крипто, arXiv, Hacker News, геокодинг, RSS.
const UA = { 'User-Agent': 'OpenAgent/1.0 (personal assistant)' };
const get = async (url, signal, headers = {}) => {
  const r = await fetch(url, { headers: { ...UA, ...headers }, signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(12000)]) : AbortSignal.timeout(12000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r;
};
const strip = (h) => String(h || '').replace(/<!\[CDATA\[|\]\]>/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/\s+/g, ' ').trim();

const WMO = { 0: 'ясно', 1: 'преимущественно ясно', 2: 'переменная облачность', 3: 'пасмурно', 45: 'туман', 48: 'изморозь', 51: 'морось', 53: 'морось', 55: 'сильная морось', 61: 'небольшой дождь', 63: 'дождь', 65: 'сильный дождь', 66: 'ледяной дождь', 67: 'ледяной дождь', 71: 'небольшой снег', 73: 'снег', 75: 'сильный снег', 77: 'снежная крупа', 80: 'ливень', 81: 'ливень', 82: 'сильный ливень', 85: 'снегопад', 86: 'сильный снегопад', 95: 'гроза', 96: 'гроза с градом', 99: 'сильная гроза с градом' };

async function geocode(q, signal, n = 1) {
  const j = await (await get(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=${n}&language=ru`, signal)).json();
  return j.results || [];
}

async function weather(q, signal) {
  const [p] = await geocode(q, signal);
  if (!p) return `Город «${q}» не найден`;
  const j = await (await get(`https://api.open-meteo.com/v1/forecast?latitude=${p.latitude}&longitude=${p.longitude}&current=temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code,precipitation&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code&timezone=auto&forecast_days=4`, signal)).json();
  const c = j.current, d = j.daily;
  let out = `Погода: ${p.name}${p.admin1 ? ', ' + p.admin1 : ''}, ${p.country || ''}\nСейчас: ${Math.round(c.temperature_2m)}°C (ощущается ${Math.round(c.apparent_temperature)}°C), ${WMO[c.weather_code] || 'код ' + c.weather_code}, влажность ${c.relative_humidity_2m}%, ветер ${Math.round(c.wind_speed_10m)} км/ч, осадки ${c.precipitation} мм\n`;
  d.time.forEach((t, i) => { out += `${t}: ${Math.round(d.temperature_2m_min[i])}…${Math.round(d.temperature_2m_max[i])}°C, ${WMO[d.weather_code[i]] || ''}, осадки ${d.precipitation_sum[i]} мм\n`; });
  return out.trim();
}

async function wiki(q, lang, signal) {
  const l = /^[a-z]{2,3}$/.test(lang || '') ? lang : (/[а-яё]/i.test(q) ? 'ru' : 'en');
  const s = await (await get(`https://${l}.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(q)}&format=json&srlimit=3`, signal)).json();
  const hit = s.query?.search?.[0];
  if (!hit) return `В Википедии (${l}) ничего не найдено по «${q}»`;
  const j = await (await get(`https://${l}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(hit.title.replace(/ /g, '_'))}`, signal)).json();
  const others = (s.query.search || []).slice(1).map((x) => x.title).join('; ');
  return `${j.title}${j.description ? ` — ${j.description}` : ''}\n${j.extract || strip(hit.snippet)}\n${j.content_urls?.desktop?.page || ''}${others ? `\nПохожие статьи: ${others}` : ''}`;
}

const CRYPTO = { btc: 'bitcoin', bitcoin: 'bitcoin', биткоин: 'bitcoin', eth: 'ethereum', ethereum: 'ethereum', эфир: 'ethereum', ton: 'the-open-network', toncoin: 'the-open-network', sol: 'solana', solana: 'solana', xrp: 'ripple', doge: 'dogecoin', bnb: 'binancecoin', usdt: 'tether', ltc: 'litecoin' };
async function rates(q, signal) {
  const words = String(q || '').toLowerCase().split(/[\s,;/→>-]+/).filter(Boolean);
  const coins = words.filter((w) => CRYPTO[w]);
  const out = [];
  if (coins.length) {
    const ids = [...new Set(coins.map((w) => CRYPTO[w]))].join(',');
    const j = await (await get(`https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd,rub,eur&include_24hr_change=true`, signal)).json();
    for (const [id, v] of Object.entries(j)) out.push(`${id}: $${v.usd} · ${v.rub} ₽ · ${v.eur} € (за 24 ч: ${v.usd_24h_change?.toFixed(1)}%)`);
  }
  const fiat = words.filter((w) => /^[a-z]{3}$/.test(w) && !CRYPTO[w]).map((w) => w.toUpperCase());
  if (fiat.length || !coins.length) {
    const base = fiat[0] || 'USD';
    const j = await (await get(`https://open.er-api.com/v6/latest/${base}`, signal)).json();
    const targets = fiat.length > 1 ? fiat.slice(1) : ['RUB', 'EUR', 'KZT', 'USD', 'CNY', 'GBP'].filter((x) => x !== base);
    out.push(`Курс 1 ${base}: ` + targets.map((t) => `${t} ${j.rates?.[t] ? (+j.rates[t]).toFixed(j.rates[t] > 50 ? 2 : 4) : '—'}`).join(' · ') + ` (обновлено ${String(j.time_last_update_utc || '').slice(5, 16)})`);
  }
  return out.join('\n');
}

async function arxiv(q, signal) {
  const x = await (await get(`https://export.arxiv.org/api/query?search_query=all:${encodeURIComponent(q)}&max_results=5&sortBy=relevance`, signal)).text();
  const items = [...x.matchAll(/<entry>([\s\S]*?)<\/entry>/g)].map((m) => ({ title: strip((m[1].match(/<title>([\s\S]*?)<\/title>/) || [])[1]), url: (m[1].match(/<id>(.*?)<\/id>/) || [])[1], date: ((m[1].match(/<published>(.*?)<\/published>/) || [])[1] || '').slice(0, 10), sum: strip((m[1].match(/<summary>([\s\S]*?)<\/summary>/) || [])[1]).slice(0, 380) }));
  return items.length ? items.map((i, n) => `${n + 1}. ${i.title} [${i.date}]\n   ${i.url}\n   ${i.sum}`).join('\n') : 'На arXiv ничего не найдено';
}

async function hn(q, signal) {
  const url = q ? `https://hn.algolia.com/api/v1/search?query=${encodeURIComponent(q)}&tags=story&hitsPerPage=8` : 'https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=10';
  const j = await (await get(url, signal)).json();
  return (j.hits || []).map((h, i) => `${i + 1}. ${h.title} (${h.points} очков, ${h.num_comments} комм.)\n   ${h.url || `https://news.ycombinator.com/item?id=${h.objectID}`}`).join('\n') || 'Ничего не найдено';
}

async function geo(q, signal) {
  const j = await (await get(`https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=3&accept-language=ru`, signal)).json();
  return j.map((p, i) => `${i + 1}. ${p.display_name}\n   координаты ${(+p.lat).toFixed(5)}, ${(+p.lon).toFixed(5)} · https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}`).join('\n') || 'Место не найдено';
}

async function rss(url, signal) {
  if (!/^https?:\/\//.test(url)) throw new Error('нужен адрес RSS/Atom-ленты (https://…)');
  const x = await (await get(url, signal)).text();
  const items = [...x.matchAll(/<(item|entry)[\s>][\s\S]*?<\/\1>/g)].slice(0, 10).map((m) => {
    const b = m[0];
    return { title: strip((b.match(/<title[^>]*>([\s\S]*?)<\/title>/) || [])[1]), link: (b.match(/<link[^>]*href="([^"]+)"/) || b.match(/<link[^>]*>([\s\S]*?)<\/link>/) || [])[1]?.trim(), date: strip((b.match(/<(pubDate|updated|published)>([\s\S]*?)<\/\1>/) || [])[2] || '').slice(0, 25) };
  });
  return items.length ? items.map((i, n) => `${n + 1}. ${i.title}${i.date ? ` [${i.date}]` : ''}\n   ${i.link || ''}`).join('\n') : 'Лента пуста или формат не распознан';
}

async function reverse(q, signal) {
  const [lat, lon] = String(q).split(/[,\s;]+/).map(Number);
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return 'Нужны координаты «широта,долгота»';
  const j = await (await get(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&accept-language=ru&zoom=18`, signal)).json();
  return j.display_name || 'Адрес не найден';
}
const OSM = { аптека: 'amenity=pharmacy', кафе: 'amenity=cafe', ресторан: 'amenity=restaurant', банкомат: 'amenity=atm', заправка: 'amenity=fuel', больница: 'amenity=hospital', парковка: 'amenity=parking', магазин: 'shop=supermarket', продукты: 'shop=convenience', метро: 'station=subway', остановка: 'highway=bus_stop', туалет: 'amenity=toilets', банк: 'amenity=bank', pharmacy: 'amenity=pharmacy', cafe: 'amenity=cafe', restaurant: 'amenity=restaurant', atm: 'amenity=atm', fuel: 'amenity=fuel', supermarket: 'shop=supermarket' };
/** query: «широта,долгота категория» (аптека, кафе, ресторан, банкомат, заправка, больница, парковка, магазин, банк…) */
async function nearby(q, signal) {
  const m = /^\s*(-?\d+(?:\.\d+)?)[,\s;]+(-?\d+(?:\.\d+)?)\s+(.+)$/.exec(String(q));
  if (!m) return 'Формат: «широта,долгота категория», например «43.23,76.91 аптека»';
  const [, lat, lon, cat] = m; const tag = OSM[cat.trim().toLowerCase()];
  if (!tag) return `Неизвестная категория. Доступны: ${Object.keys(OSM).filter((k) => /[а-я]/.test(k)).join(', ')}`;
  const ql = `[out:json][timeout:15];(node(around:1500,${lat},${lon})[${tag}];way(around:1500,${lat},${lon})[${tag}];);out center 12;`;
  let j = null, lastErr = null;
  for (const host of ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter', 'https://overpass.private.coffee/api/interpreter']) {   // публичные зеркала часто заняты
    try { j = await (await get(`${host}?data=${encodeURIComponent(ql)}`, signal)).json(); break; } catch (e) { lastErr = e; }
  }
  if (!j) throw lastErr || new Error('сервис карт недоступен');
  const rad = Math.PI / 180, dist = (a, b) => Math.round(6371000 * Math.hypot((a - lat) * rad, (b - lon) * rad * Math.cos(lat * rad)));
  const items = (j.elements || []).map((e) => { const la = e.lat ?? e.center?.lat, lo = e.lon ?? e.center?.lon; return { name: e.tags?.name || e.tags?.brand || cat, d: dist(la, lo), addr: [e.tags?.['addr:street'], e.tags?.['addr:housenumber']].filter(Boolean).join(' '), hours: e.tags?.opening_hours || '', la, lo }; }).sort((a, b) => a.d - b.d).slice(0, 6);
  return items.length ? items.map((x, i) => `${i + 1}. ${x.name} — ${x.d} м${x.addr ? `, ${x.addr}` : ''}${x.hours ? ` · ${x.hours}` : ''} (${(+x.la).toFixed(5)}, ${(+x.lo).toFixed(5)})`).join('\n') : `Рядом (1,5 км) ничего не найдено: ${cat}`;
}

export const LOOKUP_SOURCES = ['weather', 'wiki', 'rates', 'arxiv', 'hn', 'geocode', 'rss', 'reverse', 'nearby'];
export async function lookup(source, query, lang, signal) {
  try {
    switch (source) {
      case 'weather': return await weather(query, signal);
      case 'wiki': return await wiki(query, lang, signal);
      case 'rates': return await rates(query, signal);
      case 'arxiv': return await arxiv(query, signal);
      case 'hn': return await hn(query, signal);
      case 'geocode': return await geo(query, signal);
      case 'rss': return await rss(query, signal);
      case 'reverse': return await reverse(query, signal);
      case 'nearby': return await nearby(query, signal);
      default: return `Неизвестный источник. Доступны: ${LOOKUP_SOURCES.join(', ')}`;
    }
  } catch (e) { return `Ошибка источника ${source}: ${e.message}`; }
}
