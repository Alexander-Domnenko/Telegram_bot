from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.database.requests import get_all_modules, get_lessons_by_module, get_test_questions_by_lesson, get_all_users
from statistics import mean

async def create_admin_menu():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📤 Добавить урок", callback_data="upload_lesson")
    keyboard.button(text="✏️ Обновить уроки", callback_data="update_content")
    keyboard.button(text="🗑 Удалить урок", callback_data="delete_lesson")
    keyboard.button(text="📝 Добавить тест", callback_data="add_test")
    keyboard.button(text="✏️ Редактировать тесты", callback_data="edit_tests")
    keyboard.button(text="📚 Добавить модуль", callback_data="add_module")
    keyboard.button(text="🗑 Удалить модуль", callback_data="delete_module")
    keyboard.button(text="📊 Прогресс студентов", callback_data="show_stats")
    keyboard.button(text="❓ Помощь", callback_data="admin_help")
    keyboard.button(text="🚪 Выйти", callback_data="exit_admin")
    keyboard.adjust(2)
    return keyboard.as_markup()

async def create_module_selection_kb_dynamic(db_session):
    content = await get_all_modules(db_session)
    builder = InlineKeyboardBuilder()
    for module in content:
        builder.button(text=f"📘 {module.code.capitalize()} модуль", callback_data=module.code)
    builder.button(text="🚪 Выйти", callback_data="exit_admin")
    builder.adjust(1)
    return builder.as_markup()

async def create_lesson_selection_kb(db_session, module):
    lessons = await get_lessons_by_module(db_session, module)
    lessons.sort(key=lambda x: int(x.code.split("-")[1]))
    builder = InlineKeyboardBuilder()
    for lesson in lessons:
        lesson_num = lesson.code.split("-")[1]
        builder.button(text=f"📚 Урок {lesson_num}", callback_data=lesson.code)
    builder.button(text="🚪 Выйти", callback_data="exit_admin")
    builder.adjust(2)
    return builder.as_markup()

async def create_question_selection_kb(db_session, test_key):
    lesson_key = test_key.replace("test", "lesson")
    questions = await get_test_questions_by_lesson(db_session, lesson_key)
    builder = InlineKeyboardBuilder()
    for i, _ in enumerate(questions, 1):
        builder.button(text=f"❓ Вопрос {i}", callback_data=f"question_{i-1}")
    builder.button(text="➕ Добавить новый вопрос", callback_data="add_new_question")
    builder.button(text="🚪 Выйти", callback_data="exit_admin")
    builder.adjust(2)
    return builder.as_markup()

async def create_test_field_selection_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="❓ Вопрос", callback_data="question")
    builder.button(text="📋 Варианты ответа", callback_data="options")
    builder.button(text="✅ Правильный ответ", callback_data="correct")
    builder.button(text="🖼️ Фото", callback_data="photo")
    builder.button(text="🗑️ Удалить вопрос", callback_data="delete_question")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.button(text="✔️ Завершить", callback_data="finish")
    builder.adjust(2)
    return builder.as_markup()

async def create_preview_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm")
    builder.button(text="❌ Отменить", callback_data="cancel_preview")
    builder.adjust(2)
    return builder.as_markup()

async def create_add_question_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ещё вопрос", callback_data="add_another_question")
    builder.button(text="✔️ Завершить", callback_data="finish")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()

async def create_cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel")
    return builder.as_markup()

async def create_field_selection_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Текст", callback_data="text")
    builder.button(text="🖼️ Фото", callback_data="photo")
    builder.button(text="▶️ Видео", callback_data="video")
    builder.button(text="📄 Конспект", callback_data="notes")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.button(text="✔️ Завершить", callback_data="finish")
    builder.adjust(2)
    return builder.as_markup()

async def create_student_selection_kb(db_session):
    users = await get_all_users(db_session)
    builder = InlineKeyboardBuilder()
    for user in users:
        student_name = f"{user.first_name} {user.last_name}".strip() or user.username or f"Студент {user.id}"
        builder.button(text=f"👤 {student_name}", callback_data=f"student_{user.id}")
    builder.button(text="🚪 Выйти", callback_data="exit_admin")
    builder.adjust(2)
    return builder.as_markup()

async def create_stats_filter_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Менее 50% уроков", callback_data="filter_lessons_less_50")
    builder.button(text="📚 50% и более уроков", callback_data="filter_lessons_50_plus")
    builder.button(text="📚 Все уроки", callback_data="filter_lessons_all")
    builder.button(text="📝 Тесты < 50%", callback_data="filter_tests_below_50")
    builder.button(text="📝 Тесты > 80%", callback_data="filter_tests_above_80")
    builder.button(text="🔢 Сорт. по урокам", callback_data="sort_by_lessons")
    builder.button(text="🔢 Сорт. по тестам", callback_data="sort_by_tests")
    builder.button(text="📊 Общая статистика", callback_data="show_stats_overview")
    builder.button(text="🚪 Выйти", callback_data="exit_admin")
    builder.adjust(2)
    return builder.as_markup()


