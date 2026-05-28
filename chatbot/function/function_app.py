import azure.functions as func
import json
import os
import re
import urllib.request
import urllib.parse
import logging
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

app = func.FunctionApp()

# ── 클라이언트 초기화 (Function 인스턴스당 1회) ───────────
aoai_client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version="2024-02-01",
)
search_client = SearchClient(
    endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
    index_name="smartfactory-rag-index",
    credential=AzureKeyCredential(os.environ["AZURE_SEARCH_API_KEY"]),
)

BOT_APP_ID = os.environ["BOT_APP_ID"]
BOT_APP_PASSWORD = os.environ["BOT_APP_PASSWORD"]

# ════════════════════════════════════════════════════════════
# 의도 분류
# ════════════════════════════════════════════════════════════

HISTORY_KEYWORDS = [
    "이전에도", "전에도", "이력", "과거", "몇 번", "반복",
    "또 났어", "또 생겼", "같은 문제", "예전에도", "수리 이력",
]
CONTACT_KEYWORDS = [
    "연락처", "전화번호", "업체", "출동", "긴급", "불러줘",
    "맡길", "연락", "전화", "담당자",
]

def classify_intent_by_keyword(question: str) -> str:
    if any(kw in question for kw in HISTORY_KEYWORDS):
        return "history"
    if any(kw in question for kw in CONTACT_KEYWORDS):
        return "contact"
    return "unknown"

def classify_intent_by_llm(question: str) -> str:
    response = aoai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "질문을 아래 세 가지 중 하나로만 분류하세요. 단어 하나만 답하세요.\n"
                    "- history: 특정 설비의 과거 수리 이력, 이전 고장 여부 질문\n"
                    "- contact: 수리 업체 연락처, 출동 요청 관련 질문\n"
                    "- guideline: 고장 대응 절차, 지금 뭐해야 하는지 질문"
                ),
            },
            {"role": "user", "content": question},
        ],
        max_tokens=10,
        temperature=0,
    )
    result = response.choices[0].message.content.strip().lower()
    if result not in ("history", "contact", "guideline"):
        return "guideline"
    return result

def classify_intent(question: str) -> str:
    """키워드로 먼저 분류, 애매하면 LLM에게 위임"""
    intent = classify_intent_by_keyword(question)
    if intent == "unknown":
        intent = classify_intent_by_llm(question)
    return intent


# ════════════════════════════════════════════════════════════
# 검색 함수
# ════════════════════════════════════════════════════════════

def search_documents(question: str, query_vector: list) -> list:
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=3,
        fields="content_vector",
    )

    intent = classify_intent(question)
    logging.info(f"[intent] {intent}")

    if intent == "history":
        results = list(search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            select=["id", "fault_type", "section", "content"],
            filter="doc_type eq 'repair_history'",
            top=3,
        ))
    elif intent == "contact":
        results = list(search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            select=["id", "fault_type", "section", "content"],
            filter="doc_type eq 'contact'",
            top=3,
        ))
    else:
        results = list(search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="rag-semantic-config",
            select=["id", "fault_type", "section", "content"],
            top=3,
        ))

    # 결과 없으면 필터 없이 재시도
    if not results:
        logging.warning("[search] 필터 결과 없음 — 전체 검색으로 재시도")
        results = list(search_client.search(
            search_text=question,
            vector_queries=[vector_query],
            query_type="semantic",
            semantic_configuration_name="rag-semantic-config",
            select=["id", "fault_type", "section", "content"],
            top=3,
        ))

    return results


# ════════════════════════════════════════════════════════════
# RAG 핵심 로직 (rag_chat, messages 공통 사용)
# ════════════════════════════════════════════════════════════

SYSTEM_PROMPT = (
    "당신은 반도체 OSAT 협력사의 클린룸 HVAC 공조 압축기 설비 관리 전문 챗봇입니다. "
    "아래 참고 문서를 바탕으로 질문에 답하세요. "
    "참고 문서에 없는 내용은 모른다고 답하세요. "
    "답변은 현장 엔지니어가 바로 행동할 수 있도록 명확하고 단계적으로 작성하세요."
)

def run_rag(question: str) -> str:
    # 1. 벡터화
    embed_response = aoai_client.embeddings.create(
        input=question,
        model="text-embedding-3-small",
        dimensions=1536,
    )
    query_vector = embed_response.data[0].embedding

    # 2. 의도 기반 검색
    search_results = search_documents(question, query_vector)

    # 3. 컨텍스트 조합
    context = ""
    for r in search_results:
        context += f"[{r['section']}]\n{r['content']}\n\n"
    if not context:
        context = "관련 문서를 찾을 수 없습니다."

    # 4. GPT 답변 생성
    chat_response = aoai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"참고 문서:\n{context}\n\n질문: {question}"},
        ],
        max_tokens=1000,
        temperature=0.3,
    )
    return chat_response.choices[0].message.content


# ════════════════════════════════════════════════════════════
# HTTP 엔드포인트 1: rag_chat (기존 Power Automate / 테스트용)
# ════════════════════════════════════════════════════════════

@app.route(route="rag_chat", methods=["POST"])
def rag_chat(req: func.HttpRequest) -> func.HttpResponse:

    try:
        body = req.get_json()
        question = body.get("question", "")
    except Exception:
        return func.HttpResponse(
            json.dumps({"error": "요청 본문을 파싱할 수 없습니다."}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json",
        )

    if not question:
        return func.HttpResponse(
            json.dumps({"error": "question 필드가 없습니다."}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json",
        )

    answer = run_rag(question)

    return func.HttpResponse(
        json.dumps({"answer": answer}, ensure_ascii=False),
        status_code=200,
        mimetype="application/json",
    )


# ════════════════════════════════════════════════════════════
# HTTP 엔드포인트 2: messages (Bot Framework — Teams 연동)
# ════════════════════════════════════════════════════════════

@app.route(route="messages", methods=["POST"])
def messages(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
        question = body.get("text", "") or body.get("question", "")

        if not question:
            return func.HttpResponse(status_code=200)

        answer = run_rag(question)

        # Bot Framework 응답 전송
        activity = json.loads(req.get_body())
        response_activity = {
            "type": "message",
            "from": {"id": activity.get("recipient", {}).get("id", "bot")},
            "conversation": activity.get("conversation"),
            "recipient": activity.get("from"),
            "replyToId": activity.get("id"),
            "text": answer,
        }

        service_url = activity.get("serviceUrl", "")
        conversation_id = activity.get("conversation", {}).get("id", "")

        # 토큰 획득
        tenant_id = os.environ.get("BOT_TENANT_ID", "botframework.com")
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": BOT_APP_ID,
            "client_secret": BOT_APP_PASSWORD,
            "scope": "https://api.botframework.com/.default",
        }).encode()
        token_req = urllib.request.Request(token_url, data=token_data, method="POST")
        with urllib.request.urlopen(token_req) as resp:
            token_json = json.loads(resp.read())
        access_token = token_json["access_token"]

        # 답변 전송
        reply_url = f"{service_url}v3/conversations/{conversation_id}/activities"
        reply_data = json.dumps(response_activity).encode("utf-8")
        reply_req = urllib.request.Request(
            reply_url,
            data=reply_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            method="POST",
        )
        urllib.request.urlopen(reply_req)

        return func.HttpResponse(status_code=200)

    except Exception as e:
        logging.error(f"messages error: {e}")
        return func.HttpResponse(status_code=200)
