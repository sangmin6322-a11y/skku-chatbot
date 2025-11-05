import os, re, random
from flask import current_app
from openai import OpenAI
from app import db, ChatLog

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 💭 PHQ-A 문항 정의
# =========================
PHQ_ITEMS = [
    ("motivation", "요즘은 의욕이 좀 떨어진 느낌이야?"),
    ("sleep", "잠은 잘 자? 아니면 뒤척이거나 자주 깨?"),
    ("appetite", "요즘 입맛은 어때? 예전이랑 달라?"),
    ("focus", "공부나 일할 때 집중이 잘 안 될 때가 있어?"),
    ("worthlessness", "스스로가 쓸모없다고 느낀 적 있어?"),
    ("fatigue", "요즘 유난히 피곤하거나 기운이 없을 때가 많아?"),
    ("anhedonia", "예전엔 즐겁던 일들이 이제는 덜 즐겁게 느껴질 때가 있어?"),
    ("social", "사람 만나는 게 귀찮거나 피하고 싶을 때가 많아?"),
    ("suicidal", "혹시 죽고 싶거나 사라지고 싶다는 생각이 든 적 있어?")
]

phq_state = {}  # user_id → {"index":int, "score":int, "done":bool}

# =========================
# 🧮 PHQ 점수화 함수
# =========================
def classify_phq_response(text: str) -> int:
    t = text.lower()
    if re.search(r"(전혀|없|괜찮|안 그래|별로 아님|거의 없|드물|잘 안)", t): return 0
    if re.search(r"(가끔|며칠|조금|약간|때때로|간혹)", t): return 1
    if re.search(r"(자주|종종|절반|많이|꽤|종일|하루의 절반)", t): return 2
    if re.search(r"(매일|맨날|항상|늘|매번|하루종일|계속|매 순간)", t): return 3
    return 1


# =========================
# 🧠 PHQ 로직 메인
# =========================
def handle_phq_flow(user_input, user_id):
    """입력과 진행 상태를 기반으로 PHQ 대화 흐름 관리"""
    ctx = phq_state.get(user_id, {"index": 0, "score": 0, "done": False})
    text = user_input.strip().lower()

    # 이미 완료된 경우
    if ctx["done"]:
        return None

    # 방금 답한 문항 점수 반영
    if ctx["index"] > 0:
        score = classify_phq_response(text)
        ctx["score"] += score
        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="system",
                                   message=f"[PHQ] {PHQ_ITEMS[ctx['index']-1][1]} → {score}점"))
            db.session.commit()

    # 모든 문항 완료 시 → 자동 리포트 안내
    if ctx["index"] >= len(PHQ_ITEMS):
        ctx["done"] = True
        phq_state[user_id] = ctx
        total = ctx["score"]

        if total < 5:
            mood = "정상 😊"
            msg = "요즘 마음이 꽤 안정적인 시기야."
        elif total < 10:
            mood = "경미한 저하 😐"
            msg = "조금 지쳐 있는 듯해. 충분히 쉬는 것도 중요해."
        elif total < 15:
            mood = "중등도 우울 😔"
            msg = "감정적 피로가 누적된 것 같아. 가까운 사람에게 털어놔봐."
        else:
            mood = "심한 우울 😢"
            msg = "많이 힘들어 보여. 꼭 주변의 도움을 받아보자."

        return (f"💡 지금까지 이야기해본 결과, 현재 상태는 **{mood}** 수준으로 보여.\n"
                f"{msg}\n\n📊 리포트가 자동으로 완성됐어! "
                f"상단 ‘리포트’ 버튼을 눌러 확인해봐.")

    # 다음 질문 준비
    q = PHQ_ITEMS[ctx["index"]][1]
    ctx["index"] += 1
    phq_state[user_id] = ctx

    # 🌿 자연스러운 연결 멘트
    neutral_bridges = [
        "응, 알겠어.",
        "그럴 수도 있지.",
        "음, 그런 말 들으니까 생각나는데.",
        "괜찮아, 솔직하게 말해줘서 고마워.",
        "그런 답변도 괜찮아. 사람마다 다 다르잖아."
    ]
    lead_bridges = [
        "조금 더 이해하고 싶어서 그러는데,",
        "그럼 이번엔 다른 쪽으로 물어볼게.",
        "음… 혹시 하나만 더 물어봐도 될까?",
        "그렇구나. 그럼 궁금한 게 하나 생겼어."
    ]

    if re.search(r"(아니|없|별로|그냥|모르겠)", text):
        bridge = random.choice(neutral_bridges)
    else:
        bridge = random.choice(["응, 흥미롭네.", "그렇구나.", "알겠어."])

    follow = random.choice(lead_bridges)
    return f"{bridge} {follow} {q}"


# =========================
# ✨ GPT 백업 및 자연 대화
# =========================
def classify_and_respond(user_input, user_id=None):
    # 리포트 직접 요청 감지
    if re.search(r"(리포트|보고서|결과|점수|분석)", user_input):
        return "리포트는 이미 만들어졌어! 상단의 ‘리포트’ 버튼을 눌러 확인해봐 😊"

    # PHQ 자동 흐름
    phq_reply = handle_phq_flow(user_input, user_id)
    if phq_reply:
        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=phq_reply))
            db.session.commit()
        return phq_reply

    # GPT 백업: 잡담이나 자연스러운 이어말
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content":
                 "너는 '끼리'라는 이름의 다정한 친구야. "
                 "대화는 자연스럽고 따뜻하게 이어가되, 감정과 기분을 파악하려고 노력해. "
                 "질문은 부드럽게 한 번에 하나만, 문장은 짧게."},
                {"role": "user", "content": user_input}
            ]
        )
        reply = res.choices[0].message.content.strip()

        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="user", message=user_input))
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=reply))
            db.session.commit()

        return reply

    except Exception as e:
        return f"⚠️ AI 응답 오류: {str(e)}"
