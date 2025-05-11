from ast import parse
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
# from networkx import parse_adjlist
from app.database.models import Lesson
from app.user.states import RegistrationState, TestState
from app.user.keyboards import create_main_menu_dynamic, create_module_kb, create_lesson_kb, create_test_kb, create_retry_test_kb, create_update_confirmation_kb
from app.database.requests import get_all_modules, get_module_by_code, get_lesson_by_code, get_test_questions_by_lesson, get_user_by_id, create_user, get_user_progress, get_user_test_scores, mark_lesson_completed, save_test_score, sync_progress_with_content, update_user
import os
import logging
from sqlalchemy import select

router = Router()

def create_progress_bar(current, total):
    bar_length = 10
    filled = int(bar_length * current / total)
    empty = bar_length - filled
    return f"[{('🟩' * filled) + ('⬜' * empty)}] {current}/{total}"

@router.message(Command("start"))
async def start_handler(message: Message, db_session):
    try:
        user_id = message.from_user.id
        logging.info(f"Handling /start for user_id: {user_id}")

        # Проверка регистрации
        user = await get_user_by_id(db_session, user_id)
        if not user:
            logging.info(f"User {user_id} not found, prompting to register")
            await message.answer(
                "👋 Добро пожаловать в обучающий бот по основам инфографики и не только!\n\n"
                "📝 Чтобы начать обучение, необходимо пройти регистрацию — /register\n"
                "📚 После регистрации вам откроются обучающие модули — /modules\n"
                "ℹ️ Чтобы узнать о всех возможностях, используйте /help или меню внизу 💬\n\n"
                "🚀 Удачи в обучении!"
            )
            return

        # Если зарегистрирован
        welcome_text = (
            "👋 *С возвращением!*\n\n"
            "📚 Вам доступны обучающие модули — /modules\n"
            "ℹ️ Посмотрите команды бота через /help или через главное меню 💬\n\n"
            "Желаю продуктивного обучения! 🚀"
        )
        keyboard = await create_main_menu_dynamic(db_session)
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Ошибка в /start: {e}")
        await message.answer("⚠️ Произошла ошибка при запуске. Попробуй ещё раз позже.")

