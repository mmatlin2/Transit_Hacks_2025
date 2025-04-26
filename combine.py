#!/usr/bin/env python3
"""
CTA Bus, Taxi, Train Ridership Map — correctly normalized by people/day
"""

import os, zipfile, xml.etree.ElementTree as ET, requests, pandas as pd, folium
from branca.colormap import LinearColormap

# ───────── CONFIG ────────────────────────────────────────────
DATE         = "2012-10-01"
DAYTYPE      = "Weekday"
THRESHOLD    = 100
LOCAL_CSV    = "CTA_-_Ridership_-_Avg._Weekday_Bus_Stop_Boardings_in_October_2012_20250426.csv"
CITY_API     = "https://data.cityofchicago.org/resource/t2qc-9pjd.csv"

TAXI_API     = "https://data.cityofchicago.org/resource/ajtu-isnz.json"
TRAIN_CSV    = "CTA_-_System_Information_-_List_of__L__Stops_20250426.csv"
TRAIN_API    = "https://data.cityofchicago.org/resource/5neh-572f.json"
FETCH_LIMIT  = 50000

BUS_KMZ      = "CTA_BusRoutes.kmz"
RAIL_KMZ     = "CTA_RailLines.kmz"

CENTER       = (41.88, -87.63)
FIXED_RADIUS = 6  # same size for all points

# Days to normalize by
BUS_DAYS   = 1
TAXI_DAYS  = 5
TRAIN_DAYS = 353
# ─────────────────────────────────────────────────────────────

# ╭──────────────────── LOAD BUS DATA ─────────────────────────╮
if os.path.exists(LOCAL_CSV):
    bus = pd.read_csv(LOCAL_CSV)
else:
    bus = pd.read_csv(
        CITY_API,
        params={"$limit": FETCH_LIMIT, "month_beginning": DATE, "daytype": DAYTYPE},
        headers={"X-App-Token": os.getenv("SOCRATA_TOKEN", "")}
    )
bus = bus[bus.boardings >= THRESHOLD].copy()
bus[["lat", "lon"]] = (bus["location"].str.strip("()").str.split(",", expand=True).astype(float))
bus.rename(columns={"boardings": "count"}, inplace=True)
bus["count_per_day"] = bus["count"] / BUS_DAYS
# ╰────────────────────────────────────────────────────────────╯

# ╭──────────────────── LOAD TAXI DATA ────────────────────────╮
resp = requests.get(TAXI_API, params={"$limit": FETCH_LIMIT})
resp.raise_for_status()
taxi = pd.DataFrame(resp.json())
for c in ["pickup_centroid_latitude","pickup_centroid_longitude","dropoff_centroid_latitude","dropoff_centroid_longitude"]:
    taxi[c] = pd.to_numeric(taxi[c], errors="coerce")
taxi = taxi.dropna(subset=["pickup_centroid_latitude","pickup_centroid_longitude","dropoff_centroid_latitude","dropoff_centroid_longitude"])

pickup = (taxi.groupby(["pickup_centroid_latitude","pickup_centroid_longitude"])
            .size().reset_index(name="count")
            .rename(columns={"pickup_centroid_latitude":"lat", "pickup_centroid_longitude":"lon"}))
dropoff = (taxi.groupby(["dropoff_centroid_latitude","dropoff_centroid_longitude"])
            .size().reset_index(name="count")
            .rename(columns={"dropoff_centroid_latitude":"lat", "dropoff_centroid_longitude":"lon"}))

pickup["count_per_day"] = pickup["count"] / TAXI_DAYS
dropoff["count_per_day"] = dropoff["count"] / TAXI_DAYS
# ╰────────────────────────────────────────────────────────────╯

# ╭──────────────────── LOAD TRAIN DATA ───────────────────────╮
if os.path.exists(TRAIN_CSV):
    stations = pd.read_csv(TRAIN_CSV)[["MAP_ID","STATION_NAME","Location"]].drop_duplicates()
    stations.columns = ["station_id","stationname","location"]
    stations["station_id"] = pd.to_numeric(stations["station_id"], errors="coerce").fillna(0).astype(int)
    stations[["lat", "lon"]] = (stations["location"].str.extract(r"\(\s*([\d\.\-]+)\s*,\s*([\d\.\-]+)\s*\)").astype(float))

    resp = requests.get(TRAIN_API, params={"$limit": FETCH_LIMIT})
    resp.raise_for_status()
    rides = pd.DataFrame(resp.json())
    rides["station_id"] = pd.to_numeric(rides["station_id"], errors="coerce").fillna(0).astype(int)
    rides["rides"] = pd.to_numeric(rides["rides"], errors="coerce").fillna(0)

    train_df = (stations.merge(rides.groupby("station_id", as_index=False)["rides"].sum().rename(columns={"rides":"train_total"}),
                               on="station_id", how="left").fillna({"train_total": 0}))
    train_df["train_total_per_day"] = train_df["train_total"] / TRAIN_DAYS
