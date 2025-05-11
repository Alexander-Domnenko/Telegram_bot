from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from app.user.handlers import create_progress_bar

from config import ADMIN_SECRET_CODE
from app.admin.keyboards import create_admin_menu, create_module_selection_kb_dynamic, create_lesson_selection_kb, create_question_selection_kb, create_test_field_selection_kb, create_preview_kb, create_add_question_kb, create_cancel_kb, create_field_selection_kb, create_student_selection_kb, create_stats_filter_kb
from app.admin.states import AdminRegistrationState, UploadLessonState, UpdateState, EditTestStates, AddTestStates, DeleteLessonState, AddModuleState, DeleteModuleState
from app.database.requests import create_user, get_all_modules, get_module_by_code, get_lessons_by_module, get_lesson_by_code, get_test_questions_by_lesson, create_lesson, update_lesson, delete_lesson, create_test_question, update_test_question, delete_test_question, create_module, delete_module, get_all_users, get_user_by_id, get_user_progress, get_user_test_scores, sync_progress_with_content
from sqlalchemy import select
from app.database.models import Lesson
import os
import time
import re
import logging
from statistics import mean

router = Router()

# Функция проверки is_admin
async def is_admin(user_id, db_session):
    user = await get_user_by_id(db_session, user_id)
    return user is not None and user.is_admin
# def is_admin(user_id):
#     return user_id in ADMIN_IDS

def is_valid_text(text):
    return text and 0 < len(text) <= 1000

def is_valid_url(url):
    return bool(re.match(r"^https?://", url))

def is_valid_options(text):
    options = text.split("\n")
    return len(options) >= 2 and all(0 < len(opt.strip()) <= 100 for opt in options)

def is_valid_correct(text, options_count):
    try:
        num = int(text)
        return 1 <= num <= options_count
    except ValueError:
        return False

async def generate_current_question_text(db_session, test_key, question_idx):
    lesson_key = test_key.replace("test", "lesson")
    questions = await get_test_questions_by_lesson(db_session, lesson_key)
    question_data = questions[question_idx]
    options = [question_data.option_1, question_data.option_2]
    if question_data.option_3:
        options.append(question_data.option_3)
    options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
    return f"✦ Вопрос {question_idx + 1}:\n{question_data.question_text}\n\n✦ Варианты:\n{options_text}\n\n✦ Правильный ответ: {question_data.correct_option}"

async def generate_preview_text(db_session, data, new_value):
    lesson_key = data["test_key"].replace("test", "lesson")
    questions = await get_test_questions_by_lesson(db_session, lesson_key)
    question_data = questions[data["question_idx"]]
    options = [question_data.option_1, question_data.option_2]
    if question_data.option_3:
        options.append(question_data.option_3)
    
    if data["field"] == "question":
        question_text = new_value
    else:
        question_text = question_data.question_text
    
    if data["field"] == "options":
        options = [opt.strip() for opt in new_value.split("\n")]
    elif data["field"] == "correct":
        correct = int(new_value)
    else:
        correct = question_data.correct_option
    
    options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
    return f"✦ Вопрос:\n{question_text}\n\n✦ Варианты:\n{options_text}\n\n✦ Правильный ответ: {correct}"

async def get_next_lesson_key(db_session, module):
    lessons = await get_lessons_by_module(db_session, module)
    if not lessons:
        return f"{module}_lesson-1"
    numbers = [int(lesson.code.split("-")[1]) for lesson in lessons]
    next_number = max(numbers) + 1
    return f"{module}_lesson-{next_number}"

# Обработчик команды /admin обновил
@router.message(Command("admin"))
async def admin_handler(message: Message, state: FSMContext, db_session):
    logging.info(f"Received /admin command from user {message.from_user.id}")
    if not await is_admin(message.from_user.id, db_session):  # Передаём db_session
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return
    await state.clear()
    await message.answer(
        "🔧 *Панель администратора*\n"
        "Выберите действие:",
        reply_markup=await create_admin_menu(),
        parse_mode="Markdown"
    )

@router.message(Command("stats"))
async def stats_handler(message: Message, db_session):
    if not await is_admin(message.from_user.id, db_session):
        await message.answer(
            "🚫 **Доступ запрещён**\n"
            "Эта команда доступна только администраторам."
        )
        return
    await show_stats_overview(message, db_session)

