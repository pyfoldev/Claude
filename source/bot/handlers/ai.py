"""Команда «ии, вопрос» (River AI) и расшифровка голосовых/кружков/видео (Mistral Voxtral)."""
import asyncio
from weakref import WeakValueDictionary
import html
import logging
import random
import re
import time

from aiogram import F, Router
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import chatmind, media, plans
from bot.ai import AiClient, AiError
from bot import gender, perf, ux
from bot.db import Database
from bot.fmt import escaped_clip
from bot.runtime import Runtime

router = Router(name="ai")

# Как обратиться к ИИ:
#   «ии, вопрос», «ии: вопрос», «ии - вопрос», «нейро, вопрос», «/ai вопрос» — всегда;
#   «ии вопрос» (без знака) — только если это похоже на вопрос или просьбу («ии как дела?», «ии расскажи анекдот»),
#   и @имя_бота вопрос. Обычная фраза «ии развивается быстро» командой не считается.
_SLASH_RE = re.compile(r"^/ai(?:@\w+)?\s+(.{2,1000})$", re.IGNORECASE | re.DOTALL)
_PUNCT_RE = re.compile(r"^(?:ии|нейро)\s*[,:;—–\-?]\s*(.{2,1000})$", re.IGNORECASE | re.DOTALL)
_SPACE_RE = re.compile(r"^(?:ии|нейро)\s+(.{2,1000})$", re.IGNORECASE | re.DOTALL)
_MENTION_RE = re.compile(r"^@(\w+)[,:]?\s+(.{2,1000})$", re.DOTALL)
_REQUEST_WORDS = (
    "кто", "что", "как", "почему", "зачем", "где", "когда", "сколько", "какой", "какая", "какое", "какие", "чем",
    "откуда", "куда", "расскажи", "объясни", "напиши", "придумай", "посчитай", "переведи", "ответь", "скажи",
    "помоги", "сделай", "дай", "покажи", "реши", "составь", "сочини", "подскажи", "найди", "есть ли", "можно ли",
    "правда ли", "привет", "здравствуй", "здорово", "хай", "добрый", "hello", "hi",
)
COOLDOWN = 15
AI_DAILY = 100    # бесплатных вопросов к ИИ в сутки на чат (защита вашего ключа от чужих трат)
STT_DAILY = 150   # расшифровок в сутки на чат
_last_ask: dict[tuple[int, int], float] = {}
_stt_slots = asyncio.Semaphore(3)  # не больше 3 одновременных расшифровок


def extract_question(text: str | None) -> str | None:
    t = (text or "").strip()
    for rx in (_SLASH_RE, _PUNCT_RE):
        m = rx.match(t)
        if m:
            return m.group(1).strip()
    m = _SPACE_RE.match(t)
    if m:
        q = m.group(1).strip()
        if q.endswith("?") or q.lower().startswith(_REQUEST_WORDS):
            return q
    return None


def _is_ask(t: str | None) -> bool:
    return extract_question(t) is not None


def _mentions_candidate(t: str | None) -> bool:
    return bool(t) and _MENTION_RE.match(t.strip()) is not None


@router.message(F.text.func(_is_ask))
async def ask_cmd(message: Message, db: Database, ai: AiClient | None, owner_ids: frozenset = frozenset(),
                  rt: Runtime | None = None) -> None:
    await _answer(message, extract_question(message.text), db, ai, owner_ids, rt)


@router.message(F.text.func(_mentions_candidate))
async def ask_by_mention(message: Message, bot, db: Database, ai: AiClient | None,
                         owner_ids: frozenset = frozenset(), rt: Runtime | None = None) -> None:
    """«@имя_бота вопрос». Чужие @упоминания игнорируем (этот роутер последний, больше никому не мешает)."""
    m = _MENTION_RE.match(message.text.strip())
    if m.group(1).lower() != ((await bot.me()).username or "").lower():
        return
    await _answer(message, m.group(2).strip(), db, ai, owner_ids, rt)


ASK_CONTEXT_LINES = 15


