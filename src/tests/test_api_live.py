import requests
import json
import time

def test_api():
    base_url = "http://localhost:8888/api/point_mapping"
    
    print(f"Testing API at {base_url}")
    
    # 1. GET all
    try:
        response = requests.get(f"{base_url}/")
        print(f"GET Status Code: {response.status_code}")
        if response.status_code == 200:
            print("GET Response:", response.json())
        else:
            print("GET Error:", response.text)
    except Exception as e:
        print(f"GET Request failed: {e}")
        return

    # 2. POST create
    payload = {
        "target_point_code": "API_TEST_T1",
        "source_point_codes": ["API_S1", "API_S2"],
        "formula": "API_S1 + API_S2",
        "enable": True
    }
    
    try:
        print(f"POST Creating mapping...")
        response = requests.post(f"{base_url}/", json=payload)
        print(f"POST Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("POST Response:", data)
            new_id = data['id']
            
            # 3. DELETE
            print(f"DELETE mapping {new_id}...")
            del_resp = requests.delete(f"{base_url}/{new_id}")
            print(f"DELETE Status Code: {del_resp.status_code}")
        else:
            print("POST Error:", response.text)
            
    except Exception as e:
        print(f"POST/DELETE Request failed: {e}")

if __name__ == "__main__":
    test_api()
