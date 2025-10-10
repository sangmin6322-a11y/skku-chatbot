import random
from flask import current_app
from app import db, ChatLog

# === 💬 일상 대화 카테고리 ===
daily_categories = {
    "인사": ["안녕", "하이", "반가워", "안녕하세요"],
    "밥": ["밥", "배고파", "치킨", "피자", "라면", "떡볶이"],
    "날씨": ["날씨", "비", "눈", "더워", "추워", "가을"],
    "취미": ["게임", "영화", "유튜브", "운동", "노래", "여행"],
    "공부": ["공부", "시험", "학교", "과제", "수업", "학점"],
    "관계": ["친구", "가족", "연애", "남친", "여친", "동아리"]
}

daily_responses = {
    "인사": ["안녕! 만나서 반가워 😊", "하이~ 오늘 기분 어때?", "좋은 하루 보내고 있지?"],
    "밥": ["밥은 먹었어?", "오늘 뭐 먹었어?", "요즘 뭐가 맛있어?"],
    "날씨": ["오늘 날씨 어땠어?", "비 오는 날 좋아해?", "요즘 좀 쌀쌀하지 않아?"],
    "취미": ["요즘 뭐 해?", "영화 봤어?", "게임 자주 해?"],
    "공부": ["공부 힘들지?", "과제는 다 했어?", "시험기간이야?"],
    "관계": ["친구들이랑 잘 지내?", "가족은 잘 있어?", "요즘 외롭지 않아?"]
}

# === 💭 감정 관련 카테고리 ===
emotion_categories = {
    "기분": ["기분", "무기력", "짜증", "우울", "불안", "슬퍼", "피곤"],
    "잠": ["잠", "졸려", "불면", "못자", "피곤", "숙면"],
    "밥": ["입맛", "배고파", "식욕없", "폭식", "굶음"],
    "집중": ["집중", "산만", "딴짓", "공부안됨"],
    "사고": ["생각", "비관", "죽고 싶", "희망없", "무의미", "절망"],
    "신체": ["두통", "복통", "속쓰림", "토할", "어지러", "무기력"],
    "관계": ["친구", "가족", "외로움", "왕따", "사람싫어"]
}

emotion_questions = {
    "기분": ["요즘 하루 보낼 때 어떤 감정이 제일 자주 느껴져?", "최근에 웃은 적 있어?"],
    "잠": ["요즘 잠은 잘 자?", "밤에 잠들기 힘든 편이야?"],
    "밥": ["요즘 식사 패턴은 어때?", "입맛이 예전 같지 않다고 느낀 적 있어?"],
    "집중": ["요즘 집중이 잘 안돼?", "공부할 때 자꾸 딴생각 나?"],
    "사고": ["요즘 자주 드는 생각이 있어?", "스스로에 대한 생각이 부정적으로 변했어?"],
    "신체": ["요즘 몸은 괜찮아?", "피곤이 잘 안 풀리는 느낌이야?"],
    "관계": ["요즘 사람들 만나는 게 편해?", "가끔 외롭다고 느껴?"]
}

# === 기본 응답 ===
default_responses = ["음… 잘 모르겠어.", "그렇구나~ 좀 더 얘기해줄래?", "흥미롭네.", "재밌는 얘기야!"]

def classify_and_respond(user_input, user_id):
    with current_app.app_context():
        # 1️⃣ 사용자 메시지 저장
        db.session.add(ChatLog(user_id=user_id, role="user", message=user_input))
        db.session.commit()

        # 2️⃣ 감정 카테고리 우선 탐색
        for category, keywords in emotion_categories.items():
            for kw in keywords:
                if kw in user_input:
                    reply = random.choice(emotion_questions.get(category, default_responses))
                    db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
                    db.session.commit()
                    return reply

        # 3️⃣ 일상 대화 카테고리 탐색
        for category, keywords in daily_categories.items():
            for kw in keywords:
                if kw in user_input:
                    reply = random.choice(daily_responses.get(category, default_responses))
                    db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
                    db.session.commit()
                    return reply

        # 4️⃣ 기본 응답
        reply = random.choice(default_responses)
        db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
        db.session.commit()
        return reply
