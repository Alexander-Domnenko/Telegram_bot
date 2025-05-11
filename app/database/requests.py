import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.database.models import User, Module, Lesson, TestQuestion, UserProgress, UserTestScore
from typing import Dict, List, Optional

async def get_all_modules(session: AsyncSession) -> List[Module]:
    result = await session.execute(select(Module))
    return result.scalars().all()

async def get_module_by_code(session: AsyncSession, code: str) -> Optional[Module]:
    result = await session.execute(select(Module).where(Module.code == code))
    return result.scalars().first()

async def create_module(session: AsyncSession, code: str, text: str, photo: str) -> Module:
    module = Module(code=code, text=text, photo=photo)
    session.add(module)
    await session.commit()
    return module

async def delete_module(session: AsyncSession, code: str):
    await session.execute(delete(Module).where(Module.code == code))
    await session.commit()

async def get_lessons_by_module(session: AsyncSession, module_code: str) -> List[Lesson]:
    result = await session.execute(
        select(Lesson).join(Module).where(Module.code == module_code)
    )
    return result.scalars().all()

async def get_lesson_by_code(session: AsyncSession, code: str) -> Optional[Lesson]:
    result = await session.execute(select(Lesson).where(Lesson.code == code))
    return result.scalars().first()

async def create_lesson(session: AsyncSession, code: str, module_id: int, text: str, photo: str, video_link: str, notes_link: str) -> Lesson:
    lesson = Lesson(
        code=code, module_id=module_id, text=text, photo=photo,
        video_link=video_link, notes_link=notes_link
    )
    session.add(lesson)
    await session.commit()
    return lesson

async def update_lesson(session: AsyncSession, lesson: Lesson, field: str, value: str):
    if field == "text":
        lesson.text = value
    elif field == "photo":
        lesson.photo = value
    elif field == "video":
        lesson.video_link = value
    elif field == "notes":
        lesson.notes_link = value
    await session.commit()

async def delete_lesson(session: AsyncSession, code: str):
    await session.execute(delete(Lesson).where(Lesson.code == code))
    await session.commit()

async def get_test_questions_by_lesson(session: AsyncSession, lesson_code: str) -> List[TestQuestion]:
    result = await session.execute(
        select(TestQuestion).where(TestQuestion.lesson_code == lesson_code)
    )
    return result.scalars().all()

async def create_test_question(session: AsyncSession, lesson_code: str, question_text: str, options: List[str], correct_option: int, photo: str) -> TestQuestion:
    question = TestQuestion(
        lesson_code=lesson_code, question_text=question_text,
        option_1=options[0], option_2=options[1],
        option_3=options[2] if len(options) > 2 else None,
        correct_option=correct_option, photo=photo
    )
    session.add(question)
    await session.commit()
    return question

async def update_test_question(session: AsyncSession, question: TestQuestion, field: str, value):
    if field == "question":
        question.question_text = value
    elif field == "options":
        options = [opt.strip() for opt in value.split("\n")]
        question.option_1 = options[0]
        question.option_2 = options[1]
        question.option_3 = options[2] if len(options) > 2 else None
    elif field == "correct":
        question.correct_option = int(value)
    elif field == "photo":
        question.photo = value
    await session.commit()

async def delete_test_question(session: AsyncSession, question_id: int):
    await session.execute(delete(TestQuestion).where(TestQuestion.id == question_id))
    await session.commit()

async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalars().first()

async def create_user(session: AsyncSession, user_id: int, first_name: str, last_name: str, username: str, is_admin: bool = False) -> User:
    user = User(
        id=user_id, first_name=first_name, last_name=last_name,
        username=username, is_admin=is_admin
    )
    session.add(user)
    await session.commit()
    return user

async def get_all_users(session: AsyncSession) -> List[User]:
    result = await session.execute(select(User))
    return result.scalars().all()

async def get_user_progress(session: AsyncSession, user_id: int) -> List[UserProgress]:
    result = await session.execute(
        select(UserProgress).where(UserProgress.user_id == user_id)
    )
    return result.scalars().all()

async def mark_lesson_completed(session: AsyncSession, user_id: int, lesson_code: str):
    progress = UserProgress(user_id=user_id, lesson_code=lesson_code, completed=True)
    session.add(progress)
    await session.commit()

async def get_user_test_scores(session: AsyncSession, user_id: int) -> List[UserTestScore]:
    result = await session.execute(
        select(UserTestScore).where(UserTestScore.user_id == user_id)
    )
    return result.scalars().all()

async def save_test_score(session: AsyncSession, user_id: int, test_code: str, score: int, total: int):
    test_score = UserTestScore(user_id=user_id, test_code=test_code, score=score, total=total)
    session.add(test_score)
    await session.commit()

async def sync_progress_with_content(session: AsyncSession):
    # Удаляем прогресс и результаты тестов для уроков, которых больше нет
    lessons = (await session.execute(select(Lesson))).scalars().all()
    lesson_codes = {lesson.code for lesson in lessons}
    test_codes = {lesson.code.replace("lesson", "test") for lesson in lessons}

    # Удаляем прогресс для несуществующих уроков
    await session.execute(
        delete(UserProgress).where(UserProgress.lesson_code.not_in(lesson_codes))
    )
    # Удаляем результаты тестов для несуществующих тестов
    await session.execute(
        delete(UserTestScore).where(UserTestScore.test_code.not_in(test_codes))
    )
    await session.commit()


async def update_user(db_session, user, first_name: str, last_name: str):
    try:
        user.first_name = first_name
        user.last_name = last_name
        await db_session.commit()
        logging.info(f"Updated user {user.id}: first_name={first_name}, last_name={last_name}")
    except Exception as e:
        await db_session.rollback()
        logging.error(f"Error updating user {user.id}: {e}")
        raise