@router.message(Command("account"))
async def account_handler(message: Message, db_session):
    try:
        user_id = message.from_user.id
        logging.info(f"Handling /account for user_id: {user_id}")

        # Шаг 1: Получение пользователя
        logging.info("Step 1: Fetching user from database")
        user = await get_user_by_id(db_session, user_id)
        if not user:
            logging.info(f"User {user_id} not found, prompting to register")
            await message.answer(
                "👋 Привет! Чтобы посмотреть профиль, тебе нужно зарегистрироваться.\n"
                "Используй команду /register, чтобы указать своё имя и фамилию.",
                parse_mode="Markdown"
            )
            return

        # Шаг 2: Синхронизация прогресса
        logging.info("Step 2: Syncing progress with content")
        await sync_progress_with_content(db_session)

        # Шаг 3: Получение прогресса пользователя
        logging.info("Step 3: Fetching user progress")
        progress = await get_user_progress(db_session, user_id)
        completed_lessons = {p.lesson_code for p in progress}
        completed_count = len(completed_lessons)

        # Шаг 4: Получение всех уроков
        logging.info("Step 4: Fetching all lessons")
        lessons = (await db_session.execute(select(Lesson))).scalars().all()
        total_lessons = len(lessons)

        # Шаг 5: Получение результатов тестов
        logging.info("Step 5: Fetching user test scores")
        test_scores = await get_user_test_scores(db_session, user_id)
        score_text = "\n".join([f"➤ {ts.test_code}: {ts.score}/{ts.total}" for ts in test_scores]) or "— Тесты ещё не пройдены"

        # Шаг 6: Формирование прогресс-бара
        logging.info("Step 6: Creating progress bar")
        if total_lessons == 0:
            progress_bar = "Пока нет доступных уроков."
        else:
            progress_bar = create_progress_bar(completed_count, total_lessons)

        # Шаг 7: Формирование имени для отображения
        logging.info("Step 7: Preparing user display name")
        display_name = f"{user.first_name} {user.last_name}".strip()
        if not display_name:
            display_name = "Не указано (используй /register)"

        # Шаг 8: Отправка ответа
        logging.info("Step 8: Sending response to user")
        await message.answer(
            "📊 *Ваш профиль*\n"
            f"Имя: {display_name}\n"
            f"ID: `{user_id}`\n\n"
            "✦ **Прогресс обучения**\n"
            f"Пройдено уроков: {completed_count}/{total_lessons}\n"
            f"{progress_bar}\n\n"
            "✦ **Результаты тестов**\n"
            f"{score_text}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logging.error(f"Error in /account at user_id {user_id}: {str(e)}", exc_info=True)
        await message.answer("⚠️ Ошибка при загрузке профиля. Попробуй позже!")

        
@router.message(Command("about"))
async def about_handler(message: Message):
    await message.answer(
        "ℹ️ **О нас**\n"
        "Мы — команда, создающая удобные инструменты для обучения.\n"
        "Наша цель — сделать процесс изучения интересным и эффективным!\n\n"
        "✉️ Связь: @SupportBot",
        parse_mode="Markdown"
    )

@router.message(Command("contacts"))
async def contacts_handler(message: Message):
    await message.answer(
        "📞 **Контакты**\n"
        "✦ Поддержка: @SupportBot\n"
        "✦ Email: support@learningbot.com\n"
        "✦ Telegram-канал: @LearningHub",
        parse_mode="Mardown"
    )

@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "ℹ️ **Помощь**\n"
        "Вот что я умею:\n"
        "✦ /start — начать обучение и выбрать модуль\n"
        "✦ /account — посмотреть свой прогресс\n"
        "✦ /about — узнать о нас\n"
        "✦ /contacts — контакты для связи\n\n"
        "Выбери модуль в главном меню и проходи уроки с тестами. Удачи в обучении! 🚀\n"
        "Если что-то не работает, пиши @SupportBot.",
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("show_module_"))
async def show_module(callback: CallbackQuery, db_session):
    try:
        module_name = callback.data.split("_")[2]
        module = await get_module_by_code(db_session, module_name)
        if not module:
            await callback.message.edit_text("⚠️ Модуль не найден.")
            return
        photo = FSInputFile(os.path.join(os.getcwd(), module.photo))
        await callback.message.delete()
        await callback.message.answer_photo(
            photo,
            caption=(
                f"📘 *{module_name.capitalize()} модуль*\n"
                f"{module.text}\n\n"
                "Выбери урок:"
                
            ),
            parse_mode="Markdown",
            reply_markup=await create_module_kb(db_session, module_name)
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка в show_module: {e}")
        await callback.message.answer("⚠️ Ошибка загрузки модуля!")

@router.callback_query(F.data.regexp(r"^.+\_lesson-\d+$"))
async def process_lesson(callback: CallbackQuery, state: FSMContext, db_session):
    try:
        lesson_key = callback.data
        module_prefix = lesson_key.split("_")[0]
        lesson_num = int(lesson_key.split("-")[1])
        
        lesson = await get_lesson_by_code(db_session, lesson_key)
        if not lesson:
            await callback.message.edit_text("⚠️ Урок не найден.")
            return
        
        photo = FSInputFile(os.path.join(os.getcwd(), lesson.photo))
        await callback.message.delete()
        await callback.message.answer_photo(
            photo,
            caption=(
                f"📚 *Урок {lesson_num}*\n"
                f"{lesson.text}\n\n"
                "Выберите действие:"
            ),
            parse_mode="Markdown",
            reply_markup=await create_lesson_kb(lesson.video_link, lesson.notes_link, module_prefix, lesson_num)
        )
        await state.clear()
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка в process_lesson: {e}")
        await callback.message.answer(f"⚠️ Ошибка загрузки урока: {str(e)}")

@router.callback_query(F.data.startswith("module_menu_"))
async def back_to_module_menu(callback: CallbackQuery, state: FSMContext, db_session):
    try:
        module_prefix = callback.data.split("_")[2]
        module = await get_module_by_code(db_session, module_prefix)
        if not module:
            await callback.message.edit_text("⚠️ Модуль не найден.")
            return
        
        photo = FSInputFile(os.path.join(os.getcwd(), module.photo))
        await callback.message.delete()
        await callback.message.answer_photo(
            photo,
            caption=(
                f"📘 **{module_prefix.capitalize()} модуль**\n"
                f"{module.text}\n\n"
                "Выбери урок:",
                
            ),
            
            reply_markup=await create_module_kb(db_session, module_prefix)
        )
        await state.clear()
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка в back_to_module_menu: {e}")
        await callback.message.answer("⚠️ Ошибка возврата к модулю!")

@router.callback_query(F.data.regexp(r"^.+\_test-\d+$"))
async def start_test(callback: CallbackQuery, state: FSMContext, db_session):
    try:
        test_key = callback.data
        module_prefix = test_key.split("_")[0]
        lesson_num = int(test_key.split("-")[1])
        lesson_key = f"{module_prefix}_lesson-{lesson_num}"
        
        questions = await get_test_questions_by_lesson(db_session, lesson_key)
        if not questions:
            await callback.message.edit_text("⚠️ Для этого урока нет теста.")
            return
        await state.set_state(TestState.testing)
        await state.update_data(
            module_prefix=module_prefix,
            lesson_num=lesson_num,
            test_key=test_key,
            question_idx=0,
            correct_answers=0
        )
        question_data = questions[0]
        photo = FSInputFile(os.path.join(os.getcwd(), question_data.photo))
        progress_bar = create_progress_bar(1, len(questions))
        await callback.message.delete()
        await callback.message.answer_photo(
            photo,
            caption=(
                f"📝 *Тест к уроку {lesson_num}*\n"
                f"{question_data.question_text}\n\n"
                f"📊 Прогресс: {progress_bar}"
            ),
            parse_mode="Markdown",
            reply_markup=await create_test_kb(db_session, module_prefix, lesson_num, 0)
        )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка в start_test: {e}")
        await callback.message.answer("⚠️ Ошибка запуска теста!")

@router.callback_query(TestState.testing, F.data.contains("_answer-"))
async def process_test_answer(callback: CallbackQuery, state: FSMContext, db_session):
    try:
        data = await state.get_data()
        module_prefix = data["module_prefix"]
        lesson_num = data["lesson_num"]
        test_key = data["test_key"]
        question_idx = data["question_idx"]
        correct_answers = data["correct_answers"]
        
        answer_num = int(callback.data.split("-")[-1])
        questions = await get_test_questions_by_lesson(db_session, f"{module_prefix}_lesson-{lesson_num}")
        question_data = questions[question_idx]
        
        response = "✅ Правильно!" if answer_num == question_data.correct_option else "❌ Неправильно"
        correct_answers += 1 if answer_num == question_data.correct_option else 0
        
        question_idx += 1
        await callback.message.delete()
        if question_idx < len(questions):
            next_question = questions[question_idx]
            photo = FSInputFile(os.path.join(os.getcwd(), next_question.photo))
            progress_bar = create_progress_bar(question_idx + 1, len(questions))
            await state.update_data(question_idx=question_idx, correct_answers=correct_answers)
            await callback.message.answer_photo(
                photo,
                caption=(
                    f"{response}\n\n"
                    f"📝 **Вопрос {question_idx + 1}**\n"
                    f"{next_question.question_text}\n\n"
                    f"📊 Прогресс: {progress_bar}"
                ),
                parse_mode="Markdown",
                reply_markup=await create_test_kb(db_session, module_prefix, lesson_num, question_idx)
            )
        else:
            lesson_key = f"{module_prefix}_lesson-{lesson_num}"
            lesson = await get_lesson_by_code(db_session, lesson_key)
            photo = FSInputFile(os.path.join(os.getcwd(), lesson.photo))
            user_id = callback.from_user.id
            
            await sync_progress_with_content(db_session)
            user = await get_user_by_id(db_session, user_id)
            if not user:
                user = await create_user(
                    db_session, user_id, callback.from_user.first_name,
                    callback.from_user.last_name or "", callback.from_user.username or ""
                )

            await save_test_score(db_session, user_id, test_key, correct_answers, len(questions))
            
            if correct_answers == len(questions):
                progress = await get_user_progress(db_session, user_id)
                if lesson_key not in {p.lesson_code for p in progress}:
                    await mark_lesson_completed(db_session, user_id, lesson_key)
                caption = (
                    f"{response}\n\n"
                    f"🎉 **Тест успешно завершён!**\n"
                    f"Результат: {correct_answers}/{len(questions)}\n"
                    f"Урок {lesson_num} пройден!"
                )
                
                reply_markup = await create_lesson_kb(lesson.video_link, lesson.notes_link, module_prefix, lesson_num,parse_mode="Markdown")
            else:
                caption = (
                    f"{response}\n\n"
                    f"📝 **Тест завершён**\n"
                    f"Результат: {correct_answers}/{len(questions)}\n"
                    "Для прохождения урока нужно ответить правильно на все вопросы.\n"
                    "Попробуйте ещё раз:",
                    
                )
                
                reply_markup = await create_retry_test_kb(module_prefix, lesson_num,parse_mode="Markdown")
            
            await state.clear()
            await callback.message.answer_photo(
                photo,
                caption=caption,
                reply_markup=reply_markup
            )
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка в process_test_answer: {e}")
        await callback.message.answer("⚠️ Ошибка обработки ответа!")

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext, db_session):
    try:
        await state.clear()
        modules = await get_all_modules(db_session)
        welcome_text = "👋 Добро пожаловать!\nВыбери модуль, чтобы начать:\n"
        for module in modules:
            welcome_text += f"— {module.code.capitalize()} модуль\n"
        keyboard = await create_main_menu_dynamic(db_session)
        await callback.message.delete()
        await callback.message.answer(welcome_text, reply_markup=keyboard)
        await callback.answer()
    except Exception as e:
        logging.error(f"Ошибка в back_to_main: {e}")
        await callback.message.answer("⚠️ Ошибка возврата в меню!")

