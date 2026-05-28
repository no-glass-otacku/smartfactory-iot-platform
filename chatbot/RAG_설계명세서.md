# RAG 챗봇 설계 명세서
## 스마트팩토리 IoT 설비 이상탐지 관제 시스템 — RAG-01

---

## 1. 청킹(Chunking) 전략

### 핵심 원칙
Azure AI Search Free 티어는 **인덱스 문서 수 10,000개 제한**이 있으므로,
청크를 너무 잘게 나누지 않고 **의미 단위(섹션 단위)** 로 나누는 전략을 사용한다.

---

### 문서별 청킹 계획

#### [A] 대응 가이드라인 5개 (Overheating / VibrationIssue / PressureDrop / ElectricalFault / Normal)

| 청크 단위 | 내용 | 예상 청크 수 |
|---|---|---|
| 섹션 1: 발생 기준 | "어떤 상태일 때 이 고장인가" | 1개/문서 |
| 섹션 2: 즉각 조치 순서 (STEP 전체) | "지금 당장 뭐부터 해야 해?" 질문 대응 핵심 | 1개/문서 |
| 섹션 3: 에스컬레이션 조건 + 모니터링 | "언제 업체 불러야 해?" 대응 | 1개/문서 |
| 섹션 4: 복구 절차 | "수리 끝났는데 다음은?" 대응 | 1개/문서 |
| 섹션 5: 반복 발생 기준 | "이 기계 전에도 같은 문제 있었어?" 보조 | 1개/문서 |

→ 가이드라인 5문서 × 5섹션 = **최대 25개 청크**

> **STEP 1~5를 하나로 합치는 이유**: 즉각 조치는 순서가 중요하므로
> 단계를 쪼개면 검색 시 일부 STEP만 가져올 위험이 있음.
> "지금 당장 뭐부터 해야 해?" 질문에는 STEP 전체가 필요함.

---

#### [B] 수리 이력 (M-014)

| 청크 단위 | 내용 | 예상 청크 수 |
|---|---|---|
| 수리 이력 건별 1개 | 1건의 수리 전체 (날짜, 원인, 조치, 비용) | 4개 (현재 이력 4건) |
| 수리 이력 요약 | 연도별 집계 + 특이사항 | 1개 |
| 정기 점검 이력 | 최근 2년 정기 점검 목록 | 1개 |

→ **최대 6개 청크**

> **건별로 쪼개는 이유**: "M-014 전에도 같은 문제 있었어?" 질문에
> 특정 날짜/원인 단위로 검색되어야 정확한 이력 응답 가능.

---

#### [C] 수리 업체 연락처

| 청크 단위 | 내용 | 예상 청크 수 |
|---|---|---|
| 업체별 1개 (A~D) | 담당 고장 유형 + 연락처 + 출동 시간 + 출장비 | 4개 |
| 고장 유형별 우선순위 표 | 어떤 고장에 어떤 업체를 불러야 하는지 | 1개 |
| 수리 의뢰 절차 | 평일/야간 절차, 필수 전달 정보 | 1개 |

→ **최대 6개 청크**

> **업체별로 쪼개는 이유**: "냉각 계통 점검 업체 연락처 알려줘" 질문에
> 한국냉열테크 청크만 정확하게 가져올 수 있음.

---

### 전체 예상 청크 수: 약 37개 (Free 티어 10,000개 제한 내 여유)

---

## 2. 메타데이터(Metadata) 설계

각 청크에 아래 메타데이터를 부착한다. 이를 통해 벡터 검색 + 필터 검색을 조합할 수 있다.

| 필드명 | 타입 | 예시값 | 용도 |
|---|---|---|---|
| `id` | String | `"overheating-steps-001"` | 청크 고유 ID |
| `doc_type` | String | `"guideline"` / `"repair_history"` / `"contact"` | 문서 종류 필터 |
| `fault_type` | String | `"Overheating"` / `"VibrationIssue"` / `"PressureDrop"` / `"ElectricalFault"` / `"Normal"` / `"All"` | 고장 유형 필터 |
| `equipment_id` | String | `"M-014"` / `"M-001~M-030"` | 설비 ID 필터 |
| `section` | String | `"즉각조치"` / `"에스컬레이션"` / `"복구절차"` / `"수리이력"` / `"연락처"` | 섹션 구분 |
| `urgency` | String | `"emergency"` / `"normal"` | 긴급 여부 분기용 |
| `content` | String | 청크 본문 텍스트 | 전문 검색 및 임베딩 원본 |
| `content_vector` | Collection(Single) | `[0.023, -0.118, ...]` | 벡터 유사도 검색용 |
| `source_file` | String | `"RAG_문서_Overheating_대응가이드라인.md"` | 출처 추적 |
| `last_modified` | String | `"2024-11-15"` | 문서 최신성 확인 |

---

## 3. Azure AI Search 인덱스 스키마 (JSON)

Azure Portal > AI Search > 인덱스 > JSON 편집기에 붙여넣는다.

