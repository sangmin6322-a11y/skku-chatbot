import random
from flask import current_app

# === 감정 + 일상 대화 통합 카테고리 ===
daily_categories = {
    "인사": ["안녕", "하이", "반가워", "안녕하세요"],
    "밥": ["밥", "배고파", "치킨", "피자", "라면", "떡볶이"],
    "날씨": ["날씨", "비", "눈", "더워", "추워", "가을"],
    "취미": ["게임", "영화", "유튜브", "운동", "노래", "여행"],
    "공부": ["공부", "시험", "학교", "과제", "수업", "학점"],
    "관계": ["친구", "가족", "연애", "남친", "여친", "동아리"]
}

emotion_categories = {
    "기분": ["기분", "무기력", "짜증", "우울", "불안", "슬퍼", "피곤"],
    "잠": ["잠", "졸려", "불면", "못자", "숙면"],
    "밥": ["입맛", "배고파", "식욕없", "폭식", "굶음"],
    "집중": ["집중", "산만", "공부안됨"],
    "사고": ["생각", "비관", "죽고 싶", "희망없", "무의미"],
    "신체": ["두통", "복통", "속쓰림", "어지러"],
    "관계": ["외로움", "왕따", "사람싫어"]
}

daily_responses = {
    "인사": ["안녕! 만나서 반가워 😊", "하이~ 오늘 기분 어때?", "좋은 하루 보내고 있지?"],
    "밥": ["밥은 먹었어?", "오늘 뭐 먹었어?", "요즘 뭐가 맛있어?"],
    "날씨": ["오늘 날씨 어땠어?", "비 오는 날 좋아해?", "요즘 좀 쌀쌀하지 않아?"],
    "취미": ["요즘 뭐 해?", "영화 봤어?", "게임 자주 해?"],
    "공부": ["공부 힘들지?", "과제는 다 했어?", "시험기간이야?"],
    "관계": ["친구들이랑 잘 지내?", "가족은 잘 있어?", "요즘 외롭지 않아?"]
}

emotion_responses = {
    "기분": ["요즘 감정 기복이 좀 있나봐?", "최근에 웃은 적 있어?", "기분이 자주 가라앉는 편이야?"],
    "잠": ["요즘 잠은 잘 자?", "밤에 잠들기 힘든 편이야?"],
    "밥": ["요즘 입맛은 어때?", "식사 거르지 말고 챙겨 먹자."],
    "집중": ["집중이 잘 안 돼?", "공부할 때 산만하다고 느껴져?"],
    "사고": ["요즘 자주 하는 생각이 있어?", "스스로에 대한 생각이 부정적일 때가 있지?"],
    "신체": ["요즘 몸은 괜찮아?", "피곤이 잘 안 풀려?"],
    "관계": ["요즘 외로움을 느껴?", "사람들과 있을 때 편안해?"]
}

default_responses = ["음… 잘 모르겠어.", "그렇구나~ 좀 더 얘기해줄래?", "흥미롭네.", "재밌는 얘기야!"]


def classify_and_respond(user_input, user_id):
    # ✅ 순환 import 방지: 여기서 Flask app context 안에서 import
    from app import db, ChatLog  

    with current_app.app_context():
        # 사용자 메시지 저장
        db.session.add(ChatLog(user_id=user_id, role="user", message=user_input))
        db.session.commit()

        # 감정 카테고리 우선
        for category, keywords in emotion_categories.items():
            for kw in keywords:
                if kw in user_input:
                    reply = random.choice(emotion_responses.get(category, default_responses))
                    db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
                    db.session.commit()
                    return reply

        # 일상 카테고리
        for category, keywords in daily_categories.items():
            for kw in keywords:
                if kw in user_input:
                    reply = random.choice(daily_responses.get(category, default_responses))
                    db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
                    db.session.commit()
                    return reply

        # 기본 응답
        reply = random.choice(default_responses)
        db.session.add(ChatLog(user_id=user_id, role="bot", message=reply))
        db.session.commit()
        return reply
