import os, re, random
from flask import current_app
from openai import OpenAI
from datetime import datetime
from app import db, ChatLog   # ✅ DB 접근 필요

# === PHQ-A 리딩 모듈 ===
phq_questions = [
    "요즘은 의욕이 좀 떨어진 느낌이야?",
    "잠은 잘 자? 아니면 뒤척이거나 자주 깨?",
    "요즘 입맛은 어때? 전이랑 좀 달라?",
    "집중이 잘 안 되거나, 수업 때 멍할 때 있어?",
    "가끔은 스스로가 쓸모없다고 느껴질 때 있어?",
    "요즘 피곤하거나 기운 빠질 때가 많아?",
    "아무것도 하기 싫을 때 있지?",
    "사람 만나는 게 귀찮거나 피하고 싶을 때 있어?",
    "혹시 죽고 싶거나 사라지고 싶다는 생각이 든 적 있어?"
]
phq_context = {}  # {user_id: {"index": int, "score": int, "cool": int}}

def classify_phq_response(text: str) -> int:
    """사용자 답변을 0~3점으로 점수화 (PHQ-A 기준)"""
    text = text.lower()
    if re.search(r"(전혀|없|괜찮|안 그래|별로 아님|거의 없|드물|잘 안)", text): return 0
    if re.search(r"(가끔|며칠|조금|약간|때때로|간혹)", text): return 1
    if re.search(r"(자주|종종|절반|많이|꽤|종일|하루의 절반)", text): return 2
    if re.search(r"(매일|맨날|항상|늘|매번|하루종일|계속|매 순간)", text): return 3
    return 1

def update_phq(user_input, user_id):
    """PHQ 문항 답변 점수화 + DB 기록"""
    if user_id not in phq_context:
        return
    ctx = phq_context[user_id]
    if 0 < ctx["index"] <= len(phq_questions):
        score = classify_phq_response(user_input)
        ctx["score"] += score
        phq_context[user_id] = ctx
        with current_app.app_context():
            db.session.add(ChatLog(
                user_id=user_id,
                role="system",
                message=f"[PHQ] {phq_questions[ctx['index']-1]} → {score}점"
            ))
            db.session.commit()

def maybe_ask_phq(user_input, user_id):
    """감정 단서 감지 → PHQ 질문 자연스럽게 삽입"""
    cues = ["힘들", "지쳐", "귀찮", "짜증", "불안", "피곤", "우울", "공부", "잠", "식욕", "의욕", "무기력"]
    ctx = phq_context.get(user_id, {"index": 0, "score": 0, "cool": 0})

    if ctx["cool"] > 0:
        ctx["cool"] -= 1
        phq_context[user_id] = ctx
        return None

    if any(c in user_input for c in cues):
        if ctx["index"] < len(phq_questions):
            q = phq_questions[ctx["index"]]
            ctx["index"] += 1
            ctx["cool"] = 3
            phq_context[user_id] = ctx
            prefix = random.choice([
                "그런 얘길 들으니까 좀 걱정돼.",
                "음… 요즘 네 상태가 살짝 걱정돼서 그런데,",
                "혹시 궁금해서 묻는데,"
            ])
            return f"{prefix} {q}"

    if ctx["index"] >= len(phq_questions):
        total = ctx["score"]
        phq_context[user_id] = {"index": 0, "score": 0, "cool": 0}
        return f"테스트가 끝났어! (총점: {total}점)\n결과는 리포트에서 볼 수 있어 😊"

    return None


# === GPT 엔진 ===
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def load_recent_memory(user_id, limit=10):
    """DB에서 최근 N턴 대화 불러오기 (user/assistant만)"""
    with current_app.app_context():
        logs = (ChatLog.query
                .filter(ChatLog.user_id == user_id, ChatLog.role.in_(["user", "assistant"]))
                .order_by(ChatLog.timestamp.desc())
                .limit(limit)
                .all())
        logs.reverse()
        messages = [{"role": log.role, "content": log.message} for log in logs]
        return messages


def classify_and_respond(user_input, user_id=None):
    """GPT 대화 + PHQ 추적 + DB 기반 기억 유지"""
    text = user_input.strip()

    # 🔹 PHQ 점수 업데이트
    update_phq(text, user_id)
    natural_q = maybe_ask_phq(text, user_id)
    if natural_q:
        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=natural_q))
            db.session.commit()
        return natural_q

    # 🔹 DB에서 최근 대화 로드
    recent_messages = load_recent_memory(user_id)

    # 🔹 GPT 입력 구성
    messages = [
        {"role": "system", "content": (
            "너는 '끼리'라는 이름의 다정하고 공감 잘하는 친구야. "
            "대화는 자연스럽고 따뜻하게 이어가고, "
            "사용자의 감정 변화나 피로도를 눈치채면 조용히 위로해줘. "
            "이전 대화 맥락을 기억해서 어색하지 않게 이어가. "
            "필요할 때는 PHQ-A 문항을 자연스럽게 떠올리듯 묻기도 해."
        )}
    ] + recent_messages + [{"role": "user", "content": text}]

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        reply = completion.choices[0].message.content.strip()

        # 🔹 DB에 대화 저장 (assistant role 사용)
        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="user", message=text))
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=reply))
            db.session.commit()

        return reply

    except Exception as e:
        return f"⚠️ AI 응답 오류: {str(e)}"