async def _ask_context(message: Message, db: Database) -> str | None:
    """Для «ии, …» в группе: кто спрашивает, сообщение, на которое ответили командой («ии, переведи это»),
    и — если в чате включено живое общение (переписка и так уходит ИИ) — последние реплики."""
    if message.from_user is None:
        return None
    u = message.from_user
    from bot.handlers import memory
    mem_block = await memory.context_block(db, u.id)             # что человек просил запомнить о себе
    if message.chat.type not in ("group", "supergroup"):
        return mem_block
    parts = [f"Спрашивает: {u.full_name}" + (f" (@{u.username})" if u.username else "")]
    if mem_block:
        parts.append(mem_block)
    r = message.reply_to_message
    if r is not None and getattr(r, "forum_topic_created", None) is None and (r.text or r.caption):
        who = "ты (Нори)" if r.from_user and r.from_user.id == message.bot.id else (
            (r.from_user.full_name if r.from_user else "") or "участник")
        parts.append(f"Вопрос задан ответом на сообщение, автор — {who}: «{(r.text or r.caption)[:1000]}»")
    if (await db.get_settings(message.chat.id))["ai_chat"] != "off":
        lines = chatmind.MEMORY.transcript(message.chat.id, upto_msg_id=message.message_id).split("\n")
        lines = [ln for ln in lines if ln][-ASK_CONTEXT_LINES:]
        if lines:
            parts.append("Недавняя переписка (новые внизу; «Имя → Кому» — ответ тому человеку):\n" + "\n".join(lines))
    return "\n".join(parts)


def premium_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ Nori Premium", callback_data="prem:info")]])


DRAFT_EVERY = 0.8          # не чаще раза в ~0.8 с обновляем «печать»: Telegram режет частые вызовы


async def _ask_streaming(message: Message, ai: AiClient, question: str, context, system, model, max_tokens,
                         limit: int) -> str:
    """Ответ ИИ «печатается» прямо в личке (sendMessageDraft, Bot API 9.3+). Если стрим или черновик недоступны —
    тихо отвечаем обычным запросом: пользователь получит тот же ответ, просто без анимации."""
    draft_id = random.randint(1, 2**31 - 1)
    drafts_ok, last, last_text = True, 0.0, ""

    async def draft(text: str) -> None:
        nonlocal drafts_ok
        if not drafts_ok:
            return
        try:
            await message.bot.send_message_draft(message.chat.id, draft_id, text=text)
        except Exception:
            drafts_ok = False                                     # старый клиент/сервер — дальше без черновиков

    await draft("")                                               # «Думает…» пока ждём первые слова
    answer = ""
    try:
        async for answer in ai.ask_stream(question, context=context, system=system, model=model, max_tokens=max_tokens):
            now = time.monotonic()
            raw = answer[:limit]
            shown = html.escape(raw)
            while len(shown) > 4000:                              # экранирование раздувает текст — режем сырой, не готовый HTML
                raw = raw[:-300]
                shown = html.escape(raw)
            if drafts_ok and now - last >= DRAFT_EVERY and shown != last_text:
                last, last_text = now, shown
                await draft(shown)
    except AiError:
        if not answer:                                            # стрим не пошёл — обычный запрос
            return await ai.ask(question, context=context, system=system, model=model, max_tokens=max_tokens)
        # оборвался посередине — отдаём то, что успели получить
    return answer


