from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
from pymongo import MongoClient
from pydantic import BaseModel
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import os
import logging
from logging.handlers import RotatingFileHandler

# -----------------------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")  # Default to local MongoDB if env variable is not set
DATABASE_NAME = "strava_db"
COLLECTION_NAME = "activities"
LOG_DIR = os.getenv("LOG_DIR", "./logs")

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

# -----------------------------------------------------------------------------
# 2. Logging Setup
# -----------------------------------------------------------------------------
def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_filename = f"{LOG_DIR}/api_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    handler = RotatingFileHandler(log_filename, maxBytes=10*1024*1024, backupCount=5)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(handler)
    logging.getLogger().addHandler(console_handler)

setup_logging()

# -----------------------------------------------------------------------------
# 3. FastAPI App
# -----------------------------------------------------------------------------
app = FastAPI()

# -----------------------------------------------------------------------------
# 4. Pydantic Models for Validation
# -----------------------------------------------------------------------------
class Activity(BaseModel):
    id: int
    name: str
    type: str
    distance: float
    moving_time: int
    elapsed_time: int
    total_elevation_gain: float
    sport_type: str
    start_date: str
    start_date_local: str
    timezone: str
    map: Optional[dict] = None
    polyline: Optional[str] = None
    decoded_polyline: Optional[List[List[float]]] = None
    average_speed: Optional[float] = None
    max_speed: Optional[float] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    calories: Optional[float] = None
    photos: Optional[List[str]] = None

# -----------------------------------------------------------------------------
# 5. API Endpoints
# -----------------------------------------------------------------------------

@app.get("/")
def read_root():
    logging.info("Root endpoint accessed")
    return {"message": "Welcome to the Strava Activities API!"}


@app.get("/activities", response_model=List[Activity])
def get_activities(
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Number of activities to return (default: all)"),
    offset: int = Query(0, ge=0, description="Number of activities to skip for pagination"),
    include_polyline: bool = Query(False, description="Include decoded_polyline in the response")
):
    """
    Get activities with optional pagination. Default is to return all activities.
    """
    logging.info(f"Fetching activities with limit={limit}, offset={offset}, include_polyline={include_polyline}")
    
    # If no limit is provided, fetch all activities
    if limit is None:
        activities = list(collection.find().skip(offset))
    else:
        activities = list(collection.find().skip(offset).limit(limit))
    
    for activity in activities:
        activity["_id"] = str(activity["_id"])  # Convert ObjectId to string
        # Convert datetime fields to ISO format
        if "start_date" in activity and isinstance(activity["start_date"], datetime):
            activity["start_date"] = activity["start_date"].isoformat()
        if "start_date_local" in activity and isinstance(activity["start_date_local"], datetime):
            activity["start_date_local"] = activity["start_date_local"].isoformat()

        # Exclude decoded_polyline unless requested
        if not include_polyline:
            activity.pop("decoded_polyline", None)

    logging.info(f"Fetched {len(activities)} activities")
    return jsonable_encoder(activities)


@app.get("/activities/{activity_id}", response_model=Activity)
def get_activity(activity_id: int):
    """Get a single activity by its Strava ID."""
    activity = collection.find_one({"id": activity_id})
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    activity["_id"] = str(activity["_id"])  # Convert ObjectId to string
    return activity


@app.post("/activities", response_model=Activity)
def create_activity(activity: Activity):
    """Add a new activity to the database."""
    if collection.find_one({"id": activity.id}):
        raise HTTPException(status_code=400, detail="Activity with this ID already exists")
    collection.insert_one(activity.dict())
    return activity


@app.put("/activities/{activity_id}", response_model=Activity)
def update_activity(activity_id: int, activity: Activity):
    """Update an existing activity."""
    result = collection.find_one_and_update(
        {"id": activity_id},
        {"$set": activity.dict()},
        return_document=True
    )
    if not result:
        raise HTTPException(status_code=404, detail="Activity not found")
    result["_id"] = str(result["_id"])  # Convert ObjectId to string
    return result


@app.delete("/activities/{activity_id}")
def delete_activity(activity_id: int):
    """Delete an activity by its Strava ID."""
    result = collection.delete_one({"id": activity_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"message": f"Activity {activity_id} deleted successfully"}

# -----------------------------------------------------------------------------
# 5. Run the Server
# -----------------------------------------------------------------------------
# To run: uvicorn script_name:app --reload

# uvicorn strava_fast_api:app --host 0.0.0.0 --port 8000 --reloa