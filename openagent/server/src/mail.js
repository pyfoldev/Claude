// Почта по IMAP/SMTP (пароль приложения хранится на сервере в зашифрованном виде): агент читает, ищет, разбирает и отправляет письма сам — в том числе по расписанию.
import { ImapFlow } from 'imapflow';
import nodemailer from 'nodemailer';
import { simpleParser } from 'mailparser';
import { db, now } from './db.js';
import { encSecret, decSecret } from './providers.js';

export const MAIL_PRESETS = [
  { rx: /@(gmail|googlemail)\.com$/i, imap: 'imap.gmail.com', smtp: 'smtp.gmail.com', hint: 'Gmail: нужен «пароль приложения» (аккаунт Google → Безопасность → двухэтапная аутентификация → Пароли приложений).' },
  { rx: /@(yandex\.(ru|com|kz|by|ua)|ya\.ru)$/i, imap: 'imap.yandex.com', smtp: 'smtp.yandex.com', hint: 'Яндекс Почта: включите доступ по IMAP и создайте пароль приложения (id.yandex.ru → Безопасность).' },
  { rx: /@(mail|inbox|list|bk)\.ru$/i, imap: 'imap.mail.ru', smtp: 'smtp.mail.ru', hint: 'Mail.ru: создайте пароль для внешнего приложения в настройках безопасности.' },
  { rx: /@(icloud|me|mac)\.com$/i, imap: 'imap.mail.me.com', smtp: 'smtp.mail.me.com', smtpPort: 587, hint: 'iCloud: пароль приложения из appleid.apple.com.' },
  { rx: /@(outlook|hotmail|live)\.com$/i, imap: 'outlook.office365.com', smtp: 'smtp.office365.com', smtpPort: 587, hint: 'Outlook: личные ящики часто запрещают вход по паролю; если не подключится — используйте другой ящик.' },
];
export const presetFor = (email) => MAIL_PRESETS.find((p) => p.rx.test(email));

const accountsOf = (uid) => db.prepare('SELECT * FROM mail_accounts WHERE user_id=? ORDER BY id').all(uid);
export const hasMail = (uid) => !!db.prepare('SELECT 1 FROM mail_accounts WHERE user_id=? LIMIT 1').get(uid);
const pick = (uid, email) => { const l = accountsOf(uid); return (email && l.find((a) => a.email.toLowerCase() === String(email).toLowerCase())) || l[0] || null; };
const client = (a) => new ImapFlow({ host: a.imap_host, port: a.imap_port, secure: a.imap_port === 993, auth: { user: a.login, pass: decSecret(a.pass) }, logger: false, socketTimeout: 25000, greetingTimeout: 12000 });
async function withImap(a, fn) {
  const c = client(a); c.on('error', () => {});
  await c.connect();
  try { return await fn(c); } finally { try { await c.logout(); } catch {} }
}

export async function addAccount(uid, { email, password, imapHost, imapPort, smtpHost, smtpPort }) {
  email = String(email || '').trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !password) throw new Error('Нужны email и пароль приложения');
  const p = presetFor(email);
  const a = { email, imap_host: imapHost || p?.imap, imap_port: +imapPort || 993, smtp_host: smtpHost || p?.smtp, smtp_port: +smtpPort || p?.smtpPort || 465, login: email, pass: encSecret(String(password).replace(/\s+/g, '')), user_id: uid, created_at: now() };
  if (!a.imap_host || !a.smtp_host) throw new Error('Для этого провайдера укажите адреса IMAP и SMTP серверов');
  try { await withImap(a, async (c) => { await c.mailboxOpen('INBOX', { readOnly: true }); }); }
  catch (e) { throw new Error(`Не удалось войти (${String(e.responseText || e.message).slice(0, 140)}). ${p?.hint || 'Проверьте пароль приложения и включённый IMAP.'}`); }
  db.prepare('INSERT INTO mail_accounts(user_id,email,imap_host,imap_port,smtp_host,smtp_port,login,pass,created_at) VALUES (@user_id,@email,@imap_host,@imap_port,@smtp_host,@smtp_port,@login,@pass,@created_at) ON CONFLICT(user_id,email) DO UPDATE SET imap_host=excluded.imap_host, imap_port=excluded.imap_port, smtp_host=excluded.smtp_host, smtp_port=excluded.smtp_port, pass=excluded.pass').run(a);
  return a.email;
}
export const listAccounts = (uid) => accountsOf(uid).map((a) => ({ id: a.id, email: a.email, imapHost: a.imap_host }));
export const removeAccount = (uid, id) => db.prepare('DELETE FROM mail_accounts WHERE id=? AND user_id=?').run(+id, uid).changes > 0;