```json
{
  "name": "smartfactory-rag-index",
  "fields": [
    {
      "name": "id",
      "type": "Edm.String",
      "key": true,
      "searchable": false,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "doc_type",
      "type": "Edm.String",
      "searchable": false,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "fault_type",
      "type": "Edm.String",
      "searchable": true,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "equipment_id",
      "type": "Edm.String",
      "searchable": true,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "section",
      "type": "Edm.String",
      "searchable": false,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "urgency",
      "type": "Edm.String",
      "searchable": false,
      "filterable": true,
      "retrievable": true
    },
    {
      "name": "content",
      "type": "Edm.String",
      "searchable": true,
      "filterable": false,
      "retrievable": true,
      "analyzer": "ko.microsoft"
    },
    {
      "name": "content_vector",
      "type": "Collection(Edm.Single)",
      "searchable": true,
      "retrievable": false,
      "dimensions": 1536,
      "vectorSearchProfile": "rag-vector-profile"
    },
    {
      "name": "source_file",
      "type": "Edm.String",
      "searchable": false,
      "filterable": false,
      "retrievable": true
    },
    {
      "name": "last_modified",
      "type": "Edm.String",
      "searchable": false,
      "filterable": false,
      "retrievable": true
    }
  ],
  "vectorSearch": {
    "algorithms": [
      {
        "name": "rag-hnsw",
        "kind": "hnsw",
        "hnswParameters": {
          "metric": "cosine",
          "m": 4,
          "efConstruction": 400,
          "efSearch": 500
        }
      }
    ],
    "profiles": [
      {
        "name": "rag-vector-profile",
        "algorithm": "rag-hnsw"
      }
    ]
  },
  "semantic": {
    "configurations": [
      {
        "name": "rag-semantic-config",
        "prioritizedFields": {
          "contentFields": [
            { "fieldName": "content" }
          ],
          "keywordsFields": [
            { "fieldName": "fault_type" },
            { "fieldName": "section" }
          ]
        }
      }
    ]
  }
}
```

---

## 4. 청크 샘플 — Overheating 즉각 조치 섹션

인덱스에 실제로 올라갈 청크 1개의 예시 (JSON):

```json
{
  "id": "overheating-steps-001",
  "doc_type": "guideline",
  "fault_type": "Overheating",
  "equipment_id": "M-001~M-030",
  "section": "즉각조치",
  "urgency": "emergency",
  "source_file": "RAG_문서_Overheating_대응가이드라인.md",
  "last_modified": "2024-11-15",
  "content": "## Overheating 즉각 조치 순서 (알림 수신 후 15분 이내)\n\n### STEP 1 — 현장 확인 (알림 수신 즉시)\n- 해당 설비의 운전 패널에서 토출 온도, 냉각수 온도, 오일 온도를 직접 확인한다.\n- 설비 외관에서 이상 소음, 진동, 냉각수 누수 여부를 육안 점검한다.\n- 클린룸 내 온도·습도 모니터링 패널에서 환경 편차 여부를 확인한다.\n  - 반도체 후공정 기준: 온도 23 ± 0.5°C, 습도 45 ± 5% RH 유지 필요\n  - 편차 발생 시 즉시 설비팀장에게 보고\n\n### STEP 2 — 냉각 팬 및 방열 상태 점검 (5분 이내)\n...(이하 STEP 2~5 전체 포함)..."
}
```

---

## 5. 질문 예시 → 검색 흐름 매핑

| 질문 | 예상 검색 결과 | 핵심 메타데이터 |
|---|---|---|
| "M-014에서 Overheating 알림이 왔어. 지금 당장 뭐부터 해야 해?" | Overheating 즉각조치 섹션 | `fault_type=Overheating`, `section=즉각조치` |
| "M-014 이 기기 전에도 같은 문제 있었어?" | 수리이력 M-014 Overheating 건들 | `equipment_id=M-014`, `doc_type=repair_history` |
| "냉각 계통 점검 맡길 업체 연락처 알려줘. 긴급이야." | 한국냉열테크 연락처 청크 | `doc_type=contact`, `urgency=emergency` |
| "토출 온도 100도 넘었어. 어떻게 해?" | Overheating 에스컬레이션 조건 | `fault_type=Overheating`, `section=에스컬레이션` |

---

## 6. 다음 단계 체크리스트

- [ ] **Azure OpenAI 리소스 생성** (Korea Central 권장)
  - [ ] `gpt-4o-mini` 모델 배포
  - [ ] `text-embedding-3-small` 모델 배포 (차원: 1536)
- [ ] **Azure Blob Storage 생성**
  - [ ] 컨테이너명: `rag-documents`
  - [ ] 마크다운 파일 7개 업로드
- [ ] **Azure AI Search 생성** (Free 티어: F0)
  - [ ] 위 JSON으로 인덱스 생성
  - [ ] 인덱서 실행 전 임베딩 스크립트 준비 필요 (별도 안내)
- [ ] **청킹 + 임베딩 스크립트 실행**
  - [ ] Python 스크립트로 문서 → 청크 → 벡터화 → AI Search 업로드
