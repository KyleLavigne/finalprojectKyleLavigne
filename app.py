import os
import requests
from flask import Flask, render_template, request
from dotenv import load_dotenv
from datetime import datetime, timezone


# matplotlib for server-side charts
import matplotlib
matplotlib.use("Agg")  # non-GUI backend for servers / PyCharm
import matplotlib.pyplot as plt

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("WEATHER_API_KEY")


def fetch_weather(query: str, days: int = 5):
    """
    Calls WeatherAPI.com forecast endpoint for the given location query
    and number of days.
    Returns (data, error_message).
    """
    if not API_KEY:
        return None, "Weather API key is not configured. Set WEATHER_API_KEY in your .env file."

    base_url = "https://api.weatherapi.com/v1/forecast.json"

    try:
        resp = requests.get(
            base_url,
            params={
                "key": API_KEY,
                "q": query,
                "days": days,
                "aqi": "no",
                "alerts": "no",
            },
            timeout=10,
        )
    except requests.RequestException as e:
        return None, f"Network error while contacting weather service: {e}"

    if resp.status_code != 200:
        try:
            err_msg = resp.json().get("error", {}).get("message", "Unknown error from weather service.")
        except Exception:
            err_msg = f"Unexpected error from weather service (status {resp.status_code})."
        return None, err_msg

    try:
        data = resp.json()
    except ValueError:
        return None, "Failed to parse response from weather service."

    return data, None


def generate_hourly_chart(day_data: dict, location_name: str) -> str | None:
    """
    Given one day's forecast data from WeatherAPI, generate an hourly
    temperature chart as a PNG in static/charts and return the filename.
    """
    hours_data = day_data.get("hour", [])
    if not hours_data:
        return None

    times_full = [h.get("time", "") for h in hours_data]
    temps = [h.get("temp_f") for h in hours_data]

    if not temps or not times_full:
        return None

    hours = [(t.split(" ")[1] if " " in t else t) for t in times_full]

    charts_dir = os.path.join(app.static_folder, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    date_str = day_data.get("date", "unknown")
    safe_loc = "".join(c for c in location_name if c.isalnum() or c in ("-", "_")).strip() or "location"
    filename = f"{safe_loc}_{date_str}.png"
    filepath = os.path.join(charts_dir, filename)

    # ---- nicer dark chart style ----
    import matplotlib.pyplot as plt
    plt.style.use("default")

    fig, ax = plt.subplots(figsize=(7.5, 3), facecolor="#020617")
    ax.set_facecolor("#020617")

    x_vals = list(range(len(temps)))
    ax.plot(x_vals, temps, color="#38bdf8", marker="o", linewidth=2)
    ax.fill_between(x_vals, temps, color="#38bdf8", alpha=0.18)

    step = max(1, len(hours) // 8)
    tick_positions = list(range(0, len(hours), step))
    tick_labels = [hours[i] for i in tick_positions]

    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=45, fontsize=8, color="#e5e7eb")
    ax.tick_params(axis="y", colors="#e5e7eb", labelsize=8)

    ax.set_ylabel("Temperature (°F)", color="#e5e7eb", fontsize=9)
    ax.set_title(f"Hourly Temperature — {date_str}", color="#e5e7eb", fontsize=10)

    for spine in ax.spines.values():
        spine.set_color("#1f2937")

    ax.grid(color="#1f2937", alpha=0.7, linestyle="--", linewidth=0.5)

    fig.tight_layout()
    fig.savefig(filepath, transparent=True)
    plt.close(fig)

    return filename


def derive_bg_class(current: dict) -> str:
  """
  Map current weather to a background theme class.
  Uses condition text + is_day flag.
  """
  if not current:
      return "default"

  text = str(current.get("condition", {}).get("text", "")).lower()
  is_day = current.get("is_day", 1)

  if any(word in text for word in ["thunder", "storm"]):
      return "storm"
  if any(word in text for word in ["snow", "blizzard", "sleet", "ice"]):
      return "snow"
  if any(word in text for word in ["rain", "drizzle", "shower"]):
      return "rain"
  if any(word in text for word in ["fog", "mist", "haze", "overcast"]):
      return "fog"
  if "cloud" in text or "overcast" in text:
      return "cloudy"
  # fallback sunny/clear
  return "clear-day" if is_day == 1 else "clear-night"



def attach_charts_to_forecast(weather_data: dict) -> None:
    """
    For each forecast day, generate an hourly chart and attach a
    'chart_image' field to the day's data, plus a human-readable date.
    """
    try:
        location_name = weather_data["location"]["name"]
        forecast_days = weather_data["forecast"]["forecastday"]
    except (KeyError, TypeError):
        return

    for day in forecast_days:
        # pretty date like "December 12, 2025"
        raw_date = day.get("date")
        if raw_date:
            try:
                dt = datetime.strptime(raw_date, "%Y-%m-%d")
                day["date_pretty"] = f"{dt.strftime('%B')} {dt.day}, {dt.year}"
            except ValueError:
                day["date_pretty"] = raw_date

        chart_filename = generate_hourly_chart(day, location_name)
        if chart_filename:
            day["chart_image"] = chart_filename

def compute_weather_map_timestamp() -> str:
        """
        Returns WeatherAPI weather-map timestamp in the form YYYYMMDDHH (UTC),
        used in the tile URL like .../{YYYYMMDDHH}/{z}/{x}/{y}.png
        """
        now_utc = datetime.now(timezone.utc)
        return now_utc.strftime("%Y%m%d%H")


@app.route("/", methods=["GET", "POST"])
def index():
    query = ""
    weather_data = None
    error = None
    days = 5  # default view is 5-day
    bg_theme = "default"

    # compute a timestamp for WeatherAPI map tiles (UTC YYYYMMDDHH)
    map_timestamp = compute_weather_map_timestamp()

    if request.method == "POST":
        query = request.form.get("location", "").strip()
        days_str = request.form.get("days", "5")

        try:
            days = int(days_str)
        except ValueError:
            days = 5

        if not query:
            error = "Please enter a city name or ZIP code."
        else:
            weather_data, error = fetch_weather(query, days=days)
            if weather_data and not error:
                attach_charts_to_forecast(weather_data)
                bg_theme = derive_bg_class(weather_data.get("current", {}))
                # (optional) recompute timestamp right when we actually have data
                map_timestamp = compute_weather_map_timestamp()

    return render_template(
        "index.html",
        query=query,
        weather=weather_data,
        error=error,
        days=days,
        bg_theme=bg_theme,
        map_timestamp=map_timestamp,
    )




if __name__ == "__main__":
    app.run(debug=True)
