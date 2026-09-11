import sys
import argparse
import pandas as pd
from fpl_client import FPLClient

# User's players for Rubies Rangers
PLAYERS = [
    'Roefs', 'Verbruggen',
    'Pedro Porro', 'Senesi', 'Guéhi', 'Robinson', 'Thiaw',
    'Foden', 'Ødegaard', 'Mbeumo', 'Cherki', 'Rogers',
    'João Pedro', 'Isak', 'Solanke'
]

def main():
    parser = argparse.ArgumentParser(description="Extract Rubies Rangers squad stats")
    parser.add_argument("--live", action="store_true", help="Fetch live stats from official FPL API")
    args = parser.parse_args()

    if args.live:
        client = FPLClient()
        df = client.get_players_df()
        cols = ['web_name', 'club_name', 'position_name', 'now_cost', 'total_points', 
                'form', 'status', 'moneyball_score', 'moneyball_efficiency', 'news']
        name_col = 'web_name'
    else:
        df = pd.read_csv('fpl_player_statistics.csv')
        cols = ['player_name', 'position_name', 'now_cost', 'expected_goals_per_90', 
                'expected_assists_per_90', 'ict_index', 'defensive_contribution_per_90', 
                'points_per_game', 'selected_by_percent']
        name_col = 'player_name'

    # Filter players
    matched = df[df[name_col].str.contains('|'.join(PLAYERS), case=False, na=False)].copy()
    print(matched[cols].to_string(index=False))

if __name__ == "__main__":
    main()