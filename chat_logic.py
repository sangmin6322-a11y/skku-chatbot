import os, re, random
from flask import current_app
from openai import OpenAI
from app import db, ChatLog

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# =========================
# 💭 PHQ-A 문항 정의
# =========================
PHQ_ITEMS = [
    "요즘은 의욕이 좀 떨어진 느낌이야?",
    "잠은 잘 자? 아니면 뒤척이거나 자주 깨?",
    "요즘 입맛은 어때? 예전이랑 달라?",
    "공부나 일할 때 집중이 잘 안 될 때가 있어?",
    "스스로가 쓸모없다고 느낀 적 있어?",
    "요즘 유난히 피곤하거나 기운이 없을 때가 많아?",
    "예전엔 즐겁던 일들이 이제는 덜 즐겁게 느껴질 때가 있어?",
    "사람 만나는 게 귀찮거나 피하고 싶을 때가 많아?",
    "혹시 죽고 싶거나 사라지고 싶다는 생각이 든 적 있어?"
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
# 💬 감정 키워드 기반 확률 조절
# =========================
positive_words = ["좋아", "괜찮", "행복", "편해", "재밌", "신나", "기분 좋", "웃겼"]
negative_words = ["힘들", "피곤", "우울", "지쳤", "짜증", "불안", "걱정", "귀찮", "슬퍼", "죽고 싶"]

def get_phq_probability(user_input):
    """사용자 문장에 따라 PHQ 질문 확률 가중치 계산"""
    prob = 0.25  # 기본 확률 25%
    if any(w in user_input for w in negative_words):
        prob += 0.4
    elif any(w in user_input for w in positive_words):
        prob -= 0.15
    return min(max(prob, 0.1), 0.8)  # 0.1~0.8 사이로 제한


# =========================
# 🧠 감정탐색 + 일상대화형 PHQ
# =========================
def maybe_insert_phq(user_input, user_id):
    """일상 대화 중 확률적으로 PHQ 문항을 자연스럽게 삽입"""
    ctx = phq_state.get(user_id, {"index": 0, "score": 0, "done": False})
    if ctx["done"]: 
        return None

    idx = ctx["index"]
    if idx >= len(PHQ_ITEMS):
        ctx["done"] = True
        phq_state[user_id] = ctx
        return None

    # 확률 계산
    prob = get_phq_probability(user_input)
    if random.random() < prob:
        q = PHQ_ITEMS[idx]
        ctx["index"] += 1
        phq_state[user_id] = ctx
        prefix = random.choice([
            "근데 말이야,", "그런 얘길 들으니까 문득 궁금해졌어.",
            "음… 혹시 조금만 더 물어봐도 될까?", "그런데 요즘엔",
            "그럴 때 너는 보통 어떻게 해?", "그 얘기, 조금만 더 자세히 들어보고 싶다.",
            "혹시 그때 기분이 어땠는지도 기억나?", "그러고 보니까 비슷한 경험이 있었던 것 같아.",
            "맞아, 나도 그런 생각 한 적 있어."
        ])
        return f"{prefix} {q}"
    return None


# =========================
# ✨ GPT 기반 자연 대화
# =========================
def classify_and_respond(user_input, user_id=None):
    # 리포트 직접 요청
    if re.search(r"(리포트|보고서|결과|점수|분석)", user_input):
        return "리포트는 자동으로 만들어져! 상단의 ‘리포트’ 버튼을 눌러 확인해봐 😊"

    # GPT로 일상 대화 생성
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """
[끼리 AI 지침]
- 우리는 지금 고등학생들의 우울감을 감지하는 일을 하고 있어. 이제부터 너는 챗봇이야. 너는 학생들이 감정을 설명할 수 있는 질문을 주로 해야 해. 그리고 아래의 모든 ‘<지침>’을 모두 지켜야만 해.
- 사용자 정보 : 불특정 다수의 고등학생 중 한 명, 한국어 사용, 대한민국 고등학생(17세~19세), 성별 미정(사용자에 따라 달라짐)
- 사용자는 챗봇을 ‘찐친’처럼 인식하고 있으므로, 경어체를 사용하지 말고 무조건 반말을 사용할 것. 이때 어미는 경어체만 아니라면 어떤 것이든 상관이 없다.

<지침>
- 50자 이내로 답변할 것.
- 첫 인사와 함께, 요새의 기분을 묻는 질문을 필수적으로 제시한다.
- 같은 단어가 여러번 사용되었을 때, 믿을 수 있는 기관에서 인증된 논문에서 사용된 MMPI & CBCL의 질문을 바탕으로 맥락에 맞추어 답변한다.
- 사용자가 감정을 드러냈다면, 그 감정이 얼마나 지속됐는지, 강도는 어떤지 물어본다.
- 신체적인 증상들에 대한 사용자의 답변이 있었다면, 그 증상은 어느정도 지속됐는지 물어보기.
- 감정 관련 질문이 두 번 제기되면 이후에는 반드시 그 감정에 대한 이유나 그렇게 생각한 까닭에 대해 물어본다.
- 일상·취미·학교생활 등 감정에 대한 이유를 말하면 해당 일반적인 주제와 관련되어 그것이 무엇인지, 어떤건지 자세히 물어본다.
- 일반적인 일상 질문에서 감정과 ‘자연스럽게’ 연결지을만한 지점이 있다면 그 감정과 연관된 질문을 던지며 해당 대화 과정을 반복한다.
- 일상 질문은 감정 연결형으로 전환하며, 탐색형 질문 비율을 70% 이상 유지한다.
- 챗봇의 발화는 2문장 이하로 유지한다.
- 한 답변 안에 질문은 무조건 하나씩만 넣는다. 두 개 이상의 질문을 절대로 하지 않는다.
- 사용자의 답변이 단답형(6글자 이내)일 경우 ‘확장 유도형’ 질문으로 이어간다.
- 전체 대화 길이는 15~20 turn 내에서 우울감 지표 산출 가능하도록 설계한다.
- 신조어/초성(ㅋㅋ, ㄹㅇ, ㅇㅋ, 에바 등)을 자연스럽게 섞어 쓴다.
- ‘~어?’, ‘~야?’, ‘~음?’, ‘~ㅋㅋ’, ‘!!!’ 등 친구 말투를 사용한다.
- 개방형 질문 위주로 한다. 단답 유도 금지.
- ‘~~야? 아니면 ~~야?’ 같은 선택지는 절대 금지.
- 일상·취미·학교생활 등 다양한 맥락에서 사용자가 자신의 경험과 감정을 자연스럽게 풀 수 있게 유도한다.
- 초기: 자연스러운 안부 → 오늘 일상 → 감정 상태 탐색 순.
- 중반 이후: 형식적 질문은 지양하고, 친구와 수다 떠는 느낌 유지.
- 우울감/스트레스 등 민감 주제가 나오면 1~2회 질문 후 일상으로 전환했다가 다시 감정 질문 반복.
- “그럼 그때 어떤 생각함?”, “헐 그때 기분은 어땠음?”처럼 자연스럽게 이어간다.
"""},
                {"role": "user", "content": user_input}
            ]
        )
        reply = res.choices[0].message.content.strip()

        # ✅ PHQ 문항 확률 삽입
        phq_extra = maybe_insert_phq(user_input, user_id)
        if phq_extra:
            reply += f"\n\n{phq_extra}"

        # DB 기록
        with current_app.app_context():
            db.session.add(ChatLog(user_id=user_id, role="user", message=user_input))
            db.session.add(ChatLog(user_id=user_id, role="assistant", message=reply))
            db.session.commit()

        return reply

    except Exception as e:
        return f"⚠️ AI 응답 오류: {str(e)}"
