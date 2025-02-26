

class DebtMgr:
    def __init__(self):
        self.debt_in_game = {} # uid -> debt

    def add_debt_ingame(self, uid, debt):
        if uid in self.debt_in_game:
            self.debt_in_game[uid] += debt
        else:
            self.debt_in_game[uid] = debt
        
    def get_debt_ingame(self, uid):
        return self.debt_in_game.get(uid, 0)
    
    def remove_debt_ingame(self, uid):
        self.debt_in_game.pop(uid, None)

    