from db.models import User, db


class UserService:
    def reg(self, msg):
        telegram_id = msg.chat.id
        
        user = User.query.filter_by(telegram_id=telegram_id).first()
      
        if not user:
            try:
                user = User(
                    name=msg.from_user.first_name or msg.from_user.username or '',
                    last_name=msg.from_user.last_name or '',
                    user_name=msg.from_user.username or '',
                    first_name=msg.from_user.first_name or '',
                    telegram_id=telegram_id,
                    role='seller'
                ) # type: ignore
                db.session.add(user)
            except Exception as e:
                print("not create user", e)
        elif msg.from_user.is_bot == False:
            user.user_name = msg.from_user.username
            user.first_name = msg.from_user.first_name
        
        db.session.commit()
        return user


    def get_user(self, call):
        return User.query.filter_by(telegram_id=call.message.chat.id).first()

    
    
    def change_user_role(self, role, msg):
        user = self.reg(msg)

        if user is not None:
            user.role = role
        
        db.session.commit()
        return user


    def get_role(self, msg=None, call=None):
        if msg is not None:
            telegram_id = msg.chat.id
        elif call is not None:
            telegram_id = call.message.chat.id
        else:
            telegram_id = None

        user = User.query.filter_by(telegram_id=telegram_id).first()

        if user is not None:
            return user.role
        return "None"


    def change_material(self, material, msg):
        try:
            user = self.reg(msg)

            if user is not None:
                user.material = material

            db.session.commit()
            
            return user
        
        except Exception as e:
            print("error in change_material: ", e)


    def get_material(self, msg=None, call=None):
        if msg is not None:
            telegram_id = msg.chat.id
        elif call is not None:
            telegram_id = call.message.chat.id
        else:
            telegram_id = None

        user = User.query.filter_by(telegram_id=telegram_id).first()

        if user is not None:
            return user.material