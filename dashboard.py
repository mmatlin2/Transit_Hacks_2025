
# filepath: c:\Users\firef\OneDrive\Desktop\Transit Hacks\Transit_Hacks_2025\Transit_Hacks_2025\dashboard.py
import os, zipfile, xml.etree.ElementTree as ET, requests
import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import dash_leaflet as dl
import dash_leaflet.express as dlx
import dash_table
import plotly.express as px
from branca.colormap import LinearColormap

# ───────── CONFIG & DATA ─────────
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

BUS_DAYS     = 1
TAXI_DAYS    = 5
TRAIN_DAYS   = 353

CENTER       = (41.88, -87.63)
ZOOM         = 11
FIXED_RADIUS = 5

def parse_kmz_routes(kmz_path, color, weight=2):
    if not os.path.exists(kmz_path):
        return []
    lines = []
    with zipfile.ZipFile(kmz_path) as zf:
        kml_name = next(n for n in zf.namelist() if n.lower().endswith(".kml"))
        kml_data = zf.read(kml_name)
    root = ET.fromstring(kml_data)
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    coords_tags = root.findall(".//k:LineString/k:coordinates", ns)
    for tag in coords_tags:
        coords_text = tag.text.strip().split()
        pts = []
        for c in coords_text:
            lon, lat, *_ = map(float, c.split(","))
            pts.append([lat, lon])
        if len(pts) > 1:
            lines.append(dl.Polyline(positions=pts, color=color, weight=weight))
    return lines

def load_bus():
    if os.path.exists(LOCAL_CSV):
        df = pd.read_csv(LOCAL_CSV)
    else:
        df = pd.read_csv(
            CITY_API,
            params={"$limit": FETCH_LIMIT, "month_beginning": DATE, "daytype": DAYTYPE},
        )
    df = df[df.boardings >= THRESHOLD].copy()
    df[["lat","lon"]] = df["location"].str.strip("()").str.split(",", expand=True).astype(float)
    df.rename(columns={"boardings": "count"}, inplace=True)
    df["count_per_day"] = df["count"] / BUS_DAYS
    return df

def load_taxi():
    resp = requests.get(TAXI_API, params={"$limit": FETCH_LIMIT})
    resp.raise_for_status()
    taxi = pd.DataFrame(resp.json())
    for c in [
        "pickup_centroid_latitude","pickup_centroid_longitude",
        "dropoff_centroid_latitude","dropoff_centroid_longitude"
    ]:
        taxi[c] = pd.to_numeric(taxi[c], errors="coerce")
    taxi = taxi.dropna(subset=[
        "pickup_centroid_latitude","pickup_centroid_longitude",
        "dropoff_centroid_latitude","dropoff_centroid_longitude"
    ])
    pickup = (taxi.groupby(["pickup_centroid_latitude","pickup_centroid_longitude"])
              .size().reset_index(name="count"))
    pickup.columns = ["lat","lon","count"]
    dropoff = (taxi.groupby(["dropoff_centroid_latitude","dropoff_centroid_longitude"])
               .size().reset_index(name="count"))
    dropoff.columns = ["lat","lon","count"]
    pickup["count_per_day"]  = pickup["count"]  / TAXI_DAYS
    dropoff["count_per_day"] = dropoff["count"] / TAXI_DAYS
    return pickup, dropoff

def load_train():
    if os.path.exists(TRAIN_CSV):
        stations = pd.read_csv(TRAIN_CSV)[["MAP_ID","STATION_NAME","Location"]].drop_duplicates()
        stations.columns = ["station_id","stationname","location"]
        stations["station_id"] = pd.to_numeric(stations["station_id"], errors="coerce").fillna(0).astype(int)
        stations[["lat","lon"]] = stations["location"].str.extract(r"\(\s*([\d\.\-]+)\s*,\s*([\d\.\-]+)\s*\)").astype(float)

        resp = requests.get(TRAIN_API, params={"$limit": FETCH_LIMIT})
        resp.raise_for_status()
        rides = pd.DataFrame(resp.json())
        rides["station_id"] = pd.to_numeric(rides["station_id"], errors="coerce").fillna(0).astype(int)
        rides["rides"]      = pd.to_numeric(rides["rides"], errors="coerce").fillna(0)
        
        g = rides.groupby("station_id", as_index=False)["rides"].sum().rename(columns={"rides":"train_total"})
        train_df = stations.merge(g, on="station_id", how="left").fillna({"train_total":0})
        train_df["train_total_per_day"] = train_df["train_total"] / TRAIN_DAYS
    else:
        train_df = pd.DataFrame(columns=[
            "station_id","stationname","lat","lon",
            "train_total","train_total_per_day"
        ])
    return train_df

