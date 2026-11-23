// Извлечение текста из документов: PDF, DOCX, XLSX, PPTX (+ обычные текстовые файлы).
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const decode = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n));
const unzipText = (file, inner) => { const r = spawnSync('unzip', ['-p', file, inner], { encoding: 'utf8', timeout: 15000, maxBuffer: 40e6 }); return r.status === 0 ? r.stdout : ''; };
const unzipList = (file) => { const r = spawnSync('unzip', ['-Z1', file], { encoding: 'utf8', timeout: 10000 }); return r.status === 0 ? r.stdout.split('\n').filter(Boolean) : []; };
const clean = (t) => t.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();

export const DOC_EXT = /\.(pdf|docx?|xlsx?|xlsm|pptx?|odt|ods|odp|rtf|epub|html?|ipynb|zip|tar|tgz|gz|7z|rar|db|sqlite3?|png|jpe?g|webp|bmp|tiff?|gif)$/i;
const have = (cmd) => { const r = spawnSync(cmd, ['--version'], { encoding: 'utf8' }); return !r.error; };
const stripHtml = (h) => decode(h.replace(/<(script|style)[\s\S]*?<\/\1>/gi, ' ').replace(/<br\s*\/?>|<\/(p|div|li|h\d|tr)>/gi, '\n').replace(/<[^>]+>/g, ' ').replace(/[ \t]+/g, ' '));

