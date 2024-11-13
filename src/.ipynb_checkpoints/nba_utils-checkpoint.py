from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import time
from datetime import datetime

from nba_api.stats.endpoints import playergamelog
from nba_api.stats.static import players

import pandas as pd

# Set up the web driver (make sure to install the appropriate WebDriver, like ChromeDriver)
options = webdriver.ChromeOptions()
#options.add_argument("--headless")  # Run headlessly for better performance, but no window

options.add_experimental_option("prefs", {
    "download.prompt_for_download": False,
    "download.directory_upgrade": True, 
    #"safebrowsing.enabled": True
})

active_nba_players = [entry for entry in players.get_players() if entry['is_active']]
player_dict = {player['full_name'] : player['id']for player in active_nba_players}

def calculate_FPS(row):
    """
    Input -> Pandas DataFrame Row
    Output -> int: single FPS Score

    """
    
    scoring_criteria = { 'PTS':1, 'REB': 1.2, 'AST':1.5, 'STL':3, 'BLK':3, 'TOV':-1}
    score = 0
    for stat, weight in scoring_criteria.items():
        score += row.get(stat, 0) * weight  # Use .get() to avoid KeyError if the column doesn't exist
    return score



def weighted_FPS(df):
    
    # Define weights for each component
    weight_wa = 1 / 3
    weight_ra = 1 / 3
    weight_ema = 1 / 3
    
    # Calculate weighted average FPS based on last 5 games
    weights=[5, 4, 3, 2, 1]

    last_five_fps = df['FPS'][-5:]
    weighted_avg = sum(last_five_fps * weights) / sum(weights)    
    
    # Calculate rolling average FPS for the last 5 games
    rolling_avg_fps = df['FPS'][-5:].mean()
    
    # Calculate Exponential Moving Average (EMA) FPS with a span of 5 (last 5 games)
    ema_fps = df['FPS'].ewm(span=5, adjust=False).mean().iloc[-1]
    
    # Combine the three metrics into a single FPS prediction
    combined_fps = (weight_wa * weighted_avg) + (weight_ra * rolling_avg_fps) + (weight_ema * ema_fps)
    
    return combined_fps
    
def project_FPS(lineup, func):
    """
    inputs:
      lineup -> list of player names from yahoo DFS
    func -> that accepts PlayerGameLog DF from NBA API
    
    output: projected FPS and each player's projected FPS
    """
    
    projected_score = 0
    projected_fps_dict = {}
    for player in lineup:
        try:        
            game_log = playergamelog.PlayerGameLog(player_dict[player], season='2024-25')
            df = game_log.get_data_frames()[0]
            df['FPS'] = df.apply(calculate_FPS, axis = 1)
            
            projected_fps = func(df)  ## <- projection function applies here
            
            projected_score += projected_fps
            projected_fps_dict[player] = projected_fps
        except:        
            print(f"player: {player} not found in NBA API")
    return projected_score, projected_fps_dict    