def summary_table(series):
    df_desc = series.describe().reset_index()
    df_desc.columns = ["Statistic", "Value"]
    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in df_desc.columns],
        data=df_desc.to_dict("records"),
        style_table={"width": "200px"},
        style_cell={"textAlign": "left", "padding": "6px"},
        style_header={"backgroundColor": "#f0f0f0", "fontWeight": "bold"}
    )

bus_df = load_bus()
pickup_df, dropoff_df = load_taxi()
train_df = load_train()

bus_cmap     = LinearColormap(["lightblue","darkblue"],     vmin=bus_df["count_per_day"].min(),     vmax=bus_df["count_per_day"].max())
pickup_cmap  = LinearColormap(["yellow","red"],             vmin=pickup_df["count_per_day"].min(),  vmax=pickup_df["count_per_day"].max())
dropoff_cmap = LinearColormap(["lightgreen","darkgreen"],    vmin=dropoff_df["count_per_day"].min(), vmax=dropoff_df["count_per_day"].max())
train_cmap   = LinearColormap(["orange","red"],             vmin=train_df["train_total_per_day"].min(), vmax=train_df["train_total_per_day"].max())

def create_markers(df, lat_col, lon_col, val_col, cmap, label):
    markers = []
    for _, row in df.iterrows():
        color_val = cmap(row[val_col])
        markers.append(
            dl.CircleMarker(
                center=(row[lat_col], row[lon_col]),
                radius=FIXED_RADIUS,
                color=color_val,
                fillColor=color_val,
                fillOpacity=0.7,
                children=[dl.Tooltip(f"{label}: {row[val_col]:.1f}")]
            )
        )
    return markers

bus_markers     = create_markers(bus_df,      "lat", "lon", "count_per_day",       bus_cmap,     "Bus Boardings/Day")
pickup_markers  = create_markers(pickup_df,   "lat", "lon", "count_per_day",       pickup_cmap,  "Taxi Pickups/Day")
dropoff_markers = create_markers(dropoff_df,  "lat", "lon", "count_per_day",       dropoff_cmap, "Taxi Dropoffs/Day")
train_markers   = create_markers(train_df,    "lat", "lon", "train_total_per_day", train_cmap,   "Train Rides/Day")

bus_route_lines  = parse_kmz_routes(BUS_KMZ,  "#2b7bba", 2)
rail_route_lines = parse_kmz_routes(RAIL_KMZ, "#e34a33", 3)

layers = [
    dl.LayerGroup(bus_markers,     id="bus-markers"),
    dl.LayerGroup(pickup_markers,  id="pickup-markers"),
    dl.LayerGroup(dropoff_markers, id="dropoff-markers"),
    dl.LayerGroup(train_markers,   id="train-markers"),
    dl.LayerGroup(bus_route_lines, id="bus-routes"),
    dl.LayerGroup(rail_route_lines,id="rail-routes"),
]

def legend_div(cmap, label):
    n_steps = 6
    step_values = [cmap.vmin + i*(cmap.vmax-cmap.vmin)/(n_steps-1) for i in range(n_steps)]
    gradient_boxes = []
    for val in step_values:
        color = cmap(val)
        gradient_boxes.append(html.Div(style={
            "backgroundColor": color, "width": "20px", "height": "20px",
            "display": "inline-block", "marginRight": "2px"}))
    return html.Div([
        html.B(label),
        html.Br(),
        html.Span(f"{cmap.vmin:.1f}"),
        html.Span(" → ", style={"margin":"0 5px"}),
        html.Span(f"{cmap.vmax:.1f}"),
        html.Br(),
        *gradient_boxes
    ], style={"padding":"4px","border":"1px solid #ccc","marginRight":"15px","display":"inline-block"})

