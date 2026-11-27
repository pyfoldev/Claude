<!-- АВТОГЕНЕРАЦИЯ: tools/gen_docs.py. Не редактируйте вручную. -->

# Таблицы БД

Источник: `bot/db.py` → `SCHEMA` (пары/семья — `bot/pair/`).


## `msg_hourly`

- `chat_id INTEGER`
- `user_id INTEGER`
- `hour_ts INTEGER`
- `n INTEGER`
- `PRIMARY KEY(chat_id, user_id, hour_ts)`

## `msg_daily`

- `chat_id INTEGER`
- `user_id INTEGER`
- `day_ts INTEGER`
- `n INTEGER`
- `PRIMARY KEY(chat_id, user_id, day_ts)`

## `warns`

- `chat_id INTEGER`
- `user_id INTEGER`
- `n INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `mod_log`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `actor_id INTEGER`
- `target_id INTEGER`
- `action TEXT`
- `reason TEXT`
- `ts INTEGER`
- `duration INTEGER`

## `warn_events`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `user_id INTEGER`
- `ts INTEGER`
- `expires_at INTEGER`
- `reason TEXT`
- `actor INTEGER`

## `reports`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `reporter INTEGER`
- `target INTEGER`
- `message_id INTEGER`
- `text TEXT`
- `reason TEXT`
- `status TEXT DEFAULT 'open'`
- `ts INTEGER`
- `handled_by INTEGER`

## `filters`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `kind TEXT`
- `pattern TEXT`
- `action TEXT`
- `created_by INTEGER`
- `ts INTEGER`

## `triggers`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `event TEXT`
- `action TEXT`
- `secs INTEGER DEFAULT 0`
- `reason TEXT DEFAULT ''`
- `created_by INTEGER`
- `ts INTEGER`

## `trusted`

- `chat_id INTEGER`
- `user_id INTEGER`
- `added_by INTEGER`
- `ts INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `sticker_block`

- `chat_id INTEGER`
- `kind TEXT`
- `key TEXT`
- `PRIMARY KEY(chat_id, kind, key)`

## `faq`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `keyword TEXT`
- `answer TEXT`
- `created_by INTEGER`
- `ts INTEGER`

## `periodic`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `every INTEGER`
- `text TEXT`
- `last_sent INTEGER DEFAULT 0`
- `created_by INTEGER`

## `grid_chats`

- `chat_id INTEGER PRIMARY KEY`
- `owner_id INTEGER`
- `ts INTEGER`

## `board_games`

- `id TEXT PRIMARY KEY`
- `chat_id INTEGER`
- `data TEXT`
- `expires_at INTEGER`

## `cards_owned`

- `user_id INTEGER`
- `card_id INTEGER`
- `n INTEGER DEFAULT 1`
- `PRIMARY KEY(user_id, card_id)`

## `cards_cooldown`

- `user_id INTEGER PRIMARY KEY`
- `last_find INTEGER`

## `link_allow`

- `chat_id INTEGER`
- `domain TEXT`
- `created_by INTEGER`
- `PRIMARY KEY(chat_id, domain)`

## `aimod_events`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `user_id INTEGER`
- `message_id INTEGER`
- `category TEXT`
- `confidence INTEGER`
- `action TEXT`
- `text TEXT`
- `status TEXT DEFAULT 'open'`
- `ts INTEGER`
- `handled_by INTEGER`

## `giveaways`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `creator INTEGER`
- `step TEXT`
- `text TEXT`
- `photo TEXT`
- `winners INTEGER DEFAULT 1`
- `publish_at INTEGER`
- `ends_at INTEGER`
- `status TEXT DEFAULT 'draft'`
- `message_id INTEGER`
- `created_at INTEGER`
- `result TEXT`
- `shown_count INTEGER DEFAULT 0`

## `giveaway_entries`

- `gid INTEGER`
- `user_id INTEGER`
- `ts INTEGER`
- `PRIMARY KEY(gid, user_id)`

## `giveaway_checks`

- `gid INTEGER`
- `user_id INTEGER`
- `answer TEXT`
- `attempts INTEGER DEFAULT 0`
- `expires_at INTEGER`
- `PRIMARY KEY(gid, user_id)`

## `quotes`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `author_id INTEGER`
- `author_name TEXT`
- `text TEXT`
- `ts INTEGER`
- `added_by INTEGER`
- `added_at INTEGER`
- `message_id INTEGER`
- `card TEXT`

## `mog_ratings`

