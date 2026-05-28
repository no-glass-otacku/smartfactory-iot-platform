"""
RAG 문서 청킹 + 임베딩 + Azure AI Search 업로드 스크립트
--------------------------------------------------------------
동작 방식:
  - docs/ 폴더의 마크다운 파일을 직접 읽어서 ## 헤더 단위로 청크 분리
  - 파일명에서 doc_type, fault_type, equipment_id 메타데이터 자동 추출
  - Azure OpenAI로 각 청크를 벡터화 후 AI Search에 업로드

실행 전 준비:
  pip install -r requirements.txt
  .env 파일에 키 값 입력

사용법:
  python upload_to_ai_search.py
"""

import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

load_dotenv()

# ── 환경변수 ──────────────────────────────────────────────
AOAI_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT")
AOAI_KEY         = os.getenv("AZURE_OPENAI_API_KEY")
SEARCH_ENDPOINT  = os.getenv("AZURE_SEARCH_ENDPOINT")
SEARCH_KEY       = os.getenv("AZURE_SEARCH_API_KEY")
INDEX_NAME       = "smartfactory-rag-index"
EMBED_DEPLOYMENT = "text-embedding-3-small"  # Azure에서 배포한 이름

# 마크다운 파일이 있는 폴더 (스크립트 기준 상대경로)
DOCS_DIR = Path(__file__).parent / "docs"

# ── 클라이언트 초기화 ─────────────────────────────────────
aoai_client = AzureOpenAI(
    azure_endpoint=AOAI_ENDPOINT,
    api_key=AOAI_KEY,
    api_version="2024-02-01",
)
search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=INDEX_NAME,
    credential=AzureKeyCredential(SEARCH_KEY),
)


# ════════════════════════════════════════════════════════════
# 1. 파일명 → 메타데이터 추출
#
#    파일명 패턴:
#      RAG_문서_Overheating_대응가이드라인.md  → guideline / Overheating
#      RAG_문서_Normal_정기점검_가이드라인.md  → guideline / Normal
#      RAG_문서2_수리이력_M014.md              → repair_history / M-014
#      RAG_문서3_수리업체_연락처.md            → contact / All
# ════════════════════════════════════════════════════════════

# 파일명 → (doc_type, fault_type, equipment_id, last_modified) 매핑 테이블
# 파일이 추가될 때 여기에만 항목을 추가하면 됨
FILE_META = {
    "RAG_문서_Overheating_대응가이드라인.md": {
        "doc_type": "guideline",
        "fault_type": "Overheating",
        "equipment_id": "M-001~M-030",
        "last_modified": "2024-11-15",
    },
    "RAG_문서_VibrationIssue_대응가이드라인.md": {
        "doc_type": "guideline",
        "fault_type": "VibrationIssue",
        "equipment_id": "M-001~M-030",
        "last_modified": "2024-11-15",
    },
    "RAG_문서_PressureDrop_대응가이드라인.md": {
        "doc_type": "guideline",
        "fault_type": "PressureDrop",
        "equipment_id": "M-001~M-030",
        "last_modified": "2024-11-15",
    },
    "RAG_문서_ElectricalFault_대응가이드라인.md": {
        "doc_type": "guideline",
        "fault_type": "ElectricalFault",
        "equipment_id": "M-001~M-030",
        "last_modified": "2024-11-15",
    },
    "RAG_문서_Normal_정기점검_가이드라인.md": {
        "doc_type": "guideline",
        "fault_type": "Normal",
        "equipment_id": "M-001~M-030",
        "last_modified": "2024-11-15",
    },
    "RAG_문서2_수리이력_M014.md": {
        "doc_type": "repair_history",
        "fault_type": "All",       # 건별 파싱 시 개별 fault_type으로 덮어씀
        "equipment_id": "M-014",
        "last_modified": "2024-12-10",
    },
    "RAG_문서3_수리업체_연락처.md": {
        "doc_type": "contact",
        "fault_type": "All",
        "equipment_id": "M-001~M-030",
        "last_modified": "2025-01-08",
    },
}

FILE_ID_MAP = {
    "RAG_문서_Overheating_대응가이드라인.md":    "overheating-guide",
    "RAG_문서_VibrationIssue_대응가이드라인.md": "vibration-guide",
    "RAG_문서_PressureDrop_대응가이드라인.md":   "pressuredrop-guide",
    "RAG_문서_ElectricalFault_대응가이드라인.md":"electricalfault-guide",
    "RAG_문서_Normal_정기점검_가이드라인.md":    "normal-guide",
    "RAG_문서2_수리이력_M014.md":               "repair-m014",
    "RAG_문서3_수리업체_연락처.md":             "contact",
}