app = dash.Dash(__name__)
app.title = "Chicago Transit Dashboard"

app.layout = html.Div([
    html.H1("Chicago Transit Ridership Dashboard", style={"textAlign": "center"}),

    dl.Map([
        dl.LayersControl([
            dl.BaseLayer(
                dl.TileLayer(
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                    attribution="© OpenStreetMap contributors"
                ), name="OpenStreetMap", checked=True
            ),
            dl.BaseLayer(
                dl.TileLayer(
                    url="https://cartocdn_basemaps.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png",
                    attribution="© CARTO"
                ), name="Carto Light", checked=False
            ),
            # Overlays for data markers:
            dl.Overlay(layers[0], name="Bus Boardings",     checked=True),
            dl.Overlay(layers[1], name="Taxi Pickups",      checked=False),
            dl.Overlay(layers[2], name="Taxi Dropoffs",     checked=False),
            dl.Overlay(layers[3], name="Train Ridership",   checked=False),
            # Overlays for route lines:
            dl.Overlay(layers[4], name="Bus Routes",        checked=False),
            dl.Overlay(layers[5], name="Rail Routes",       checked=False),
        ], position="topleft")
    ],
    center=CENTER, zoom=ZOOM,
    style={"height":"600px", "width":"100%", "margin":"auto"}),

    html.Div([
        legend_div(bus_cmap,     "Bus Boardings/Day"),
        legend_div(pickup_cmap,  "Taxi Pickups/Day"),
        legend_div(dropoff_cmap, "Taxi Dropoffs/Day"),
        legend_div(train_cmap,   "Train Rides/Day")
    ], style={"textAlign":"center", "marginTop":"10px"}),

    html.H2("Data Analysis", style={"marginTop":"20px"}),
    dcc.Tabs([
        dcc.Tab(label="Bus Boardings", children=[
            dcc.Graph(
                figure=px.histogram(
                    bus_df, x="count_per_day", nbins=30,
                    title="Distribution of Bus Boardings (per day)",
                    labels={"count_per_day": "Boardings per day"}
                )
            )
        ]),
        dcc.Tab(label="Taxi Pickups & Dropoffs", children=[
            dcc.Graph(figure=px.histogram(
                pd.concat([
                    pickup_df.assign(type="Pickup"),
                    dropoff_df.assign(type="Dropoff")
                ]),
                x="count_per_day", color="type", nbins=30, barmode="overlay",
                title="Distribution of Taxi Pickups & Dropoffs (per day)",
                labels={"count_per_day": "Events per day"}
            ))
        ]),
        dcc.Tab(label="Train Rides", children=[
            dcc.Graph(
                figure=px.histogram(
                    train_df, x="train_total_per_day", nbins=30,
                    title="Distribution of Train Rides (per day)",
                    labels={"train_total_per_day": "Rides per day"}
                )
            )
        ])
    ]),

    html.H2("Summary Statistics", style={"marginTop":"20px"}),
    html.Div([
        html.Div([
            html.H4("Bus Boardings"),
            summary_table(bus_df["count_per_day"])
        ], style={"marginRight":"40px"}),

        html.Div([
            html.H4("Taxi Pickups"),
            summary_table(pickup_df["count_per_day"])
        ], style={"marginRight":"40px"}),

        html.Div([
            html.H4("Taxi Dropoffs"),
            summary_table(dropoff_df["count_per_day"])
        ], style={"marginRight":"40px"}),

        html.Div([
            html.H4("Train Rides"),
            summary_table(train_df["train_total_per_day"])
        ]),
    ], style={"display":"flex"})
])

if __name__ == "__main__":
    app.run(debug=True)
