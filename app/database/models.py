from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, ForeignKey, Text, SmallInteger, UniqueConstraint
from config import DB_URL
import asyncio

engine = create_async_engine(DB_URL, echo=True)

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String)
    is_admin = Column(Boolean, default=False)
    progress = relationship("UserProgress", back_populates="user", cascade="all, delete")
    test_scores = relationship("UserTestScore", back_populates="user", cascade="all, delete")

class Module(Base):
    __tablename__ = 'modules'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    text = Column(Text)
    photo = Column(String)
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete")

class Lesson(Base):
    __tablename__ = 'lessons'
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True)
    module_id = Column(Integer, ForeignKey('modules.id', ondelete='CASCADE'))
    text = Column(Text)
    photo = Column(String)
    video_link = Column(String)
    notes_link = Column(String)
    module = relationship("Module", back_populates="lessons")
    questions = relationship("TestQuestion", back_populates="lesson", cascade="all, delete")
    completed_by = relationship("UserProgress", back_populates="lesson", cascade="all, delete")
    test_scores = relationship(
        "UserTestScore",
        primaryjoin="foreign(UserTestScore.test_code) == Lesson.code",
        viewonly=True
    )

class TestQuestion(Base):
    __tablename__ = 'test_questions'
    id = Column(Integer, primary_key=True)
    lesson_code = Column(String, ForeignKey('lessons.code', ondelete='CASCADE'))
    question_text = Column(Text)
    option_1 = Column(String)
    option_2 = Column(String)
    option_3 = Column(String)
    correct_option = Column(SmallInteger)
    photo = Column(String)
    lesson = relationship("Lesson", back_populates="questions")

class UserProgress(Base):
    __tablename__ = 'user_progress'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    lesson_code = Column(String, ForeignKey('lessons.code', ondelete='CASCADE'))
    completed = Column(Boolean, default=True)
    user = relationship("User", back_populates="progress")
    lesson = relationship("Lesson", back_populates="completed_by")
    __table_args__ = (
        UniqueConstraint('user_id', 'lesson_code', name='unique_user_lesson'),
    )

class UserTestScore(Base):
    __tablename__ = 'user_test_scores'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'))
    test_code = Column(String)
    score = Column(Integer)
    total = Column(Integer)
    user = relationship("User", back_populates="test_scores")
    lesson = relationship(
        "Lesson",
        primaryjoin="foreign(UserTestScore.test_code) == Lesson.code",
        viewonly=True
    )
    __table_args__ = (
        UniqueConstraint('user_id', 'test_code', name='unique_user_test'),
    )

async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(create_all())