import os
import sys
import json
import urllib.request
import urllib.error

# Add parent folder of web_app to path
sys.path.append(r"c:\Users\bisha\Desktop\Traffic-Signal-Violation-Detection-System-master")

from backend.database import DatabaseManager

def run_tests():
    print("=== STARTING BACKEND REST API ENDPOINT TESTS ===")
    
    # 1. Initialize Database & Insert test mock violation
    db = DatabaseManager()
    db.clear_all_violations()
    
    mock_id = "VIO-TEST-9999"
    mock_data = {
        "violation_id": mock_id,
        "video_filename": "camera-test.mp4",
        "location": "Test Intersection",
        "violation_type": "Wrong Way Crossing",
        "vehicle_type": "car",
        "license_plate": "TEST9999",
        "confidence": 85.0,
        "timestamp_in_video": "00:05",
        "challan_status": "PENDING",
        "challan_amount": 500.0,
        "challan_number": "CH-TEST-9999",
        "crop_url": "/static/violations/test_crop.jpg",
        "detail_url": f"http://127.0.0.1:8000/violation/{mock_id}",
        "frame_count": 150,
        "centroid_x": 200,
        "centroid_y": 300,
        "box_coords": "100,200,300,400",
        "violator_name": "Test Citizen",
        "violator_mobile": "+91 99999 88888",
        "query_status": "NONE",
        "query_chat": "[]"
    }
    
    print(f"1. Inserting mock violation {mock_id} directly to DB...")
    db.insert_violation(mock_data)
    
    base_url = "http://127.0.0.1:8000"
    
    # Helper for JSON GET
    def api_get(path):
        req = urllib.request.Request(f"{base_url}{path}")
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
            
    # Helper for JSON POST
    def api_post(path, data):
        req_data = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(
            f"{base_url}{path}",
            data=req_data,
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())

    try:
        # 2. Test GET /api/violations
        print("\n2. Requesting GET /api/violations...")
        violations = api_get("/api/violations")
        print(f"   Response contains {len(violations)} violations.")
        assert len(violations) > 0, "Violations array is empty"
        found = any(v["violation_id"] == mock_id for v in violations)
        assert found, f"Violation {mock_id} not found in API list"
        print(f"   Successfully found {mock_id} in API response.")
        
        # 3. Test POST /violation/{violation_id}/query (Citizen raising query)
        print(f"\n3. Posting citizen query to /violation/{mock_id}/query...")
        query_res = api_post(f"/violation/{mock_id}/query", {"message": "I was not driving wrong way. Please verify."})
        print(f"   Query status response: {query_res['query_status']}")
        assert query_res["query_status"] == "UNDER_REVIEW", "Expected query status to be UNDER_REVIEW"
        assert len(query_res["chat"]) >= 2, "Expected automatic authority response to be appended"
        print("   Citizen query successfully submitted and automatic reply received.")
        
        # 4. Test POST /api/violation/{violation_id}/reply (Admin replying to query)
        print(f"\n4. Posting operator reply to /api/violation/{mock_id}/reply...")
        reply_res = api_post(
            f"/api/violation/{mock_id}/reply", 
            {"message": "We have checked the video log. You crossed the checkpoint segment correctly, this was a false alarm. Challan will be waived.", "status": "RESOLVED"}
        )
        print(f"   Reply query status response: {reply_res['query_status']}")
        assert reply_res["query_status"] == "RESOLVED", "Expected query status to be RESOLVED"
        print("   Operator response posted and case status updated to RESOLVED.")
        
        # 5. Test POST /violation/{violation_id}/pay (Waiving the challan)
        print(f"\n5. Waiving challan using POST /violation/{mock_id}/pay...")
        pay_res = api_post(f"/violation/{mock_id}/pay", {})
        print(f"   Challan status response: {pay_res['challan_status']}")
        assert pay_res["challan_status"] == "PAID", "Expected challan status to be PAID"
        print("   Challan marked as PAID (Waived) successfully.")
        
        # 6. Verify final DB sync in GET
        print("\n6. Checking database sync via GET /api/violations...")
        refreshed = api_get("/api/violations")
        item = next(v for v in refreshed if v["violation_id"] == mock_id)
        print(f"   Challan Status: {item['challan_status']}")
        print(f"   Query Status: {item['query_status']}")
        assert item["challan_status"] == "PAID", "Challan status not synced to PAID"
        assert item["query_status"] == "RESOLVED", "Query status not synced to RESOLVED"
        print("   All statuses synced and matching correctly.")
        
        print("\n=== ALL ENDPOINT VERIFICATION TESTS PASSED SUCCESSFULLY! ===")
        
    except urllib.error.URLError as e:
        print(f"\nERROR: Server connection failed ({e}). Please ensure 'run_app.py' is running before running tests.")
    except Exception as e:
        print(f"\nERROR during tests: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup mock record
        print("\nCleaning up mock records from database...")
        db.clear_all_violations()

if __name__ == "__main__":
    run_tests()
