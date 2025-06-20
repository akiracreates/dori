import random
import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.filters import Command
from bot.sharedState import user_flashcards

from bot.database.db_helpers import (
    get_all_modules, get_connection, get_or_create_session, add_word,
    get_words, add_library_word, can_user_edit_word, update_progress, get_achievements_for_student
)
from bot.handlers.teacher import delete_message_later
from bot.menus import personal_dict_menu, student_main_menu, student_word_view_menu
from bot.services.card_generator import generate_flashcard_image


router = Router()

# ---------- FSM States ----------
class StudentEditWord(StatesGroup):
    waiting_for_word_id = State()
    waiting_for_new_text = State()
    waiting_for_new_translation = State()

class FlashcardState(StatesGroup):
    selecting_module = State()
    awaiting_input = State()

class PersonalDictFSM(StatesGroup):
    adding_word = State()
    adding_translation = State()
    adding_synonyms = State()
    deleting_word_id = State()


# ---------- Utility ----------
def pick_weighted_word(words):
    total = sum(word["weight"] for word in words)
    r = random.uniform(0, total)
    upto = 0
    for word in words:
        if upto + word["weight"] >= r:
            return word
        upto += word["weight"]
    return words[-1]  # fallback




# ---------- Command Handlers ----------
@router.message(Command("menu_student"))
async def show_student_menu(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=student_main_menu())


@router.message(Command("help"))
async def student_help(message: types.Message):
    help_text = (
        "🎓 <b>Справка для студента:</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/menu_student - Показать меню студента\n"
        "/levelSwitch - Изменить уровень сложности (A1/A2/B1)\n"
        "/help - Показать эту справку\n"
        "/stopcard - Остановить режим флеш-карт\n\n"
        "<b>Функции меню:</b>\n"
        "• <b>Флеш-карты</b> - Тренировка перевода слов\n"
        "• <b>Редактировать слово</b> - Изменить слова из вашей библиотеки\n"
        "• <b>Мои модули</b> - Просмотреть доступные учебные модули"
    )
    await message.answer(help_text, parse_mode="HTML")