SECTION_ID_MAP = {
    "발생기준":       "criteria",
    "즉각조치":       "steps",
    "에스컬레이션":   "escalation",
    "복구절차":       "recovery",
    "반복발생":       "repeat",
    "연락처참조":     "contact-ref",
    "점검일정":       "schedule",
    "부품교체":       "parts",
    "이관기준":       "handoff",
    "수리이력":       "repair",
    "수리이력요약":   "repair-summary",
    "정기점검이력":   "inspection",
    "연락처":         "contact",
    "연락처우선순위": "priority",
    "의뢰절차":       "procedure",
}

# 수리이력 ### 헤더에서 fault_type 추출용 키워드 매핑
FAULT_KEYWORD_MAP = {
    "Overheating": "Overheating",
    "과열": "Overheating",
    "Vibration": "VibrationIssue",
    "진동": "VibrationIssue",
    "Pressure": "PressureDrop",
    "압력": "PressureDrop",
    "Electrical": "ElectricalFault",
    "전기": "ElectricalFault",
}

# section 이름 정규화: ## 헤더 텍스트 → section 값
SECTION_MAP = {
    "발생 기준": "발생기준",
    "즉각 조치": "즉각조치",
    "임시 조치": "에스컬레이션",
    "복구 절차": "복구절차",
    "반복 발생": "반복발생",
    "관련 담당": "연락처참조",
    "정상 상태": "발생기준",
    "정기 점검 일정": "점검일정",
    "부품 교체": "부품교체",
    "다음 정기": "점검일정",
    "점검 결과": "이관기준",
    "수리 이력": "수리이력",
    "정기 점검 이력": "정기점검이력",
    "요약": "수리이력요약",
    "업체 목록": "연락처",
    "고장 유형별": "연락처우선순위",
    "수리 의뢰": "의뢰절차",
}

def normalize_section(header_text: str) -> str:
    """## 헤더 텍스트에서 section 이름을 정규화한다."""
    for keyword, section in SECTION_MAP.items():
        if keyword in header_text:
            return section
    # 매핑 없으면 헤더 텍스트 앞 10자를 그대로 사용
    return header_text[:10].strip()


# ════════════════════════════════════════════════════════════
# 2. 마크다운 파싱: ## 헤더 단위 청크 분리
# ════════════════════════════════════════════════════════════

def parse_front_matter(text: str) -> dict:
    """
    # 제목 아래의 **키**: 값 형태 메타데이터를 파싱한다.
    예) **최종 수정일**: 2024-11-15
    """
    meta = {}
    for line in text.splitlines():
        m = re.match(r"\*\*(.+?)\*\*:\s*(.+)", line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def split_by_h2(text: str) -> list[tuple[str, str]]:
    """
    마크다운 텍스트를 ## 헤더 기준으로 분리한다.
    반환값: [(헤더 텍스트, 섹션 본문), ...]

    동작 원리:
      1. 줄 단위로 순회하면서 ## 로 시작하는 줄을 만나면 새 섹션 시작
      2. 이전 섹션의 내용을 저장하고 새 섹션 누적 시작
      3. ### 하위 헤더는 본문의 일부로 그대로 포함 (쪼개지 않음)
    """
    sections = []
    current_header = None
    current_lines = []

    for line in text.splitlines():
        # ## 로 시작하지만 ### 은 아닌 줄 = 섹션 구분선
        if re.match(r"^## ", line):
            # 이전 섹션 저장
            if current_header is not None:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append((current_header, body))
            # 새 섹션 시작
            current_header = line[3:].strip()  # "## " 제거
            current_lines = []
        else:
            if current_header is not None:
                current_lines.append(line)

    # 마지막 섹션 저장
    if current_header and current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_header, body))

    return sections


def split_repair_history_by_h3(h2_body: str) -> list[tuple[str, str]]:
    """
    수리 이력 문서의 ## 수리 이력 섹션 안에서
    ### [1] ... ### [2] ... 단위로 한 번 더 분리한다.

    반환값: [(헤더 텍스트, 본문), ...]
    """
    sections = []
    current_header = None
    current_lines = []

    for line in h2_body.splitlines():
        if re.match(r"^### ", line):
            if current_header is not None:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append((current_header, body))
            current_header = line[4:].strip()  # "### " 제거
            current_lines = []
        else:
            if current_header is not None:
                current_lines.append(line)

    if current_header and current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append((current_header, body))

    return sections