# @router.message()
# async def unknown_command(message: Message):
#     await message.answer(
#         "❓ **Неизвестная команда**\n"
#         "Используй /help, чтобы узнать, что я умею!"
#     )



# Функция для валидации имени и фамилии
def is_valid_name(name: str) -> bool:
    return bool(name and 1 <= len(name.strip()) <= 50 and name.isalpha())

# Обработчик команды /register
@router.message(Command("register"))
async def register_start(message: Message, state: FSMContext, db_session):
    user_id = message.from_user.id
    logging.info(f"Starting registration for user_id: {user_id}")

    # Проверяем, существует ли пользователь
    user = await get_user_by_id(db_session, user_id)
    if not user:
        logging.info("User not found, creating new user with default values")
        user = await create_user(
            db_session, user_id, "", "", message.from_user.username or ""
        )

    # Проверяем, есть ли уже данные (имя и фамилия)
    display_name = f"{user.first_name} {user.last_name}".strip()
    if display_name:  # Если пользователь уже зарегистрирован
        logging.info(f"User {user_id} already registered with name: {display_name}")
        await message.answer(
            "📝 *Ты уже зарегистрирован*\n"
            f"Твои данные:\n"
            f"*Имя:* {user.first_name}\n"
            f"*Фамилия:* {user.last_name}\n\n"
            "Хочешь обновить свои данные?",
            parse_mode="Markdown",
            reply_markup=await create_update_confirmation_kb()
        )
        return

    # Если данных нет, запускаем процесс регистрации
    await state.set_state(RegistrationState.first_name)
    await message.answer(
        "📝 **Регистрация**\n"
        "Пожалуйста, введи своё имя (только буквы, до 50 символов):",
        parse_mode="Markdown"
    )