export function extractText(file, name = file) {
  const ext = path.extname(name).toLowerCase();
  try {
    if (ext === '.pdf') {
      const r = spawnSync('pdftotext', ['-layout', '-enc', 'UTF-8', file, '-'], { encoding: 'utf8', timeout: 30000, maxBuffer: 80e6 });
      if (r.error) return { kind: 'pdf', error: 'pdftotext не установлен на сервере (apt install poppler-utils)' };
      return { kind: 'pdf', text: clean(r.stdout || ''), note: r.status ? 'PDF без текстового слоя (скан) — нужен OCR/vision' : '' };
    }
    if (ext === '.docx') {
      const x = unzipText(file, 'word/document.xml');
      const t = decode(x.replace(/<w:tab\/>/g, '\t').replace(/<\/w:p>/g, '\n').replace(/<w:br\/>/g, '\n').replace(/<[^>]+>/g, ''));
      return { kind: 'docx', text: clean(t) };
    }
    if (ext === '.pptx') {
      const slides = unzipList(file).filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n)).sort((a, b) => parseInt(a.match(/\d+/)[0]) - parseInt(b.match(/\d+/)[0]));
      const out = slides.map((n, i) => `# Слайд ${i + 1}\n` + decode(unzipText(file, n).replace(/<\/a:p>/g, '\n').replace(/<[^>]+>/g, '')).trim());
      return { kind: 'pptx', text: clean(out.join('\n\n')) };
    }
    if (ext === '.xlsx') {
      const ss = [...unzipText(file, 'xl/sharedStrings.xml').matchAll(/<si>([\s\S]*?)<\/si>/g)].map((m) => decode(m[1].replace(/<[^>]+>/g, '')));
      const sheets = unzipList(file).filter((n) => /^xl\/worksheets\/sheet\d+\.xml$/.test(n)).slice(0, 4);
      const out = [];
      for (const [k, n] of sheets.entries()) {
        const xml = unzipText(file, n); const rows = [];
        for (const rm of xml.matchAll(/<row[^>]*>([\s\S]*?)<\/row>/g)) {
          const cells = [];
          for (const cm of rm[1].matchAll(/<c ([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
            const t = /t="(\w+)"/.exec(cm[1])?.[1]; const v = /<v>([\s\S]*?)<\/v>/.exec(cm[2] || '')?.[1] ?? /<t[^>]*>([\s\S]*?)<\/t>/.exec(cm[2] || '')?.[1] ?? '';
            cells.push(t === 's' ? ss[+v] ?? '' : decode(v));
          }
          rows.push(cells.join('\t'));
          if (rows.length >= 300) break;
        }
        out.push(`# Лист ${k + 1}\n${rows.join('\n')}`);
      }
      return { kind: 'xlsx', text: clean(out.join('\n\n')) };
    }
    if (ext === '.odt' || ext === '.odp') return { kind: ext.slice(1), text: clean(decode(unzipText(file, 'content.xml').replace(/<\/text:p>|<\/text:h>/g, '\n').replace(/<[^>]+>/g, ''))) };
    if (ext === '.ods') return { kind: 'ods', text: clean(decode(unzipText(file, 'content.xml').replace(/<\/table:table-row>/g, '\n').replace(/<\/table:table-cell>/g, '\t').replace(/<[^>]+>/g, ''))) };
    if (ext === '.doc') {
      for (const [cmd, args] of [['antiword', [file]], ['catdoc', [file]]]) { const r = spawnSync(cmd, args, { encoding: 'utf8', timeout: 20000, maxBuffer: 40e6 }); if (!r.error && r.status === 0 && r.stdout.trim()) return { kind: 'doc', text: clean(r.stdout) }; }
      return { kind: 'doc', error: 'Старый .doc: на сервере нет antiword/catdoc (apt install antiword catdoc)' };
    }
    if (ext === '.xls') {
      const py = "import pandas as pd,sys\nfor n,df in pd.read_excel(sys.argv[1],sheet_name=None,header=None).items():\n print('# Лист',n); print(df.head(300).fillna('').to_csv(sep='\\t',header=False,index=False))";
      const r = spawnSync('python3', ['-c', py, file], { encoding: 'utf8', timeout: 30000, maxBuffer: 40e6 });
      return r.status === 0 ? { kind: 'xls', text: clean(r.stdout) } : { kind: 'xls', error: 'Старый .xls: нужен pandas+xlrd (pip3 install xlrd)' };
    }
    if (ext === '.ppt') { const r = spawnSync('catppt', [file], { encoding: 'utf8', timeout: 20000 }); return !r.error && r.status === 0 ? { kind: 'ppt', text: clean(r.stdout) } : { kind: 'ppt', error: 'Старый .ppt не читается (сохраните как .pptx)' }; }
    if (ext === '.rtf') return { kind: 'rtf', text: clean(fs.readFileSync(file, 'latin1').replace(/\\'([0-9a-f]{2})/gi, (_, h) => Buffer.from(h, 'hex').toString('latin1')).replace(/\\par[d]?/g, '\n').replace(/\{\\\*[^{}]*\}/g, '').replace(/\\[a-z]+-?\d* ?/gi, '').replace(/[{}]/g, '')) };
    if (ext === '.epub') {
      const parts = unzipList(file).filter((n) => /\.(x?html?)$/i.test(n)).sort().slice(0, 80);
      return { kind: 'epub', text: clean(parts.map((n) => stripHtml(unzipText(file, n))).join('\n\n')) };
    }
    if (ext === '.html' || ext === '.htm') return { kind: 'html', text: clean(stripHtml(fs.readFileSync(file, 'utf8'))) };
    if (ext === '.ipynb') {
      const j = JSON.parse(fs.readFileSync(file, 'utf8'));
      return { kind: 'ipynb', text: (j.cells || []).map((c, i) => `# [${c.cell_type} ${i + 1}]\n${[].concat(c.source || []).join('')}` + (c.outputs?.length ? '\n→ ' + c.outputs.map((o) => [].concat(o.text || o.data?.['text/plain'] || []).join('')).join('').slice(0, 500) : '')).join('\n\n') };
    }
    if (['.zip', '.tar', '.tgz', '.gz', '.7z', '.rar'].includes(ext)) {
      const r = ext === '.zip' ? spawnSync('unzip', ['-l', file], { encoding: 'utf8', timeout: 15000 })
        : ext === '.7z' || ext === '.rar' ? spawnSync(have('7z') ? '7z' : 'unrar', ['l', file], { encoding: 'utf8', timeout: 15000 })
        : spawnSync('tar', ['tf', file], { encoding: 'utf8', timeout: 15000 });
      return r.error || r.status ? { kind: 'archive', error: 'Не удалось прочитать архив' } : { kind: 'archive', text: 'Содержимое архива:\n' + r.stdout.split('\n').slice(0, 300).join('\n') };
    }
    if (['.db', '.sqlite', '.sqlite3'].includes(ext)) {
      const r = spawnSync('sqlite3', [file, '.schema'], { encoding: 'utf8', timeout: 15000 });
      return r.error || r.status ? { kind: 'sqlite', error: 'Нужен sqlite3 (apt install sqlite3)' } : { kind: 'sqlite', text: 'Схема базы:\n' + r.stdout.slice(0, 6000) };
    }
    if (/^\.(png|jpe?g|webp|bmp|tiff?|gif)$/.test(ext)) {
      const r = spawnSync('tesseract', [file, 'stdout', '-l', 'rus+eng'], { encoding: 'utf8', timeout: 40000 });
      return r.error ? { kind: 'image', error: 'Для распознавания текста с изображений нужен tesseract-ocr (apt install tesseract-ocr tesseract-ocr-rus); либо используйте vision-модель' } : { kind: 'image', text: clean(r.stdout || ''), note: 'OCR-текст изображения' };
    }
  } catch (e) { return { kind: ext.slice(1), error: e.message }; }
  return null;
}
