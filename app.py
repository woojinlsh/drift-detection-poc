import streamlit as st
import json
import os
import time
from google import genai

# 💡 Render 환경의 지속성 디스크(Persistent Disk) 경로
CONFIG_FILE = "/opt/render/project/src/data/config.json"

st.set_page_config(page_title="Storage Drift Detector", layout="wide")
st.title("⚙️ Storage Drift Detector 시스템 설정")

# 기존 설정 불러오기
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    # 최초 실행 시 기본값 세팅
    config = {
        "verkada_api_key": "", "gemini_api_key": "", "verkada_org_id": "",
        "verkada_camera_id": "", "helix_event_type_uid": "",
        "gemini_model": "gemini-2.5-flash",
        "interval_minutes": 5, "compare_count": 2, "timezone": "Asia/Seoul",
        "prompt": """제공된 사진들은 같은 카메라에서 다른 시간에 촬영된 것입니다.
두 사진을 비교하여 차이점이 있는지 분석해 주세요. 
응답은 반드시 아래 두 개의 키를 포함하는 엄격한 JSON 형식으로만 작성해야 합니다:
1. "changed": 차이가 있다면 "yes", 없다면 "no" (반드시 영어 소문자).
2. "description": 무엇이 변경되었는지 혹은 현재 상태가 어떤지에 대해 최대한 상세하고 구체적으로 한국어로 묘사해 주세요. 줄바꿈 기호를 사용하지 말고 자연스럽게 이어서 작성해 주세요.""",
        "is_running": False, "baseline_time_ms": 0
    }

# 1. 설정 폼 구성
with st.form("config_form"):
    st.subheader("🔑 1. API 및 모델 설정")
    col1, col2 = st.columns(2)
    with col1:
        config["verkada_api_key"] = st.text_input("Verkada API Key", value=config.get("verkada_api_key", ""), type="password")
        config["gemini_api_key"] = st.text_input("Gemini API Key", value=config.get("gemini_api_key", ""), type="password")
        
        # 최신 Gemini 모델 리스트
        model_list = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        current_model = config.get("gemini_model", "gemini-2.5-flash")
        config["gemini_model"] = st.selectbox(
            "사용할 Gemini 모델", 
            model_list, 
            index=model_list.index(current_model) if current_model in model_list else 0
        )

    with col2:
        config["verkada_org_id"] = st.text_input("Verkada Org ID", value=config.get("verkada_org_id", ""))
        config["verkada_camera_id"] = st.text_input("Verkada Camera ID", value=config.get("verkada_camera_id", ""))
        config["helix_event_type_uid"] = st.text_input("Helix Event Type UID", value=config.get("helix_event_type_uid", ""))

    st.subheader("⏲️ 2. 스케줄 및 로직 설정")
    col3, col4 = st.columns(2)
    with col3:
        config["interval_minutes"] = st.number_input("자동 검증 주기 (분)", value=config.get("interval_minutes", 5), min_value=1)
        
        tz_list = ["Asia/Seoul", "UTC", "America/New_York", "America/Los_Angeles"]
        current_tz = config.get("timezone", "Asia/Seoul")
        config["timezone"] = st.selectbox("타임존 (Timezone)", tz_list, index=tz_list.index(current_tz) if current_tz in tz_list else 0)
    with col4:
        config["compare_count"] = st.radio("비교 사진 개수", [2, 3], index=0 if config.get("compare_count", 2) == 2 else 1, help="3개 선택 시 [시작점, 직전, 현재] 3장을 비교합니다.")

    st.subheader("🤖 3. AI 분석 프롬프트")
    config["prompt"] = st.text_area("Gemini 지시문", value=config.get("prompt", ""), height=150)

    st.markdown("---")
    config["is_running"] = st.checkbox("백그라운드 자동 실행 활성화", value=config.get("is_running", False))
    
    submit = st.form_submit_button("설정 저장 및 적용", type="primary")

    if submit:
        # 실행 시작 시 현재 시간을 Baseline으로 잡음
        if config["is_running"] and config.get("baseline_time_ms", 0) == 0:
            config["baseline_time_ms"] = int(time.time() * 1000)
        
        # 실행 중지 시 Baseline 초기화
        if not config["is_running"]:
            config["baseline_time_ms"] = 0

        # 저장할 폴더가 없으면 생성 (안전망)
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
        st.success("✅ 설정이 성공적으로 저장되었습니다! 백그라운드 워커가 이 설정을 바탕으로 동작합니다.")

# 2. 실시간 모델 테스트 섹션
st.markdown("---")
st.subheader("🧪 설정 검증 및 Gemini 모델 테스트")

if st.button("🚀 Gemini 모델 통신 테스트"):
    if not config.get("gemini_api_key"):
        st.error("Gemini API Key가 없습니다. 입력 후 저장해주세요.")
    else:
        try:
            with st.spinner(f"[{config['gemini_model']}] 모델에 연결 중..."):
                client = genai.Client(api_key=config["gemini_api_key"])
                test_response = client.models.generate_content(
                    model=config["gemini_model"],
                    contents="안녕? 네가 정상적으로 연결되었는지 확인 중이야. 10글자 이내로 대답해줘."
                )
                st.success(f"✅ 통신 성공! AI 응답: {test_response.text}")
        except Exception as e:
            st.error(f"❌ 연결 실패: {e}")
