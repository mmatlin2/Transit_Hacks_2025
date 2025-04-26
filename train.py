import requests
import pandas as pd
import folium
import numpy as np
from branca.colormap import LinearColormap

# ───────────────────────────────────────────────────────────────
# PARAMETERS
CSV_PATH       = '/Users/markmatlin/Transit_Hacks_2025/CTA_-_System_Information_-_List_of__L__Stops_20250426.csv'
RIDERSHIP_URL  = 'https://data.cityofchicago.org/resource/5neh-572f.json'
FETCH_LIMIT    = 50000     # max rows per Socrata page
MIN_RADIUS     = 2         # px
MAX_RADIUS     = 20        # px
# ───────────────────────────────────────────────────────────────

# 1. Load station CSV & parse coords
stations = pd.read_csv(CSV_PATH)[['MAP_ID','STATION_NAME','Location']].drop_duplicates()
stations.columns = ['station_id','stationname','location']
stations['station_id'] = pd.to_numeric(stations['station_id'], errors='coerce').astype(int)
stations[['lat','lng']] = (
    stations['location']
            .str.extract(r'\(\s*([\d\.\-]+)\s*,\s*([\d\.\-]+)\s*\)')
            .astype(float)
)
stations_df = stations[['station_id','stationname','lat','lng']]

# 2. Fetch ridership JSON & sum rides per station_id
resp = requests.get(RIDERSHIP_URL, params={'$limit': FETCH_LIMIT})
resp.raise_for_status()
rides = pd.DataFrame(resp.json())
rides['station_id'] = pd.to_numeric(rides['station_id'], errors='coerce').astype(int)
rides['rides']      = pd.to_numeric(rides['rides'], errors='coerce').fillna(0)

totals = (
    rides.groupby('station_id', as_index=False)['rides']
         .sum()
         .rename(columns={'rides':'total_rides'})
)

# 3. Merge & sort
df = stations_df.merge(totals, on='station_id', how='left').fillna({'total_rides':0})
df['total_rides'] = df['total_rides'].astype(int)
df = df.sort_values('total_rides').reset_index(drop=True)

# 4. Compute max for normalization
max_rides = df['total_rides'].max()

# 5. Build Folium map centered on Chicago
m = folium.Map(
    location=[df['lat'].mean(), df['lng'].mean()],
    zoom_start=11
)

# 6. Create a normalized colormap (domain [0,1])
colormap = LinearColormap(
    ['yellow','orange','red'],
    vmin=0, vmax=1,
    caption="Relative 'L' Station Rides"
)
colormap.add_to(m)

# 7. Plot each station with size & color relative to max_rides
for _, row in df.iterrows():
    qty = row['total_rides']
    # normalized [0,1]
    rel = qty / max_rides if max_rides > 0 else 0

    # circle radius between MIN_RADIUS and MAX_RADIUS
    radius = MIN_RADIUS + rel * (MAX_RADIUS - MIN_RADIUS)

    # color from yellow→orange→red based on rel
    color = colormap(rel)

    folium.CircleMarker(
        location=[row['lat'], row['lng']],
        radius=radius,
        color=color,
        fill=True, fill_color=color, fill_opacity=0.7,
        popup=f"{row['stationname']}: {qty} rides"
    ).add_to(m)

# 8. Save or display
m.save('cta_l_ridership_map_relative_color.html')
