# run.py
from yahoo_dfs import process_lineup

def main():
    # Instantiate and run the yahoo_dfs pipeline
    dfs_processor = yahoo_dfs()
    dfs_processor.run()

if __name__ == "__main__":
    main()