@router.callback_query(F.data == "show_stats")
async def stats_callback_handler(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    await show_stats_overview(callback.message, db_session)
    await callback.message.delete()
    await callback.answer()

def calculate_average_test_score(test_scores):
    if not test_scores:
        return 0
    scores = [v.score / v.total * 100 for v in test_scores]
    return round(mean(scores), 2)

async def show_stats_overview(message: Message, db_session):
    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    total_lessons = len(lessons)
    students = await get_all_users(db_session)
    total_students = len(students)
    
    if total_students == 0:
        await message.answer(
            "📊 **Прогресс студентов**\n"
            "ℹ️ Пока нет данных о студентах.",
            reply_markup=await create_admin_menu()
        )
        return
    
    total_completed_lessons = 0
    avg_test_scores = []
    for student in students:
        progress = await get_user_progress(db_session, student.id)
        total_completed_lessons += len(progress)
        test_scores = await get_user_test_scores(db_session, student.id)
        avg_test_scores.append(calculate_average_test_score(test_scores))
    
    avg_completion = round(total_completed_lessons / (total_students * total_lessons) * 100, 2)
    avg_test_score = round(mean(avg_test_scores), 2) if avg_test_scores else 0
    
    await message.answer(
        "📊 **Прогресс студентов**\n"
        f"✦ Всего студентов: {total_students}\n"
        f"✦ Пройдено уроков: {total_completed_lessons}/{total_students * total_lessons}\n"
        f"✦ Средний % завершения уроков: {avg_completion}%\n"
        f"✦ Средний балл по тестам: {avg_test_score}%\n\n"
        "Выберите фильтр или действие:",
        reply_markup=await create_stats_filter_kb()
    )

@router.callback_query(F.data == "show_stats_overview")
async def stats_overview_callback(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    await show_stats_overview(callback.message, db_session)
    await callback.message.delete()
    await callback.answer()

async def show_filtered_stats(callback: CallbackQuery, db_session, filter_text: str, filtered_students: list):
    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    total_lessons = len(lessons)
    
    if not filtered_students:
        await callback.message.edit_text(
            f"📊 **{filter_text}**\n"
            "ℹ️ Нет студентов, соответствующих этому фильтру.",
            reply_markup=await create_stats_filter_kb()
        )
        return
    
    stats_text = f"📊 **{filter_text}**\n✦ Найдено студентов: {len(filtered_students)}\n\n"
    for user in filtered_students[:10]:
        progress = await get_user_progress(db_session, user.id)
        completed_count = len(progress)
        test_scores = await get_user_test_scores(db_session, user.id)
        avg_test_score = calculate_average_test_score(test_scores)
        student_name = f"{user.first_name} {user.last_name}".strip() or user.username or f"Студент {user.id}"
        stats_text += (
            f"👤 {student_name}\n"
            f"Уроки: {completed_count}/{total_lessons} ({round(completed_count/total_lessons*100, 2)}%)\n"
            f"Тесты: {avg_test_score}%\n\n"
        )
    
    if len(filtered_students) > 10:
        stats_text += "ℹ️ Показаны первые 10 студентов.\n"
    
    await callback.message.edit_text(stats_text, reply_markup=await create_stats_filter_kb())

@router.callback_query(F.data == "filter_lessons_less_50")
async def filter_lessons_less_50(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    total_lessons = len(lessons)
    threshold = total_lessons * 0.5
    users = await get_all_users(db_session)
    filtered = []
    for user in users:
        progress = await get_user_progress(db_session, user.id)
        if len(progress) < threshold:
            filtered.append(user)
    await show_filtered_stats(callback, db_session, "Студенты с менее 50% уроков", filtered)
    await callback.answer()

@router.callback_query(F.data == "filter_lessons_50_plus")
async def filter_lessons_50_plus(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    total_lessons = len(lessons)
    threshold = total_lessons * 0.5
    users = await get_all_users(db_session)
    filtered = []
    for user in users:
        progress = await get_user_progress(db_session, user.id)
        if len(progress) >= threshold:
            filtered.append(user)
    await show_filtered_stats(callback, db_session, "Студенты с 50% и более уроков", filtered)
    await callback.answer()

@router.callback_query(F.data == "filter_lessons_all")
async def filter_lessons_all(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    total_lessons = len(lessons)
    users = await get_all_users(db_session)
    filtered = []
    for user in users:
        progress = await get_user_progress(db_session, user.id)
        if len(progress) == total_lessons:
            filtered.append(user)
    await show_filtered_stats(callback, db_session, "Студенты, завершившие все уроки", filtered)
    await callback.answer()

@router.callback_query(F.data == "filter_tests_below_50")
async def filter_tests_below_50(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    users = await get_all_users(db_session)
    filtered = []
    for user in users:
        test_scores = await get_user_test_scores(db_session, user.id)
        if calculate_average_test_score(test_scores) < 50:
            filtered.append(user)
    await show_filtered_stats(callback, db_session, "Студенты с тестами ниже 50%", filtered)
    await callback.answer()

@router.callback_query(F.data == "filter_tests_above_80")
async def filter_tests_above_80(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    users = await get_all_users(db_session)
    filtered = []
    for user in users:
        test_scores = await get_user_test_scores(db_session, user.id)
        if calculate_average_test_score(test_scores) > 80:
            filtered.append(user)
    await show_filtered_stats(callback, db_session, "Студенты с тестами выше 80%", filtered)
    await callback.answer()

@router.callback_query(F.data == "sort_by_lessons")
async def sort_by_lessons(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    users = await get_all_users(db_session)
    sorted_students = sorted(
        users,
        key=lambda user: len(user.progress),
        reverse=True
    )
    await show_filtered_stats(callback, db_session, "Сортировка по количеству уроков", sorted_students)
    await callback.answer()

@router.callback_query(F.data == "sort_by_tests")
async def sort_by_tests(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    users = await get_all_users(db_session)
    sorted_students = sorted(
        users,
        key=lambda user: calculate_average_test_score(user.test_scores),
        reverse=True
    )
    await show_filtered_stats(callback, db_session, "Сортировка по среднему баллу тестов", sorted_students)
    await callback.answer()

@router.callback_query(F.data.startswith("student_"))
async def show_student_stats(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    
    user_id = int(callback.data.split("_")[1])
    user = await get_user_by_id(db_session, user_id)
    if not user:
        await callback.message.edit_text(
            "⚠️ Данные студента не найдены.",
            reply_markup=await create_admin_menu()
        )
        await callback.answer()
        return
    
    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    total_lessons = len(lessons)
    progress = await get_user_progress(db_session, user_id)
    completed_lessons = {p.lesson_code for p in progress}
    test_scores = await get_user_test_scores(db_session, user_id)
    
    student_name = f"{user.first_name} {user.last_name}".strip() or user.username or "Неизвестный студент"
    completed_text = "\n".join([f"✔️ {lesson}" for lesson in completed_lessons]) or "— Нет завершенных уроков"
    incomplete_lessons = [lesson.code for lesson in lessons if lesson.code not in completed_lessons]
    incomplete_text = "\n".join([f"❌ {lesson}" for lesson in incomplete_lessons]) or "— Все уроки завершены"
    score_text = "\n".join([f"➤ {k.test_code}: {k.score}/{k.total} ({round(k.score/k.total*100, 2)}%)" for k in test_scores]) or "— Тесты не пройдены"
    avg_test_score = calculate_average_test_score(test_scores)
    
    completed_count = len(completed_lessons)
    progress_bar = create_progress_bar(completed_count, total_lessons)
    
    await callback.message.edit_text(
        f"📋 **Профиль студента**\n"
        f"Имя: {student_name}\n"
        f"ID: `{user_id}`\n\n"
        "✦ **Прогресс обучения**\n"
        f"Пройдено уроков: {completed_count}/{total_lessons}\n"
        f"{progress_bar}\n\n"
        "✦ **Завершенные уроки**\n"
        f"{completed_text}\n\n"
        "✦ **Незавершенные уроки**\n"
        f"{incomplete_text}\n\n"
        "✦ **Результаты тестов**\n"
        f"{score_text}\n"
        f"Средний балл: {avg_test_score}%",
        reply_markup=await create_stats_filter_kb()
    )
    await callback.answer()

def create_progress_bar(current, total):
    bar_length = 10
    filled = int(bar_length * current / total) if total > 0 else 0
    empty = bar_length - filled
    return f"[{('🟩' * filled) + ('⬜' * empty)}] {current}/{total}"

@router.callback_query(F.data == "cancel", StateFilter(None, UploadLessonState, UpdateState, EditTestStates, AddTestStates, DeleteLessonState, AddModuleState, DeleteModuleState))
async def cancel_handler(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "✅ **Действие отменено**\n"
        "Вы вернулись в панель администратора:",
        reply_markup=await create_admin_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "finish", StateFilter(UploadLessonState, UpdateState, EditTestStates, AddTestStates))
async def finish_handler(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "✅ **Редактирование завершено**\n"
        "Вы вернулись в панель администратора:",
        reply_markup=await create_admin_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "exit_admin", StateFilter(None, UploadLessonState, UpdateState, EditTestStates, AddTestStates, DeleteLessonState, AddModuleState, DeleteModuleState))
async def exit_admin_handler(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("👋 Вы вышли из панели администратора.")
    await callback.answer()

@router.callback_query(F.data == "admin_help")
async def admin_help_handler(callback: CallbackQuery, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    help_text = (
        "ℹ️ **Помощь для админа — всё пошагово!**\n\n"
        "Ты в панели администратора. Вот что можно делать и как:\n\n"
        
        "✦ **Добавить урок**\n"
        "1. Жми 'Добавить урок'.\n"
        "2. Выбери модуль (например, 'first').\n"
        "3. Напиши текст урока (например, 'Это урок про основы').\n"
        "4. Отправь фотку или напиши 'нет', если фотки нет.\n"
        "5. Вставь ссылку на видео (например, 'https://youtube.com/...').\n"
        "6. Вставь ссылку на конспект (например, 'https://docs.google.com/...').\n"
        "7. Готово — урок добавлен!\n\n"
        
        "✦ **Обновить урок**\n"
        "1. Жми 'Обновить уроки'.\n"
        "2. Выбери модуль (например, 'second').\n"
        "3. Выбери урок (например, 'second_lesson-1').\n"
        "4. Выбери, что менять: текст, фото, видео или конспект.\n"
        "5. Введи новое (например, новый текст или ссылку).\n"
        "6. Жми 'Завершить', когда закончишь.\n\n"
        
        "✦ **Добавить тест**\n"
        "1. Жми 'Добавить тест'.\n"
        "2. Выбери модуль (например, 'third').\n"
        "3. Выбери урок (например, 'third_lesson-2').\n"
        "4. Напиши вопрос (например, 'Что такое бот?').\n"
        "5. Напиши варианты ответа (по одному на строке, например:\n"
        "   - Робот\n"
        "   - Человек\n"
        "   - Программа).\n"
        "6. Укажи номер правильного ответа (например, '3').\n"
        "7. Отправь фотку или напиши 'нет'.\n"
        "8. Подтверди или отмени предпросмотр.\n"
        "9. Добавь ещё вопросы или жми 'Завершить'.\n\n"
        
        "✦ **Редактировать тесты**\n"
        "1. Жми 'Редактировать тесты'.\n"
        "2. Выбери модуль (например, 'first').\n"
        "3. Выбери урок (например, 'first_lesson-1').\n"
        "4. Выбери вопрос или добавь новый.\n"
        "5. Для изменения: выбери, что менять (вопрос, варианты, ответ, фото).\n"
        "6. Введи новое значение.\n"
        "7. Подтверди изменения.\n"
        "8. Для удаления: выбери 'Удалить вопрос' и подтверди.\n"
        "9. Жми 'Завершить', когда закончишь.\n\n"
        
        "✦ **Удалить урок**\n"
        "1. Жми 'Удалить урок'.\n"
        "2. Выбери модуль (например, 'second').\n"
        "3. Выбери урок (например, 'second_lesson-3').\n"
        "4. Подтверди удаление или отмени.\n"
        "5. Урок и его тест удалятся.\n\n"
        
        "✦ **Добавить модуль**\n"
        "1. Жми 'Добавить модуль'.\n"
        "2. Напиши название (например, 'fourth', только латиница, до 20 символов).\n"
        "3. Напиши описание (например, 'Модуль про Python').\n"
        "4. Отправь фотку.\n"
        "5. Новый модуль готов!\n\n"
        
        "✦ **Удалить модуль**\n"
        "1. Жми 'Удалить модуль'.\n"
        "2. Выбери модуль (например, 'third').\n"
        "3. Подтверди удаление или отмени.\n"
        "4. Модуль и все его уроки с тестами удалятся.\n\n"
        
        "✦ **Статистика**\n"
        "1. Жми 'Статистика'.\n"
        "2. Смотри общее количество студентов и пройденных уроков.\n"
        "3. Выбери студента, чтобы увидеть его прогресс и результаты тестов.\n\n"
        
        "✦ **Выйти**\n"
        "1. Жми 'Выйти'.\n"
        "2. Ты вернёшься в обычное меню.\n\n"
        
        "Если что-то не работает, пиши @SupportBot. Удачи, админ! 🚀"
    )
    await callback.message.edit_text(
        help_text,
        reply_markup=await create_admin_menu()
    )
    await callback.answer()

# Обработчик для команды /upload_lesson
# Добавляем обработчик для кнопки "Добавить урок"
@router.callback_query(F.data == "upload_lesson")
async def upload_lesson_callback(callback: CallbackQuery, state: FSMContext, db_session):
    logging.info(f"Received callback for 'upload_lesson' button from user {callback.from_user.id}")
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await callback.message.edit_text(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(UploadLessonState.module)
    await callback.message.delete()
    await callback.message.answer(
        "📚 **Добавление урока**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )
    await callback.answer()

# Обработчик выбора модуля
@router.callback_query(UploadLessonState.module, F.data.not_in(["cancel", "exit_admin"]))
async def upload_lesson_module(callback: CallbackQuery, state: FSMContext, db_session):
    logging.info(f"Received callback for UploadLessonState.module: {callback.data}")
    module = callback.data
    module_obj = await get_module_by_code(db_session, module)
    if not module_obj:
        await callback.message.edit_text(
            "⚠️ Модуль не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    key = await get_next_lesson_key(db_session, module)
    await state.update_data(key=key, module_id=module_obj.id)
    await state.set_state(UploadLessonState.text)
    await callback.message.delete()
    await callback.message.answer(
        f"📝 **Новый урок: {key}**\n"
        "Введите текст урока (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

# Обработчик текста урока
@router.message(UploadLessonState.text, F.text)
async def upload_lesson_text(message: Message, state: FSMContext):
    logging.info(f"Received text in UploadLessonState.text: {message.text}")
    text = message.text
    if not is_valid_text(text):
        await message.answer(
            "⚠️ Текст не может быть пустым или длиннее 1000 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(text=text)
    await state.set_state(UploadLessonState.photo)
    await message.answer(
        "🖼 **Фото урока**\n"
        "Отправьте фото (или напишите 'нет', чтобы использовать фото по умолчанию):",
        reply_markup=await create_cancel_kb()
    )

# Обработчик фото урока
@router.message(UploadLessonState.photo, F.photo)
async def upload_lesson_photo(message: Message, state: FSMContext):
    logging.info("Received photo in UploadLessonState.photo")
    try:
        photo_file = await message.bot.download(message.photo[-1])
        photo_path = f"./img/lesson_{int(time.time())}.jpg"
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getvalue())
        await state.update_data(photo=photo_path)
        await state.set_state(UploadLessonState.video_url)
        await message.answer(
            "🎥 **Видеоурок**\n"
            "Введите ссылку на видео (например, https://youtube.com/...):",
            reply_markup=await create_cancel_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "⚠️ Ошибка при сохранении фото.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )

# Обработчик для варианта "нет" при отправке фото
@router.message(UploadLessonState.photo, F.text.lower() == "нет")
async def upload_lesson_no_photo(message: Message, state: FSMContext):
    logging.info("Received 'нет' in UploadLessonState.photo")
    await state.update_data(photo="./img/57fa8b50d6ab7b9f49e84f790d5b4d82.jpg")
    await state.set_state(UploadLessonState.video_url)
    await message.answer(
        "🎥 **Видеоурок**\n"
        "Введите ссылку на видео (например, https://youtube.com/...):",
        reply_markup=await create_cancel_kb()
    )

# Обработчик для некорректного ввода в состоянии photo
@router.message(UploadLessonState.photo)
async def upload_lesson_photo_invalid(message: Message, state: FSMContext):
    logging.warning(f"Invalid message in UploadLessonState.photo: {message.content_type}")
    await message.answer(
        "⚠️ Ожидалось фото или текст 'нет'.\n"
        "Попробуйте снова:",
        reply_markup=await create_cancel_kb()
    )

# Обработчик ссылки на видео
@router.message(UploadLessonState.video_url, F.text)
async def upload_lesson_video_url(message: Message, state: FSMContext):
    logging.info(f"Received video URL in UploadLessonState.video_url: {message.text}")
    url = message.text
    if not is_valid_url(url):
        await message.answer(
            "⚠️ Ссылка должна начинаться с http:// или https://\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(video_url=url)
    await state.set_state(UploadLessonState.notes_url)
    await message.answer(
        "📖 **Конспект**\n"
        "Введите ссылку на конспект (например, https://docs.google.com/...):",
        reply_markup=await create_cancel_kb()
    )

# Обработчик для некорректного ввода в состоянии video_url
@router.message(UploadLessonState.video_url)
async def upload_lesson_video_url_invalid(message: Message, state: FSMContext):
    logging.warning(f"Invalid message in UploadLessonState.video_url: {message.content_type}")
    await message.answer(
        "⚠️ Ожидалась ссылка на видео (например, https://youtube.com/...).\n"
        "Попробуйте снова:",
        reply_markup=await create_cancel_kb()
    )

# Обработчик ссылки на конспект
@router.message(UploadLessonState.notes_url, F.text)
async def upload_lesson_notes_url(message: Message, state: FSMContext, db_session):
    logging.info(f"Received notes URL in UploadLessonState.notes_url: {message.text}")
    url = message.text
    if not is_valid_url(url):
        await message.answer(
            "⚠️ Ссылка должна начинаться с http:// или https://\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    try:
        data = await state.get_data()
        await create_lesson(
            db_session, data["key"], data["module_id"], data["text"],
            data["photo"], data["video_url"], url
        )
        await state.clear()
        await message.answer(
            f"✅ **Урок {data['key']} добавлен!**\n"
            "Вы вернулись в панель администратора:",
            reply_markup=await create_admin_menu()
        )
    except Exception as e:
        logging.error(f"Ошибка при добавлении урока: {e}")
        await message.answer(
            "⚠️ Ошибка при добавлении урока.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
# Обработчик для некорректного ввода в состоянии notes_url
@router.message(UploadLessonState.notes_url)
async def upload_lesson_notes_url_invalid(message: Message, state: FSMContext):
    logging.warning(f"Invalid message in UploadLessonState.notes_url: {message.content_type}")
    await message.answer(
        "⚠️ Ожидалась ссылка на конспект (например, https://docs.google.com/...).\n"
        "Попробуйте снова:",
        reply_markup=await create_cancel_kb()
    )
# Обработчик для команды /update
@router.message(Command("update"))
async def update_start(message: Message, state: FSMContext, db_session):
    if not await is_admin(message.from_user.id):
        await message.answer("🚫 У вас нет доступа к этой команде.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await message.answer(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(UpdateState.module)
    await message.answer(
        "🛠 **Обновление урока**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )

# Добавляем callback для кнопки "Обновить уроки" в меню
@router.callback_query(F.data == "update_content")
async def update_content_callback(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await callback.message.edit_text(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(UpdateState.module)
    await callback.message.delete()
    await callback.message.answer(
        "🛠 **Обновление урока**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )
    await callback.answer()

@router.callback_query(UpdateState.module, F.data.not_in(["cancel", "exit_admin"]))
async def update_module(callback: CallbackQuery, state: FSMContext, db_session):
    module = callback.data
    module_obj = await get_module_by_code(db_session, module)
    if not module_obj:
        await callback.message.edit_text(
            "⚠️ Модуль не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    lessons = await get_lessons_by_module(db_session, module)
    if not lessons:
        await callback.message.edit_text(
            "⚠️ В этом модуле нет уроков. Сначала добавьте урок.",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    await state.update_data(module=module)
    await state.set_state(UpdateState.key)
    await callback.message.delete()
    await callback.message.answer(
        f"📚 **Модуль: {module}**\n"
        "Выберите урок для обновления:",
        reply_markup=await create_lesson_selection_kb(db_session, module)
    )
    await callback.answer()

@router.callback_query(UpdateState.key, F.data.regexp(r"^.+\_lesson-\d+$"))
async def update_key(callback: CallbackQuery, state: FSMContext, db_session):
    key = callback.data
    lesson = await get_lesson_by_code(db_session, key)
    if not lesson:
        await callback.message.edit_text(
            "⚠️ Урок не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
    else:
        await state.update_data(key=key)
        await state.set_state(UpdateState.field)
        await callback.message.delete()
        await callback.message.answer(
            f"📝 **Урок: {key}**\n"
            "Что хотите обновить?",
            reply_markup=await create_field_selection_kb()
        )
    await callback.answer()

@router.callback_query(UpdateState.field, F.data.in_(["text", "photo", "video", "notes"]))
async def update_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data
    await state.update_data(field=field)
    await state.set_state(UpdateState.value)
    if field == "photo":
        await callback.message.delete()
        await callback.message.answer(
            "🖼 **Новое фото**\n"
            "Отправьте фото (или напишите 'нет', чтобы оставить текущее):",
            reply_markup=await create_cancel_kb()
        )
    else:
        field_names = {"text": "Текст", "video": "Видео", "notes": "Конспект"}
        await callback.message.delete()
        await callback.message.answer(
            f"✦ **{field_names[field]}**\n"
            f"Введите новое значение:",
            reply_markup=await create_cancel_kb()
        )
    await callback.answer()

@router.message(UpdateState.value, F.photo)
async def update_photo_value(message: Message, state: FSMContext, db_session):
    data = await state.get_data()
    if data["field"] != "photo":
        await message.answer(
            "⚠️ Ожидалось текстовое сообщение.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    try:
        photo_file = await message.bot.download(message.photo[-1])
        photo_path = f"./img/update_{int(time.time())}.jpg"
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getvalue())
        lesson = await get_lesson_by_code(db_session, data["key"])
        await update_lesson(db_session, lesson, "photo", photo_path)
        await state.set_state(UpdateState.field)
        await message.answer(
            f"✅ **Фото для {data['key']} обновлено!**\n"
            "Что ещё обновить?",
            reply_markup=await create_field_selection_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "⚠️ Ошибка при сохранении фото.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )

@router.message(UpdateState.value, F.text.lower() == "нет")
async def update_no_photo_value(message: Message, state: FSMContext, db_session):
    data = await state.get_data()
    if data["field"] != "photo":
        await message.answer(
            "⚠️ Ожидалось текстовое сообщение для этого поля.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    # Если пользователь написал "нет", оставляем текущее фото
    await state.set_state(UpdateState.field)
    await message.answer(
        f"✅ **Фото для {data['key']} оставлено без изменений!**\n"
        "Что ещё обновить?",
        reply_markup=await create_field_selection_kb()
    )

@router.message(UpdateState.value)
async def update_value(message: Message, state: FSMContext, db_session):
    data = await state.get_data()
    field = data["field"]
    value = message.text
    
    if field in ["video", "notes"] and not is_valid_url(value):
        await message.answer(
            "⚠️ Ссылка должна начинаться с http:// или https://\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    
    if field == "text" and not is_valid_text(value):
        await message.answer(
            "⚠️ Текст не может быть пустым или длиннее 1000 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    
    try:
        lesson = await get_lesson_by_code(db_session, data["key"])
        await update_lesson(db_session, lesson, field, value)
        await state.set_state(UpdateState.field)
        await message.answer(
            f"✅ **{field.capitalize()} для {data['key']} обновлено!**\n"
            "Что ещё обновить?",
            reply_markup=await create_field_selection_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка при обновлении урока: {e}")
        await message.answer(
            "⚠️ Ошибка при обновлении урока.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()

@router.callback_query(F.data == "delete_lesson")
async def delete_lesson_start(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await callback.message.edit_text(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(DeleteLessonState.module)
    await callback.message.delete()
    await callback.message.answer(
        "🗑 **Удаление урока**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )
    await callback.answer()

@router.callback_query(DeleteLessonState.module, F.data.not_in(["cancel", "exit_admin"]))
async def delete_lesson_module(callback: CallbackQuery, state: FSMContext, db_session):
    module = callback.data
    module_obj = await get_module_by_code(db_session, module)
    if not module_obj:
        await callback.message.edit_text(
            "⚠️ Модуль не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    lessons = await get_lessons_by_module(db_session, module)
    if not lessons:
        await callback.message.edit_text(
            "⚠️ В этом модуле нет уроков. Сначала добавьте урок.",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    await state.update_data(module=module)
    await state.set_state(DeleteLessonState.lesson)
    await callback.message.delete()
    await callback.message.answer(
        f"📚 **Модуль: {module}**\n"
        "Выберите урок для удаления:",
        reply_markup=await create_lesson_selection_kb(db_session, module)
    )
    await callback.answer()

@router.callback_query(DeleteLessonState.lesson, F.data.regexp(r"^.+\_lesson-\d+$"))
async def delete_lesson_select(callback: CallbackQuery, state: FSMContext, db_session):
    key = callback.data
    lesson = await get_lesson_by_code(db_session, key)
    if not lesson:
        await callback.message.edit_text(
            "⚠️ Урок не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    await state.update_data(key=key)
    await state.set_state(DeleteLessonState.confirm)
    await callback.message.delete()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_delete")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    await callback.message.answer(
        f"⚠️ **Подтверждение**\n"
        f"Вы уверены, что хотите удалить урок {key}?\n"
        "Это также удалит связанный тест.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(DeleteLessonState.confirm, F.data == "confirm_delete")
async def delete_lesson_confirm(callback: CallbackQuery, state: FSMContext, db_session):
    data = await state.get_data()
    key = data["key"]
    try:
        await delete_lesson(db_session, key)
        await sync_progress_with_content(db_session)
        await state.clear()
        await callback.message.delete()
        await callback.message.answer(
            f"✅ **Урок {key} удалён!**\n"
            "Вы вернулись в панель администратора:",
            reply_markup=await create_admin_menu()
        )
    except Exception as e:
        logging.error(f"Ошибка при удалении урока: {e}")
        await callback.message.edit_text(
            "⚠️ Ошибка при удалении урока.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
    await callback.answer()

@router.callback_query(F.data == "add_test")
async def add_test_start(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await callback.message.edit_text(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(AddTestStates.module)
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Добавление теста**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )
    await callback.answer()

@router.callback_query(AddTestStates.module, F.data.not_in(["cancel", "exit_admin"]))
async def add_test_module(callback: CallbackQuery, state: FSMContext, db_session):
    module = callback.data
    module_obj = await get_module_by_code(db_session, module)
    if not module_obj:
        await callback.message.edit_text(
            "⚠️ Модуль не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    lessons = await get_lessons_by_module(db_session, module)
    if not lessons:
        await callback.message.edit_text(
            "⚠️ В этом модуле нет уроков. Сначала добавьте урок.",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    await state.update_data(module=module)
    await state.set_state(AddTestStates.lesson)
    await callback.message.delete()
    await callback.message.answer(
        f"📚 **Модуль: {module}**\n"
        "Выберите урок для теста:",
        reply_markup=await create_lesson_selection_kb(db_session, module)
    )
    await callback.answer()

@router.callback_query(AddTestStates.lesson, F.data.regexp(r"^.+\_lesson-\d+$"))
async def add_test_lesson(callback: CallbackQuery, state: FSMContext, db_session):
    lesson_key = callback.data
    lesson = await get_lesson_by_code(db_session, lesson_key)
    if not lesson:
        await callback.message.edit_text(
            "⚠️ Урок не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    test_key = lesson_key.replace("lesson", "test")
    await state.update_data(test_key=test_key)
    await state.set_state(AddTestStates.question)
    await callback.message.delete()
    await callback.message.answer(
        f"📝 **Тест для {lesson_key}**\n"
        "Введите текст вопроса (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

@router.message(AddTestStates.question)
async def add_test_question(message: Message, state: FSMContext):
    question_text = message.text
    if not is_valid_text(question_text):
        await message.answer(
            "⚠️ Вопрос не может быть пустым или длиннее 1000 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(question_text=question_text)
    await state.set_state(AddTestStates.options)
    await message.answer(
        "📋 **Варианты ответа**\n"
        "Введите варианты ответа (по одному на строку, минимум 2, до 100 символов каждый):\n"
        "Пример:\n- Вариант 1\n- Вариант 2\n- Вариант 3",
        reply_markup=await create_cancel_kb()
    )

@router.message(AddTestStates.options)
async def add_test_options(message: Message, state: FSMContext):
    options_text = message.text
    if not is_valid_options(options_text):
        await message.answer(
            "⚠️ Нужно минимум 2 варианта, каждый до 100 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(options=options_text)
    await state.set_state(AddTestStates.correct)
    await message.answer(
        "✅ **Правильный ответ**\n"
        "Введите номер правильного ответа (например, 1):",
        reply_markup=await create_cancel_kb()
    )

@router.message(AddTestStates.correct)
async def add_test_correct(message: Message, state: FSMContext):
    data = await state.get_data()
    options = data["options"].split("\n")
    correct = message.text
    if not is_valid_correct(correct, len(options)):
        await message.answer(
            f"⚠️ Номер должен быть от 1 до {len(options)}.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(correct=correct)
    await state.set_state(AddTestStates.photo)
    await message.answer(
        "🖼 **Фото для вопроса**\n"
        "Отправьте фото (или напишите 'нет', чтобы использовать фото по умолчанию):",
        reply_markup=await create_cancel_kb()
    )

@router.message(AddTestStates.photo, F.photo)
async def add_test_photo(message: Message, state: FSMContext, db_session):
    try:
        photo_file = await message.bot.download(message.photo[-1])
        photo_path = f"./img/test_{int(time.time())}.jpg"
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getvalue())
        await state.update_data(photo=photo_path)
        await state.set_state(AddTestStates.preview)
        data = await state.get_data()
        preview_text = await generate_preview_text(message.db_session, data, None)
        await message.answer(
            f"👀 **Предпросмотр вопроса**\n\n{preview_text}",
            reply_markup=await create_preview_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "⚠️ Ошибка при сохранении фото.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )

@router.message(AddTestStates.photo, F.text.lower() == "нет")
async def add_test_no_photo(message: Message, state: FSMContext):
    await state.update_data(photo="./img/57fa8b50d6ab7b9f49e84f790d5b4d82.jpg")
    await state.set_state(AddTestStates.preview)
    data = await state.get_data()
    preview_text = await generate_preview_text(message.db_session, data, None)
    await message.answer(
        f"👀 **Предпросмотр вопроса**\n\n{preview_text}",
        reply_markup=await create_preview_kb()
    )

@router.message(AddTestStates.photo)
async def add_test_photo_invalid(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ Ожидалось фото или текст 'нет'.\n"
        "Попробуйте снова:",
        reply_markup=await create_cancel_kb()
    )

@router.callback_query(AddTestStates.preview, F.data == "confirm")
async def add_test_confirm(callback: CallbackQuery, state: FSMContext, db_session):
    data = await state.get_data()
    options = [opt.strip() for opt in data["options"].split("\n")]
    try:
        await create_test_question(
            db_session, data["test_key"].replace("test", "lesson"),
            data["question_text"], options, int(data["correct"]), data["photo"]
        )
        await state.set_state(AddTestStates.question)
        await callback.message.delete()
        await callback.message.answer(
            "✅ **Вопрос добавлен!**\n"
            "Что дальше?",
            reply_markup=await create_add_question_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка при добавлении вопроса: {e}")
        await callback.message.edit_text(
            "⚠️ Ошибка при добавлении вопроса.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
    await callback.answer()

@router.callback_query(AddTestStates.preview, F.data == "cancel_preview")
async def add_test_cancel_preview(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddTestStates.question)
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Добавление теста**\n"
        "Введите текст нового вопроса (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

@router.callback_query(AddTestStates.question, F.data == "add_another_question")
async def add_another_question(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Добавление нового вопроса**\n"
        "Введите текст вопроса (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "edit_tests")
async def edit_tests_start(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await callback.message.edit_text(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(EditTestStates.module)
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Редактирование тестов**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )
    await callback.answer()

@router.callback_query(EditTestStates.module, F.data.not_in(["cancel", "exit_admin"]))
async def edit_tests_module(callback: CallbackQuery, state: FSMContext, db_session):
    module = callback.data
    module_obj = await get_module_by_code(db_session, module)
    if not module_obj:
        await callback.message.edit_text(
            "⚠️ Модуль не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    lessons = await get_lessons_by_module(db_session, module)
    if not lessons:
        await callback.message.edit_text(
            "⚠️ В этом модуле нет уроков. Сначала добавьте урок.",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    await state.update_data(module=module)
    await state.set_state(EditTestStates.lesson)
    await callback.message.delete()
    await callback.message.answer(
        f"📚 **Модуль: {module}**\n"
        "Выберите урок:",
        reply_markup=await create_lesson_selection_kb(db_session, module)
    )
    await callback.answer()

@router.callback_query(EditTestStates.lesson, F.data.regexp(r"^.+\_lesson-\d+$"))
async def edit_tests_lesson(callback: CallbackQuery, state: FSMContext, db_session):
    lesson_key = callback.data
    lesson = await get_lesson_by_code(db_session, lesson_key)
    if not lesson:
        await callback.message.edit_text(
            "⚠️ Урок не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    test_key = lesson_key.replace("lesson", "test")
    questions = await get_test_questions_by_lesson(db_session, lesson_key)
    if not questions:
        await state.update_data(test_key=test_key, question_idx=0)
        await state.set_state(EditTestStates.add_question)
        await callback.message.delete()
        await callback.message.answer(
            f"📝 **Тест для {lesson_key}**\n"
            "Тест пока пуст. Давайте добавим вопрос.\n"
            "Введите текст вопроса (до 1000 символов):",
            reply_markup=await create_cancel_kb()
        )
    else:
        await state.update_data(test_key=test_key, question_idx=0)
        await state.set_state(EditTestStates.question)
        question_text = await generate_current_question_text(db_session, test_key, 0)
        await callback.message.delete()
        await callback.message.answer(
            f"📝 **Тест для {lesson_key}**\n\n{question_text}\n\nВыберите действие:",
            reply_markup=await create_question_selection_kb(db_session, test_key)
        )
    await callback.answer()

@router.callback_query(EditTestStates.question, F.data.startswith("question_"))
async def edit_tests_select_question(callback: CallbackQuery, state: FSMContext, db_session):
    question_idx = int(callback.data.split("_")[1])
    data = await state.get_data()
    questions = await get_test_questions_by_lesson(db_session, data["test_key"].replace("test", "lesson"))
    if question_idx >= len(questions):
        await callback.message.edit_text(
            "⚠️ Вопрос не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    await state.update_data(question_idx=question_idx)
    question_text = await generate_current_question_text(db_session, data["test_key"], question_idx)
    await callback.message.delete()
    await callback.message.answer(
        f"📝 **Редактирование вопроса**\n\n{question_text}\n\nЧто хотите изменить?",
        reply_markup=await create_test_field_selection_kb()
    )
    await callback.answer()

@router.callback_query(EditTestStates.question, F.data == "add_new_question")
async def edit_tests_add_new_question(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditTestStates.add_question)
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Добавление нового вопроса**\n"
        "Введите текст вопроса (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

@router.message(EditTestStates.add_question)
async def edit_tests_add_question_text(message: Message, state: FSMContext):
    question_text = message.text
    if not is_valid_text(question_text):
        await message.answer(
            "⚠️ Вопрос не может быть пустым или длиннее 1000 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(new_question_text=question_text)
    await state.set_state(EditTestStates.add_question_options)
    await message.answer(
        "📋 **Варианты ответа**\n"
        "Введите варианты ответа (по одному на строку, минимум 2, до 100 символов каждый):\n"
        "Пример:\n- Вариант 1\n- Вариант 2\n- Вариант 3",
        reply_markup=await create_cancel_kb()
    )

@router.message(EditTestStates.add_question_options)
async def edit_tests_add_question_options(message: Message, state: FSMContext):
    options_text = message.text
    if not is_valid_options(options_text):
        await message.answer(
            "⚠️ Нужно минимум 2 варианта, каждый до 100 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(new_options=options_text)
    await state.set_state(EditTestStates.add_question_correct)
    await message.answer(
        "✅ **Правильный ответ**\n"
        "Введите номер правильного ответа (например, 1):",
        reply_markup=await create_cancel_kb()
    )

@router.message(EditTestStates.add_question_correct)
async def edit_tests_add_question_correct(message: Message, state: FSMContext):
    data = await state.get_data()
    options = data["new_options"].split("\n")
    correct = message.text
    if not is_valid_correct(correct, len(options)):
        await message.answer(
            f"⚠️ Номер должен быть от 1 до {len(options)}.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(new_correct=correct)
    await state.set_state(EditTestStates.add_question_photo)
    await message.answer(
        "🖼 **Фото для вопроса**\n"
        "Отправьте фото (или напишите 'нет', чтобы использовать фото по умолчанию):",
        reply_markup=await create_cancel_kb()
    )

@router.message(EditTestStates.add_question_photo, F.photo)
async def edit_tests_add_question_photo(message: Message, state: FSMContext):
    try:
        photo_file = await message.bot.download(message.photo[-1])
        photo_path = f"./img/test_{int(time.time())}.jpg"
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getvalue())
        await state.update_data(new_photo=photo_path)
        await state.set_state(EditTestStates.add_question_preview)
        data = await state.get_data()
        preview_text = await generate_preview_text(message.db_session, data, None)
        await message.answer(
            f"👀 **Предпросмотр вопроса**\n\n{preview_text}",
            reply_markup=await create_preview_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "⚠️ Ошибка при сохранении фото.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )

@router.message(EditTestStates.add_question_photo, F.text.lower() == "нет")
async def edit_tests_add_question_no_photo(message: Message, state: FSMContext):
    await state.update_data(new_photo="./img/57fa8b50d6ab7b9f49e84f790d5b4d82.jpg")
    await state.set_state(EditTestStates.add_question_preview)
    data = await state.get_data()
    preview_text = await generate_preview_text(message.db_session, data, None)
    await message.answer(
        f"👀 **Предпросмотр вопроса**\n\n{preview_text}",
        reply_markup=await create_preview_kb()
    )

@router.message(EditTestStates.add_question_photo)
async def edit_tests_add_question_photo_invalid(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ Ожидалось фото или текст 'нет'.\n"
        "Попробуйте снова:",
        reply_markup=await create_cancel_kb()
    )

@router.callback_query(EditTestStates.add_question_preview, F.data == "confirm")
async def edit_tests_add_question_confirm(callback: CallbackQuery, state: FSMContext, db_session):
    data = await state.get_data()
    options = [opt.strip() for opt in data["new_options"].split("\n")]
    try:
        await create_test_question(
            db_session, data["test_key"].replace("test", "lesson"),
            data["new_question_text"], options, int(data["new_correct"]), data["new_photo"]
        )
        await state.set_state(EditTestStates.question)
        await state.update_data(question_idx=0)
        question_text = await generate_current_question_text(db_session, data["test_key"], 0)
        await callback.message.delete()
        await callback.message.answer(
            f"✅ **Вопрос добавлен!**\n\n{question_text}\n\nВыберите действие:",
            reply_markup=await create_question_selection_kb(db_session, data["test_key"])
        )
    except Exception as e:
        logging.error(f"Ошибка при добавлении вопроса: {e}")
        await callback.message.edit_text(
            "⚠️ Ошибка при добавлении вопроса.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
    await callback.answer()

@router.callback_query(EditTestStates.add_question_preview, F.data == "cancel_preview")
async def edit_tests_add_question_cancel_preview(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditTestStates.add_question)
    await callback.message.delete()
    await callback.message.answer(
        "📝 **Добавление нового вопроса**\n"
        "Введите текст вопроса (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

@router.callback_query(EditTestStates.question, F.data.in_(["question", "options", "correct", "photo", "delete_question"]))
async def edit_tests_select_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data
    await state.update_data(field=field)
    if field == "delete_question":
        await state.set_state(EditTestStates.delete_confirm)
        await callback.message.delete()
        await callback.message.answer(
            "⚠️ **Подтверждение**\n"
            "Вы уверены, что хотите удалить этот вопрос?",
            reply_markup=await create_preview_kb()
        )
    else:
        await state.set_state(EditTestStates.field)
        if field == "photo":
            await callback.message.delete()
            await callback.message.answer(
                "🖼 **Новое фото**\n"
                "Отправьте фото (или напишите 'нет', чтобы оставить текущее):",
                reply_markup=await create_cancel_kb()
            )
        else:
            field_names = {"question": "Вопрос", "options": "Варианты ответа", "correct": "Правильный ответ"}
            await callback.message.delete()
            await callback.message.answer(
                f"✦ **{field_names[field]}**\n"
                f"Введите новое значение:",
                reply_markup=await create_cancel_kb()
            )
    await callback.answer()

@router.callback_query(EditTestStates.delete_confirm, F.data == "confirm")
async def edit_tests_delete_confirm(callback: CallbackQuery, state: FSMContext, db_session):
    data = await state.get_data()
    lesson_key = data["test_key"].replace("test", "lesson")
    questions = await get_test_questions_by_lesson(db_session, lesson_key)
    if data["question_idx"] >= len(questions):
        await callback.message.edit_text(
            "⚠️ Вопрос не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    question = questions[data["question_idx"]]
    try:
        await delete_test_question(db_session, question.id)
        questions = await get_test_questions_by_lesson(db_session, lesson_key)
        if not questions:
            await state.clear()
            await callback.message.delete()
            await callback.message.answer(
                "✅ **Тест удалён!**\n"
                "Вы вернулись в панель администратора:",
                reply_markup=await create_admin_menu()
            )
        else:
            await state.update_data(question_idx=0)
            await state.set_state(EditTestStates.question)
            question_text = await generate_current_question_text(db_session, data["test_key"], 0)
            await callback.message.delete()
            await callback.message.answer(
                f"✅ **Вопрос удалён!**\n\n{question_text}\n\nВыберите действие:",
                reply_markup=await create_question_selection_kb(db_session, data["test_key"])
            )
    except Exception as e:
        logging.error(f"Ошибка при удалении вопроса: {e}")
        await callback.message.edit_text(
            "⚠️ Ошибка при удалении вопроса.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
    await callback.answer()

@router.callback_query(EditTestStates.delete_confirm, F.data == "cancel_preview")
async def edit_tests_delete_cancel(callback: CallbackQuery, state: FSMContext, db_session):
    await state.set_state(EditTestStates.question)
    data = await state.get_data()
    question_text = await generate_current_question_text(db_session, data["test_key"], data["question_idx"])
    await callback.message.delete()
    await callback.message.answer(
        f"📝 **Редактирование вопроса**\n\n{question_text}\n\nЧто хотите изменить?",
        reply_markup=await create_test_field_selection_kb()
    )
    await callback.answer()

@router.message(EditTestStates.field, F.photo)
async def edit_tests_photo(message: Message, state: FSMContext, db_session):
    data = await state.get_data()
    if data["field"] != "photo":
        await message.answer(
            "⚠️ Ожидалось текстовое сообщение.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    try:
        photo_file = await message.bot.download(message.photo[-1])
        photo_path = f"./img/test_{int(time.time())}.jpg"
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getvalue())
        await state.update_data(new_value=photo_path)
        await state.set_state(EditTestStates.preview)
        preview_text = await generate_preview_text(db_session, data, photo_path)
        await message.answer(
            f"👀 **Предпросмотр вопроса**\n\n{preview_text}",
            reply_markup=await create_preview_kb()
        )
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "⚠️ Ошибка при сохранении фото.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )

@router.message(EditTestStates.field, F.text.lower() == "нет")
async def edit_tests_no_photo(message: Message, state: FSMContext, db_session):
    data = await state.get_data()
    if data["field"] != "photo":
        await message.answer(
            "⚠️ Ожидалось текстовое сообщение для этого поля.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    # Оставляем текущее фото
    await state.set_state(EditTestStates.question)
    question_text = await generate_current_question_text(db_session, data["test_key"], data["question_idx"])
    await message.answer(
        f"✅ **Фото оставлено без изменений!**\n\n{question_text}\n\nВыберите действие:",
        reply_markup=await create_question_selection_kb(db_session, data["test_key"])
    )

@router.message(EditTestStates.field)
async def edit_tests_field_value(message: Message, state: FSMContext, db_session):
    data = await state.get_data()
    field = data["field"]
    value = message.text
    
    if field == "question" and not is_valid_text(value):
        await message.answer(
            "⚠️ Вопрос не может быть пустым или длиннее 1000 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    
    if field == "options" and not is_valid_options(value):
        await message.answer(
            "⚠️ Нужно минимум 2 варианта, каждый до 100 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    
    if field == "correct":
        options = (await get_test_questions_by_lesson(db_session, data["test_key"].replace("test", "lesson")))[data["question_idx"]]
        options_count = 2 if not options.option_3 else 3
        if not is_valid_correct(value, options_count):
            await message.answer(
                f"⚠️ Номер должен быть от 1 до {options_count}.\n"
                "Попробуйте снова:",
                reply_markup=await create_cancel_kb()
            )
            return
    
    await state.update_data(new_value=value)
    await state.set_state(EditTestStates.preview)
    preview_text = await generate_preview_text(db_session, data, value)
    await message.answer(
        f"👀 **Предпросмотр вопроса**\n\n{preview_text}",
        reply_markup=await create_preview_kb()
    )

@router.callback_query(EditTestStates.preview, F.data == "confirm")
async def edit_tests_confirm(callback: CallbackQuery, state: FSMContext, db_session):
    data = await state.get_data()
    lesson_key = data["test_key"].replace("test", "lesson")
    questions = await get_test_questions_by_lesson(db_session, lesson_key)
    if data["question_idx"] >= len(questions):
        await callback.message.edit_text(
            "⚠️ Вопрос не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
        return
    question = questions[data["question_idx"]]
    try:
        await update_test_question(db_session, question, data["field"], data["new_value"])
        await state.set_state(EditTestStates.question)
        question_text = await generate_current_question_text(db_session, data["test_key"], data["question_idx"])
        await callback.message.delete()
        await callback.message.answer(
            f"✅ **Вопрос обновлён!**\n\n{question_text}\n\nВыберите действие:",
            reply_markup=await create_question_selection_kb(db_session, data["test_key"])
        )
    except Exception as e:
        logging.error(f"Ошибка при обновлении вопроса: {e}")
        await callback.message.edit_text(
            "⚠️ Ошибка при обновлении вопроса.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
    await callback.answer()

@router.callback_query(EditTestStates.preview, F.data == "cancel_preview")
async def edit_tests_cancel_preview(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EditTestStates.field)
    data = await state.get_data()
    field = data["field"]
    if field == "photo":
        await callback.message.delete()
        await callback.message.answer(
            "🖼 **Новое фото**\n"
            "Отправьте фото (или напишите 'нет', чтобы оставить текущее):",
            reply_markup=await create_cancel_kb()
        )
    else:
        field_names = {"question": "Вопрос", "options": "Варианты ответа", "correct": "Правильный ответ"}
        await callback.message.delete()
        await callback.message.answer(
            f"✦ **{field_names[field]}**\n"
            f"Введите новое значение:",
            reply_markup=await create_cancel_kb()
        )
    await callback.answer()

@router.callback_query(F.data == "add_module")
async def add_module_start(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    await state.set_state(AddModuleState.name)
    await callback.message.delete()
    await callback.message.answer(
        "📚 **Добавление модуля**\n"
        "Введите название модуля (например, 'fourth', только латиница, до 20 символов):",
        reply_markup=await create_cancel_kb()
    )
    await callback.answer()

@router.message(AddModuleState.name)
async def add_module_name(message: Message, state: FSMContext, db_session):
    name = message.text.lower()
    if not re.match(r"^[a-zA-Z0-9_]{1,20}$", name):
        await message.answer(
            "⚠️ Название должно быть до 20 символов и содержать только латиницу и цифры.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    if await get_module_by_code(db_session, name):
        await message.answer(
            "⚠️ Модуль с таким названием уже существует.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(name=name)
    await state.set_state(AddModuleState.text)
    await message.answer(
        "📝 **Описание модуля**\n"
        "Введите текст описания (до 1000 символов):",
        reply_markup=await create_cancel_kb()
    )

@router.message(AddModuleState.text)
async def add_module_text(message: Message, state: FSMContext):
    text = message.text
    if not is_valid_text(text):
        await message.answer(
            "⚠️ Текст не может быть пустым или длиннее 1000 символов.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        return
    await state.update_data(text=text)
    await state.set_state(AddModuleState.photo)
    await message.answer(
        "🖼 **Фото модуля**\n"
        "Отправьте фото:",
        reply_markup=await create_cancel_kb()
    )

@router.message(AddModuleState.photo, F.photo)
async def add_module_photo(message: Message, state: FSMContext, db_session):
    try:
        photo_file = await message.bot.download(message.photo[-1])
        photo_path = f"./img/module_{int(time.time())}.jpg"
        os.makedirs(os.path.dirname(photo_path), exist_ok=True)
        with open(photo_path, "wb") as f:
            f.write(photo_file.getvalue())
        data = await state.get_data()
        await create_module(db_session, data["name"], data["text"], photo_path)
        await state.clear()
        await message.answer(
            f"✅ **Модуль {data['name']} добавлен!**\n"
            "Вы вернулись в панель администратора:",
            reply_markup=await create_admin_menu()
        )
    except Exception as e:
        logging.error(f"Ошибка сохранения фото: {e}")
        await message.answer(
            "⚠️ Ошибка при сохранении фото.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )

@router.message(AddModuleState.photo)
async def add_module_photo_invalid(message: Message, state: FSMContext):
    await message.answer(
        "⚠️ Ожидалось фото.\n"
        "Попробуйте снова:",
        reply_markup=await create_cancel_kb()
    )

@router.callback_query(F.data == "delete_module")
async def delete_module_start(callback: CallbackQuery, state: FSMContext, db_session):
    if not await is_admin(callback.from_user.id, db_session):
        await callback.message.edit_text("🚫 У вас нет доступа.")
        return
    modules = await get_all_modules(db_session)
    if not modules:
        await callback.message.edit_text(
            "⚠️ Нет доступных модулей. Сначала добавьте модуль с помощью команды 'Добавить модуль'.",
            reply_markup=await create_admin_menu()
        )
        return
    await state.set_state(DeleteModuleState.module)
    await callback.message.delete()
    await callback.message.answer(
        "🗑 **Удаление модуля**\n"
        "Выберите модуль:",
        reply_markup=await create_module_selection_kb_dynamic(db_session)
    )
    await callback.answer()

@router.callback_query(DeleteModuleState.module, F.data.not_in(["cancel", "exit_admin"]))
async def delete_module_select(callback: CallbackQuery, state: FSMContext, db_session):
    module = callback.data
    module_obj = await get_module_by_code(db_session, module)
    if not module_obj:
        await callback.message.edit_text(
            "⚠️ Модуль не найден.\n"
            "Попробуйте снова:",
            reply_markup=await create_cancel_kb()
        )
        await state.clear()
        return
    await state.update_data(module=module)
    await state.set_state(DeleteModuleState.confirm)
    await callback.message.delete()
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="confirm_delete_module")
    builder.button(text="❌ Отмена", callback_data="cancel")
    builder.adjust(2)
    await callback.message.answer(
        f"⚠️ **Подтверждение**\n"
        f"Вы уверены, что хотите удалить модуль {module}?\n"
        "Это также удалит все уроки и тесты модуля.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(DeleteModuleState.confirm, F.data == "confirm_delete_module")
async def delete_module_confirm(callback: CallbackQuery, state: FSMContext, db_session):
    data = await state.get_data()
    module = data["module"]
    try:
        await delete_module(db_session, module)
        await sync_progress_with_content(db_session)
        await state.clear()
        await callback.message.delete()
        await callback.message.answer(
            f"✅ **Модуль {module} удалён!**\n"
            "Вы вернулись в панель администратора:",
            reply_markup=await create_admin_menu()
        )
    except Exception as e:
        logging.error(f"Ошибка при удалении модуля: {e}")
        await callback.message.edit_text(
            "⚠️ Ошибка при удалении модуля.\n"
            "Попробуйте снова:",
            reply_markup=await create_admin_menu()
        )
        await state.clear()
    await callback.answer()

@router.callback_query(DeleteModuleState.confirm, F.data == "cancel")
async def delete_module_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "✅ **Действие отменено**\n"
        "Вы вернулись в панель администратора:",
        reply_markup=await create_admin_menu()
    )
    await callback.answer()



# Обработчик команды /admin_register
@router.message(Command("admin_register"))
async def admin_register_start(message: Message, state: FSMContext, db_session):
    user_id = message.from_user.id
    logging.info(f"Starting admin registration for user_id: {user_id}")

    # Проверяем, существует ли пользователь
    user = await get_user_by_id(db_session, user_id)
    if not user:
        logging.info("User not found, creating new user with default values")
        user = await create_user(
            db_session, user_id, "", "", message.from_user.username or ""
        )

    # Проверяем, является ли пользователь уже админом
    if user.is_admin:
        await message.answer("ℹ️ Ты уже администратор!")
        return

    # Запускаем процесс регистрации админа
    await state.set_state(AdminRegistrationState.code)
    await message.answer(
        "🔒 **Регистрация администратора**\n"
        "Пожалуйста, введи секретный код:",
        reply_markup=await create_cancel_kb()  # Добавляем клавиатуру с кнопкой "Отмена"
    )

# Обработчик ввода кода
@router.message(AdminRegistrationState.code, F.text)
async def admin_register_code(message: Message, state: FSMContext, db_session):
    code = message.text.strip()
    user_id = message.from_user.id
    logging.info(f"Received admin registration code from user_id {user_id}: {code}")

    if code != ADMIN_SECRET_CODE:
        await message.answer(
            "⚠️ Неверный код. Попробуй снова:",
            reply_markup=await create_cancel_kb()  # Добавляем клавиатуру при неверном коде
        )
        return

    # Код верный, обновляем статус is_admin
    try:
        user = await get_user_by_id(db_session, user_id)
        if user:
            user.is_admin = True
            await db_session.commit()
            await state.clear()
            await message.answer(
                "✅ **Ты теперь администратор!**\n"
                "Используй команду /admin для доступа к панели администратора."
            )
        else:
            raise ValueError("User not found during admin registration")
    except Exception as e:
        logging.error(f"Error during admin registration for user_id {user_id}: {e}")
        await message.answer("⚠️ Ошибка при регистрации админа. Попробуй позже!")
        await state.clear()

# Обработчик для некорректного ввода кода
@router.message(AdminRegistrationState.code)
async def admin_register_code_invalid(message: Message):
    logging.warning(f"Invalid input for admin registration code: {message.content_type}")
    await message.answer(
        "⚠️ Ожидался текст с секретным кодом.\n"
        "Попробуй снова:",
        reply_markup=await create_cancel_kb()  # Добавляем клавиатуру при некорректном вводе
    )

# Обработчик кнопки "Отмена"
@router.callback_query(AdminRegistrationState.code, F.data == "cancel")
async def cancel_admin_registration(callback: CallbackQuery, state: FSMContext):
    logging.info(f"User {callback.from_user.id} canceled admin registration")
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "✅ **Регистрация администратора отменена**"
    )
    await callback.answer()