from aiogram.fsm.state import State, StatesGroup

class UploadLessonState(StatesGroup):
    module = State()
    text = State()
    photo = State()
    video_url = State()
    notes_url = State()

class UpdateState(StatesGroup):
    module = State()
    key = State()
    field = State()
    value = State()

class EditTestStates(StatesGroup):
    module = State()
    lesson = State()
    question = State()
    field = State()
    value = State()
    preview = State()
    add_question = State()
    add_question_text = State()
    add_question_options = State()
    add_question_correct = State()
    add_question_photo = State()
    add_question_preview = State()
    delete_confirm = State()

class AddTestStates(StatesGroup):
    module = State()
    lesson = State()
    question = State()
    options = State()
    correct = State()
    photo = State()
    preview = State()

class DeleteLessonState(StatesGroup):
    module = State()
    lesson = State()
    confirm = State()

class AddModuleState(StatesGroup):
    name = State()
    text = State()
    photo = State()

class DeleteModuleState(StatesGroup):
    module = State()
    confirm = State()

class AdminRegistrationState(StatesGroup):
    code = State()  # Шаг для ввода секретного кода