async def _answer(message: Message, question: str, db: Database, ai: AiClient | None, owner_ids: frozenset,
                  rt: Runtime | None) -> None:
    """Вопрос к ИИ по тарифу: бесплатно — кулдаун, личный суточный лимит, ответы короче, модель по умолчанию;
    Premium — без кулдауна, лимит больше, ответы длиннее, своя модель, ИИ и в личке. Тон — характер Нори из настроек."""
    if rt is not None and not rt.flag("ai"):
        await message.reply("🤖 ИИ временно отключён владельцем бота.")
        return
    uid, chat = message.from_user.id, message.chat.id
    plan = await plans.plan_for(db, uid, owner_ids)
    if message.chat.type == "private":
        if not plan.ai_private:                       # в личке — только Premium: чужие не тратят ключ бесплатно
            await message.answer("🤖 ИИ в личке с ботом — в Nori Premium. Бесплатно ИИ работает в группах: "
                                 "<code>ии, вопрос</code>.", reply_markup=premium_button())
            return
    elif not (await db.get_settings(chat))["ai_on"]:
        await message.reply("🤖 ИИ выключен в этом чате. Админ может включить его: «настройки» → «ИИ».")
        return
    if ai is None or not ai.has_river:
        await ux.tell(message, "⚠️ ИИ не настроен: администратору бота нужно задать RIVER_API_KEY.")
        return
    now = int(time.time())
    key = (chat, uid)
    wait = plan.ai_cooldown - (time.time() - _last_ask.get(key, 0))
    if wait > 0:
        await ux.tell(message, f"⚠️ Подождите {int(wait) + 1} с. С Premium — без ожидания.", reply_markup=premium_button())
        return
    reserved = time.time()
    _last_ask[key] = reserved  # до await: параллельные запросы не обходят паузу
    try:
        personal_allowed = await db.take_quota(uid, "uai", now, plan.ai_daily)
    except BaseException:
        if _last_ask.get(key) == reserved:
            _last_ask.pop(key, None)
        raise
    if not personal_allowed:
        if _last_ask.get(key) == reserved:
            _last_ask.pop(key, None)
        await message.reply(f"⚠️ Лимит вопросов к ИИ на сегодня ({plan.ai_daily}) исчерпан."
                            + ("" if plan is plans.PREMIUM else f" С Premium — {plans.PREMIUM.ai_daily} в сутки."),
                            reply_markup=None if plan is plans.PREMIUM else premium_button())
        return
    shared = plan is plans.FREE and message.chat.type != "private"
    if shared and not await db.take_quota(chat, "ai", now, AI_DAILY):     # общий лимит чата — только для бесплатных
        await db.refund_quota(uid, "uai", now)
        if _last_ask.get(key) == reserved:
            _last_ask.pop(key, None)
        await message.reply("⚠️ Общий лимит бесплатных вопросов к ИИ в этом чате на сегодня исчерпан. "
                            "С Premium — свой лимит.", reply_markup=premium_button())
        return
    perf.chat_action(message.bot, chat, "typing")   # «печатает…» — в фоне, параллельно с запросом к ИИ
    from bot.handlers import memory
    name_fact = memory.capture_name(question)                    # «меня зовут Аня» — запоминаем сами (человек сказал прямо)
    if name_fact and (await db.memory_get(uid))["enabled"]:
        await memory.add_fact(db, uid, name_fact, now)
    context = await _ask_context(message, db)
    style = (await db.get_settings(chat)).get("ai_chat_style", chatmind.DEFAULT_STYLE) \
        if message.chat.type != "private" else chatmind.DEFAULT_STYLE
    model = (await db.get_ai_model(uid)) if plan.choose_model else None
    try:
        if message.chat.type == "private":
            answer = await _ask_streaming(message, ai, question, context, chatmind.ask_system(style), model,
                                          plan.ai_max_tokens, plan.ai_reply_chars)
        else:
            answer = await ai.ask(question, context=context, system=chatmind.ask_system(style), model=model,
                                  max_tokens=plan.ai_max_tokens)
    except AiError as e:
        logging.warning("ai ask failed: %s", e)
        await db.refund_quota(uid, "uai", now)                          # сбой сервиса не съедает лимиты
        if shared:
            await db.refund_quota(chat, "ai", now)
        await ux.tell(message, "❌ Не получилось получить ответ от ИИ, попробуйте позже.")
        return
    await message.reply(escaped_clip(answer[:plan.ai_reply_chars], 4000, 3900))


@router.message(F.voice | F.video_note | F.video | F.audio)
async def transcribe(message: Message, bot, db: Database, ai: AiClient | None, rt: Runtime | None = None) -> None:
    if message.chat.type not in ("group", "supergroup") or ai is None or not ai.has_stt:
        return
    if rt is not None and not rt.flag("stt"):
        return
    s = await db.get_settings(message.chat.id)
    if not s["transcribe_on"]:
        return
    obj = message.voice or message.video_note or message.video or message.audio
    if (obj.duration or 0) > s["transcribe_max"]:
        await message.reply(f"🎙 Слишком длинное для расшифровки (больше {s['transcribe_max']} с).")
        return
    if obj.file_size and obj.file_size > media.MAX_DOWNLOAD:
        return
    quota_time = int(time.time())
    if not await db.take_quota(message.chat.id, "stt", quota_time, STT_DAILY):
        return
    suffix = ".ogg" if message.voice else ".mp4"
    completed = False
    try:
        async with _stt_slots:
            raw = await media.download(bot, obj.file_id, obj.file_size)
            if raw is None:
                return
            mp3 = await media.to_mp3(raw, suffix)
            if mp3 is None:
                logging.warning("transcribe: ffmpeg не смог извлечь звук")
                return
            text = await ai.transcribe(mp3)
            completed = True
    except AiError as e:
        logging.warning("transcribe failed: %s", e)
        return
    except Exception:
        logging.exception("transcribe crashed")
        return
    finally:
        if not completed:
            # Возвращаем именно ту квоту, которую заняли, в том числе после полуночи.
            await db.refund_quota(message.chat.id, "stt", quota_time)
    if text:  # тишина/музыка без речи — молчим
        body = html.escape(text[:1800])
        tag = "blockquote expandable" if len(body) > 300 else "blockquote"       # длинный текст сворачивается
        await message.reply(f"🎙 <b>Расшифровка:</b>\n<{tag}>{body}</blockquote>")


