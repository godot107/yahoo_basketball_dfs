# main.py

from src import yahoo_dfs

def main():
    # Initialize the yahoo_dfs instance
    dfs_instance = yahoo_dfs()
    
    # Run the workflow
    dfs_instance.run()

if __name__ == "__main__":
    main()