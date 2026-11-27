<!-- АВТОГЕНЕРАЦИЯ: tools/gen_docs.py. Не редактируйте вручную. -->

# Настройки чата

Источники: `bot/db.py` → `DEFAULT_SETTINGS`, `bot/handlers/settings.py` → `PAGES`.


## 🛡 Капча  (`captcha`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `captcha_on` | Капча для новичков | toggle | 1 |
| `captcha_timeout` | Время | choice | 180 |
| `captcha_recheck` | Повторно | choice | 'off' |
| `guard_default` | Заявки без капчи | choice | 'queue' |

## 🚫 Антиспам  (`spam`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `spam_on` | Антиспам | toggle | 0 |
| `spam_flood_n` | Флуд, сообщ. | choice | 5 |
| `spam_flood_sec` | за, сек | choice | 10 |
| `spam_dup` | Одинаковые сообщения | toggle | 1 |
| `links_mode` | Ссылки | choice | 'newbies' |
| `spam_mentions` | Упоминаний макс. | choice | 5 |
| `spam_forward` | Пересылки от новичков | toggle | 0 |
| `spam_ai` | ИИ-проверка новичков | toggle | 0 |
| `spam_action` | Действие | choice | 'delete' |

## 🕵 Фишинг  (`phish`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `phish_on` | Фишинг-ссылки | toggle | 0 |
| `phish_action` | Действие | choice | 'delete' |

## 🤖 Гостевые боты  (`guest`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `guest_mode` | Режим | choice | 'check' |

## 🚀 База спамеров  (`cas`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `cas_mode` | Новички из базы спамеров | choice | 'off' |

## 📝 Стоп-слова  (`filters`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `filter_action` | Действие | choice | 'delete' |

## 🚨 Антирейд  (`raid`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `raid_on` | Антирейд | toggle | 0 |
| `dupe_on` | Двойники забаненных | toggle | 0 |
| `raid_n` | Входов | choice | 5 |
| `raid_sec` | за, сек | choice | 60 |
| `raid_action` | Новичкам | choice | 'captcha' |
| `raid_minutes` | Режим, мин | choice | 10 |

## 🔞 Фильтр 18+  (`nsfw`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `nsfw_on` | Фильтр 18+ | toggle | 0 |
| `nsfw_threshold` | Строгость | choice | 55 |
| `nsfw_action` | Действие | choice | 'delete' |
| `nsfw_ai` | ИИ-проверка (картинка уходит во внешний ИИ) | toggle | 0 |

## 🎞 Гифки наказаний  (`modgif`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `mod_gif` | Гифки к бану, муту, варну | toggle | 1 |
| `transcribe_on` | Расшифровка голосовых | toggle | 0 |
| `transcribe_max` | Макс. длина | choice | 180 |

## 🤖 ИИ-модерация  (`aimod`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `ai_mod` | Проверять | choice | 'off' |
| `ai_mod_action` | Действие | choice | 'delete' |
| `ai_mod_conf` | Уверенность | choice | 75 |

## 🤖 ИИ  (`ai`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `ai_on` | Команда «ии …» | toggle | 1 |
| `ai_chat` | Живое общение | choice | 'off' |
| `ai_chat_style` | Стиль | choice | 'casual' |

## 📅 Активность  (`activity`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `quota_on` | Норма сообщений в неделю (автокик) | toggle | 0 |
| `quota_min` | Норма, сообщений | choice | 250 |
| `quota_warn` | Предупреждать, кто не набирает | toggle | 1 |
| `wake_on` | Подъём молчунов (Нори тегает) | toggle | 0 |
| `idle_on` | Нори сама пишет, если чат затих | toggle | 0 |
| `idle_hours` | Затих, часов | choice | 6 |

## 🌐 Язык / Language  (`lang`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `lang` | Язык | choice | 'ru' |

## 👋 Приветствие  (`welcome`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `welcome_on` | Приветствие | toggle | 1 |
| `report_on` | Команда «жалоба» | toggle | 1 |
| `games_on` | Игры | toggle | 1 |
| `mafia_on` | Мафия (/game) | toggle | 1 |
| `fun_on` | «кто …» | toggle | 1 |
| `rp_on` | РП и семья | toggle | 1 |
| `rp_gifs` | Гифки в РП и семье | toggle | 1 |
| `rp_adult` | РП 18+: флирт и мат | toggle | 0 |
| `pair_intim` | Близость пар (18+) | toggle | 0 |
| `rep_on` | Репутация | toggle | 1 |

## ⚠️ Варны  (`warns`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `warn_limit` | Лимит до наказания | choice | 3 |
| `warn_ttl_days` | Срок жизни варна | choice | 30 |
| `warn_action` | При лимите | choice | 'mute' |
| `warn_secs` | Срок мута/бана | choice | 86400 |
| `mute_secs` | Мут без срока | choice | 0 |
| `ban_secs` | Бан без срока | choice | 0 |

## 🗑 Удалять сообщения  (`delete`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `del_caps` | КАПС | toggle | 0 |
| `del_sticker` | Стикеры | toggle | 0 |
| `del_gif` | Гифки | toggle | 0 |
| `del_voice` | Голосовые | toggle | 0 |
| `del_note` | Кружки | toggle | 0 |
| `del_forward` | Пересланные | toggle | 0 |
| `del_mention` | @упоминания | toggle | 0 |
| `del_emoji` | Кастомные эмодзи | toggle | 0 |
| `del_story` | Сторис | toggle | 0 |
| `del_dice` | Игровые эмодзи (кубик, дартс) | toggle | 0 |
| `del_format` | С форматированием | toggle | 0 |
| `del_via` | Через inline-ботов | toggle | 0 |
| `del_poll` | Опросы | toggle | 0 |
| `del_service` | Служебные (вход, выход, закреп) | toggle | 0 |
| `del_cmds` | Все /команды | toggle | 0 |
| `unpin_channel` | Откреплять посты канала | toggle | 0 |
| `leave_wipe` | Удалять сообщения ушедшего (48 ч) | toggle | 0 |

## 🕵 Фейс-контроль  (`face`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `fc_on` | Проверять новичков | toggle | 0 |
| `fc_photo` | Нужно фото профиля | toggle | 0 |
| `fc_username` | Нужен @username | toggle | 0 |
| `fc_premium` | Нужен Telegram Premium | toggle | 0 |
| `fc_age` | Возраст аккаунта (по id, примерно) | choice | 0 |
| `fc_action` | Не прошёл | choice | 'kick' |

## 🚪 Быстрый выход  (`leave`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `leave_on` | Банить за быстрый выход | toggle | 0 |
| `leave_sec` | Вышел раньше, чем через | choice | 120 |
| `leave_hours` | Бан на | choice | 24 |

## 🌙 Ночной режим  (`night`)

| Ключ | Подпись | Тип | По умолчанию |
|---|---|---|---|
| `night_on` | Закрывать чат ночью | toggle | 0 |
| `night_from` | С | choice | 23 |
| `night_to` | До | choice | 7 |

## Остальные ключи (без страницы в меню)

| Ключ | По умолчанию |
|---|---|
| `log_chat_id` | 0 |
| `mod_on` | 1 |
| `svc_on` | 1 |
| `cards_on` | 1 |
| `stats_on` | 1 |
| `rally_on` | 1 |
| `quotes_on` | 1 |
| `mog_on` | 1 |
| `giveaway_on` | 1 |
| `suggest_on` | 1 |
| `img_on` | 1 |
| `dl_on` | 1 |
| `dl_auto` | 1 |
| `tz` | 'Europe/Moscow' |
| `night_closed` | 0 |
| `quota_since` | 0 |