_talk_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
PEOPLE_MAX = 8        # сколько анкет участников показываем ИИ


async def _people(db: Database, chat_id: int, entries) -> list[str]:
    """Что участники разговора сами написали о себе (+ник, +звание, +о себе) — помогает не путать людей."""
    lab = chatmind.labels(entries)
    out = []
    for uid in dict.fromkeys(e.user_id for e in reversed(entries) if e.user_id != chatmind.BOT_UID):
        p = await db.get_profile(chat_id, uid)
        bits = [f"{k}: {str(p[f])[:100]}" for f, k in (("nick", "ник"), ("title", "звание"), ("about", "о себе")) if p.get(f)]
        g = await gender.get(db, uid)
        if g:
            bits.append("пол: " + ("парень (мужской род)" if g == "m" else "девушка (женский род)"))
        if bits:
            out.append(f"- {lab[uid]} — " + "; ".join(bits))
        if len(out) >= PEOPLE_MAX:
            break
    return out


def _own_text(message: Message) -> str:
    """Текст сообщения для ИИ: текст или подпись, с пометкой о вложении («[фото] что это?»)."""
    text = message.text or message.caption or ""
    tag = chatmind.media_tag(message)
    return f"{tag} {text}".strip() if tag else text


async def _images_for(bot, db: Database, message: Message) -> list[bytes]:
    """Картинки сообщения (или того, на что ответили) для зрения Нори; суточный лимит на чат."""
    src = message
    if not chatmind_has_media(message) and message.reply_to_message is not None:
        src = message.reply_to_message
    if not chatmind_has_media(src):
        return []
    quota_time = int(time.time())
    if not await db.take_quota(message.chat.id, "aivision", quota_time, VISION_DAILY):
        return []
    imgs = []
    try:
        from bot import nsfw as nsfw_mod
        imgs = await nsfw_mod.images_from_message(bot, src)
    except Exception:
        logging.exception("ai chat: не удалось получить картинку")
    finally:
        if not imgs:
            await db.refund_quota(message.chat.id, "aivision", quota_time)
    return imgs


def chatmind_has_media(m: Message) -> bool:
    return bool(chatmind.media_tag(m)) or bool(m.document and (m.document.mime_type or "").startswith("image/"))


VISION_DAILY = 150


async def _conversation(message: Message, db: Database):
    """(переписка до этого сообщения включительно, (автор, текст) этого сообщения, анкеты участников).
    Обрезаем по сообщению-поводу: пока ИИ думает, приходят новые реплики, и раньше Нори отвечала не тому человеку."""
    chat, u = message.chat.id, message.from_user
    mem = chatmind.MEMORY
    entries = mem.recent(chat, upto_msg_id=message.message_id)
    own = mem.find(chat, message.message_id)
    own_text = _own_text(message)
    if own is None:                                  # сообщение не попало в память (например, только что включили режим)
        mem.add(chat, u.id, u.first_name or u.full_name, own_text, username=u.username, msg_id=message.message_id)
        entries = mem.recent(chat, upto_msg_id=message.message_id)
        own = mem.find(chat, message.message_id)
    lab = chatmind.labels(entries)
    transcript = mem.transcript(chat, upto_msg_id=message.message_id)
    target = (lab.get(u.id, u.first_name), own.text if own else own_text)
    return transcript, target, await _people(db, chat, entries)


