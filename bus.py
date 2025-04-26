#!/usr/bin/env python3
"""
Map CTA bus stops with heavy boardings on a given day
----------------------------------------------------

Input  (one of the two):
  • local CSV   e.g. data/cta_stop_boardings_2012-10-01.csv
  • OR pull directly from Socrata resource **t2qc-9pjd** for the date you want

Output:
  • heavy_boardings_map.html   – opens in any browser
"""

import os, pandas as pd, folium, branca.colormap as cm
from datetime import date

# ------------------------------------------------------------------
# CONFIG – adjust to taste
# ------------------------------------------------------------------
DATE      = "2012-10-01"          # yyyy-mm-dd you want to visualise
DAYTYPE   = "Weekday"             # or "Saturday"/"Sunday"
THRESHOLD = 100                   # min boardings to call a stop “heavy”
LOCAL_CSV = 'CTA_-_Ridership_-_Avg._Weekday_Bus_Stop_Boardings_in_October_2012_20250426.csv'                 # set path if you already downloaded the file
SODA_APP  = os.getenv("SOCRATA_TOKEN", "")  # optional for higher rate
CITY_API  = "https://data.cityofchicago.org/resource/t2qc-9pjd.csv"
OUT_HTML  = "heavy_boardings_map.html"

# ------------------------------------------------------------------
# 1.  Load the boarding data  (from local file **or** via API)
# ------------------------------------------------------------------
if LOCAL_CSV and os.path.exists(LOCAL_CSV):
    df = pd.read_csv(LOCAL_CSV)
else:
    params = {
        "$limit": 50000,
        "month_beginning": DATE,
        "daytype": DAYTYPE
    }
    headers = {"X-App-Token": SODA_APP} if SODA_APP else {}
    df = pd.read_csv(CITY_API, params=params, headers=headers)

# ------------------------------------------------------------------
# 2.  Filter to “heavy” boardings and split lat/long
# ------------------------------------------------------------------
df = df[df.boardings >= THRESHOLD].copy()
# location comes in as "(lat, lon)"  ➜  split into two floats
df[["lat", "lon"]] = (df["location"]
                      .str.strip("()")
                      .str.split(",", expand=True)
                      .astype(float))

# colour ramp  – darkest = busiest
cmap = cm.LinearColormap(["yellow","red"],
                         vmin=df.boardings.min(),
                         vmax=df.boardings.max())

# ------------------------------------------------------------------
# 3.  Build the map
# ------------------------------------------------------------------
m = folium.Map(location=[41.88, -87.63], tiles="CartoDB positron", zoom_start=11)

for _, row in df.iterrows():
    folium.CircleMarker(
        location=[row.lat, row.lon],
        radius = max(4, row.boardings**0.5/2),   # √boardings for size
        color  = cmap(row.boardings),
        fill=True, fill_opacity=0.8,
        popup=(f"<b>{row.on_street} &amp; {row.cross_street}</b><br>"
               f"Routes: {row.routes}<br>"
               f"Boardings: {row.boardings:.1f}<br>"
               f"Alightings: {row.alightings:.1f}")
    ).add_to(m)

cmap.caption = f"Boardings on {DATE} ({DAYTYPE})"
cmap.add_to(m)
m.save(OUT_HTML)
print(f"✓  map written to {OUT_HTML}")
