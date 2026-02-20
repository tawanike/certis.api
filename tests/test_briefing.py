import requests
import time
import os

BASE_URL = "http://localhost:8000/v1"

def test_sbd_pipeline():
    # 1. Create a Matter
    print("Creating Matter...")
    matter_payload = {
        "title": "SBD Test Matter",
        "description": "Testing the Structured Brief Decomposition pipeline.",
        "jurisdiction": "USPTO",
        "matter_type": "UTILITY"
    }
    # Note: Adjust endpoint if needed (assuming /matters based on previous context)
    # The router prefix in main.py is /v1/matters (from src.matter.router)
    # Let's check src/matter/router.py to be sure of the path
    # But usually it's POST /matters
    resp = requests.post(f"{BASE_URL}/matters", json=matter_payload)
    if resp.status_code != 200:
        print(f"Failed to create matter: {resp.text}")
        return
    
    matter_id = resp.json()["id"]
    print(f"Matter Created: {matter_id}")
    
    # 2. Upload Brief
    print("Uploading Brief...")
    
    # Create a dummy file
    dummy_text = """
    Invention: Autonomous Drone Delivery System
    
    Technical Field: The present invention relates to unmanned aerial vehicles (UAVs) and logistics.
    
    Problem: Current delivery drones struggle with precise landing in urban environments due to GPS multipath errors.
    
    Solution: The system uses a visual fiducial marker landing pad and a downward-facing camera with optical flow processing to guide the drone during the final descent, independent of GPS.
    
    Components:
    - UAV (Unmanned Aerial Vehicle)
    - Camera Module
    - Onboard Processor
    - Landing Pad with Fiducial Marker
    
    Method:
    1. Drone navigates to approximate location via GPS.
    2. Drone activates downward camera.
    3. Drone detects fiducial marker.
    4. Processor calculates relative position.
    5. Drone descends adjusting position to center marker.
    """
    
    files = {
        'file': ('invention.txt', dummy_text, 'text/plain')
    }
    
    upload_url = f"{BASE_URL}/matters/{matter_id}/briefs/upload"
    resp = requests.post(upload_url, files=files)
    
    if resp.status_code == 200:
        print("Brief Uploaded and Analyzed Successfully!")
        data = resp.json()
        print(f"Brief Version ID: {data['id']}")
        print(f"Structure Data Keys: {data['structure_data'].keys()}")
    else:
        print(f"Upload Failed: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    # Give server a moment to start
    time.sleep(2) 
    test_sbd_pipeline()