def get_salary_pts(contest_id, yahoo_player_name, n_games):
    driver = webdriver.Chrome(service=webdriver.chrome.service.Service('../src/chromedriver-win32/chromedriver.exe'), options=options)
    driver.get(f"https://sports.yahoo.com/dailyfantasy/contest/{contest_id}/setlineup")

    # Locate the search bar by its ID
    search_bar = driver.find_element(By.ID, "playerSearch")
    
    # Clear the search bar if it has pre-filled text, then enter the player's name
    search_bar.clear()
    search_bar.send_keys(yahoo_player_name)  # Replace "Player Name" with the actual player's name you're searching for
    
    search_bar.send_keys(Keys.RETURN)
    
    # Wait to see results (adjust time if necessary)
    time.sleep(2)

    # Open Game Log
    target_element = driver.find_element(By.XPATH, "/html/body/div[@id='app']/div[@id='page']/div/div[@id='render-target-default']/div/div[@id='content']/div[@class='Mx(a) Pb(10px) Bbbw(1px) Bdbs(s) Bdbc($c-fuji-dirty-seagull) W(1080px) Thm-lite']/div[@class='Pos(r)']/div[@class='IbBox W(3/5)']/div[@id='jumptocontent']/div[@id='primary-1-DesktopLineupSelection-Proxy']/div[@id='lineupSelection']/div[@class='Px(10px)']/div[@class='Pb(10px) Px(10px)']/div[@class='Us(n) Mih(670px)']/table[@class='W(100%) Hover TableRowBorderTop TableVa(m) Mt(-1px) LinkColorOnHover']/tbody[@class='infinite-scroll-list']/tr[@class='Cur(p)'][1]/td[@class='Px(6px) Py(10px)']")
    
    # Click the element
    target_element.click()
    
    # Wait for any subsequent actions or results to load (adjust as necessary)
    time.sleep(2)

    # Access Game Log    
    target_element = driver.find_element(By.XPATH, "/html[@id='atomic']/body/div[@id='app']/div[@id='page']/div/div[@id='render-target-default']/div/div[@class='Z(11) End(0) Pos(f) Start(0) T(0)']/div/div[@id='overlay-1-Lightbox-Proxy']/div[@id='overlay-1-Lightbox']/div[@class='lightbox-wrapper Ta(c) Pos(f) T(0) Start(0) H(100%) W(100%) PageOverlay Z(50) Op(1)']/div[@id='myLightboxContainer']/div[@class='ys-playerModal ys-modalContent Thm-lite Pos(r)']/div[@class='Fxg(1)']/div[@class='D(f) W(100%) Tbbdsx(2px)']/div[@class='Fxg(1) Pos(r) Cur(p) Bdb(1px) Ta(c) Py(6px) Va(m) Bdb(0) C(color-gray-light) Py(16px)!']/div[@class='Pos(r)']")
    
    # Click the element
    target_element.click()
    
    # Wait for any subsequent actions or results to load (adjust as necessary)
    time.sleep(2)
    
    base_url = "/html[@id='atomic']/body/div[@id='app']/div[@id='page']/div/div[@id='render-target-default']/div/div[@class='Z(11) End(0) Pos(f) Start(0) T(0)']/div/div[@id='overlay-1-Lightbox-Proxy']/div[@id='overlay-1-Lightbox']/div[@class='lightbox-wrapper Ta(c) Pos(f) T(0) Start(0) H(100%) W(100%) PageOverlay Z(50) Op(1)']/div[@id='myLightboxContainer']/div[@class='ys-playerModal ys-modalContent Thm-lite Pos(r)']/div[@class='Fxg(1)']/div[2]/div[@class='Bt-lite bd Ovy(a)']/table[@class='W(100%) Ta(start) Bdt(0) B-lite My(0px) TableRowBorderTop']/tbody[@class='D(b) Ov(a) W(100%)']/tr[@class='Whs(nw) W(100%) D(b)']"
    
    players_data = []
    
    for i in range(1,n_games):
        date_xpath = f"{base_url}[{i}]/th[@class='D(ib) W(10%) Px(0) Py(10px) Ta(c)']"
        fan_pts_xpath = f"{base_url}[{i}]/td[@class='Fw(500) D(ib) W(8%) Px(0) Py(10px) Ta(c)']/span[@class='ydfs-scoring-points']"
        salary_xpath = f"{base_url}[{i}]/td[@class='D(ib) W(6%) Px(0) Py(10px) Ta(c)']/span"
            
        try:
            date = driver.find_element(By.XPATH, date_xpath).text  
            fan_pts = driver.find_element(By.XPATH, fan_pts_xpath).text 
            salary = driver.find_element(By.XPATH, salary_xpath).text  
            players_data.append({"Name": yahoo_player_name, "Fan_Pts": fan_pts,"Salary": salary, "Date":date})
        except Exception as e:
            print(e)

    # Process DF
    df= pd.DataFrame(players_data)
        
    df['Salary'] = df['Salary'].apply(lambda x: int(x.replace('$', '')))
    df['Fan_Pts'] = df['Fan_Pts'].astype(float)
    df['Value'] = df['Fan_Pts'] / df['Salary']
    df['formatted_date'] = df['Date'].apply(lambda x: pd.to_datetime(x + ' 2024').strftime('%m-%d-%Y'))

    return df