- `fp TEXT PRIMARY KEY`
- `avatar INTEGER`
- `name INTEGER`
- `meaning INTEGER`
- `ts INTEGER`

## `mog_results`

- `chat_id INTEGER`
- `winner INTEGER`
- `loser INTEGER`
- `ts INTEGER`

## `suggestions`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `user_id INTEGER`
- `user_name TEXT`
- `text TEXT`
- `ts INTEGER`
- `status TEXT DEFAULT 'new'`
- `handled_by INTEGER`
- `handled_at INTEGER`

## `premium`

- `user_id INTEGER PRIMARY KEY`
- `until INTEGER`
- `since INTEGER`
- `payments INTEGER DEFAULT 0`

## `payments`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `user_id INTEGER`
- `charge_id TEXT`
- `amount INTEGER`
- `ts INTEGER`
- `recurring INTEGER DEFAULT 0`
- `refunded INTEGER DEFAULT 0`

## `payment_receipts`

- `charge_id TEXT PRIMARY KEY`
- `ts INTEGER`

## `payment_effects`

- `charge_id TEXT PRIMARY KEY`
- `kind TEXT`
- `target_id INTEGER`
- `previous_until INTEGER`
- `until INTEGER`

## `schema_migrations`

- `name TEXT PRIMARY KEY`

## `user_prefs`

- `user_id INTEGER PRIMARY KEY`
- `ai_model TEXT`

## `promo_codes`

- `code TEXT PRIMARY KEY`
- `days INTEGER`
- `uses_left INTEGER`
- `created_by INTEGER`
- `created_at INTEGER`

## `promo_uses`

- `code TEXT`
- `user_id INTEGER`
- `ts INTEGER`
- `PRIMARY KEY(code, user_id)`

## `settings`

- `chat_id INTEGER`
- `key TEXT`
- `value TEXT`
- `PRIMARY KEY(chat_id, key)`

## `wallets`

- `chat_id INTEGER`
- `user_id INTEGER`
- `balance INTEGER`
- `last_bonus_day INTEGER DEFAULT -1`
- `wins INTEGER DEFAULT 0`
- `PRIMARY KEY(chat_id, user_id)`

## `captchas`

- `token TEXT PRIMARY KEY`
- `chat_id INTEGER`
- `user_id INTEGER`
- `answer TEXT`
- `expires_at INTEGER`
- `message_id INTEGER`

## `users`

- `user_id INTEGER PRIMARY KEY`
- `username TEXT`
- `name TEXT`

## `chat_members`

- `chat_id INTEGER`
- `user_id INTEGER`
- `first_seen INTEGER`
- `last_seen INTEGER`
- `joined_at INTEGER`
- `active INTEGER DEFAULT 1`
- `PRIMARY KEY(chat_id, user_id)`

## `chats`

- `chat_id INTEGER PRIMARY KEY`
- `title TEXT`
- `type TEXT`
- `username TEXT`
- `added_at INTEGER`
- `last_seen INTEGER`
- `active INTEGER DEFAULT 1`

## `bot_bans`

- `kind TEXT`
- `id INTEGER`
- `reason TEXT`
- `ts INTEGER`
- `PRIMARY KEY(kind, id)`

## `owner_log`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `ts INTEGER`
- `owner_id INTEGER`
- `action TEXT`
- `detail TEXT`

## `marriages`

- `chat_id INTEGER`
- `u1 INTEGER`
- `u2 INTEGER`
- `since INTEGER`
- `b1 INTEGER DEFAULT -1`
- `b2 INTEGER DEFAULT -1`
- `PRIMARY KEY(chat_id, u1, u2)`

## `relations`

- `chat_id INTEGER`
- `u1 INTEGER`
- `u2 INTEGER`
- `since INTEGER`
- `PRIMARY KEY(chat_id, u1, u2)`

## `parents`

- `chat_id INTEGER`
- `child INTEGER`
- `parent INTEGER`
- `since INTEGER`
- `PRIMARY KEY(chat_id, child, parent)`

