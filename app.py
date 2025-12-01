import os
import requests
from flask import Flask, render_template, request
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

# Read WeatherAPI key from environment
API_KEY = os.getenv("WEATHER_API_KEY")


def fetch_weather(query: str, days: int = 5):
    """
    Calls WeatherAPI.com forecast endpoint for the given location query
    and number of days.
    Returns (data, error_message).
    """
    if not API_KEY:
        return None, "Weather API key is not configured. Set WEATHER_API_KEY in your .env file."

    # ⚠️ NOTE: WeatherAPI free tier usually supports up to 3 or 7–10 days.
    # Using 14 days may require a paid plan, but the code will still work.
    base_url = "https://api.weatherapi.com/v1/forecast.json"

    try:
        resp = requests.get(
            base_url,
            params={
                "key": API_KEY,
                "q": query,   # city name or ZIP code
                "days": days,
                "aqi": "no",
                "alerts": "no",
            },
            timeout=10,
        )
    except requests.RequestException as e:
        return None, f"Network error while contacting weather service: {e}"

    if resp.status_code != 200:
        # WeatherAPI sends errors in JSON as {"error": {"message": "..."}}
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


@app.route("/", methods=["GET", "POST"])
def index():
    query = ""
    weather_data = None
    error = None
    days = 5  # default view is 5-day forecast

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

    return render_template(
        "index.html",
        query=query,
        weather=weather_data,
        error=error,
        days=days,
    )


if __name__ == "__main__":
    app.run(debug=True)
