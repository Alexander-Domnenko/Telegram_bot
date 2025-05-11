from aiogram.fsm.state import State, StatesGroup

class TestState(StatesGroup):
    testing = State()

class RegistrationState(StatesGroup):
    first_name = State()  
    last_name = State()   
    



    