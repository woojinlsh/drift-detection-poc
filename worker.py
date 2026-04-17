import time
import json
import os
import requests
from google import genai
from PIL import Image
import io
import datetime
import zoneinfo

# 💡 Render 환경의 지속성 디스크(Persistent Disk) 경로
CONFIG_FILE = "/opt/render/project/src/data/config.json"

def get_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"설정 파일 읽기 오류: {e}")
    return None

def get_verkada_token(api_key):
    url = "https://api.verkada.com/token"
    headers = {"x-api-key": api_key, "accept": "application/json"}
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("token")
    return None

def get_verkada_thumbnail(token, cam_id, time_sec):
    url = "https://api.verkada.com/cameras/v1/footage/thumbnails"
    headers = {"x-verkada-auth": token, "accept": "image/jpeg"}
    params = {"camera_id": cam_id, "timestamp": time_sec, "resolution": "hi-res"}
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return Image.open(io.BytesIO(response.content))
    elif response.status_code == 303:
        img_url = response.json().get("url")
        img_res = requests.get(img_url)
        return Image.open(io.BytesIO(img_res.content))
    return None

def compare_with_gemini(api_key, model_name, prompt, images):
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model_name, 
            contents=[prompt] + images
        )
        result_text = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(result_text)
    except Exception as e:
        print(f"[Gemini Error] 모델({model_name}) 실행 중 오류: {e}")
        return None

def send_to_verkada_helix(api_key, cam_id, event_uid, time_ms, changed_status, desc_1, desc_2, org_id):
    url = "https://api.verkada.com/cameras/v1/video_tagging/event"
    params = {"org_id": org_id}
    headers = {
        "x-verkada-auth": api_key, # Token 대신 원본 API Key 사용
        "content-type": "application/json"
    }
    payload = {
        "attributes": {
            "changed": changed_status,
            "description": desc_1,
            "description_cont": desc_2
        },
        "event_type_uid": event_uid,
        "camera_id": cam_id,
        "time_ms": time_ms 
    }
    return requests.post(url, headers=headers, params=params, json=payload)

def run_scheduler():
    print("🚀 Background Worker (스케줄러) 가 시작되었습니다...")
    
    while True:
        config = get_config()
        
        if not config or not config.get("is_running"):
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 대기 중... (자동 실행 설정이 꺼져 있습니다)")
            time.sleep(10) # 설정이 꺼져있을 땐 10초마다 재확인
            continue

        try:
            local_tz = zoneinfo.ZoneInfo(config.get("timezone", "Asia/Seoul"))
            now = datetime.datetime.now(local_tz)
            interval_mins = config.get("interval_minutes", 5)
            
            curr_sec = int(now.timestamp())
            curr_ms = int(now.timestamp() * 1000)
            
            prev_sec = curr_sec - (interval_mins * 60)
            base_sec = int(config.get("baseline_time_ms", 0) / 1000)

            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 자동 분석 루틴 시작...")
            
            v_token = get_verkada_token(config["verkada_api_key"])
            if not v_token:
                raise Exception("Verkada 토큰 발급에 실패했습니다.")

            # 이미지 수집
            images = []
            img_base = get_verkada_thumbnail(v_token, config["verkada_camera_id"], base_sec)
            if img_base: images.append(img_base)
            
            if config.get("compare_count", 2) == 3:
                img_prev = get_verkada_thumbnail(v_token, config["verkada_camera_id"], prev_sec)
                if img_prev: images.append(img_prev)
                
            img_curr = get_verkada_thumbnail(v_token, config["verkada_camera_id"], curr_sec)
            if img_curr: images.append(img_curr)

            if len(images) < config.get("compare_count", 2):
                raise Exception("카메라 이미지를 충분히 가져오지 못했습니다.")

            # AI 분석
            model_to_use = config.get("gemini_model", "gemini-2.5-flash")
            gemini_result = compare_with_gemini(config["gemini_api_key"], model_to_use, config["prompt"], images)
            
            if gemini_result:
                changed = gemini_result.get("changed", "no")
                full_desc = gemini_result.get("description", "설명 없음")
                
                # 250자 단위 자르기
                full_desc = full_desc.replace('\n', ' ').strip()
                desc_1 = full_desc[:250]
                desc_2 = full_desc[250:500] if len(full_desc) > 250 else ""
                
                print(f" - 분석 결과: Changed({changed.upper()})")
                
                # Helix 전송
                helix_res = send_to_verkada_helix(
                    config["verkada_api_key"], 
                    config["verkada_camera_id"], 
                    config["helix_event_type_uid"], 
                    curr_ms, 
                    changed, desc_1, desc_2, 
                    config["verkada_org_id"]
                )
                
                if helix_res.status_code in [200, 201, 202]:
                    print(" - ✅ Helix 이벤트 기록 완료")
                else:
                    print(f" - ❌ Helix 전송 실패 ({helix_res.status_code}): {helix_res.text}")
                    
        except Exception as e:
            print(f" - ❌ 루틴 실행 중 에러: {e}")

        # 다음 실행 시점까지 안전하게 대기
        wait_seconds = interval_mins * 60
        print(f"대기 중... (다음 분석은 {interval_mins}분 뒤에 실행됩니다)")
        time.sleep(wait_seconds)

if __name__ == "__main__":
    run_scheduler()
