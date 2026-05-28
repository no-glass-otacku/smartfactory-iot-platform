# 🏭 스마트팩토리 IoT 플랫폼

**스마트팩토리 설비의 실시간 데이터를 수집하고, AI 챗봇을 통해 이상 상황을 빠르게 대응하는 시스템입니다.**

---

## 📋 프로젝트 구조

```
smartfactory-iot-platform/
├── producer/              # IoT 데이터 수집 및 전송
├── chatbot/              # AI 챗봇 (RAG 기반 지원)
├── dashboard/            # 모니터링 대시보드
└── smart_manufacturing_data.csv  # 샘플 데이터
```

---

## 🚀 빠른 시작

### 1️⃣ 설치 준비

**필요한 것:**
- Python 3.8 이상
- Azure IoT Hub 계정
- Azure OpenAI 계정 (선택사항)

### 2️⃣ producer (데이터 수집) 설정

```bash
cd producer

# 가상 환경 생성
python -m venv .venv

# 가상 환경 활성화
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 필요한 라이브러리 설치
pip install -r requirements.txt
```

**`.env` 파일 생성** (producer 폴더에):

```env
CONNECTION_STRING=your_azure_iot_hub_connection_string
CSV_PATH=../smart_manufacturing_data.csv
SPEED_FACTOR=15
NOISE_SEED=42
```

- `CONNECTION_STRING`: Azure IoT Hub 연결 문자열
- `CSV_PATH`: CSV 데이터 파일 경로
- `SPEED_FACTOR`: 데이터 전송 속도 (숫자가 작을수록 빠름)
- `NOISE_SEED`: 노이즈 주입 시드값

**실행:**

```bash
python producer.py
```

이 스크립트는:
- CSV 파일에서 제조 설비 데이터를 읽습니다
- 실시간 데이터를 Azure IoT Hub로 전송합니다
- 5% 확률로 오염된 데이터(노이즈)를 섞어서 전송합니다

---

### 3️⃣ chatbot (AI 챗봇) 설정

```bash
cd chatbot

# 가상 환경 생성 및 활성화
python -m venv venv

# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 필요한 라이브러리 설치
pip install -r requirements.txt
```

**`.env` 파일 생성** (chatbot 폴더에):

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_API_VERSION=2024-08-01-preview
OPENAI_API_BASE=your_azure_openai_endpoint
AZURE_SEARCH_SERVICE_NAME=your_search_service_name
AZURE_SEARCH_ADMIN_KEY=your_search_admin_key
AZURE_SEARCH_INDEX_NAME=smartfactory-rag-index
```

**RAG 문서 업로드:**

```bash
# Azure Blob Storage에 RAG 문서 업로드
python upload_to_ai_search.py
```

**챗봇 실행:**

```bash
# Azure Functions 활용 시
func start

# 또는 로컬 스크립트 실행
python main.py  # 구체적인 실행 방식은 프로젝트 구조에 따름
```

---

### 4️⃣ dashboard (대시보드) 실행

```bash
cd dashboard

# 필요에 따라 설정 후 실행
npm install      # (Node.js 프로젝트인 경우)
npm start
```

또는 웹 브라우저에서 대시보드 URL에 접속합니다.

---

## 📊 주요 기능

### 🔴 Producer (데이터 수집)

| 기능 | 설명 |
|------|------|
| **IoT 데이터 전송** | CSV 파일의 제조 설비 센서 데이터를 Azure IoT Hub로 실시간 전송 |
| **노이즈 주입** | 5% 확률로 비정상 데이터를 섞어서 현실적인 상황 시뮬레이션 |
| **속도 제어** | `SPEED_FACTOR`로 전송 속도 조절 가능 |
| **재현성** | `NOISE_SEED`로 동일한 노이즈 패턴 재현 가능 |

**수집되는 데이터:**
- 🌡️ 온도 (temperature)
- 📈 진동 (vibration)
- 💧 습도 (humidity)
- 🔧 압력 (pressure)
- ⚡ 에너지 소비량 (energy_consumption)
- 🏷️ 설비 ID (machine_id)
- 🕐 타임스탐프 (timestamp)

---

### 🤖 Chatbot (AI 챗봇)

**RAG(Retrieval-Augmented Generation) 기반** - 설비 운영 매뉴얼과 수리 이력을 학습하여 지원합니다.

#### 설비 고장 대응 시나리오

| 고장 유형 | 설명 |
|----------|------|
| **Overheating** | 과열 문제 - 냉각 계통 점검 |
| **VibrationIssue** | 진동 이상 - 베어링/축 점검 |
| **PressureDrop** | 압력 저하 - 누수/벨브 점검 |
| **ElectricalFault** | 전기 장애 - 전원/배선 점검 |
| **Normal** | 정상 작동 |

#### 챗봇에게 물어볼 수 있는 질문

```
"M-014에서 Overheating 알림이 왔어. 지금 당장 뭐부터 해야 해?"
→ 📋 즉각 조치 순서 (STEP 1~5) 제공

