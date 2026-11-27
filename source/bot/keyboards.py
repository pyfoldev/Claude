from aiogram.types import InlineKeyboardButton as B
from aiogram.types import InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="🛡 Модерация", callback_data="menu:mod"),
         B(text="📊 Статистика", callback_data="menu:stats")],
        [B(text="🎮 Игры и фан", callback_data="menu:games"),
         B(text="🚫 Защита", callback_data="menu:protect")],
        [B(text="🎭 РП и семья", callback_data="menu:rp"),
         B(text="⚙️ Настройки", callback_data="menu:settings")],
        [B(text="🎖 Ранги и профиль", callback_data="menu:ranks"),
         B(text="❓ Помощь", callback_data="menu:help")],
    ])


def section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="⬅️ В меню", callback_data="menu:home")]
    ])


def stats_keyboard(active: str) -> InlineKeyboardMarkup:
    def b(label: str, key: str) -> B:
        mark = "• " if key == active else ""
        return B(text=mark + label, callback_data=f"stats:{key}", style="primary" if key == active else None)
    return InlineKeyboardMarkup(inline_keyboard=[
        [b("2 часа", "2"), b("День", "24"), b("Вся", "all")]
    ])


def undo_keyboard(action: str, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="↩️ Отменить", callback_data=f"undo:{action}:{target_id}")]
    ])
