import sqlite3
import pandas as pd

class fantasy_db:
    def __init__(self, db_path:str = '../data/fantasy.db'):
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()