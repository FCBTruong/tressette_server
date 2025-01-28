

class UserInfo:
    uid: int
    name: str
    gold: int
    level: int
    avatar: str
    def __init__(self, uid: int, name: str, gold: int, level: int, avatar: str):
        self.uid = uid
        self.name = name
        self.gold = gold
        self.level = level
        self.avatar = avatar