"이 기계 전에도 같은 문제 있었어?"
→ 🔍 수리 이력 및 반복 발생 패턴 제공

"냉각 계통 점검 업체 연락처를 알려줘. 긴급이야."
→ 📞 응급 대응 업체 정보 및 출동 시간 제공

"토출 온도 100도 넘었어. 어떻게 해?"
→ ⚠️ 에스컬레이션 기준 및 모니터링 방법 제공
```

---

### 📊 Dashboard (대시보드)

실시간 설비 모니터링 및 상태 관제를 제공합니다.

- 📉 센서 데이터 실시간 그래프
- 🚨 이상 알림 즉시 표시
- 📋 설비별 상태 현황
- 📞 챗봇 통합 지원

---

## 📂 데이터 흐름

```
CSV 파일 (smart_manufacturing_data.csv)
    ↓
Producer (producer.py)
    ↓
Azure IoT Hub
    ↓
┌─────────────────────────┐
│                         │
├→ Dashboard (모니터링)   │
│                         │
└→ Chatbot (AI 대응)      │
    - Azure AI Search (RAG 벡터 DB)
    - Azure OpenAI (응답 생성)
```

---

## 🔧 환경 변수 전체 목록

### Producer (producer/.env)

```env
# Azure IoT Hub 연결
CONNECTION_STRING=HostName=your-hub.azure-devices.net;SharedAccessKeyName=owner;SharedAccessKey=xxxxx

# 데이터 파일 경로
CSV_PATH=../smart_manufacturing_data.csv

# 전송 속도 (ms, 작을수록 빠름)
SPEED_FACTOR=15

# 노이즈 주입 시드 (재현성을 위한 고정값)
NOISE_SEED=42
```

### Chatbot (chatbot/.env)

```env
# Azure OpenAI 설정
OPENAI_API_KEY=your-api-key
OPENAI_API_VERSION=2024-08-01-preview
OPENAI_API_BASE=https://your-resource.openai.azure.com/

# Azure AI Search 설정 (RAG 벡터 DB)
AZURE_SEARCH_SERVICE_NAME=your-search-service
AZURE_SEARCH_ADMIN_KEY=your-search-key
AZURE_SEARCH_INDEX_NAME=smartfactory-rag-index
```

---

## 📝 CSV 데이터 형식

`smart_manufacturing_data.csv` 예시:

```csv
machine_id,timestamp,temperature,vibration,humidity,pressure,energy_consumption
M-001,2024-01-15 09:00:00,72.5,2.1,45.3,8.2,1250.5
M-001,2024-01-15 09:05:00,73.1,2.0,45.5,8.1,1255.2
M-014,2024-01-15 09:00:00,85.2,3.5,48.1,7.9,1320.8
...
```

---

## 🐛 문제 해결

### Producer 연결 실패

```
❌ 오류: Connection string not found
✅ 해결: .env 파일의 CONNECTION_STRING이 올바른지 확인하세요.
```

### Chatbot 응답이 없음

```
❌ 오류: Azure OpenAI API 오류
✅ 해결: 
  1. API 키와 엔드포인트가 올바른지 확인
  2. Azure OpenAI 배포 이름 확인
  3. 모델이 배포되어 있는지 확인 (gpt-4o-mini 권장)
```

### RAG 검색 결과 없음

```
❌ 오류: 검색 인덱스가 비어있음
✅ 해결: upload_to_ai_search.py 실행하여 RAG 문서 업로드
```

---

## 📚 추가 참고자료

- **RAG 설계명세서**: `chatbot/RAG_설계명세서.md`
  - 청킹 전략
  - 메타데이터 설계
  - Azure AI Search 인덱스 스키마

---

## 📄 라이선스

이 프로젝트는 LICENSE 파일을 따릅니다.

---

## 💡 팁

### Producer 성능 최적화

- `SPEED_FACTOR` 감소 → 데이터 전송 속도 증가
- `SPEED_FACTOR` 증가 → 데이터 전송 속도 감소

**예시:**
```python
SPEED_FACTOR=5   # 빠름 (5ms 간격)
SPEED_FACTOR=30  # 느림 (30ms 간격)
```

### Chatbot 정확도 향상

1. RAG 문서 최신 유지
2. 청크 메타데이터 정확한 입력
3. 질문을 구체적으로 (설비 ID, 고장 유형 포함)

---

**🎉 프로젝트 시작이 준비되었습니다!**

궁금한 점이 있으시면 chatbot에 문의하거나, 각 폴더의 기술 문서를 참고하세요.