const addr = (x) => (x?.[0] ? `${x[0].name ? x[0].name + ' ' : ''}<${x[0].address}>` : '');
const day = (d) => (d ? new Date(d).toISOString().slice(0, 16).replace('T', ' ') : '');
const clean = (t) => String(t || '').replace(/\r/g, '').replace(/\n{3,}/g, '\n\n').replace(/[ \t]+/g, ' ').trim();
const htmlText = (h) => clean(String(h || '').replace(/<style[\s\S]*?<\/style>|<script[\s\S]*?<\/script>/gi, ' ').replace(/<br\s*\/?>|<\/p>|<\/div>|<\/tr>|<\/li>/gi, '\n').replace(/<[^>]+>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>'));

/** Единый вход для инструмента `mail`. */
export async function mailTool(user, args, ctx = {}) {
  const a = pick(user.id, args.account);
  if (!a) return 'Почта не подключена. Пользователь может подключить её в приложении: Инструменты → Подключения → «Почта».';
  const op = String(args.op || 'list');
  const folder = args.folder || 'INBOX';
  try {
    if (op === 'list' || op === 'search') {
      return await withImap(a, async (c) => {
        const lock = await c.getMailboxLock(folder, { readOnly: true });
        try {
          const limit = Math.min(Math.max(+args.limit || 15, 1), 40);
          let query = op === 'search' && args.query ? { or: [{ subject: args.query }, { from: args.query }, { body: args.query }] } : args.unseen === false ? { all: true } : { seen: false };
          if (args.since_days) query = { ...query, since: new Date(Date.now() - args.since_days * 86400e3) };
          const uids = (await c.search(query, { uid: true })) || [];
          const take = uids.slice(-limit).reverse();
          if (!take.length) return op === 'search' ? 'Писем по запросу не найдено' : 'Новых (непрочитанных) писем нет';
          const rows = [];
          for await (const m of c.fetch(take, { uid: true, envelope: true, flags: true, bodyStructure: false }, { uid: true })) rows.push(m);
          rows.sort((x, y) => y.uid - x.uid);
          return `${uids.length} писем${op === 'list' && args.unseen !== false ? ' непрочитанных' : ''} (показаны ${rows.length}):\n` + rows.map((m) => `#${m.uid} ${m.flags?.has('\\Seen') ? '' : '● '}${day(m.envelope.date)} · ${addr(m.envelope.from)} · ${m.envelope.subject || '(без темы)'}`).join('\n');
        } finally { lock.release(); }
      });
    }
    if (op === 'read') {
      return await withImap(a, async (c) => {
        const lock = await c.getMailboxLock(folder);
        try {
          const m = await c.fetchOne(+args.uid, { source: true, envelope: true }, { uid: true });
          if (!m?.source) return 'Письмо не найдено';
          const p = await simpleParser(m.source);
          if (args.keep_unread !== true) await c.messageFlagsAdd(+args.uid, ['\\Seen'], { uid: true });
          const body = clean(p.text) || htmlText(p.html);
          return `От: ${addr(p.from?.value)}\nКому: ${(p.to?.value || []).map((x) => x.address).join(', ')}\nДата: ${day(p.date)}\nТема: ${p.subject || ''}\nMessage-ID: ${p.messageId || ''}\n${p.attachments?.length ? `Вложения: ${p.attachments.map((x) => `${x.filename} (${Math.round(x.size / 1024)} КБ)`).join(', ')}\n` : ''}\n${body.slice(0, 6000)}${body.length > 6000 ? '\n[… письмо обрезано]' : ''}`;
        } finally { lock.release(); }
      });
    }
    if (op === 'mark') {
      return await withImap(a, async (c) => {
        const lock = await c.getMailboxLock(folder);
        try {
          const uid = String(args.uid || '').split(',').map((x) => +x).filter(Boolean); if (!uid.length) return 'Нужен uid';
          const act = String(args.action || 'read');
          if (act === 'read') await c.messageFlagsAdd(uid, ['\\Seen'], { uid: true });
          else if (act === 'unread') await c.messageFlagsRemove(uid, ['\\Seen'], { uid: true });
          else if (act === 'flag') await c.messageFlagsAdd(uid, ['\\Flagged'], { uid: true });
          else if (act === 'archive') { const boxes = await c.list(); const arch = boxes.find((b) => b.specialUse === '\\Archive' || b.specialUse === '\\All') || boxes.find((b) => /archive|архив/i.test(b.path)); if (!arch) return 'Папка архива не найдена'; await c.messageMove(uid, arch.path, { uid: true }); }
          else return 'Действия: read, unread, flag, archive';
          return `Готово: ${act} · писем ${uid.length}`;
        } finally { lock.release(); }
      });
    }
    if (op === 'send') {
      const said = String(ctx.userText || '');
      const explicit = /отправь|отправить|ответь|ответить|напиши|написать|пошли|перешли|напомни ему/i.test(said);
      if (ctx.autonomy === 'ask' && !args.confirmed && !explicit) return 'Нужно подтверждение: пользователь прямо не просил отправить письмо. Покажи адресата, тему и текст, дождись «да» и повтори с confirmed=true.';
      if (!args.to || !args.text) return 'Нужны to и text';
      const tr = nodemailer.createTransport({ host: a.smtp_host, port: a.smtp_port, secure: a.smtp_port === 465, auth: { user: a.login, pass: decSecret(a.pass) }, connectionTimeout: 15000, socketTimeout: 25000 });
      let inReplyTo, refs;
      if (args.reply_to_uid) { try { const mm = await withImap(a, async (c) => { const l = await c.getMailboxLock(folder, { readOnly: true }); try { const m = await c.fetchOne(+args.reply_to_uid, { envelope: true }, { uid: true }); return m?.envelope; } finally { l.release(); } }); inReplyTo = mm?.messageId; refs = mm?.messageId; if (!args.subject && mm?.subject) args.subject = /^re:/i.test(mm.subject) ? mm.subject : `Re: ${mm.subject}`; } catch {} }
      const info = await tr.sendMail({ from: a.email, to: args.to, subject: args.subject || '(без темы)', text: String(args.text), inReplyTo, references: refs });
      return `Письмо отправлено: ${args.to} · «${args.subject || '(без темы)'}» (${info.messageId || 'ok'})`;
    }
    return 'Операции: list, search, read, mark, send';
  } catch (e) { return `Ошибка почты: ${String(e.responseText || e.message).slice(0, 200)}`; }
}
