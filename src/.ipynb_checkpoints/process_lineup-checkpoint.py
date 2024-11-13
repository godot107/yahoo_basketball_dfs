import pandas as pd
import numpy as np
import json
import os
import requests

from pathlib import Path
import logging 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') 
#logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s') # USE logging.DEBUG if testing

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import time
from datetime import datetime
import pytz

from fuzzywuzzy import fuzz
from fuzzywuzzy import process

import basketball_reference_scraper
from basketball_reference_scraper.teams import get_roster, get_team_stats, get_opp_stats, get_roster_stats, get_team_misc, get_team_ratings
from basketball_reference_scraper.players import get_stats, get_game_logs, get_player_headshot

# https://github.com/swar/nba_api
from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players

from yahoo_oauth import OAuth2
import yahoo_fantasy_api as yfa  # yahoo-fantasy-api.readthedocs.io/en/latest/yahoo_fantasy_api.html

from dotenv import load_dotenv
# Load the .env file from the current directory
load_dotenv(dotenv_path = Path("../src/.env"))

today = datetime.utcnow().date()

class yahoo_dfs:
    
    def __init__(self, oauth_path = "../src/oauth2.json", mapper_path = "../data/team_mapper.json", yahoo_league = "454.l.222542"):
        src_path = os.path.abspath(os.path.join(os.getcwd(), '..', 'src'))
        self.oauth = OAuth2(None, None, from_file= oauth_path)
        
        self.gm = yfa.Game(self.oauth, 'nba')
        self.lg = yfa.League(self.oauth, yahoo_league)

        # Open the JSON file and load its content
        with open(mapper_path, 'r') as file:
            team_mapper  = json.load(file)
        
        self.yahoo_to_bball_teams = {v['Yahoo']: v['BBall Reference'] for k, v in team_mapper.items()}
        self.bball_to_yahoo_teams = {v['BBall Reference'] : v['Yahoo'] for k, v in team_mapper.items()}
        
        #team names to Yahoo codes
        self.team_to_yahoo_mapper = {team: details["Yahoo"] for team, details in team_mapper.items()}
        
        # NBA API
        self.active_nba_players = [entry for entry in players.get_players() if entry['is_active']]


    def import_available_players(self, available_player_path:str = '../data/Yahoo_DF_player_export.csv', season:int = 2024):
        """
        Import available players from a yahoo DFS contest

        Parameters:
        available_player_path: csv file of python export.
        season: NBA season start year

        Outputs:
            season_stats -> pd.DataFrame

        """
        
        self.available_players = pd.read_csv(available_player_path) 

        # save for historic
        self.available_players.to_csv(f"../data/yahoo_df_player_export_history/Yahoo_DF_player_export_{today}")
        
        self.available_players['date'] = datetime.now().date()
        self.available_players['parsed_id'] = self.available_players['ID'].str.extract(r'nba\.p\.(\d+)').astype(int)
        
        # Add Home_Away column using a lambda function
        self.available_players['Home_Game'] = self.available_players.apply(lambda x: '0' if f"{x['Team']}@{x['Opponent']}" == x['Game'] else '1', axis=1)        
        self.available_players['full_name'] = self.available_players['First Name'] + ' ' + self.available_players['Last Name']
        
        yahoo_teams_playing_today = self.available_players['Team'].unique()

        self.bball_reference_teams = np.array([self.yahoo_to_bball_teams.get(team, team) for team in yahoo_teams_playing_today])


        self.season_stats = pd.DataFrame(self.lg.player_stats(list(self.available_players['parsed_id']), 'average_season',  season= season))
        self.season_stats.replace('-', np.nan, inplace=True)
        self.season_stats.set_index('name', inplace = True)

    def process_nba_teams(self, nba_year = 2025, output_path = f"../data/team_ratings_history/team_ratings_{today}.csv"):

        """
        Webscrape NBA Team Statistics

        Input:
            path

        Output:
            updates self.available_players df

        """
        all_team_ratings = get_team_ratings(nba_year)
        all_team_ratings.to_csv(output_path)
        
        team_ratings = get_team_ratings(nba_year, team = self.bball_reference_teams )
        
        for i, row in team_ratings.iterrows():
            team = self.bball_to_yahoo_teams[row.TEAM]
            
            self.available_players.loc[self.available_players['Team'] == team, 'ORTG'] = row.ORTG
            self.available_players.loc[self.available_players['Team'] == team, 'DRTG'] = row.DRTG
        
            self.available_players.loc[self.available_players['Opponent'] == team, "Opponent_ORTG"] = row.ORTG  
            self.available_players.loc[self.available_players['Opponent'] == team, "Opponent_DRTG"] = row.DRTG 
            
        # Team Ranking for pace
        for team in self.bball_reference_teams:
            try:
                team_rank_sr = get_team_misc(team, 2025)
        
                # Add the Series attributes to each row where 'Team'
                for key, value in team_rank_sr.items():
                    self.available_players.loc[self.available_players['Team'] == self.bball_to_yahoo_teams[team], key] = value
                    self.available_players.loc[self.available_players['Opponent'] == self.bball_to_yahoo_teams[team], "Opponent_"+key] = value            
        
            except:
                logging.error(f"Error with {team}")  

    def process_players(self, min_games = 5):
        """
        Invoke NBA API to gather game logs and calculate DFS fan points

        """
        

        # Create a dictionary mapping player_id to player_name
        player_dict = {player['full_name'] : player['id']for player in self.active_nba_players}

        # Extract the full names from the dictionary list
        all_player_names = {entry['full_name'] for entry in self.active_nba_players}
        
        # Find names in `full_name_list` that are not in `dict_full_names`
        non_matching_names = [name for name in self.available_players['full_name'].values if name not in all_player_names]
        
        self.error_players = []
        scoring_criteria = { 'PTS':1, 'REB': 1.2, 'AST':1.5, 'STL':3, 'BLK':3, 'TOV':-1}
        
        for player_name in self.season_stats.index:

            logging.info(f'Processing {player_name} for game logs')
            
            try:

                # use fuzzy matching
                match, score = process.extractOne(player_name, player_dict.keys())

                if score >= 80:  # You can adjust the threshold as needed
                    player_id = player_dict[match]

                # if else
                    # hard code mapper
                    
                else:                
                    player_id = player_dict[player_name]

                time.sleep(0.6) # adding delay to limit timeout error when invoking gamelog
                game_log = playergamelog.PlayerGameLog(player_id, season='2024-25')
        
                temp_df =  game_log.get_data_frames()[0]

                # Skips the player because not enough minimum games played
                if len(temp_df) < min_games:
                    logging.info(f"Skipping {player_name} due to playing less than {min_games} games")
                    continue
        
                temp_df['actual_FP'] = [sum(row[col] * scoring_criteria[col] for col in scoring_criteria ) for _, row in temp_df.iterrows() ]
                        
                # last 5 games
                FPS1 = temp_df['actual_FP'][0]
                FPS2 = temp_df['actual_FP'][1]
                FPS3 = temp_df['actual_FP'][2]
                FPS4 = temp_df['actual_FP'][3]
                FPS5 = temp_df['actual_FP'][4]
                FPPG_std = temp_df['actual_FP'].std()

                self.season_stats.loc[player_name, 'FPPG_std'] = FPPG_std 
                self.season_stats.loc[player_name, 'FPS1'] = FPS1
                self.season_stats.loc[player_name, 'FPS2'] = FPS2
                self.season_stats.loc[player_name, 'FPS3'] = FPS3
                self.season_stats.loc[player_name, 'FPS4'] = FPS4
                self.season_stats.loc[player_name, 'FPS5'] = FPS5
                
            except Exception as e:
                logging.error(f"Error processing {player_name}")
                self.error_players.append(player_name)
        
    def vegas_odds(self, API_KEY = os.getenv("odds_API_KEY"), SPORT = "upcoming", REGIONS = "us", MARKETS = "h2h,spreads", ODDS_FORMAT = "decimal", DATE_FORMAT = "iso",COMMENCE_TIME = f"{str(today)}T00:00:00Z"):

        """
        Get Today's Vegas odds for the NBA games

        Input:

        Output:
            Exports odds data for historical purpose

        """
        
        odds_response = requests.get( f'https://api.the-odds-api.com/v4/sports/basketball_nba/odds', params={
        'api_key': API_KEY,
        'regions': REGIONS,
        'markets': MARKETS,
        'oddsFormat': ODDS_FORMAT,
        'dateFormat': DATE_FORMAT,
        'commenceTimeFrom': COMMENCE_TIME
        })
        
        json_odds = odds_response.json()

        self.todays_odds = [
            game for game in json_odds
            if datetime.strptime(game['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
            .replace(tzinfo=pytz.utc)
            .astimezone(pytz.timezone('US/Central')).date() == today
        ]
        
        # Export for historical
        with open(f"../data/odds_history/nba_vegas_odds_{today}.json", 'w') as output_file:
            json.dump(self.todays_odds, output_file, indent=4)
                


        # Parse odds into a DataFrame
        odds_list = []
        
        for game in self.todays_odds:
            home_team = game['home_team']
            away_team = game['away_team']
            for bookmaker in game['bookmakers']:
                for market in bookmaker['markets']:
                    if market['key'] == 'h2h':
                        for outcome in market['outcomes']:
                            odds_list.append({
                                'Team': outcome['name'],
                                'Odds': outcome['price']
                            })
        odds_df = pd.DataFrame(odds_list)
        
        # Group by 'Team' and calculate the average odds for each team
        self.grouped_odds = odds_df.groupby('Team').agg({'Odds': 'mean'}).reset_index()
        
        self.grouped_odds['Team_Abbreviation'] = self.grouped_odds['Team'].replace(self.team_to_yahoo_mapper)


    def merge_data(self):
        merged_df = pd.merge(self.available_players, self.season_stats, left_on='parsed_id', right_on='player_id', how='inner')

        # One-hot encode player positions
        position_dummies = pd.get_dummies(merged_df['Position'])
        merged_df = pd.concat([merged_df, position_dummies], axis=1)

        merged_df['U'] = True # all players count towards a Util funcion
        merged_df['F'] = merged_df.apply(lambda x: True if x['PF'] == 1 or x['SF'] == 1 else False, axis=1)
        merged_df['G'] = merged_df.apply(lambda x: True if x['PG'] == 1 or x['SG'] == 1 else False, axis=1)

        # lower/upper bound FPS- based on STD
        merged_df['FPPG_lowerbound'] = merged_df['FPPG'] - merged_df['FPPG_std']
        merged_df['FPPG_upperbound'] = merged_df['FPPG'] + merged_df['FPPG_std']
        
        # Calculate weighted average of recent FPS (Fantasy Points Scored)
        merged_df['weighted_FPS'] = ( 0.4 * merged_df['FPPG'] + 0.3 * merged_df['FPS1'] + 0.2 * merged_df['FPS2'] + 0.05 * merged_df['FPS3'] +  0.25 * merged_df['FPS4'] + 0.25 * merged_df['FPS5'])
        
        # Calculate Home/Away Modifier
        # If home, increase value slightly (e.g., by 5%), otherwise decrease
        merged_df['Home_Modifier'] = merged_df['Home_Game'].apply(lambda x: 1.05 if x == 1 else 0.95)
        
        # Calculate Opponent Difficulty Modifier
        # Use opponent defensive rating (DRtg): Higher DRtg means worse defense, good for our player
        merged_df['Opponent_Modifier'] = merged_df['Opponent_DRTG'].apply(lambda x: 1.0 + (100 - x) / 100 if x < 100 else 1.0)
        
        # Calculate Team Offensive Rating Modifier
        # Higher offensive rating is better
        merged_df['Team_Modifier'] = merged_df['ORTG'].apply(lambda x: 1.0 + (x - 100) / 100 if x > 100 else 1.0)
        
        # Calculate Pace Modifier
        # Use both team pace and opponent pace: More possessions mean more opportunities for stats
        merged_df['Pace_Modifier'] = (merged_df['Pace'] + merged_df['Opponent_Pace']) / 200
        
        

        merged_df = merged_df.merge(self.grouped_odds[['Team_Abbreviation', 'Odds']], left_on='Team', right_on='Team_Abbreviation', how='left')
        merged_df.rename(columns={'Odds': 'Team_Odds'}, inplace=True)
        merged_df.drop(columns='Team_Abbreviation', inplace=True)
        
        merged_df = merged_df.merge(self.grouped_odds[['Team_Abbreviation', 'Odds']], left_on='Opponent', right_on='Team_Abbreviation', how='left')
        merged_df.rename(columns={'Odds': 'Opponent_Odds'}, inplace=True)
        merged_df.drop(columns='Team_Abbreviation', inplace=True)
        
        
        # Incorporate team and opponent odds to calculate the Value_Score
        merged_df['Adjusted_Team_Odds'] = 1 / merged_df['Team_Odds']
        merged_df['Adjusted_Opponent_Odds'] = 1 / merged_df['Opponent_Odds']
        
        # Normalize Adjusted Odds to avoid large disparities
        merged_df['Normalized_Team_Odds'] = merged_df['Adjusted_Team_Odds'] / merged_df['Adjusted_Team_Odds'].max()
        merged_df['Normalized_Opponent_Odds'] = merged_df['Adjusted_Opponent_Odds'] / merged_df['Adjusted_Opponent_Odds'].max()
                


        # Calculate the new Value_Score including the odds
        merged_df['Value_Score'] = (
            merged_df['weighted_FPS'] *
            merged_df['Home_Modifier'] *
            merged_df['Opponent_Modifier'] *
            merged_df['Team_Modifier'] *
            merged_df['Pace_Modifier'] *
            merged_df['Normalized_Team_Odds'] *
            merged_df['Normalized_Opponent_Odds']
        ) / (merged_df['Salary'])

        merged_df['log_Value_Score_with_std'] =  np.log( (merged_df['Value_Score'] + 1) /  ( 1 + merged_df['FPPG_std'] ) )
        
        # Drop any where value score is NaN.
        #merged_df.dropna(subset=['Value_Score'], inplace = True)

        merged_df.to_csv(f"../outputs/lineup/lineup_{datetime.now().date()}.csv")
        logging.info(f"Lineup Exported to ../outputs/lineup/lineup_{datetime.now().date()}.csv")

        return merged_df


    def run(self):
            """Executes all methods in sequence."""
            self.import_available_players()
            logging.info("yahoo players imported")
            self.process_nba_teams()
            logging.info("NBA Teams Processed")
            self.process_players()
            logging.info("NBA players game logs and FPS processed")
            self.vegas_odds()
            logging.info("Vegas Odds Processed")
            merged_data = self.merge_data()
            logging.info("Run Completed")
            return merged_data