def detect_fault_type_from_header(header: str, default: str) -> str:
    """### 헤더 텍스트에서 고장 유형을 감지한다."""
    for keyword, fault in FAULT_KEYWORD_MAP.items():
        if keyword in header:
            return fault
    return default


def make_chunk_id(filename: str, section: str, idx: int) -> str:
    file_id    = FILE_ID_MAP.get(filename, "unknown")
    section_id = SECTION_ID_MAP.get(section, f"sec{idx}")
    return f"{file_id}-{section_id}-{idx:03d}"

# ════════════════════════════════════════════════════════════
# 3. 파일별 청크 생성
# ════════════════════════════════════════════════════════════

def build_chunks_from_file(filepath: Path) -> list[dict]:
    """
    마크다운 파일 1개를 읽어서 청크 목록을 반환한다.
    파일 종류(guideline / repair_history / contact)에 따라
    파싱 전략이 약간 달라진다.
    """
    filename = filepath.name
    if filename not in FILE_META:
        print(f"  [경고] FILE_META에 없는 파일 건너뜀: {filename}")
        return []

    meta = FILE_META[filename]
    text = filepath.read_text(encoding="utf-8")
    h2_sections = split_by_h2(text)

    chunks = []
    chunk_idx = 1

    for header, body in h2_sections:
        # ── 수리이력: "수리 이력" 섹션은 ### 단위로 한 번 더 분리 ──
        if meta["doc_type"] == "repair_history" and "수리 이력" in header and "요약" not in header and "정기" not in header:
            h3_sections = split_repair_history_by_h3(body)
            for h3_header, h3_body in h3_sections:
                fault = detect_fault_type_from_header(h3_header, meta["fault_type"])
                chunk = {
                    "id": make_chunk_id(filename, "수리이력", chunk_idx),
                    "doc_type": meta["doc_type"],
                    "fault_type": fault,
                    "equipment_id": meta["equipment_id"],
                    "section": "수리이력",
                    "urgency": "normal",
                    "source_file": filename,
                    "last_modified": meta["last_modified"],
                    # 헤더를 본문 맨 앞에 포함시켜서 검색 시 컨텍스트 보존
                    "content": f"{h3_header}\n\n{h3_body}",
                }
                chunks.append(chunk)
                chunk_idx += 1
            continue

        # ── 연락처: "업체 목록" 섹션은 ### 단위로 업체별 분리 ──
        if meta["doc_type"] == "contact" and "업체 목록" in header:
            h3_sections = split_repair_history_by_h3(body)
            for h3_header, h3_body in h3_sections:
                # 헤더에서 담당 고장 유형 감지
                fault = detect_fault_type_from_header(h3_header, "All")
                chunk = {
                    "id": make_chunk_id(filename, "연락처", chunk_idx),
                    "doc_type": meta["doc_type"],
                    "fault_type": fault,
                    "equipment_id": meta["equipment_id"],
                    "section": "연락처",
                    "urgency": "emergency",
                    "source_file": filename,
                    "last_modified": meta["last_modified"],
                    "content": f"{h3_header}\n\n{h3_body}",
                }
                chunks.append(chunk)
                chunk_idx += 1
            continue

        # ── 나머지: ## 헤더 단위 그대로 1개 청크 ──
        section = normalize_section(header)
        urgency = "emergency" if section in ("즉각조치", "에스컬레이션", "연락처우선순위", "의뢰절차") else "normal"

        chunk = {
            "id": make_chunk_id(filename, section, chunk_idx),
            "doc_type": meta["doc_type"],
            "fault_type": meta["fault_type"],
            "equipment_id": meta["equipment_id"],
            "section": section,
            "urgency": urgency,
            "source_file": filename,
            "last_modified": meta["last_modified"],
            "content": f"{header}\n\n{body}",
        }
        chunks.append(chunk)
        chunk_idx += 1

    return chunks


