import streamlit as st
import json
import os
import time
from google import genai

# Render 지속성 디스크 경로
CONFIG_FILE = "/opt/render/project/src/data/config.json"

st.set_page_config(page_title="Storage Drift Detector", layout="wide")
st.title("⚙️ Storage Drift Detector 설정 대시보드")

# 기존 설정 불러오기
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = {
        "verkada_api_key": "", "gemini_api_key": "", "verkada_org_id": "",
        "verkada_camera_id": "", "helix_event_type_uid": "",
        "gemini_model": "gemini-2.5-flash",
        "interval_minutes": 5, "compare_count": 2, "timezone": "Asia/Seoul",
        "prompt": "사진들을 시간 순서대로 비교하여 차이점을 상세히 한국어로 분석해 주세요.",
        "is_running": False, "baseline_time_ms": 0
    }

with st.form("config_form"):
    st.subheader("🔑 1. 인증 및 모델 설정")
    col1, col2 = st.columns(2)
    with col1:
        config["verkada_api_key"] = st.text_input("Verkada API Key", value=config.get("verkada_api_key", ""), type="password")
        config["gemini_api_key"] = st.text_input("Gemini API Key", value=config.get("gemini_api_key", ""), type="password")
        model_list = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        config["gemini_model"] = st.selectbox("Gemini 모델", model_list, index=model_list.index(config.get("gemini_model", "gemini-2.5-flash")))

    with col2:
        config["verkada_org_id"] = st.text_input("Verkada Org ID", value=config.get("verkada_org_id", ""))
        config["verkada_camera_id"] = st.text_input("Verkada Camera ID", value=config.get("verkada_camera_id", ""))
        config["helix_event_type_uid"] = st.text_input("Helix Event Type UID", value=config.get("helix_event_type_uid", ""))

    st.subheader("⏲️ 2. 로직 및 스케줄 설정")
    col3, col4 = st.columns(2)
    with col3:
        config["interval_minutes"] = st.number_input("검증 주기 (분)", value=config.get("interval_minutes", 5), min_value=1)
        config["timezone"] = st.selectbox("타임존", ["Asia/Seoul", "UTC"], index=0)
    with col4:
        # 💡 동적 사진 개수 설정 (2~10장)
        config["compare_count"] = st.number_input("비교 사진 개수 (2~10)", value=config.get("compare_count", 2), min_value=2, max_value=10)

    st.subheader("🤖 3. AI 분석 프롬프트")
    config["prompt"] = st.text_area("분석 지시문", value=config.get("prompt", ""), height=150)

    config["is_running"] = st.checkbox("백그라운드 자동 실행 활성화", value=config.get("is_running", False))
    
    if st.form_submit_button("설정 저장 및 적용", type="primary"):
        if config["is_running"] and config.get("baseline_time_ms", 0) == 0:
            config["baseline_time_ms"] = int(time.time() * 1000)
        if not config["is_running"]:
            config["baseline_time_ms"] = 0
            
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        st.success("✅ 설정 저장 완료!")

st.markdown("---")
st.subheader("🧪 모델 테스트")
if st.button("🚀 Gemini 연결 테스트"):
    try:
        client = genai.Client(api_key=config["gemini_api_key"])
        res = client.models.generate_content(model=config["gemini_model"], contents="연결 확인용 대답 5자 이내")
        st.success(f"연결 성공: {res.text}")
    except Exception as e:
        st.error(f"실패: {e}")
