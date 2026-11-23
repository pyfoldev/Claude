const env = process.env;
const list = (v) => (v || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);

export const config = {
  port: +env.PORT || 8787,
  publicUrl: env.PUBLIC_URL || '',
  dataDir: env.DATA_DIR || './data',
  workspacesDir: env.WORKSPACES_DIR || './workspaces',
  jwtSecret: env.JWT_SECRET || 'dev-insecure-secret',
  ownerEmails: list(env.OWNER_EMAILS),
  allowedEmails: list(env.ALLOWED_EMAILS),
  openRegistration: env.OPEN_REGISTRATION === 'true',
  river: {
    baseUrl: (env.RIVER_BASE_URL || 'https://api.river.ai/v1').replace(/\/$/, ''),
    apiKey: env.RIVER_API_KEY || '',
    model: env.RIVER_MODEL || 'deepseek-ai/DeepSeek-V4.1-Flash',
    codeModel: env.RIVER_CODE_MODEL || env.RIVER_MODEL || 'deepseek-ai/DeepSeek-V4.1-Flash',   // модель движка Code (opencode)
    fastModel: env.RIVER_FAST_MODEL || 'deepseek-ai/DeepSeek-V4.1-Flash',
    voiceModel: env.RIVER_VOICE_MODEL || 'deepseek-ai/DeepSeek-V4.1-Flash-1017',   // для звонков: в замерах первое слово на ~350 мс быстрее
    visionModel: env.RIVER_VISION_MODEL || 'deepseek-ai/DeepSeek-V4.1-Flash',
    visionModels: (env.RIVER_VISION_MODELS || 'deepseek-ai/DeepSeek-V4.1-Flash,deepseek-ai/DeepSeek-V4.1-Flash-1017,zai-org/GLM-5.3-Flash,nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4').split(',').map((s) => s.trim()).filter(Boolean),
    // Только дешёвые модели (дорогие GLM-5.3, Qwen, Kimi скрыты)
    allowed: (env.RIVER_ALLOWED_MODELS || 'deepseek-ai/DeepSeek-V4.1-Flash,deepseek-ai/DeepSeek-V4.1-Flash-1017,zai-org/GLM-5.3-Flash,nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4').split(',').map((s) => s.trim()).filter(Boolean),
    vision: env.RIVER_VISION === 'true',
  },
  mistral: {
    apiKey: env.MISTRAL_API_KEY || '',
    embedModel: env.EMBED_MODEL || 'mistral-embed',
  },
  deepgram: {
    apiKey: env.DEEPGRAM_API_KEY || '',
    model: env.DEEPGRAM_MODEL || 'nova-3',                       // файлы
    ttsVoice: env.DEEPGRAM_TTS_VOICE || 'flux-vladimir-ru',      // озвучка Deepgram: Flux TTS (русский голос Владимир); Aura-2 русского не знает
    ttsExpressivity: env.DEEPGRAM_TTS_EXPRESSIVITY || '0',      // Flux: выразительность 0…
    streamModel: env.DEEPGRAM_STREAM_MODEL || 'nova-3',          // поток (звонок, диктовка): nova-3 — быстрая и точная, русский поддерживает
  },
  voiceAgent: {                                                        // Deepgram Voice Agent: STT + LLM (Claude Haiku 4.5) + TTS (Flux «Владимир») в одном потоке
    enabled: env.VOICE_AGENT !== '0',
    thinkModel: env.VOICE_THINK_MODEL || 'claude-haiku-4-5',
    thinkProvider: env.VOICE_THINK_PROVIDER || 'anthropic',
    listenModel: env.VOICE_LISTEN_MODEL || 'nova-3',
    speakModel: env.VOICE_SPEAK_MODEL || env.DEEPGRAM_TTS_VOICE || 'flux-vladimir-ru',
  },
  ttsProvider: (env.TTS_PROVIDER || 'deepgram').toLowerCase(),         // deepgram | fish — переключатель озвучки; при сбое Deepgram автоматически идёт Fish
  fish: {
    apiKey: env.FISH_API_KEY || '',
    referenceId: env.FISH_REFERENCE_ID || '',
    model: env.FISH_MODEL || 's2.1-pro-free',
  },
  smtp: {
    host: env.SMTP_HOST || 'smtp-relay.brevo.com',
    port: +env.SMTP_PORT || 587,
    user: env.SMTP_USER || '',
    pass: env.SMTP_PASS || '',
    sender: env.SENDER_EMAIL || '',
  },
  turnstile: { siteKey: env.TURNSTILE_SITE_KEY || '', secret: env.TURNSTILE_SECRET || '' },
  googleClientIds: (env.GOOGLE_CLIENT_IDS || '').split(',').map((s) => s.trim()).filter(Boolean),
  githubClientId: env.GITHUB_CLIENT_ID || '',
};

export const isOwnerEmail = (email) => config.ownerEmails.includes(email.toLowerCase());
export const isAllowedEmail = (email) =>
  config.openRegistration || isOwnerEmail(email) || config.allowedEmails.includes(email.toLowerCase());

export const SERVER_V = 16;
