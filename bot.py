import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional

import truststore

truststore.inject_into_ssl()

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, MessageEntity
from dotenv import load_dotenv

from entity_utils import replace_preserving_entities

load_dotenv()
BOT_TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("replace_bot")
router = Router()

_ESCAPE_MAP = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    "v": "\v",
    "0": "\0",
    "\\": "\\",
}
_ESCAPE_RE = re.compile(r"\\(u[0-9A-Fa-f]{4}|x[0-9A-Fa-f]{2}|.)", re.DOTALL)

_DISPLAY_MAP = {"\n": "\\n", "\t": "\\t", "\r": "\\r", "\b": "\\b", "\f": "\\f", "\v": "\\v"}


def unescape(text: str) -> str:
    """Turn escape sequences a user typed literally (\\b, \\n, \\x08, \\u0008, ...)
    into the real control character, so e.g. typing backslash-b sends an actual
    backspace to be used in the replace rule. Unknown escapes are left as-is."""

    def repl(match: "re.Match[str]") -> str:
        token = match.group(1)
        if token.startswith("u") and len(token) == 5:
            return chr(int(token[1:], 16))
        if token.startswith("x") and len(token) == 3:
            return chr(int(token[1:], 16))
        return _ESCAPE_MAP.get(token, "\\" + token)

    return _ESCAPE_RE.sub(repl, text)


def escape_for_display(text: str) -> str:
    """Inverse of unescape() for showing control characters readably in a chat message."""
    out = []
    for ch in text:
        if ch in _DISPLAY_MAP:
            out.append(_DISPLAY_MAP[ch])
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return "".join(out)


class ReplaceStates(StatesGroup):
    waiting_old = State()
    waiting_new = State()


def _extract_file(message: Message) -> Optional[Dict[str, Any]]:
    if message.document:
        return {"media_type": "document", "file_id": message.document.file_id}
    if message.video:
        return {"media_type": "video", "file_id": message.video.file_id}
    if message.audio:
        return {"media_type": "audio", "file_id": message.audio.file_id}
    if message.photo:
        return {"media_type": "photo", "file_id": message.photo[-1].file_id}
    return None


def _pack_pending(message: Message) -> Dict[str, Any]:
    info = _extract_file(message)
    entities = message.caption_entities or []
    return {
        **info,
        "caption": message.caption,
        "caption_entities": [e.model_dump() for e in entities],
    }


async def _send_transformed(bot: Bot, chat_id: int, pending: Dict[str, Any], old: str, new: str) -> None:
    entities = [MessageEntity(**e) for e in pending.get("caption_entities") or []]
    new_caption, new_entities = replace_preserving_entities(pending.get("caption"), entities, old, new)

    kwargs = {"chat_id": chat_id, "caption": new_caption, "caption_entities": new_entities}
    media_type = pending["media_type"]
    file_id = pending["file_id"]
    if media_type == "document":
        await bot.send_document(document=file_id, **kwargs)
    elif media_type == "video":
        await bot.send_video(video=file_id, **kwargs)
    elif media_type == "audio":
        await bot.send_audio(audio=file_id, **kwargs)
    elif media_type == "photo":
        await bot.send_photo(photo=file_id, **kwargs)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Salom! Menga fayl (video, hujjat, rasm yoki audio) yuboring.\n"
        "Keyin qaysi matnni nimaga o'zgartirish kerakligini so'rayman va shu qoidani "
        "barcha keyingi fayllarga avtomatik qo'llayman.\n\n"
        "Qoidani tozalash uchun /newRule buyrug'ini yuboring."
    )


@router.message(Command("newRule"))
async def cmd_new_rule(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Qoida tozalandi. Endi yangi fayl yuboring — men qayta so'rayman.")


@router.message(F.document | F.video | F.photo | F.audio)
async def handle_file(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    old = data.get("old")
    new = data.get("new")

    if old is not None and new is not None:
        pending = _pack_pending(message)
        logger.info("chat=%s auto-applying rule %r -> %r to %s", message.chat.id, old, new, pending["media_type"])
        await _send_transformed(message.bot, message.chat.id, pending, old, new)
        return

    pending_files: List[Dict[str, Any]] = data.get("pending_files", [])
    pending_files.append(_pack_pending(message))
    await state.update_data(pending_files=pending_files)
    logger.info("chat=%s queued file #%s, waiting for rule", message.chat.id, len(pending_files))

    current_state = await state.get_state()
    if current_state in (ReplaceStates.waiting_old.state, ReplaceStates.waiting_new.state):
        return

    await state.set_state(ReplaceStates.waiting_old)
    await message.answer("O'zgartirilishi kerak bo'lgan matn yoki belgini kiriting:")


@router.message(ReplaceStates.waiting_old)
async def handle_old_text(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Iltimos, matn ko'rinishida yuboring.")
        return
    await state.update_data(old=unescape(message.text))
    await state.set_state(ReplaceStates.waiting_new)
    await message.answer("Ushbu matn nimaga o'zgarishi kerakligini kiriting:")


@router.message(ReplaceStates.waiting_new)
async def handle_new_text(message: Message, state: FSMContext) -> None:
    if message.text is None:
        await message.answer("Iltimos, matn ko'rinishida yuboring.")
        return

    data = await state.get_data()
    old = data["old"]
    new = unescape(message.text)
    pending_files: List[Dict[str, Any]] = data.get("pending_files", [])

    await state.set_state(None)
    await state.update_data(old=old, new=new, pending_files=[])
    logger.info("chat=%s rule set %r -> %r, applying to %s pending file(s)", message.chat.id, old, new, len(pending_files))

    await message.answer(
        f"Qoida o'rnatildi: \"{escape_for_display(old)}\" → \"{escape_for_display(new)}\".\n"
        "Endi barcha yuborilgan va keyingi fayllar avtomatik o'zgartiriladi."
    )

    for pending in pending_files:
        await _send_transformed(message.bot, message.chat.id, pending, old, new)


@router.message(F.text & ~F.text.startswith("/"))
async def handle_plain_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    old = data.get("old")
    new = data.get("new")
    if old is None or new is None:
        await message.answer("Avval menga fayl yuboring.")
        return
    new_text, new_entities = replace_preserving_entities(message.text, message.entities or [], old, new)
    await message.answer(new_text, entities=new_entities)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
