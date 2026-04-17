import time
import json
import os
import requests
from google import genai
from PIL import Image
import io
import datetime
import zoneinfo

CONFIG_FILE = "/opt/render/project/src/data/config.json"

def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except: return None
    return None

def get_verkada_token(api_key):
    url = "https://api.verkada.com/token"
    res = requests.post(url, headers={"x-api-key": api_key, "accept": "application/json"})
    return res.json().get("token") if res.status_code == 200 else None

def get_verkada_thumbnail(token, cam_id, time_sec):
    url = "https://api.verkada.com/cameras/v1/footage/thumbnails"
    headers = {"x-verkada-auth": token, "accept": "image/jpeg"}
    params = {"camera_id": cam_id, "timestamp": time_sec, "resolution": "hi-res"}
    res = requests.get(url, headers=headers, params=params)
    if res.status_code == 200: return Image.open(io.BytesIO(res.content))
    elif res.status_code == 303: return Image.open(io.BytesIO(requests.get(res.json().get("url")).content))
    return None

def compare_with_gemini(api_key, model_name, contents):
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(model=model_name, contents=contents)
        result_text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(result_text)
    except Exception as e:
        print(f"[Gemini Error] {e}")
        return None

def send_to_verkada_helix(api_key, cam_id, event_uid, time_ms, changed, d1, d2, org_id):
    url = "https://api.verkada.com/cameras/v1/video_tagging/event"
    headers = {"x-verkada-auth": api_key, "content-type": "application/json"}
    payload = {
        "attributes": {"changed": changed, "description": d1, "description_cont": d2},
        "event_type_uid": event_uid, "camera_id": cam_id, "time_ms": time_ms
    }
    return requests.post(url, headers=headers, params={"org_id": org_id}, json=payload)

def run_scheduler():
    print("🚀 Background Worker 실행 중...")
    while True:
        config = get_config()
        if not config or not config.get("is_running"):
            time.sleep(10)
            continue

        try:
            local_tz = zoneinfo.ZoneInfo(config.get("timezone", "Asia/Seoul"))
            now = datetime.datetime.now(local_tz)
            interval = config.get("interval_minutes", 5)
            curr_sec = int(now.timestamp())
            base_sec = int(config.get("baseline_time_ms", 0) / 1000)

            v_token = get_verkada_token(config["verkada_api_key"])
            if not v_token: raise Exception("Token 실패")

            # 💡 동적 이미지 수집 (N장)
            images = []
            img_count = config.get("compare_count", 2)
            
            # 1. Baseline
            images.append(get_verkada_thumbnail(v_token, config["verkada_camera_id"], base_sec))
            # 2. 중간 지점들
            for i in range(img_count - 2, 0, -1):
                past_sec = curr_sec - (i * interval * 60)
                images.append(get_verkada_thumbnail(v_token, config["verkada_camera_id"], past_sec))
            # 3. Current
            images.append(get_verkada_thumbnail(v_token, config["verkada_camera_id"], curr_sec))

            # AI 분석용 데이터 조립
            contents = [config["prompt"]]
            for i, img in enumerate(images):
                if img:
                    contents.append(f"Image {i+1}:")
                    contents.append(img)

            res = compare_with_gemini(config["gemini_api_key"], config["gemini_model"], contents)
            if res:
                changed = res.get("changed", "no")
                f_desc = res.get("description", "분석 실패").replace('\n', ' ').strip()
                d1, d2 = f_desc[:250], f_desc[250:500]
                
                send_to_verkada_helix(config["verkada_api_key"], config["verkada_camera_id"], 
                                      config["helix_event_type_uid"], int(now.timestamp()*1000), 
                                      changed, d1, d2, config["verkada_org_id"])
                print(f"[{now}] 분석/전송 성공")
        except Exception as e: print(f"Error: {e}")
        time.sleep(config.get("interval_minutes", 5) * 60)

if __name__ == "__main__": run_scheduler()