# Обработчик кнопки "Обновить"
@router.callback_query(F.data == "update_profile")
async def confirm_update_profile(callback: CallbackQuery, state: FSMContext):
    logging.info(f"User {callback.from_user.id} chose to update profile")
    await state.set_state(RegistrationState.first_name)
    await callback.message.delete()
    await callback.message.answer(
        "📝 *Обновление данных*\n"
        "Пожалуйста, введи своё новое имя (только буквы, до 50 символов):",
        parse_mode="Markdown"
    )
    await callback.answer()

# Обработчик кнопки "Отмена"
@router.callback_query(F.data == "cancel_update")
async def cancel_update_profile(callback: CallbackQuery, state: FSMContext):
    logging.info(f"User {callback.from_user.id} canceled profile update")
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "✅ **Обновление отменено**\n"
        "Ты можешь посмотреть свой профиль с помощью /account.",
        parse_mode="Markdown"
    )
    await callback.answer()

# Обработчик ввода имени
@router.message(RegistrationState.first_name, F.text)
async def register_first_name(message: Message, state: FSMContext):
    first_name = message.text.strip()
    logging.info(f"Received first_name: {first_name}")

    if not is_valid_name(first_name):
        await message.answer(
            "⚠️ Имя должно содержать только буквы и быть длиной от 1 до 50 символов.\n"
            "Попробуй снова:",
            parse_mode="Markdown"
        )
        
        return

    await state.update_data(first_name=first_name)
    await state.set_state(RegistrationState.last_name)
    await message.answer(
        "📝 **Регистрация**\n"
        "Теперь введи свою фамилию (только буквы, до 50 символов):",
        parse_mode="Markdown"
    )