else:
    train_df = pd.DataFrame(columns=["station_id", "stationname", "lat", "lon", "train_total", "train_total_per_day"])
# ╰────────────────────────────────────────────────────────────╯

# ╭──────────────────────── MAP SETUP ─────────────────────────╮
m = folium.Map(location=CENTER, tiles="CartoDB positron", zoom_start=11)

# Use per-day data to set vmin, vmax
bus_cmap     = LinearColormap(["lightblue","darkblue"], vmin=bus["count_per_day"].min(), vmax=bus["count_per_day"].max())
pickup_cmap  = LinearColormap(["yellow","red"], vmin=pickup["count_per_day"].min(), vmax=pickup["count_per_day"].max())
dropoff_cmap = LinearColormap(["lightgreen","darkgreen"], vmin=dropoff["count_per_day"].min(), vmax=dropoff["count_per_day"].max())
train_cmap   = LinearColormap(["orange","red"], vmin=train_df["train_total_per_day"].min(), vmax=train_df["train_total_per_day"].max())

bus_fg     = folium.FeatureGroup(name="CTA Bus Boardings (per day)", show=True)
pickup_fg  = folium.FeatureGroup(name="Taxi Pickups (per day)",       show=False)
dropoff_fg = folium.FeatureGroup(name="Taxi Drop-offs (per day)",     show=False)
train_fg   = folium.FeatureGroup(name="CTA 'L' Station Ridership (per day)", show=False)
# ╰────────────────────────────────────────────────────────────╯

# ╭──────────────────── PLOT ALL POINTS ───────────────────────╮
for _, r in bus.iterrows():
    folium.CircleMarker(
        [r.lat, r.lon], radius=FIXED_RADIUS,
        color=bus_cmap(r["count_per_day"]), fill=True, fill_opacity=0.8,
        popup=(f"<b>Bus Stop</b><br>Routes: {r.routes}<br>Boardings/day: {r['count_per_day']:.1f}<br>Alightings: {r.alightings:.0f}")
    ).add_to(bus_fg)

for _, r in pickup.iterrows():
    folium.CircleMarker(
        [r.lat, r.lon], radius=FIXED_RADIUS,
        color=pickup_cmap(r["count_per_day"]), fill=True, fill_opacity=0.7,
        popup=f"Taxi Pickups/day: {r['count_per_day']:.1f}"
    ).add_to(pickup_fg)

for _, r in dropoff.iterrows():
    folium.CircleMarker(
        [r.lat, r.lon], radius=FIXED_RADIUS,
        color=dropoff_cmap(r["count_per_day"]), fill=True, fill_opacity=0.7,
        popup=f"Taxi Drop-offs/day: {r['count_per_day']:.1f}"
    ).add_to(dropoff_fg)

for _, r in train_df.iterrows():
    folium.CircleMarker(
        [r.lat, r.lon], radius=FIXED_RADIUS,
        color=train_cmap(r["train_total_per_day"]), fill=True, fill_opacity=0.7,
        popup=f"{r['stationname']}: {r['train_total_per_day']:.1f} rides/day"
    ).add_to(train_fg)

for fg in (bus_fg, pickup_fg, dropoff_fg, train_fg):
    fg.add_to(m)
# ╰────────────────────────────────────────────────────────────╯

# ╭───────────────────── KMZ ROUTES ──────────────────────────╮
def add_kmz_routes(map_obj, kmz_path, layer_name, color, weight=2, show=False):
    if not os.path.exists(kmz_path):
        return
    with zipfile.ZipFile(kmz_path) as zf:
        kml_name = next(n for n in zf.namelist() if n.lower().endswith(".kml"))
        kml_data = zf.read(kml_name)

    root = ET.fromstring(kml_data)
    ns = {"k":"http://www.opengis.net/kml/2.2"}
    coords_tags = root.findall(".//k:LineString/k:coordinates", ns)

    fg = folium.FeatureGroup(name=layer_name, show=show)
    for tag in coords_tags:
        pts = []
        for coord in tag.text.strip().split():
            lon, lat, *_ = map(float, coord.split(","))
            pts.append([lat, lon])
        if len(pts) > 1:
            folium.PolyLine(locations=pts, color=color, weight=weight, opacity=0.7).add_to(fg)
    fg.add_to(map_obj)

add_kmz_routes(m, BUS_KMZ,  "CTA Bus Routes",   color="#2b7bba", weight=2, show=False)
add_kmz_routes(m, RAIL_KMZ, "CTA 'L' Rail Lines", color="#e34a33", weight=3, show=False)
# ╰────────────────────────────────────────────────────────────╯

# ╭────────────────── LEGEND & LAYER CONTROL ─────────────────╮
for cmap in (bus_cmap, pickup_cmap, dropoff_cmap, train_cmap):
    cmap.caption = ""
    cmap.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
# ╰────────────────────────────────────────────────────────────╯

outfile = "cta_bus_taxi_train_normalized_map.html"
m.save(outfile)
print(f"✓ Map written to {outfile}")
