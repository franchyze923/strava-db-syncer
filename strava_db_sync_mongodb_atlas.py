import os
import requests
from datetime import datetime
import polyline
import time
from pymongo import MongoClient
import logging

# -----------------------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------------------
DATABASE_URL = os.environ.get('DATABASE_URL', '')
STRAVA_CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID', '')
STRAVA_CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET', '')
STRAVA_REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN', '')
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACCESS_TOKEN = None  # This will be updated after refreshing
SYNC_INTERVAL = int(os.environ.get('SYNC_INTERVAL', 6)) * 3600  # Default to 6 hours (4x per day)
ACTIVITIES_PER_PAGE = int(os.environ.get('ACTIVITIES_PER_PAGE', 200))  # Default to 50 activities per page

# -----------------------------------------------------------------------------
# 2. Logging Setup
# -----------------------------------------------------------------------------
def setup_logging():
    os.makedirs('/logs', exist_ok=True)
    log_filename = f"/logs/sync_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )

# -----------------------------------------------------------------------------
# 3. MongoDB Setup
# -----------------------------------------------------------------------------
def connect_to_db():
    try:
        client = MongoClient(DATABASE_URL)
        db = client.strava_db
        return db
    except Exception as e:
        logging.error(f"Error connecting to MongoDB: {e}")
        exit()

def initialize_db():
    db = connect_to_db()
    db.activities.create_index("id", unique=True)
    logging.info("Database initialized.")

# -----------------------------------------------------------------------------
# 4. Refresh Access Token
# -----------------------------------------------------------------------------
def refresh_access_token():
    global STRAVA_ACCESS_TOKEN
    logging.info("Refreshing access token...")
    payload = {
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "refresh_token": STRAVA_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    response = requests.post(STRAVA_TOKEN_URL, data=payload)

    if response.status_code == 200:
        token_data = response.json()
        STRAVA_ACCESS_TOKEN = token_data["access_token"]
        logging.info("Access token refreshed successfully.")
    else:
        logging.error(f"Error refreshing token: {response.status_code}, {response.text}")
        exit()

# -----------------------------------------------------------------------------
# 5. Fetch Activities from Strava
# -----------------------------------------------------------------------------
def fetch_activities(page=1, per_page=50):
    url = f"https://www.strava.com/api/v3/athlete/activities?page={page}&per_page={per_page}"
    headers = {"Authorization": f"Bearer {STRAVA_ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        logging.error(f"Error fetching activities: {response.status_code}, {response.text}")
        return []

# -----------------------------------------------------------------------------
# 6. Save Activities to MongoDB
# -----------------------------------------------------------------------------
def save_activities_to_db(activities):
    db = connect_to_db()
    collection = db.activities

    for activity in activities:
        try:
            # Extract polyline and decode it
            map_data = activity.get('map', {})
            polyline_data = map_data.get('summary_polyline')
            decoded_polyline = polyline.decode(polyline_data) if polyline_data else None

            # Insert activity into the database
            activity_document = {
                "id": activity['id'],
                "name": activity['name'],
                "type": activity['type'],
                "distance": activity.get('distance'),
                "moving_time": activity.get('moving_time'),
                "elapsed_time": activity.get('elapsed_time'),
                "total_elevation_gain": activity.get('total_elevation_gain'),
                "sport_type": activity.get('sport_type'),
                "start_date": datetime.strptime(activity['start_date'], "%Y-%m-%dT%H:%M:%SZ"),
                "start_date_local": datetime.strptime(activity['start_date_local'], "%Y-%m-%dT%H:%M:%S%z"),
                "timezone": activity.get('timezone'),
                "map": map_data,  # Store map as JSON
                "polyline": polyline_data,  # Store the raw polyline string
                "decoded_polyline": decoded_polyline,  # Store decoded polyline as JSON
                "gear": activity.get('gear'),  # Store gear as JSON
                "average_speed": activity.get('average_speed'),
                "max_speed": activity.get('max_speed'),
                "average_cadence": activity.get('average_cadence'),
                "average_heartrate": activity.get('average_heartrate'),
                "max_heartrate": activity.get('max_heartrate'),
                "calories": activity.get('calories'),
                "raw_data": activity  # Store raw activity data as JSON
            }
            collection.update_one({"id": activity['id']}, {"$set": activity_document}, upsert=True)
            logging.info(f"Saved activity {activity['id']} - {activity['name']} to the database.")
        except Exception as e:
            logging.error(f"Error saving activity {activity['id']}: {e}")

# -----------------------------------------------------------------------------
# 7. Sync Activities
# -----------------------------------------------------------------------------
def sync_activities():
    logging.info(f"Starting sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}...")

    # Refresh the access token
    refresh_access_token()

    page = 1

    while True:
        logging.info(f"Fetching page {page}...")
        activities = fetch_activities(page, ACTIVITIES_PER_PAGE)

        if not activities:
            logging.info("No more activities to fetch. Sync complete.")
            break

        save_activities_to_db(activities)
        page += 1

    logging.info(f"Sync complete at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.")

# -----------------------------------------------------------------------------
# 8. Main Function: Sync Every Interval
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    setup_logging()
    initialize_db()

    while True:
        sync_activities()
        logging.info(f"Waiting {SYNC_INTERVAL // 3600} hours for the next sync...")
        time.sleep(SYNC_INTERVAL)