async def _talk(message: Message, bot, db: Database, ai: AiClient | None, rt: Runtime | None = None,
                nori_addressed: bool = False) -> bool:
    """True — ответили. «Живое» общение: отвечает, когда к боту обращаются (ответ на его сообщение, @имя, слово «нори»), а в режиме «болтает»
    иногда сам вклинивается в оживлённый разговор. Сюда попадают только обычные фразы — команды разобрали роутеры выше."""
    u = message.from_user
    body = message.text or message.caption or ""
    if message.chat.type not in ("group", "supergroup") or u is None or u.is_bot or body.startswith("/"):
        return False
    s = await db.get_settings(message.chat.id)
    mode = s["ai_chat"]
    if mode == "off" or not s["ai_on"] or ai is None or not getattr(ai, "has_river", False) or not hasattr(ai, "converse"):
        return False
    if rt is not None and not rt.flag("ai"):
        return False
    me = await bot.me()
    r = message.reply_to_message
    addressed = nori_addressed or chatmind.is_addressed(
        body, bool(r and r.from_user and r.from_user.id == me.id), me.username)
    now = time.time()
    is_media = chatmind_has_media(message)
    kind = chatmind.decide(mode, addressed, body, message.chat.id, now, media=is_media)
    if kind is None:
        return False
    lock = _talk_locks.setdefault(message.chat.id, asyncio.Lock())
    if lock.locked() and kind == "spontaneous":
        return False
    async with lock:
        if not await db.take_quota(message.chat.id, "aichat", int(now), chatmind.DAILY_LIMIT):
            return False
        try:
            transcript, target, people = await _conversation(message, db)
            perf.chat_action(bot, message.chat.id, "typing")      # в фоне: не ждём лишний круг до Telegram
            images = await _images_for(bot, db, message)
            if is_media and not images and not body:        # одно вложение без подписи, а посмотреть не вышло — не отвечаем вслепую
                await db.refund_quota(message.chat.id, "aichat", int(now))
                return False
            raw = await ai.converse(chatmind.persona(s.get("ai_chat_style", "casual")),
                                    chatmind.build_prompt(transcript, kind == "addressed", target, people, bool(images)),
                                    images=images or None)
        except AiError as e:
            logging.warning("ai chat failed: %s", e)
            await db.refund_quota(message.chat.id, "aichat", int(now))
            if kind == "addressed":                          # к боту обратились — молчать нельзя
                await message.reply("Что-то я зависла, напиши ещё раз чуть позже 🙈")
            return False
        reply = chatmind.sanitize_reply(raw, casual=s.get("ai_chat_style", "casual") == "casual")
        if reply is None:                                   # SKIP или пусто: не отвечаем и не тратим лимит
            await db.refund_quota(message.chat.id, "aichat", int(now))
            chatmind.MEMORY.last_bot[message.chat.id] = time.time() - chatmind.SPONTANEOUS_COOLDOWN + 30
            if kind == "addressed":                          # обратились, а модель ответила SKIP/пусто: ответим коротко, а не промолчим
                await message.reply(random.choice(("м?", "я тут, что хотел(а)?", "не поняла, повтори?", "ага, слушаю")))
                return True
            return False
        parts = chatmind.split_burst(reply) if s.get("ai_chat_style", "casual") == "casual" else [reply]
        await asyncio.sleep(chatmind.typing_delay(parts[0]))   # не мгновенно, как печатает человек
        text = html.escape(parts[0])
        sent = await message.reply(text)                     # всегда реплаем: видно, кому именно отвечает Нори
        for extra in parts[1:]:                              # иногда вторым коротким сообщением подряд
            perf.chat_action(bot, message.chat.id, "typing")
            await asyncio.sleep(chatmind.typing_delay(extra))
            await message.answer(html.escape(extra))
        chatmind.MEMORY.add(message.chat.id, chatmind.BOT_UID, "Нори", " ".join(parts), bot=True,
                            msg_id=getattr(sent, "message_id", None),
                            reply_uid=u.id)   # помним, КОМУ Нори отвечала
    return True


@router.message(F.photo | F.sticker | F.animation | F.video | F.video_note)
async def chat_talk_media(message: Message, bot, db: Database, ai: AiClient | None, rt: Runtime | None = None,
                          nori_addressed: bool = False):
    """Фото, стикеры, гифки и видео (с подписью или без) — Нори смотрит и отвечает так же, как на текст."""
    if await _talk(message, bot, db, ai, rt, nori_addressed):
        return None
    return UNHANDLED


@router.message(F.text)
async def chat_talk(message: Message, bot, db: Database, ai: AiClient | None, rt: Runtime | None = None,
                    nori_addressed: bool = False):
    """Последний обработчик роутера. Не ответил — возвращает UNHANDLED, чтобы «нори <вопрос>» дошёл до команды «ии»."""
    if await _talk(message, bot, db, ai, rt, nori_addressed):
        return None
    return UNHANDLED
