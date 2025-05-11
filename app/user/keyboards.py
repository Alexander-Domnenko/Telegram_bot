from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.database.requests import get_all_modules, get_lessons_by_module, get_test_questions_by_lesson

async def create_main_menu_dynamic(db_session):
    modules = await get_all_modules(db_session)
    builder = InlineKeyboardBuilder()
    for module in modules:
        builder.button(text=f"📘 {module.code.capitalize()} модуль", callback_data=f"show_module_{module.code}")
    builder.adjust(1)
    return builder.as_markup()

async def create_module_kb(db_session, module_prefix):
    lessons = await get_lessons_by_module(db_session, module_prefix)
    lessons.sort(key=lambda x: int(x.code.split("-")[1]))
    builder = InlineKeyboardBuilder()
    for lesson in lessons:
        lesson_num = lesson.code.split("-")[1]
        builder.button(text=f"📚 Урок {lesson_num}", callback_data=f"{module_prefix}_lesson-{lesson_num}")
    builder.adjust(2)
    return builder.as_markup()

async def create_lesson_kb(video_link, notes_link, module_prefix, lesson_num):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text='▶️ Смотреть видеоурок', url=video_link),
        InlineKeyboardButton(text='📄 Читать конспект', url=notes_link)
    )
    builder.row(
        InlineKeyboardButton(text='📝 Задание', callback_data=f'{module_prefix}_test-{lesson_num}')
    )
    builder.button(text='🔙 Назад', callback_data=f'module_menu_{module_prefix}')
    builder.adjust(2)
    return builder.as_markup()

async def create_test_kb(db_session, module_prefix, lesson_num, question_idx):
    test_key = f"{module_prefix}_test-{lesson_num}"
    questions = await get_test_questions_by_lesson(db_session, f"{module_prefix}_lesson-{lesson_num}")
    builder = InlineKeyboardBuilder()
    options = [questions[question_idx].option_1, questions[question_idx].option_2]
    if questions[question_idx].option_3:
        options.append(questions[question_idx].option_3)
    for i, option in enumerate(options, 1):
        builder.button(text=f"❓ {option}", callback_data=f'{test_key}_answer-{i}')
    builder.adjust(1)
    builder.button(text='🔙 Вернуться к уроку', callback_data=f'{module_prefix}_lesson-{lesson_num}')
    return builder.as_markup()

async def create_retry_test_kb(module_prefix, lesson_num):
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Повторить тест", callback_data=f"{module_prefix}_test-{lesson_num}")
    builder.button(text="🔙 Вернуться к уроку", callback_data=f"{module_prefix}_lesson-{lesson_num}")
    builder.adjust(2)
    return builder.as_markup()

async def create_update_confirmation_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Обновить", callback_data="update_profile")
    builder.button(text="❌ Отмена", callback_data="cancel_update")
    builder.adjust(2)
    return builder.as_markup()