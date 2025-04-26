#!/usr/bin/env python3
"""
CTA Ridership Interactive Dashboard
(Improved Visualization + Streamlit Dashboard)
"""

import os, zipfile, xml.etree.ElementTree as ET, requests, tempfile
import pandas as pd
import numpy as np
import folium
import streamlit as st
from folium.plugins import MarkerCluster
from branca.colormap import LinearColormap
from streamlit_folium import st_folium
import matplotlib.pyplot as plt

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
FIXED_RADIUS = 5

BUS_DAYS   = 1
TAXI_DAYS  = 5
TRAIN_DAYS = 353
# ─────────────────────────────────────────────────────────────

st.set_page_config(page_title="CTA Ridership Dashboard", layout="wide")

st.title("🚇 Chicago Transit Ridership Dashboard")
st.markdown("Visualizing **CTA Bus**, **Taxi**, and **Train** ridership normalized by people/day.")

# ╭──────────────────── LOAD DATA ─────────────────────────╮
@st.cache_data
def load_bus_data():
    if os.path.exists(LOCAL_CSV):
        bus = pd.read_csv(LOCAL_CSV)
    else:
        bus = pd.read_csv(CITY_API, params={"$limit": FETCH_LIMIT, "month_beginning": DATE, "daytype": DAYTYPE})
    bus = bus[bus.boardings >= THRESHOLD].copy()
    bus[["lat", "lon"]] = bus["location"].str.strip("()").str.split(",", expand=True).astype(float)
    bus.rename(columns={"boardings": "count"}, inplace=True)
    bus["count_per_day"] = bus["count"] / BUS_DAYS
    return bus

@st.cache_data
def load_taxi_data():
    resp = requests.get(TAXI_API, params={"$limit": FETCH_LIMIT})
    taxi = pd.DataFrame(resp.json())
    for c in ["pickup_centroid_latitude","pickup_centroid_longitude","dropoff_centroid_latitude","dropoff_centroid_longitude"]:
        taxi[c] = pd.to_numeric(taxi[c], errors="coerce")
    taxi = taxi.dropna(subset=["pickup_centroid_latitude","pickup_centroid_longitude","dropoff_centroid_latitude","dropoff_centroid_longitude"])
    pickup = taxi.groupby(["pickup_centroid_latitude","pickup_centroid_longitude"]).size().reset_index(name="count")
    pickup.columns = ["lat", "lon", "count"]
    dropoff = taxi.groupby(["dropoff_centroid_latitude","dropoff_centroid_longitude"]).size().reset_index(name="count")
    dropoff.columns = ["lat", "lon", "count"]
    pickup["count_per_day"] = pickup["count"] / TAXI_DAYS
    dropoff["count_per_day"] = dropoff["count"] / TAXI_DAYS
    return pickup, dropoff

@st.cache_data
def load_train_data():
    if os.path.exists(TRAIN_CSV):
        stations = pd.read_csv(TRAIN_CSV)[["MAP_ID","STATION_NAME","Location"]].drop_duplicates()
        stations.columns = ["station_id","stationname","location"]
        stations["station_id"] = pd.to_numeric(stations["station_id"], errors="coerce").fillna(0).astype(int)
        stations[["lat", "lon"]] = stations["location"].str.extract(r"\(\s*([\d\.\-]+)\s*,\s*([\d\.\-]+)\s*\)").astype(float)
        rides = pd.DataFrame(requests.get(TRAIN_API, params={"$limit": FETCH_LIMIT}).json())
        rides["station_id"] = pd.to_numeric(rides["station_id"], errors="coerce").fillna(0).astype(int)
        rides["rides"] = pd.to_numeric(rides["rides"], errors="coerce").fillna(0)
        train_df = stations.merge(rides.groupby("station_id", as_index=False)["rides"].sum(), on="station_id", how="left")
        train_df["rides"] = train_df["rides"].fillna(0)
        train_df["train_total_per_day"] = train_df["rides"] / TRAIN_DAYS
    else:
        train_df = pd.DataFrame(columns=["station_id", "stationname", "lat", "lon", "rides", "train_total_per_day"])
    return train_df