# ---------- Flashcard Flow ----------
@router.callback_query(F.data == "flashcards_start")
async def start_flashcard_practice(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(FlashcardState.selecting_module)
    await callback.message.answer(
        "Режим флеш-карт активирован.\n\nВам будет показано слово на русском. Напишите его перевод на английский."
    )
    await callback.message.answer("Введите модуль (например: module 4) или 'все' для всех слов:")

@router.message(FlashcardState.selecting_module)
async def handle_module_selection(message: types.Message, state: FSMContext):
    module = message.text.strip().lower()
    conn = get_connection()
    cur = conn.cursor()

    query = "SELECT Word_ID, Text, translation, synonyms FROM Word WHERE added_by = 'teacher'"
    params = []
    if module != "все":
        query += " AND LOWER(module) = LOWER(?)"
        params.append(module)

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.answer("Слов из этого модуля не найдено.")
        return

    words = [{"Word_ID": r[0], "Text": r[1], "translation": r[2], "synonyms": r[3] or "не указаны"} for r in rows]
    random.shuffle(words)
    user_flashcards[message.from_user.id] = words[1:]
    word = words[0]

    await state.set_state(FlashcardState.awaiting_input)
    await state.update_data(current_word=word)

    image = await generate_flashcard_image(..., is_question=True)
    sent = await message.answer_photo(photo=image)

    await message.answer(f"Слово: {word['translation']}")
    asyncio.create_task(delete_message_later(message.bot, message.chat.id, sent.message_id))

@router.message(FlashcardState.awaiting_input)
async def check_flashcard_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()

    if message.text.strip().lower() == "/stopcard":
        print("[DEBUG] intercepted /stopcard inside awaiting_input")
        await state.clear()
        await message.answer("⛔️ Режим флеш-карт остановлен.")
        return

    session_id = get_or_create_session(message.from_user.id)
    data = await state.get_data()

    # ⛔️ Если /stopcard уже был вызван
    if data.get("stopcard"):
        await state.clear()
        return

    # Защита от потери current_word
    if "current_word" not in data:
        await message.answer("⚠️ Ошибка: нет текущего слова.")
        await state.update_data(stopcard=True)
        await state.set_state(None)

        return

    word = data["current_word"]
    user_input = message.text.strip().lower()
    correct = word["Text"].strip().lower()
    synonyms = [s.strip().lower() for s in (word.get("synonyms") or "").split(",")]
    is_correct = user_input == correct or user_input in synonyms

    update_progress(session_id, word["Word_ID"], is_correct)

    feedback = (
        "✅ Верно!" if user_input == correct else
        "✅ Верно (синоним)!" if user_input in synonyms else
        f"❌ Неверно.\nПравильный ответ: <b>{word['Text']}</b>"
    )
    await message.answer(
        f"{feedback}\nСинонимы: {word.get('synonyms', 'не указаны')}",
        parse_mode="HTML"
    )

    flashcards = data.get("flashcards", [])

    if not flashcards:
        await message.answer("🎉 Тренировка завершена")
        await state.clear()
        return

    if not is_correct:
        flashcards.append(word)

    next_word = flashcards.pop(0)

    # обновляем только то, что нужно
    await state.update_data(current_word=next_word, flashcards=flashcards)

    # ещё раз проверим флаг остановки
    data = await state.get_data()
    if data.get("stopcard"):
        await state.clear()
        return

    image = await generate_flashcard_image(next_word["translation"], is_question=True)
    sent = await message.answer_photo(photo=image)
    await message.answer(f"Слово: {next_word['translation']}")
    asyncio.create_task(delete_message_later(message.bot, message.chat.id, sent.message_id))


# ---------- Word Editing ----------
@router.callback_query(F.data == "student_start_edit")
async def student_prompt_edit(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(StudentEditWord.waiting_for_word_id)
    await callback.message.answer("Введите ID слова из вашей библиотеки:")

@router.message(StudentEditWord.waiting_for_word_id)
async def student_check_edit_permission(message: types.Message, state: FSMContext):
    session_id = get_or_create_session(message.from_user.id)
    try:
        word_id = int(message.text.strip())
    except ValueError:
        await message.answer("Пожалуйста, введите корректный ID.")
        return

    if not can_user_edit_word(session_id, word_id):
        await message.answer("Вы не можете редактировать это слово.")
        await state.clear()
        return

    await state.update_data(word_id=word_id)
    await state.set_state(StudentEditWord.waiting_for_new_text)
    await message.answer("Введите новое значение слова:")

@router.message(StudentEditWord.waiting_for_new_text)
async def student_edit_text(message: types.Message, state: FSMContext):
    await state.update_data(new_text=message.text)
    await state.set_state(StudentEditWord.waiting_for_new_translation)
    await message.answer("Введите новый перевод:")

@router.message(StudentEditWord.waiting_for_new_translation)
async def student_edit_translation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    with get_connection() as conn:
        conn.execute("UPDATE Word SET Text = ?, translation = ? WHERE Word_ID = ?", (data['new_text'], message.text, data['word_id']))
    await message.answer(f"Слово обновлено: {data['new_text']} – {message.text}")
    await state.clear()

# ---------- Word & Dictionary Management ----------
@router.callback_query(F.data == "view_student_words")
async def student_words_entry(callback: types.CallbackQuery):
    await callback.message.answer("Что вы хотите просмотреть?", reply_markup=student_word_view_menu())

@router.callback_query(F.data == "student_words_all")
async def view_all_words(callback: types.CallbackQuery):
    session_id = get_or_create_session(callback.from_user.id)
    words = get_words(session_id)
    if not words:
        await callback.message.answer("Слов не найдено.")
        return

    lines = [f"{w['Word_ID']}. {w['Text']} – {w['translation']}" for w in words]
    await callback.message.answer("📚 Все доступные слова:\n" + "\n".join(lines))

@router.callback_query(F.data == "view_modules")
async def student_view_modules(callback: types.CallbackQuery):
    modules = get_all_modules()
    if not modules:
        await callback.message.answer("Модули пока не найдены.")
        return
    await callback.message.answer("\n".join(modules))

@router.callback_query(F.data == "personal_dict_menu")
async def open_personal_dict_menu(callback: types.CallbackQuery):
    await callback.message.answer("Личный словарь: выберите действие", reply_markup=personal_dict_menu())

@router.callback_query(F.data == "personal_add")
async def personal_add_word_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalDictFSM.adding_word)
    await callback.message.answer("Введите английское слово:")

@router.message(PersonalDictFSM.adding_word)
async def personal_add_word_text(message: types.Message, state: FSMContext):
    await state.update_data(word=message.text.strip())
    await state.set_state(PersonalDictFSM.adding_translation)
    await message.answer("Введите перевод:")

@router.message(PersonalDictFSM.adding_translation)
async def personal_add_word_translation(message: types.Message, state: FSMContext):
    await state.update_data(translation=message.text.strip())
    await state.set_state(PersonalDictFSM.adding_synonyms)
    await message.answer("Введите синонимы через запятую (или '-' если нет синонимов):")


@router.callback_query(F.data == "personal_view")
async def personal_view(callback: types.CallbackQuery):
    session_id = get_or_create_session(callback.from_user.id)
    with get_connection() as conn:
        rows = conn.execute("SELECT Word_ID, Text, translation FROM Word WHERE added_by = 'student' AND StudentSession_ID = ?", (session_id,)).fetchall()
    if not rows:
        await callback.message.answer("🕵️ Ваш словарь пуст.")
        return
    lines = [f"{row[0]}. {row[1]} – {row[2]}" for row in rows]
    await callback.message.answer("📓 Ваши слова:\n" + "\n".join(lines))

@router.callback_query(F.data == "personal_delete")
async def personal_delete_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PersonalDictFSM.deleting_word_id)
    await callback.message.answer("Введите ID слова для удаления:")

