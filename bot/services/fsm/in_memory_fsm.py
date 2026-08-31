from .fsm_storage import FSM

class InMemoryFSMStorage(FSM):
    def __init__(self):
        self._data = {}
    
    def get(self, chat_id):
        return self._data.get(chat_id)
    
    def set(self, chat_id, data: dict):
        self._data[chat_id] = data
    
    def clear(self, chat_id):
        self._data.pop(chat_id, None) # type: ignore