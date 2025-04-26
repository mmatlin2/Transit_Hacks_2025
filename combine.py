#!/usr/bin/env python3
"""
CTA bus-stop + taxi + route map (point layers + KMZ route overlays)
"""

import os, zipfile, xml.etree.ElementTree as ET, requests, tempfile, pandas as pd, folium
from branca.colormap import LinearColormap

# ───────── CONFIG ────────────────────────────────────────────
DATE        = "2012-10-01"
DAYTYPE     = "Weekday"
THRESHOLD   = 100
LOCAL_CSV   = "CTA_-_Ridership_-_Avg._Weekday_Bus_Stop_Boardings_in_October_2012_20250426.csv"
CITY_API    = "https://data.cityofchicago.org/resource/t2qc-9pjd.csv"

TAXI_API    = "https://data.cityofchicago.org/resource/ajtu-isnz.json"
FETCH_LIMIT = 50_000

BUS_KMZ   = "CTA_BusRoutes.kmz"     # local file
RAIL_KMZ  = "CTA_RailLines.kmz"     # local file

CENTER       = (41.88, -87.63)      # downtown Chicago
BASE_RADIUS  = 1.5
TARGET_RMAX  = 20
# ─────────────────────────────────────────────────────────────


# ╭──────────────────── BUS STOP POINTS ──────────────────────╮
if LOCAL_CSV and os.path.exists(LOCAL_CSV):
    bus = pd.read_csv(LOCAL_CSV)
else:
    bus = pd.read_csv(
        CITY_API,
        params={"$limit": 50_000,
                "month_beginning": DATE,
                "daytype": DAYTYPE},
        headers={"X-App-Token": os.getenv("SOCRATA_TOKEN","")}
    )

bus = bus[bus.boardings >= THRESHOLD].copy()
bus[["lat","lon"]] = (bus["location"]
                      .str.strip("()").str.split(",",expand=True).astype(float))
bus.rename(columns={"boardings":"count"}, inplace=True)
# ╰────────────────────────────────────────────────────────────╯


# ╭──────────────────── TAXI POINTS ──────────────────────────╮
resp = requests.get(TAXI_API, params={"$limit": FETCH_LIMIT})
resp.raise_for_status()
taxi = pd.DataFrame(resp.json())

for c in ["pickup_centroid_latitude","pickup_centroid_longitude",
          "dropoff_centroid_latitude","dropoff_centroid_longitude"]:
    taxi[c] = pd.to_numeric(taxi[c], errors="coerce")

taxi = taxi.dropna(subset=[
    "pickup_centroid_latitude","pickup_centroid_longitude",
    "dropoff_centroid_latitude","dropoff_centroid_longitude"
])

pickup = (taxi.groupby(["pickup_centroid_latitude","pickup_centroid_longitude"])
                .size().reset_index(name="count")
                .rename(columns={"pickup_centroid_latitude":"lat",
                                 "pickup_centroid_longitude":"lon"}))

dropoff = (taxi.groupby(["dropoff_centroid_latitude","dropoff_centroid_longitude"])
                 .size().reset_index(name="count")
                 .rename(columns={"dropoff_centroid_latitude":"lat",
                                  "dropoff_centroid_longitude":"lon"}))
# ╰────────────────────────────────────────────────────────────╯


# ╭────────────── UNIFIED SIZE SCALE (POINTS) ────────────────╮
global_max = max(bus["count"].max(),
                 pickup["count"].max(),
                 dropoff["count"].max())
scale  = TARGET_RMAX / (global_max ** 0.5)
radius = lambda c: BASE_RADIUS + (c**0.5)*scale
# ╰────────────────────────────────────────────────────────────╯


# ╭──────────────────────── BASE MAP ─────────────────────────╮
m = folium.Map(location=CENTER, tiles="CartoDB positron", zoom_start=11)

