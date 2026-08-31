class FSM:
    def get(self, chat_id):
        raise NotImplementedError
    
    def set(self, chat_id, data: dict):
        raise NotImplementedError
    
    def clear(self, chat_id):
        raise NotImplementedError