// Транскрибация аудио/видео файлов (для read_file и вложений): Deepgram.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { config } from './config.js';
import { deepgramTranscribe } from './sttStream.js';

export const AUDIO_EXT = /\.(mp3|wav|m4a|aac|ogg|oga|opus|flac|webm|mp4|mov|mkv|avi|m4v|3gp|wma)$/i;

export async function transcribeFile(file, language) {
  if (!config.deepgram.apiKey) return { error: 'Не задан DEEPGRAM_API_KEY — расшифровка недоступна' };
  let src = file; let tmp = null;
  const ff = spawnSync('ffmpeg', ['-version'], { encoding: 'utf8' });
  if (!ff.error && ff.status === 0) {                       // сжимаем до 16 кГц моно: быстрее и влезает в лимиты API
    tmp = path.join(os.tmpdir(), `tr_${Date.now()}.mp3`);
    const r = spawnSync('ffmpeg', ['-y', '-i', file, '-vn', '-ac', '1', '-ar', '16000', '-b:a', '32k', '-t', '3000', tmp], { timeout: 180000 });
    if (r.status === 0 && fs.existsSync(tmp)) src = tmp;
  }
  try {
    const size = fs.statSync(src).size;
    if (size > 24e6) return { error: 'Файл слишком большой для расшифровки (>24 МБ); установите ffmpeg на сервере для сжатия' };
    const buf = fs.readFileSync(src);
    try { return { text: await deepgramTranscribe(buf, path.basename(src), 'audio/mpeg', language) }; } catch (e) { return { error: e.message }; }
  } catch (e) { return { error: e.message }; }
  finally { if (tmp) fs.rmSync(tmp, { force: true }); }
}
