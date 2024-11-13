# Evaluate 

import pandas as pd

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa 
import os

# Get the absolute path to the 'src' directory
src_path = os.path.abspath(os.path.join(os.getcwd(), '..', 'src'))

oauth = OAuth2(None, None, from_file='../src/oauth2.json')

gm = yfa.Game(oauth, 'nba')

lg = yfa.League(oauth, '454.l.222542')

class evaluate_entries:
    def __init__(self, players:list):
        """
        Args:
            players (list): A list of tuples where (player_id, salary)

        """
        self.selected_players = [i[0] for i in players]

        # Build a profile
        self.players_profile = {}
        
        for i in players:
            self.players_profile[i[0]] = {'salary':i[1], 'projected_fps':0, 'value_score': 0}


        # Scoring        
        self.scoring_criteria = { 'PTS':1, 'REB': 1.2, 'AST':1.5, 'ST':3, 'BLK':3, 'TO':-1}
        self.projected_score = 0
        #self.df_temp = pd.DataFrame(columns = [])
        

    def calculate_FP(self, player_stats:dict):
        """
        Calculate the fantasy points (FP) for a player based on their statistics and the scoring criteria.

        Args:
            player_stats (dict): A dictionary containing the player's statistics, where keys are the stat names
                                and values are the stat values.

        Returns:
            float: The calculated fantasy points score for the player.
        """
        fps_score = 0
        
        for criteria in self.scoring_criteria.keys():
            fps_score += player_stats[criteria] * self.scoring_criteria[criteria]

        return fps_score

    def value_score(self, player_id, method = 'simple'):
        """
        Assign a 'value score' against statistics and salary. In general, the higher the value, the more stats per salary

        Args:
            method: an approach
                simple = projected_fps/salary

        Returns:
            float: a ratio

        """

        if method == 'simple':
            return self.players_profile[player_id]['projected_fps'] / self.players_profile[player_id]['salary'] 
        

        

    def evaluate_roster(self, **kwargs):

        for player_id in self.selected_players:

            #fetch stats from API
            player_stats = lg.player_stats(player_id, req_type = 'average_season', season = 2023)[0]  # trying to see if i can parameterize this line.
            fps_score = self.calculate_FP(player_stats)
            self.projected_score += fps_score


            self.players_profile[player_id]['projected_fps'] = fps_score
            self.players_profile[player_id]['value_score'] =   self.value_score(player_id)            

        

        
        