## `pairs`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `u1 INTEGER`
- `u2 INTEGER`
- `stage TEXT DEFAULT 'relation'`
- `created INTEGER`
- `sparks INTEGER DEFAULT 100`
- `warmth INTEGER DEFAULT 0`
- `level INTEGER DEFAULT 1`
- `streak INTEGER DEFAULT 0`
- `streak_day INTEGER DEFAULT 0`
- `day INTEGER DEFAULT 0`
- `mask INTEGER DEFAULT 0`
- `n1 INTEGER DEFAULT 0`
- `n2 INTEGER DEFAULT 0`
- `rp1 INTEGER DEFAULT 0`
- `rp2 INTEGER DEFAULT 0`
- `act1 INTEGER DEFAULT 0`
- `act2 INTEGER DEFAULT 0`
- `next1 INTEGER DEFAULT 0`
- `next2 INTEGER DEFAULT 0`
- `upkeep_at INTEGER DEFAULT 0`
- `state TEXT DEFAULT 'ok'`
- `quarrel_until INTEGER DEFAULT 0`
- `offended_by INTEGER DEFAULT 0`
- `last_active INTEGER DEFAULT 0`
- `warned_day INTEGER DEFAULT 0`
- `topup_day INTEGER DEFAULT 0`
- `topup_sum INTEGER DEFAULT 0`
- `protect INTEGER DEFAULT 1`
- `intim_at INTEGER DEFAULT 0`
- `premium_until INTEGER DEFAULT 0`
- `gift_day INTEGER DEFAULT 0`
- `gift_n INTEGER DEFAULT 0`
- `ended_at INTEGER`
- `ended_reason TEXT`
- `legacy_key TEXT`

## `pair_log`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `pair_id INTEGER`
- `ts INTEGER`
- `kind TEXT`
- `amount INTEGER`
- `balance INTEGER`
- `warmth INTEGER`
- `actor INTEGER`
- `detail TEXT`

## `pair_counters`

- `pair_id INTEGER`
- `kind TEXT`
- `n INTEGER DEFAULT 0`
- `PRIMARY KEY(pair_id, kind)`

## `pair_quests`

- `pair_id INTEGER`
- `scope TEXT`
- `period INTEGER`
- `slot INTEGER`
- `kind TEXT`
- `goal INTEGER`
- `progress INTEGER DEFAULT 0`
- `reward INTEGER`
- `warmth INTEGER`
- `done INTEGER DEFAULT 0`
- `PRIMARY KEY(pair_id, scope, period, slot)`

## `pair_gifts`

- `pair_id INTEGER`
- `gift TEXT`
- `n INTEGER DEFAULT 0`
- `PRIMARY KEY(pair_id, gift)`

## `pair_houses`

- `pair_id INTEGER PRIMARY KEY`
- `tier TEXT`
- `name TEXT`
- `hoard INTEGER DEFAULT 0`
- `bill_at INTEGER`
- `debt INTEGER DEFAULT 0`
- `missed INTEGER DEFAULT 0`
- `arrested INTEGER DEFAULT 0`
- `since INTEGER`

## `pair_rooms`

- `pair_id INTEGER`
- `room TEXT`
- `level INTEGER DEFAULT 1`
- `PRIMARY KEY(pair_id, room)`

## `pair_baby`

- `pair_id INTEGER PRIMARY KEY`
- `mother INTEGER DEFAULT 0`
- `started INTEGER`
- `health INTEGER DEFAULT 80`
- `health_at INTEGER`
- `twins INTEGER DEFAULT 0`
- `name TEXT DEFAULT ''`
- `doc_at INTEGER DEFAULT 0`
- `rest_at INTEGER DEFAULT 0`
- `vit_at INTEGER DEFAULT 0`

## `pair_children`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `pair_id INTEGER`
- `name TEXT`
- `born INTEGER`
- `mood INTEGER DEFAULT 70`
- `mood_at INTEGER DEFAULT 0`
- `fed_at INTEGER DEFAULT 0`
- `play_at INTEGER DEFAULT 0`
- `study_at INTEGER DEFAULT 0`
- `sport_at INTEGER DEFAULT 0`
- `s_int INTEGER DEFAULT 0`
- `s_cre INTEGER DEFAULT 0`
- `s_spo INTEGER DEFAULT 0`
- `grown INTEGER DEFAULT 0`
- `job TEXT DEFAULT ''`

## `user_gender`

- `user_id INTEGER PRIMARY KEY`
- `gender TEXT`

## `pair_pets`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `pair_id INTEGER`
- `species TEXT`
- `rarity TEXT`
- `name TEXT DEFAULT ''`
- `egg INTEGER DEFAULT 1`
- `hatch_at INTEGER`
- `mood INTEGER DEFAULT 70`
- `mood_at INTEGER DEFAULT 0`
- `fed_at INTEGER DEFAULT 0`
- `play_at INTEGER DEFAULT 0`
- `xp INTEGER DEFAULT 0`
- `claim_day INTEGER DEFAULT 0`