@router.message(PersonalDictFSM.deleting_word_id)
async def personal_delete_confirm(message: types.Message, state: FSMContext):
    session_id = get_or_create_session(message.from_user.id)
    try:
        word_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите корректный ID.")
        return
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM Word WHERE Word_ID = ? AND added_by = 'student' AND StudentSession_ID = ?", (word_id, session_id))
        deleted = cur.rowcount
    await message.answer("✅ Слово удалено." if deleted else "❌ Не удалось удалить слово.")
    await state.clear()


@router.message(PersonalDictFSM.adding_synonyms)
async def personal_add_word_synonyms(message: types.Message, state: FSMContext):
    data = await state.get_data()
    session_id = get_or_create_session(message.from_user.id)
    synonyms = None if message.text.strip() == "-" else message.text.strip()

    try:
        add_word(
            session_id,
            data["word"],
            data["translation"],
            level="A1",
            added_by="student",
            synonyms=synonyms
        )
        await message.answer(f"✅ Слово <b>{data['word']}</b> добавлено.", parse_mode="HTML")
    except ValueError as e:
        await message.answer(f"❌ {str(e)}")

    await state.clear()



@router.message(Command("achievements"))
async def show_achievements(message: types.Message):
    session_id = get_or_create_session(message.from_user.id)
    achievements = get_achievements_for_student(session_id)

    if not achievements:
        await message.answer("😔 У вас пока нет достижений.")
        return

    text = "🏆 <b>Ваши достижения:</b>\n\n"
    for name, desc, ts in achievements:
        text += f"• <b>{name}</b>\n  {desc}\n  📅 {ts}\n\n"

    await message.answer(text.strip(), parse_mode="HTML")


# ---------- Register ----------
def register(dp):
    dp.include_router(router)