# Обработчик для некорректного ввода имени
@router.message(RegistrationState.first_name)
async def register_first_name_invalid(message: Message):
    logging.warning(f"Invalid input for first_name: {message.content_type}")
    await message.answer(
        "⚠️ Ожидался текст для имени (только буквы, до 50 символов).\n"
        "Попробуй снова:",
        parse_mode="Markdown"
    )

# Обработчик ввода фамилии
@router.message(RegistrationState.last_name, F.text)
async def register_last_name(message: Message, state: FSMContext, db_session):
    last_name = message.text.strip()
    logging.info(f"Received last_name: {last_name}")

    if not is_valid_name(last_name):
        await message.answer(
            "⚠️ Фамилия должна содержать только буквы и быть длиной от 1 до 50 символов.\n"
            "Попробуй снова:",
            parse_mode="Markdown"
        )
        return

    # Получаем данные из состояния
    data = await state.get_data()
    first_name = data["first_name"]

    # Обновляем данные пользователя в базе
    user_id = message.from_user.id
    try:
        user = await get_user_by_id(db_session, user_id)
        if user:
            await update_user(db_session, user, first_name, last_name)
            await state.clear()
            await message.answer(
                "✅ *Данные обновлены!*\n"
                f"Имя: {first_name}\n"
                f"Фамилия: {last_name}\n\n"
                "Ты можешь посмотреть свой профиль с помощью команды /account.",
                parse_mode='Markdown'
            )
        else:
            raise ValueError("User not found after registration start")
    except Exception as e:
        logging.error(f"Error during registration for user_id {user_id}: {e}")
        await message.answer("⚠️ Ошибка при регистрации. Попробуй позже!")
        await state.clear()

# Обработчик для некорректного ввода фамилии
@router.message(RegistrationState.last_name)
async def register_last_name_invalid(message: Message):
    logging.warning(f"Invalid input for last_name: {message.content_type}")
    await message.answer(
        "⚠️ Ожидался текст для фамилии (только буквы, до 50 символов).\n"
        "Попробуй снова:"
    )