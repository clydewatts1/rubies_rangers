import os
import pandas as pd

# Load the dataset
csv_path = os.path.join(os.path.dirname(__file__), 'fpl_player_statistics.csv')
df = pd.read_csv(csv_path)

# User's players
players = [
    'Roefs', 'Verbruggen',
    'Pedro Porro', 'Senesi', 'Guéhi', 'Robinson', 'Thiaw',
    'Foden', 'Ødegaard', 'Mbeumo', 'Eze', 'Rogers',
    'Watkins', 'Isak', 'Solanke'
]

# Find matches for these players in the dataframe
player_stats = df[df['player_name'].str.contains('|'.join(players), case=False, na=False)].copy()

# Select key Moneyball metrics
cols_to_show = ['player_name', 'position_name', 'now_cost', 'expected_goals_per_90', 'expected_assists_per_90', 
                'ict_index', 'defensive_contribution_per_90', 'points_per_game', 'selected_by_percent']

print(player_stats[cols_to_show].to_string())