# ╰────────────────────────────────────────────────────────╯

bus, (pickup, dropoff), train_df = load_bus_data(), load_taxi_data(), load_train_data()

# ╭────────────────────── PLOT MAP ─────────────────────────╮
st.subheader("🗺️ Ridership Map")

m = folium.Map(location=CENTER, zoom_start=11, tiles="cartodbpositron")

def add_layer(data, colormap, name, color_field, popup_field):
    fg = folium.FeatureGroup(name=name, show=True)
    cluster = MarkerCluster().add_to(fg)
    for _, r in data.iterrows():
        folium.CircleMarker(
            location=[r.lat, r.lon],
            radius=4,
            color=colormap(r[color_field]),
            fill=True, fill_opacity=0.7,
            popup=popup_field.format(**r)
        ).add_to(cluster)
    return fg

bus_cmap = LinearColormap(["lightblue","darkblue"], vmin=bus["count_per_day"].min(), vmax=bus["count_per_day"].max())
pickup_cmap = LinearColormap(["yellow","red"], vmin=pickup["count_per_day"].min(), vmax=pickup["count_per_day"].max())
dropoff_cmap = LinearColormap(["green","darkgreen"], vmin=dropoff["count_per_day"].min(), vmax=dropoff["count_per_day"].max())
train_cmap = LinearColormap(["orange","red"], vmin=train_df["train_total_per_day"].min(), vmax=train_df["train_total_per_day"].max())

add_layer(bus, bus_cmap, "Bus Boardings", "count_per_day", "<b>Bus Stop</b><br>Boardings/Day: {count_per_day:.1f}").add_to(m)
add_layer(pickup, pickup_cmap, "Taxi Pickups", "count_per_day", "<b>Taxi Pickup</b><br>Pickups/Day: {count_per_day:.1f}").add_to(m)
add_layer(dropoff, dropoff_cmap, "Taxi Drop-offs", "count_per_day", "<b>Taxi Drop-off</b><br>Dropoffs/Day: {count_per_day:.1f}").add_to(m)
add_layer(train_df, train_cmap, "Train Boardings", "train_total_per_day", "<b>Station</b><br>Rides/Day: {train_total_per_day:.1f}").add_to(m)

folium.LayerControl().add_to(m)

st_data = st_folium(m, width=1200, height=700)

# ╰────────────────────────────────────────────────────────╯

# ╭────────────────────── DASHBOARD GRAPHS ───────────────────╮
st.subheader("📈 Ridership Statistics")

tab1, tab2, tab3 = st.tabs(["Bus", "Taxi", "Train"])

with tab1:
    st.markdown("**Bus Boardings Distribution**")
    fig, ax = plt.subplots()
    ax.hist(bus["count_per_day"], bins=30, color="skyblue", edgecolor="black")
    ax.set_xlabel("Boardings per Day")
    ax.set_ylabel("Number of Stops")
    st.pyplot(fig)

with tab2:
    st.markdown("**Taxi Pickups vs Drop-offs Distribution**")
    fig, ax = plt.subplots()
    ax.hist(pickup["count_per_day"], bins=30, alpha=0.7, label="Pickups", color="gold")
    ax.hist(dropoff["count_per_day"], bins=30, alpha=0.7, label="Drop-offs", color="lightgreen")
    ax.set_xlabel("Events per Day")
    ax.set_ylabel("Number of Locations")
    ax.legend()
    st.pyplot(fig)

with tab3:
    st.markdown("**Train Ridership Distribution**")
    fig, ax = plt.subplots()
    ax.hist(train_df["train_total_per_day"], bins=30, color="tomato", edgecolor="black")
    ax.set_xlabel("Rides per Day")
    ax.set_ylabel("Number of Stations")
    st.pyplot(fig)
# ╰────────────────────────────────────────────────────────╯
