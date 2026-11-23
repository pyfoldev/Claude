// «Умное авто»: выбирает модель под тип запроса. Порядок кандидатов настраивается через .env (AUTO_*), недоступные модели пропускаются.
import { config } from './config.js';
import { cachedModels, listModels } from './providers.js';

const RIVER = {
  fast: config.river.fastModel,                                   // DeepSeek V4.1 Flash — код, агентные задачи, tool-calling
  glm: 'zai-org/GLM-5.3-Flash',
  alt: 'deepseek-ai/DeepSeek-V4.1-Flash-1017',
};
const list = (v, d) => (v || d).split(',').map((s) => s.trim()).filter(Boolean);
// формат кандидата: «groq:openai/gpt-oss-120b», «coarena:gpt-6-luna» или «river:deepseek-ai/…»; без префикса — coarena
const CFG = () => ({
  phone: list(process.env.AUTO_PHONE, `groq:openai/gpt-oss-120b,unorouter:gpt-oss-120b:free,coarena:gemini-3-8-flash`),
  code: list(process.env.AUTO_CODE, `river:${RIVER.fast},river:${RIVER.glm},unorouter:deepseek-v4.1-flash:free`),
  school: list(process.env.AUTO_SCHOOL, `coarena:gpt-6-luna,coarena:gemini-3-8-flash,coarena:deepseek-v4-1-flash-1017,unorouter:kimi-k3.1-pro:free`),
  humanities: list(process.env.AUTO_HUMANITIES, `coarena:gemini-3-8-flash,coarena:gpt-6-luna,unorouter:gemini-3.6-flash:free`),
  general: list(process.env.AUTO_GENERAL, `groq:openai/gpt-oss-120b,unorouter:gpt-oss-120b:free,coarena:gemini-3-8-flash,coarena:gpt-6-luna`),
});

const RX = {
  phone: /будильник|таймер|секундомер|фонарик|вай-?фай|wi-?fi|блютуз|bluetooth|авиарежим|не беспокоить|яркост|громкост|тише|громче|на телефоне|(открой|запусти|закрой|выключи|включи|останови)\s+(приложени|ютуб|youtube|телеграм|telegram|ватсап|whatsapp|инстаграм|instagram|тикток|tiktok|хром|chrome|камер|галере|настройки|карты|музык|spotify|браузер|калькулятор|часы)/i,
  code: /(^|[^а-яa-z])(код|скрипт|функци[яюиею]|класс|баг|дебаг|рефактор|компил|линт|тест[ыа]?\b|python|питон|javascript|typescript|kotlin|java|golang|rust|c\+\+|sql|git|github|docker|bash|linux|npm|pip|api|json|regex|регуляр|алгоритм|программ|приложени[ея]|сервер|деплой|верстк|html|css|react|android|gradle|apk)([^а-яa-z]|$)|```|stack ?trace|exception|traceback/i,
  math: /реши|решить|задач[аиеу]|уравнени|неравенств|интеграл|производн|предел|матриц|вероятност|комбинатор|геометри|алгебр|тригонометр|физик|хими[яи]|формул|теорем|докажи|вычисли|посчитай|найди (значение|x|корни|площадь|объ[её]м)|егэ|огэ|олимпиад|контрольн|домашн|\d\s*[+\-*/^×÷=]\s*\d|√|∫|∑/i,
  humanities: /сочинени|эссе|реферат|доклад|литератур|истори[яи]|обществознани|биологи|географи|перевед|перевод|грамматик|пересказ|анализ (текста|стихотворения)|ответь на вопросы по тексту/i,
};

export function classify(text, mode) {
  const t = String(text || '');
  if (RX.phone.test(t) && mode !== 'code') return 'phone';
  if (mode === 'code') return 'code';
  if (RX.code.test(t)) return 'code';
  if (RX.math.test(t)) return 'school';
  if (RX.humanities.test(t)) return 'humanities';
  return 'general';
}

let warmed = false;
function warm() {
  if (warmed) return;
  warmed = true;
  if (process.env.GROQ_API_KEY) listModels({ baseUrl: 'https://api.groq.com/openai/v1', apiKey: process.env.GROQ_API_KEY }, 'groq').catch(() => {});
  if (process.env.UNOROUTER_API_KEY) listModels({ baseUrl: 'https://api.unorouter.com/v1', apiKey: process.env.UNOROUTER_API_KEY }, 'unorouter').catch(() => {});
  if (process.env.COARENA_API_KEY) listModels({ baseUrl: 'https://coarena.ai/api/v1', apiKey: process.env.COARENA_API_KEY }, 'coarena').catch(() => {});
}

function available(c, ctx = {}) {
  const [p, ...rest] = c.includes(':') && /^(river|coarena|groq|unorouter)$/.test(c.split(':')[0]) ? c.split(':') : ['coarena', c];
  const model = rest.join(':');
  if (p === 'unorouter') {
    if (!process.env.UNOROUTER_API_KEY) return null;
    const known = cachedModels('unorouter');
    if (known.length && !known.includes(model)) return null;
    return { prov: 'unorouter', model };
  }
  if (p === 'groq') {
    if (!ctx.groq) return null;                       // Groq доступен, только если приложение подключило мост (или есть серверный ключ)
    return { prov: 'groq', model };
  }
  if (p === 'coarena') {
    if (!process.env.COARENA_API_KEY) return null;
    const known = cachedModels('coarena');
    if (known.length ? !known.includes(model) : !['gpt-6-luna', 'gemini-3-8-flash', 'deepseek-v4-1-flash-1017'].includes(model)) return null;   // список ещё не загружен → только проверенные модели
    return { prov: 'coarena', model };
  }
  if (!config.river.allowed.includes(model)) return null;
  return { prov: 'river', model };
}

/** → { kind, chain: [{prov, model}] } (первый — основной, остальные — запасные, в т.ч. у другого провайдера) */
export function autoRoute({ text, mode, hasImages, groq = false }) {
  warm();
  const kind = classify(text, mode);
  const chain = [];
  for (const c of CFG()[kind]) {
    const a = available(c, { groq });
    if (!a) continue;
    if (a.prov === 'river' && hasImages && !config.river.visionModels.includes(a.model)) continue;
    if (!chain.some((x) => x.prov === a.prov && x.model === a.model)) chain.push(a);
  }
  // всегда есть надёжный запасной вариант на river
  const tail = hasImages ? config.river.visionModel : RIVER.fast;
  if (!chain.some((x) => x.prov === 'river')) chain.push({ prov: 'river', model: tail });
  return { kind, chain };
}
export const KIND_LABEL = { phone: 'телефон', code: 'код', school: 'задача', humanities: 'гуманитарное', general: 'общение' };