## `family_requests`

- `id TEXT PRIMARY KEY`
- `chat_id INTEGER`
- `kind TEXT`
- `from_user INTEGER`
- `to_user INTEGER`
- `message_id INTEGER`
- `expires_at INTEGER`

## `ranks`

- `chat_id INTEGER`
- `user_id INTEGER`
- `rank INTEGER`
- `by_user INTEGER`
- `ts INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `cmd_access`

- `chat_id INTEGER`
- `command TEXT`
- `min_rank INTEGER`
- `PRIMARY KEY(chat_id, command)`

## `mod_state`

- `chat_id INTEGER`
- `user_id INTEGER`
- `kind TEXT`
- `until INTEGER`
- `reason TEXT`
- `actor INTEGER`
- `ts INTEGER`
- `PRIMARY KEY(chat_id, user_id, kind)`

## `pending_bans`

- `chat_id INTEGER`
- `username TEXT`
- `duration INTEGER`
- `reason TEXT`
- `actor INTEGER`
- `ts INTEGER`
- `forced INTEGER DEFAULT 0`
- `PRIMARY KEY(chat_id, username)`

## `chat_texts`

- `chat_id INTEGER`
- `key TEXT`
- `text TEXT`
- `PRIMARY KEY(chat_id, key)`

## `profiles`

- `chat_id INTEGER`
- `user_id INTEGER`
- `nick TEXT`
- `title TEXT`
- `motto TEXT`
- `about TEXT`
- `PRIMARY KEY(chat_id, user_id)`

## `reputation`

- `chat_id INTEGER`
- `user_id INTEGER`
- `score INTEGER DEFAULT 0`
- `PRIMARY KEY(chat_id, user_id)`

## `rep_log`

- `chat_id INTEGER`
- `from_user INTEGER`
- `to_user INTEGER`
- `ts INTEGER`

## `awards`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `user_id INTEGER`
- `degree INTEGER`
- `by_user INTEGER`
- `ts INTEGER`

## `notes`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `user_id INTEGER`
- `kind TEXT`
- `text TEXT`
- `ts INTEGER`

## `timers`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `chat_id INTEGER`
- `user_id INTEGER`
- `due INTEGER`
- `text TEXT`

## `family_bonus`

- `chat_id INTEGER`
- `user_id INTEGER`
- `day INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `farm`

- `chat_id INTEGER`
- `user_id INTEGER`
- `last_ts INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `user_memory`

- `user_id INTEGER PRIMARY KEY`
- `facts TEXT`
- `enabled INTEGER DEFAULT 1`
- `updated INTEGER`

## `topic_hourly`

- `chat_id INTEGER`
- `thread_id INTEGER`
- `hour_ts INTEGER`
- `n INTEGER`
- `PRIMARY KEY(chat_id, thread_id, hour_ts)`

## `topics`

- `chat_id INTEGER`
- `thread_id INTEGER`
- `name TEXT`
- `quiet INTEGER DEFAULT 0`
- `PRIMARY KEY(chat_id, thread_id)`

## `avatar_hash`

- `user_id INTEGER PRIMARY KEY`
- `hash TEXT`
- `ts INTEGER`

## `cas_allow`

- `chat_id INTEGER`
- `user_id INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `guard_queries`

- `chat_id INTEGER`
- `user_id INTEGER`
- `query_id TEXT`
- `ts INTEGER`
- `PRIMARY KEY(chat_id, user_id)`

## `guest_bots`

- `chat_id INTEGER`
- `bot_id INTEGER`
- `username TEXT`
- `status INTEGER DEFAULT 0`
- `last_seen INTEGER`
- `PRIMARY KEY(chat_id, bot_id)`

## `usage`

- `chat_id INTEGER`
- `kind TEXT`
- `day INTEGER`
- `n INTEGER`
- `PRIMARY KEY(chat_id, kind, day)`

## `garden`

- `chat_id INTEGER`
- `user_id INTEGER`
- `data TEXT`
- `PRIMARY KEY(chat_id, user_id)`

## `update_queue`

- `update_id INTEGER PRIMARY KEY`
- `ts INTEGER`
- `attempts INTEGER DEFAULT 0`
- `payload TEXT`

## `duels`

- `id TEXT PRIMARY KEY`
- `chat_id INTEGER`
- `data TEXT`
- `expires_at INTEGER`