bus_cmap     = LinearColormap(["lightblue","darkblue"],
                              vmin=bus["count"].min(),     vmax=bus["count"].max())
pickup_cmap  = LinearColormap(["yellow","red"],
                              vmin=pickup["count"].min(),  vmax=pickup["count"].max())
dropoff_cmap = LinearColormap(["lightgreen","darkgreen"],
                              vmin=dropoff["count"].min(), vmax=dropoff["count"].max())

bus_fg     = folium.FeatureGroup(name="CTA bus heavy boardings", show=True)
pickup_fg  = folium.FeatureGroup(name="Taxi pickups",            show=False)
dropoff_fg = folium.FeatureGroup(name="Taxi drop-offs",          show=False)

for _, r in bus.iterrows():
    folium.CircleMarker(
        [r.lat,r.lon], radius=radius(r["count"]),
        color=bus_cmap(r["count"]), fill=True, fill_opacity=.8,
        popup=(f"<b>Bus stop</b><br>Routes: {r.routes}<br>"
               f"Boardings: {r['count']:.0f}<br>"
               f"Alightings: {r.alightings:.0f}")
    ).add_to(bus_fg)

for _, r in pickup.iterrows():
    folium.CircleMarker(
        [r.lat,r.lon], radius=radius(r["count"]),
        color=pickup_cmap(r["count"]), fill=True, fill_opacity=.7,
        popup=f"Taxi pickups: {r['count']}"
    ).add_to(pickup_fg)

for _, r in dropoff.iterrows():
    folium.CircleMarker(
        [r.lat,r.lon], radius=radius(r["count"]),
        color=dropoff_cmap(r["count"]), fill=True, fill_opacity=.7,
        popup=f"Taxi drop-offs: {r['count']}"
    ).add_to(dropoff_fg)
# ╰────────────────────────────────────────────────────────────╯


# ╭───────────────────── KMZ ROUTE LAYERS ────────────────────╮
def add_kmz_routes(map_obj, kmz_path, layer_name, color, weight=2, show=False):
    """
    Extract every LineString in a .kmz and plot it as a PolyLine.
    Only standard-lib zipfile + xml.etree are used.
    """
    if not os.path.exists(kmz_path):
        raise FileNotFoundError(kmz_path)

    with zipfile.ZipFile(kmz_path) as zf:
        kml_name = next(n for n in zf.namelist() if n.lower().endswith(".kml"))
        kml_data = zf.read(kml_name)

    root = ET.fromstring(kml_data)

    ns = {"k":"http://www.opengis.net/kml/2.2"}
    coords_tags = root.findall(".//k:LineString/k:coordinates", ns)

    fg = folium.FeatureGroup(name=layer_name, show=show)

    for tag in coords_tags:
        # coordinates string → list of [lat, lon]
        pts = []
        for coord in tag.text.strip().split():
            lon, lat, *_ = map(float, coord.split(","))
            pts.append([lat, lon])
        # draw the polyline
        if len(pts) > 1:
            folium.PolyLine(
                locations=pts, color=color, weight=weight, opacity=0.7
            ).add_to(fg)

    fg.add_to(map_obj)

add_kmz_routes(m, BUS_KMZ,  "CTA bus routes",   color="#2b7bba", weight=2, show=False)
add_kmz_routes(m, RAIL_KMZ, "CTA ‘L’ rail lines", color="#e34a33", weight=3, show=False)
# ╰────────────────────────────────────────────────────────────╯


# ╭────────────────── LEGENDS & LAYER CONTROL ─────────────────╮
for fg in (bus_fg, pickup_fg, dropoff_fg):
    fg.add_to(m)

for cmap in (bus_cmap, pickup_cmap, dropoff_cmap):
    cmap.caption = ""
    cmap.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
# ╰────────────────────────────────────────────────────────────╯

outfile = "cta_bus_taxi_routes.html"
m.save(outfile)
print(f"✓ map written to {outfile}")