def build_all_chunks() -> list[dict]:
    """docs/ 폴더의 모든 마크다운 파일을 읽어서 전체 청크 목록을 반환한다."""
    all_chunks = []
    md_files = sorted(DOCS_DIR.glob("*.md"))

    if not md_files:
        print(f"[오류] docs/ 폴더에 마크다운 파일이 없습니다: {DOCS_DIR}")
        return []

    print(f"\n[파일 목록] docs/ 폴더에서 {len(md_files)}개 파일 발견:")
    for f in md_files:
        print(f"  - {f.name}")

    print()
    for filepath in md_files:
        chunks = build_chunks_from_file(filepath)
        print(f"  {filepath.name} → {len(chunks)}개 청크 생성")
        all_chunks.extend(chunks)

    print(f"\n[합계] 총 {len(all_chunks)}개 청크\n")
    return all_chunks


# ════════════════════════════════════════════════════════════
# 4. 임베딩 생성
# ════════════════════════════════════════════════════════════

def embed(text: str) -> list[float]:
    """
    Azure OpenAI로 텍스트를 1536차원 벡터로 변환한다.
    dimensions=1536: text-embedding-3-large를 small 이름으로 배포했으므로
    차원을 명시적으로 1536으로 줄여서 AI Search 인덱스 스키마와 맞춘다.
    """
    response = aoai_client.embeddings.create(
        input=text,
        model=EMBED_DEPLOYMENT,
        dimensions=1536,
    )
    time.sleep(0.3)  # TPM 한도 초과 방지
    return response.data[0].embedding


# ════════════════════════════════════════════════════════════
# 5. AI Search 업로드
# ════════════════════════════════════════════════════════════

def upload_chunks(chunks: list[dict]) -> None:
    total = len(chunks)
    print(f"[임베딩 시작] 총 {total}개 청크 처리 중...\n")

    documents = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  [{i:02d}/{total}] {chunk['id']}")
        vector = embed(chunk["content"])
        documents.append({**chunk, "content_vector": vector})

    print(f"\n[업로드] AI Search 인덱스 '{INDEX_NAME}'에 업로드 중...")
    result = search_client.upload_documents(documents=documents)

    success = sum(1 for r in result if r.succeeded)
    fail    = sum(1 for r in result if not r.succeeded)
    print(f"[완료] 성공: {success}개 / 실패: {fail}개")

    if fail > 0:
        print("\n[실패 목록]")
        for r in result:
            if not r.succeeded:
                print(f"  - {r.key}: {r.error_message}")


# ════════════════════════════════════════════════════════════
# 6. 검증: 샘플 벡터 검색 테스트
# ════════════════════════════════════════════════════════════

def verify_search(query: str) -> None:
    from azure.search.documents.models import VectorizedQuery

    print(f"\n[검증] '{query}'")
    time.sleep(3)

    qv = embed(query)
    results = search_client.search(
        search_text=query,
        vector_queries=[VectorizedQuery(vector=qv, k_nearest_neighbors=3, fields="content_vector")],
        select=["id", "fault_type", "section", "content"],
        query_type="semantic",
        semantic_configuration_name="rag-semantic-config",
        top=3,
    )
    for r in results:
        print(f"  ✅ [{r['id']}] fault_type={r['fault_type']} / section={r['section']}")
        print(f"     {r['content'][:80]}...")
        print()


# ════════════════════════════════════════════════════════════
# 7. 메인 실행
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # # 환경변수 확인
    # missing = [v for v in [
    #     "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY",
    #     "AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_API_KEY",
    # ] if not os.getenv(v)]
    # if missing:
    #     print(f"[오류] .env 누락 항목: {missing}")
    #     exit(1)

    # # docs/ 폴더 존재 확인
    # if not DOCS_DIR.exists():
    #     print(f"[오류] docs/ 폴더가 없습니다: {DOCS_DIR}")
    #     print("  chatbot/docs/ 폴더를 만들고 마크다운 파일 7개를 넣어주세요.")
    #     exit(1)

    # chunks = build_all_chunks()
    # if not chunks:
    #     exit(1)

    # # 청크 구조 미리보기 (업로드 전 확인용)
    # print("[청크 미리보기] 처음 3개:")
    # for c in chunks[:3]:
    #     print(f"  id={c['id']} / doc_type={c['doc_type']} / fault_type={c['fault_type']} / section={c['section']}")
    #     print(f"  content 앞 60자: {c['content'][:60]}...")
    #     print()

    # upload_chunks(chunks)

    verify_search("M-014 Overheating 알림 지금 당장 뭐부터 해야 해")
    verify_search("M-014 전에도 같은 문제 있었어")
    verify_search("냉각 계통 점검 업체 긴급 연락처")
