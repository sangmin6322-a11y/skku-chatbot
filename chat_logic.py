import os, re, random
from collections import deque
from flask import current_app
from openai import OpenAI
from app import db, ChatLog

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ============================
# 🧠 설정값: 리드 강도 조절
# ============================
# calm: 거의 먼저 말 안 함
# normal: 가끔 먼저 리드
# active: 자주 먼저 말 걸기
LEAD_MODE = os.getenv("LEAD_MODE", "normal")

def lead_chance():
    if LEAD_MODE == "calm":
        return 0.1
    elif LEAD_MODE == "active":
        return 0.6
    return 0.35


# =========================
# PHQ-A 문항 + 주제키 매핑
# =========================
PHQ_ITEMS = [
    ("motivation", "요즘은 의욕이 좀 떨어진 느낌이야?"),
    ("sleep", "잠은 잘 자? 아니면 뒤척이거나 자주 깨?"),
    ("appetite", "요즘 입맛은 어때? 전이랑 좀 달라?"),
    ("focus", "집중이 잘 안 되거나, 수업 때 멍할 때 있어?"),
    ("worthlessness", "가끔은 스스로가 쓸모없다고 느껴질 때 있어?"),
    ("fatigue", "요즘 피곤하거나 기운 빠질 때가 많아?"),
    ("anhedonia", "아무것도 하기 싫을 때 있지?"),
    ("social", "사람 만나는 게 귀찮거나 피하고 싶을 때 있어?"),
    ("si", "혹시 죽고 싶거나 사라지고 싶다는 생각이 든 적 있어?")
]

phq_ctx = {}  # user_id -> {"i":int, "score":int, "cool":int, "asked":deque, "nudged":bool}

LEAD_PROMPTS = [
    "오늘 하루는 어땠어?",
    "요즘 마음은 좀 괜찮아?",
    "최근에 즐겁거나 힘들었던 일 있었어?",
    "요즘 잠은 어떤 편이야?",
    "기운이 좀 떨어지는 날이 많은 편이야?",
    "요즘 밥맛은 어때?",
    "집중은 잘 되는 편이야?",
]

NEG_PAT = re.compile(r"(없어|없었어|글쎄|모르겠|잘 몰라|그냥|아니|별로|안 해|안해)")
REPORT_PAT = re.compile(r"(리포트|보고서|감정\s*분석|결과|점수)")

def _get_ctx(user_id):
    if user_id not in phq_ctx:
        phq_ctx[user_id] = {"i": 0, "score": 0, "cool": 0, "asked": deque(maxlen=6), "nudged": False}
    return phq_ctx[user_id]


# ============================
# 점수화 및 PHQ 진행 관리
# ============================
def classify_phq_response(text: str) -> int:
    t = text.lower()
    if re.search(r"(전혀|없|괜찮|안 그래|별로 아님|거의 없|드물|잘 안)", t): return 0
    if re.search(r"(가끔|며칠|조금|약간|때때로|간혹)", t): return 1
    if re.search(r"(자주|종종|절반|많이|꽤|종일|하루의 절반)", t): return 2
    if re.search(r"(매일|맨날|항상|늘|매번|하루종일|계속|매 순간)", t): return 3
    return 1


def update_phq(user_input, user_id):
    ctx = _get_ctx(user_id)
    if 0 < ctx["i"] <= len(PHQ_ITEMS):
        score = classify_phq_response(user_input)
        ctx["score"] += score
        with current_app.app_context():
            topic, q = PHQ_ITEMS[ctx["i"] - 1]
            db.session.add(ChatLog(user_id=user_id, role="system", message=f"[PHQ] {q} → {score}점"))
            db.session.commit()


def _pick_next_unasked(ctx):
    start = ctx["i"]
    for j in range(start, len(PHQ_ITEMS)):
        topic, q = PHQ_ITEMS[j]
        if topic not in ctx["asked"]:
            ctx["i"] = j + 1
            ctx["cool"] = 2
            ctx["asked"].append(topic)
            return q
    if start < len(PHQ_ITEMS):
        topic, q = PHQ_ITEMS[start]
        ctx["i"] = start + 1
        ctx["cool"] = 2
        ctx["asked"].append(topic)
        return q
    return None


def maybe_ask_proactively(user_input, user_id):
    """능동 리딩 + PHQ 병행"""
    ctx = _get_ctx(user_id)

    if ctx["cool"] > 0:
        ctx["cool"] -= 1
        return None

    # 1️⃣ 부정 응답
    if NEG_PAT.search(user_input):
        q = _pick_next_unasked(ctx)
        return "괜찮아, 그렇게 느낄 때도 있어.\n" + (q or random.choice(LEAD_PROMPTS))

    # 2️⃣ 랜덤 리드
    if ctx["i"] == 0 and random.random() < lead_chance():
        ctx["cool"] = 1
        return random.choice(LEAD_PROMPTS)

    # 3️⃣ 감정 단서 기반
    cues = ["힘들", "지쳐", "귀찮", "짜증", "불안", "우울", "피곤", "잠", "식욕", "의욕", "무기력", "집중"]
    if any(c in user_input for c in cues):
        return _pick_next_unasked(ctx)

    # 4️⃣ 리포트 유도
    if ctx["i"] >= 6 and not ctx["nudged"]:
        ctx["nudged"] = True
        return "지금까지 이야기로 어느 정도 파악됐어. 상단 ‘리포트’를 눌러 최근 결과를 확인해볼래?"

    # 5️⃣ 완료 처리
    if ctx["i"] >= len(PHQ_ITEMS):
        total = ctx["score"]
        ctx.update({"i": 0, "score": 0, "asked": deque(maxlen=6)})
        return f"간단 체크는 여기까지! (총점: {total}점) 상단 ‘리포트’에서 자세히 볼 수 있어."

    return None


# ============================
# 대화 기록 + GPT 응답 처리
# ============================
def load_recent_memory(user_id, limit=10):
    with current_app.app_context():
        logs = (
            ChatLog.query
            .filter(ChatLog.user_id == user_id, ChatLog.role.in_(["user", "assistant"]))
            .order_by(ChatLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        logs.reverse()
        return [{"role": l.role, "content": l.message} for l in logs]


def classify_and_respond(user_input, user_id=None):
    text = user_input.strip()

    # 📊 리포트 관련 문장 즉시 처리
    if REPORT_PAT.search(text):
        return "지금까지 대화를 바탕으로 리포트를 만들었어. 상단 ‘리포트’를 눌러 확인해봐!"

    # 📈 PHQ 점수 반영
    update_phq(text, user_id)

    # 💬 능동 리드 질문
    proactive = maybe_ask_proactively(text, user_id)
    if proactive:
        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=proactive))
            db.session.commit()
        return proactive

    # 🧠 최근 대화 문맥
    recent = load_recent_memory(user_id)
    messages = [
        {"role": "system", "content":
         "너는 '끼리'라는 이름의 다정한 친구야. 말은 짧고 자연스럽게, 이모지는 가볍게. "
         "항상 공감 한마디 + 한 번에 질문 1개만. 중복 주제 반복 금지. "
         "리포트 요청엔 길게 설명하지 말고 바로 리포트 안내.하지만 주어진 질문을 최대한 끝내도록 유도."
         "사용자는 너를 친구로 생각하고 있음. 경어를 절대 사용하지 말것."}
    ] + recent + [{"role": "user", "content": text}]

    try:
        res = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
        reply = res.choices[0].message.content.strip()

        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="user", message=text))
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=reply))
            db.session.commit()

        return reply

    except Exception as e:
        return f"⚠️ AI 응답 오류: {str(e)}"
