#!/usr/bin/env python3
"""
Combined CTA bus-and-taxi map with comparable symbol sizes + layer toggle
"""

import os, requests, pandas as pd, folium
from branca.colormap import LinearColormap
from datetime import date

# ───────────────────────── CONFIG ─────────────────────────
# --- Bus data -------------------------------------------------
DATE      = "2012-10-01"            # yyyy-mm-dd
DAYTYPE   = "Weekday"               # Weekday / Saturday / Sunday
THRESHOLD = 100                     # min boardings to draw
LOCAL_CSV = "CTA_-_Ridership_-_Avg._Weekday_Bus_Stop_Boardings_in_October_2012_20250426.csv"
CITY_API  = "https://data.cityofchicago.org/resource/t2qc-9pjd.csv"
SODA_APP  = os.getenv("SOCRATA_TOKEN", "")

# --- Taxi data ------------------------------------------------
#  • 2017 trips with pickup / drop-off centroids
TAXI_API  = "https://data.cityofchicago.org/resource/ajtu-isnz.json"
FETCH_LIMIT = 50_000                 # cut-down sample to keep map light

# --- Map and scaling -----------------------------------------
CENTER      = (41.88, -87.63)
BASE_RADIUS = 1.5                    # px added to every marker so very small ones stay visible
TARGET_RMAX = 20                     # px radius for the single busiest location
# ──────────────────────────────────────────────────────────────


# ╭────────────────────── BUS STOPS ───────────────────────╮
if LOCAL_CSV and os.path.exists(LOCAL_CSV):
    bus = pd.read_csv(LOCAL_CSV)
else:
    bus = pd.read_csv(
        CITY_API,
        params={
            "$limit": 50_000,
            "month_beginning": DATE,
            "daytype": DAYTYPE},
        headers={"X-App-Token": SODA_APP} if SODA_APP else {}
    )

bus = bus[bus.boardings >= THRESHOLD].copy()
bus[["lat", "lon"]] = (bus["location"]
                       .str.strip("()")
                       .str.split(",", expand=True)
                       .astype(float))
bus.rename(columns={"boardings": "count"}, inplace=True)
# ╰─────────────────────────────────────────────────────────╯


# ╭────────────────────── TAXI TRIPS ──────────────────────╮
resp = requests.get(TAXI_API, params={"$limit": FETCH_LIMIT})
resp.raise_for_status()
taxi = pd.DataFrame(resp.json())

# force numeric & drop bad rows
for col in ["pickup_centroid_latitude","pickup_centroid_longitude",
            "dropoff_centroid_latitude","dropoff_centroid_longitude"]:
    taxi[col] = pd.to_numeric(taxi[col], errors="coerce")
taxi = taxi.dropna(subset=[
    "pickup_centroid_latitude","pickup_centroid_longitude",
    "dropoff_centroid_latitude","dropoff_centroid_longitude"
])

pickup = (taxi.groupby(["pickup_centroid_latitude","pickup_centroid_longitude"])
                .size()
                .reset_index(name="count")
                .rename(columns={
                    "pickup_centroid_latitude": "lat",
                    "pickup_centroid_longitude": "lon"}))

dropoff = (taxi.groupby(["dropoff_centroid_latitude","dropoff_centroid_longitude"])
                 .size()
                 .reset_index(name="count")
                 .rename(columns={
                     "dropoff_centroid_latitude": "lat",
                     "dropoff_centroid_longitude": "lon"}))
# ╰─────────────────────────────────────────────────────────╯


# ╭────────────── UNIFIED SIZE SCALE ──────────────────────╮
global_max = max(bus["count"].max(),
                 pickup["count"].max(),
                 dropoff["count"].max())
scale      = TARGET_RMAX / (global_max ** 0.5)   # so   r = √count · scale  ≤ TARGET_RMAX
def radius(c):          # consistent for every layer
    return BASE_RADIUS + (c ** 0.5) * scale
# ╰─────────────────────────────────────────────────────────╯


# ╭────────────────────── BUILD MAP ───────────────────────╮
m = folium.Map(location=CENTER, tiles="CartoDB positron", zoom_start=11)

# colour ramps per layer (they do *not* affect size ratios)
bus_cmap     = LinearColormap(["lightblue","darkblue"], vmin=bus["count"].min(),     vmax=bus["count"].max())
pickup_cmap  = LinearColormap(["yellow","red"],         vmin=pickup["count"].min(),  vmax=pickup["count"].max())
dropoff_cmap = LinearColormap(["lightgreen","darkgreen"],vmin=dropoff["count"].min(),vmax=dropoff["count"].max())

bus_fg     = folium.FeatureGroup(name="CTA bus heavy boardings", show=True)
pickup_fg  = folium.FeatureGroup(name="Taxi pickups",            show=False)
dropoff_fg = folium.FeatureGroup(name="Taxi drop-offs",          show=False)

for _, r in bus.iterrows():
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=radius(r["count"]),
        color=bus_cmap(r["count"]),
        fill=True, fill_opacity=.8,
        popup=(f"<b>Bus stop</b><br>Routes: {r.routes}<br>"
               f"Boardings: {r['count']:.0f}<br>"
               f"Alightings: {r.alightings:.0f}")
    ).add_to(bus_fg)

for _, r in pickup.iterrows():
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=radius(r["count"]),
        color=pickup_cmap(r["count"]),
        fill=True, fill_opacity=.7,
        popup=f"Taxi pickups: {r['count']}"
    ).add_to(pickup_fg)

for _, r in dropoff.iterrows():
    folium.CircleMarker(
        location=[r.lat, r.lon],
        radius=radius(r["count"]),
        color=dropoff_cmap(r["count"]),
        fill=True, fill_opacity=.7,
        popup=f"Taxi drop-offs: {r['count']}"
    ).add_to(dropoff_fg)

# add layers + legends
for fg in (bus_fg, pickup_fg, dropoff_fg):
    fg.add_to(m)

for cmap in (bus_cmap, pickup_cmap, dropoff_cmap):
    cmap.caption = cmap.caption or ""
    cmap.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

out = "bus_taxi_overlay.html"
m.save(out)
print(f"✓  map written to {out}")
