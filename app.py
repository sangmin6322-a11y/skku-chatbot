from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta, datetime
import random, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from flask_cors import CORS

# --- 기본 Flask 설정 ---
app = Flask(__name__)
CORS(app, supports_credentials=True)  # app 정의 후 CORS 적용
app.config.update(
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=True
)
app.secret_key = "secret-key"

# --- PostgreSQL 연결 ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL", "sqlite:///users.db")
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
db = SQLAlchemy(app)

# --- Flask-Login 설정 ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# --- 유저 모델 ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# --- 대화 로그 모델 ---
class ChatLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    role = db.Column(db.String(10))
    message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- 회원가입 ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_pw = generate_password_hash(password)
        if User.query.filter_by(username=username).first():
            flash("이미 존재하는 아이디입니다.")
            return redirect(url_for("register"))
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("회원가입 성공! 로그인 해주세요.")
        return redirect(url_for("login"))
    return render_template("register.html")

# --- 로그인 ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("chat_page"))
        else:
            flash("로그인 실패. 아이디나 비밀번호를 확인하세요.")
    return render_template("login.html")

# --- 로그아웃 ---
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("로그아웃되었습니다.")
    return redirect(url_for("login"))

# --- 채팅 페이지 ---
@app.route("/")
@login_required
def chat_page():
    return render_template("index.html", username=current_user.username)

# --- 챗봇 로직 ---
def classify_and_respond(user_input):
    mood_words = ["힘들", "우울", "무기력", "귀찮", "짜증", "죽고 싶", "의욕없", "불안"]
    if any(w in user_input for w in mood_words):
        return random.choice([
            "그랬구나... 요즘 마음이 많이 무거운가 봐.",
            "괜찮아, 그런 기분 느끼는 거 자연스러워.",
            "힘들면 잠시 쉬어가도 괜찮아."
        ])
    return random.choice([
        "응, 그래!",
        "그렇구나~",
        "음… 흥미롭네.",
        "좋아, 계속 얘기해줘!"
    ])

# --- 대화 처리 ---
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    user_id = current_user.id
    message = request.form["message"]
    bot_reply = classify_and_respond(message)

    db.session.add(ChatLog(user_id=user_id, role="user", message=message))
    db.session.add(ChatLog(user_id=user_id, role="bot", message=bot_reply))
    db.session.commit()

    return jsonify({"response": bot_reply})


# --- 7일치 감정 분석 + 그래프 ---
@app.route("/analyze")
@login_required
def analyze():
    user_id = current_user.id
    logs = ChatLog.query.filter(
        ChatLog.user_id == user_id,
        ChatLog.role == "user",
        ChatLog.timestamp >= datetime.utcnow() - timedelta(days=7)
    ).all()

    mood_keywords = ["힘들", "우울", "무기력", "짜증", "귀찮", "죽고 싶", "의욕없", "불안"]
    daily_score = {}

    for log in logs:
        date = log.timestamp.date()
        score = sum(1 for kw in mood_keywords if kw in log.message)
        daily_score[date] = daily_score.get(date, 0) + score

    total_score = sum(daily_score.values())

    if total_score == 0:
        level = "정상 😊"
        advice = "최근 대화에서 부정적인 감정은 거의 보이지 않아요. 잘 지내고 있네요!"
    elif total_score <= 3:
        level = "경도 우울 😐"
        advice = "가벼운 스트레스나 피로가 느껴져요. 충분히 쉬고 좋아하는 걸 해보세요."
    elif total_score <= 6:
        level = "중등도 우울 😔"
        advice = "감정적 피로가 누적된 것 같아요. 가까운 사람에게 털어놓는 것도 좋아요."
    else:
        level = "고위험 😢"
        advice = "최근 대화에서 심한 무기력감이 보여요. 전문 상담사에게 도움을 받아보는 게 좋겠어요."

    if daily_score:
        dates = sorted(daily_score.keys())
        scores = [daily_score[d] for d in dates]
        plt.figure(figsize=(6, 3))
        plt.plot(dates, scores, marker='o', color='#2a6fb4')
        plt.title("최근 7일 감정 키워드 변화")
        plt.xlabel("날짜")
        plt.ylabel("감정 점수")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()

        os.makedirs("static", exist_ok=True)
        graph_path = os.path.join("static", "mood_graph.png")
        plt.savefig(graph_path)
        plt.close()
    else:
        graph_path = None

    return render_template("result.html",
                           username=current_user.username,
                           score=total_score,
                           level=level,
                           advice=advice,
                           graph=graph_path)

if __name__ == "__main__":
    app.run(debug=True)

# === 챗봇 데이터 (코랩에서 쓰던 거) ===
import random
# === 일상 대화 키워드 ===여기보다는 뒤에 categories 리스트를 수정해주세요
daily_categories = {
    "무맥락 애매한 것들": ["에바야"],
    "인사/자기소개": [
        "안녕", "안녕하세요", "하이", "헬로", "반가워", "잘 지냈어",
        "누구", "정체", "챗봇", "너 뭐야", "이름", "소개", "자기소개"
    ],
    "감사/칭찬": [
        "고마워", "감사", "덕분", "땡큐", "사랑해", "좋아해",
        "대단해", "멋지다", "굿", "잘했어", "최고", "대박"
    ],
    "놀람/감탄": [
        "헐", "세상에", "진짜", "와", "우와", "헉", "대박", "쩐다", "미쳤다", "소름", "미친", "ㅁㅊ", "쉣", "헐", "엥"
    ],
    "욕설/부정": [
        "짜증", "빡쳐", "열받아", "화나", "개빡쳐", "씨발", "젠장", "망했다",
        "개노답", "개같", "병신", "멍청", "좆", "꺼져"
    ],
    "밥/음식": [
        "밥", "식사", "밥맛", "입맛", "배고파", "배불러", "먹기 싫어", "과식", "폭식",
        "라면", "짜파게티", "신라면", "컵라면", "우동", "국수", "칼국수",
        "피자", "치킨", "햄버거", "샌드위치", "김밥", "떡볶이", "순대", "오뎅", "튀김",
        "파스타", "스테이크", "돈까스", "초밥", "회", "삼겹살", "불고기",
        "과자", "쿠키", "빵", "케이크", "초콜릿", "아이스크림", "빙수", "젤리",
        "간식", "야식", "분식", "마라탕", "김치찌개", "된장찌개", "국", "찌개"
    ],
    "음료/디저트": [
        "커피", "아메리카노", "라떼", "카푸치노", "모카", "콜드브루", "에스프레소",
        "녹차", "홍차", "밀크티", "버블티", "코코아", "핫초코", "주스", "스무디",
        "쉐이크", "탄산", "콜라", "사이다", "환타", "맥주", "소주", "막걸리", "와인",
        "칵테일", "레몬에이드", "청포도에이드"
    ],
    "날씨/계절": [
        "날씨", "맑아", "흐려", "비", "눈", "장마", "소나기", "태풍", "번개", "천둥",
        "무지개", "안개", "미세먼지", "황사", "더워", "추워", "쌀쌀", "서늘", "봄",
        "여름", "가을", "겨울", "꽃", "벚꽃", "단풍", "낙엽", "햇빛", "햇살", "바람"
    ],
    "학교/공부": [
        "학교", "학원", "공부", "시험", "모의고사", "수능", "중간고사", "기말고사",
        "수업", "과제", "숙제", "성적", "등급", "학점", "레포트", "팀플",
        "교실", "교과서", "문제집", "필기", "노트필기", "수학", "영어", "국어",
        "과학", "역사", "사회", "한국사", "체육", "음악", "미술", "선생님", "쌤"
    ],
    "취미/여가": [
        "게임", "롤", "오버워치", "발로란트", "피파", "배그", "마인크래프트",
        "음악", "노래", "가수", "아이돌", "콘서트", "영화", "드라마", "넷플릭스",
        "유튜브", "틱톡", "책", "소설", "웹툰", "만화", "운동", "헬스", "러닝",
        "산책", "등산", "축구", "농구", "배구", "야구", "수영", "요가", "필라테스",
        "여행", "국내여행", "해외여행", "캠핑", "피크닉", "쇼핑", "패션", "옷", "코디"
    ],
    "관계/생활": [
        "친구", "베프", "단짝", "선배", "후배", "동기",
        "가족", "엄마", "아빠", "형", "누나", "동생", "언니",
        "연애", "사랑", "남친", "여친", "썸", "짝사랑", "커플", "데이트",
        "약속", "모임", "동아리", "스터디", "생일", "파티", "축하", "기념일", "선물"
    ]
}

daily_responses = {
    "무맥락 애매한 것들": [ ""],
    "밥/음식": [
        "오늘 뭐 먹었어?", "밥은 먹었어?", "요즘 자주 먹는 음식 있어?", "야식 자주 먹어?",
        "라면 좋아해?", "치킨은 언제 먹어도 옳지 🐔", "피자랑 치킨 중에 뭐가 더 좋아?",
        "밥 먹고 나면 기분이 어때?", "요즘 입맛 당기는 음식 있어?", "밥은 혼자 먹는 게 좋아?"
    ],
    "음료/디저트": [
        "커피 자주 마셔?", "요즘은 무슨 음료가 제일 좋아?", "단 거 좋아해? 🍫",
        "버블티 좋아해?", "여름엔 빙수지 🍧", "콜라파야 사이다파야?", "차 마시는 거 좋아해?",
        "요즘 디저트 카페 가봤어?", "커피는 아이스? 핫?", "아이스크림 무슨 맛 좋아해?"
    ],
    "날씨/계절": [
        "오늘 날씨 어땠어?", "비 오는 날 기분 달라져?", "눈 오는 거 좋아해?",
        "여름이랑 겨울 중에 뭐가 더 좋아?", "요즘 좀 쌀쌀하지 않아?",
        "햇살 좋은 날엔 뭐 하고 싶어?", "바람 부는 날엔 기분이 어때?",
        "장마철은 힘들지 않아?", "가을엔 단풍 구경 가고 싶지?", "봄엔 벚꽃 보러 가봤어?"
    ],
    "학교/공부": [
        "오늘 수업 어땠어?", "과제는 다 했어?", "시험기간 힘들지?", "공부할 때 집중 잘 돼?",
        "싫어하는 과목 있어?", "좋아하는 과목은 뭐야?", "학교에서 제일 재밌는 시간은?",
        "친한 친구랑 같은 반이야?", "숙제 밀린 거 있지 않아?ㅋㅋ", "요즘 학원 자주 가?"
    ],
    "취미/여가": [
        "요즘 무슨 게임 해?", "최근에 본 영화 있어?", "드라마 보는 거 좋아해?",
        "유튜브 자주 봐?", "좋아하는 노래 있어?", "아이돌 누구 좋아해?",
        "운동 자주 해?", "여행 가고 싶은 곳 있어?", "요즘 빠져 있는 취미 있어?",
        "웹툰 보는 거 좋아해?"
    ],
    "관계/생활": [
        "친구들이랑 뭐 하고 놀아?", "가족이랑 지낼 때 어때?", "좋아하는 사람이 있어?",
        "요즘 사람 만나는 거 즐거워?", "주말에 약속 있어?", "친한 친구랑 자주 연락해?",
        "생일파티 한 적 있어?", "연애해본 적 있어?", "가족이랑 같이 시간 보내는 거 좋아해?",
        "요즘 외롭다고 느낀 적 있어?"
    ],
    "인사/자기소개": [
        "안녕! 만나서 반가워 😀",
        "하이~ 오늘 기분 어때?",
        "안녕하세요! 저는 그냥 대화하는 챗봇이에요 🤖",
        "나는 네 얘기 들어주는 AI야.",
        "나? 너랑 얘기하려고 만들어진 챗봇이야!",
        "내 이름은 끼리야, 네 얘기 잘 들어줄게!",
        "난 챗봇인데, 친구처럼 얘기해도 돼."
    ],
    "감사/칭찬": [
        "나도 고마워 🙏",
        "그렇게 말해주니까 기분 좋다 😀",
        "너 진짜 착하다!",
        "칭찬 고마워 ㅎㅎ",
        "나도 너 멋지다고 생각해 👏",
        "대단하다~",
        "너 최고야!"
    ],
    "놀람/감탄": [
        "헐 대박…",
        "진짜? ㄹㅇ?",
        "와… 그건 신기하다!",
        "소름돋아 😲",
        "우와~ 멋지다!",
        "헉 대단해!",
        "와 미쳤다ㅋㅋ"
    ],
    "욕설/부정": [
        "많이 화난 것 같아 😢",
        "그럴 때도 있지…",
        "기분 풀릴 때까지 얘기해도 돼.",
        "속상했겠다.",
        "누구나 열받을 때는 있어.",
        "괜찮아, 천천히 얘기해."
    ]
}

# 카테고리별 키워드 사전 #여기부분을 수정해주시면 됩니다
categories = {
    "기분": [
        # 기본
        "기분", "무기력", "짜증", "불쾌", "흥미없", "재미없", "힘들", "귀찮",
        # 확장
        "우울","그럭저럭", "침울", "허무", "의욕없", "짜증나", "화나", "열받", "빡쳐",
        "심심", "멍함", "무가치", "슬퍼", "불행", "지침", "권태", "짜증남",
        "짜증이남", "속상", "우울감", "의미없", "무력감", "피곤", "무감정",
        "공허", "허탈", "무기력함", "감정없", "짜증남", "불안", "마음이 무거워"
    ],
    "잠": [
        # 기본
        "잠", "불면", "졸려", "피곤", "설쳐", "못자", "깊이", "눈이 무거워",
        "누워", "밤샘", "밤새", "못잤", "깨", "졸음",
        # 확장
        "불면증", "뒤척", "뒤척임", "숙면", "단잠", "잠이 안와", "잠이 안옴",
        "수면", "수면장애", "깜빡", "비몽사몽", "잠투정", "깊은잠", "선잠",
        "꿈많음", "악몽", "자다깸", "잠깸", "자도피곤", "아침에 힘듦",
        "늦게잠", "새벽까지", "아예 못잠", "아예못잠"
    ],
    "밥": [
        # 기본
        "밥", "폭식", "굶", "허기", "배고프", "밥맛", "입맛", "토했", "간식",
        "라면", "피자", "치킨", "햄버거", "배부른데도", "과식", "먹기 싫어",
        # 확장
        "과자", "빵", "단거", "단거땡겨", "단음식", "군것질", "자극적 음식",
        "달달", "짜게", "매운거", "떡볶이", "김밥", "샌드위치", "분식",
        "단거만", "폭식증", "거식", "식욕없", "식욕부진", "아무것도 안먹음",
        "배고픈데 먹기싫", "입맛없음", "계속먹음"
    ],
    "집중": [
        # 기본
        "집중", "글자", "수업", "이해", "불안",
        # 확장
        "멍때림", "주의산만", "산만", "집중안됨", "정신없음", "멍함",
        "공부안됨", "딴짓", "자꾸산만", "몰입안됨", "집중력떨어짐",
        "산만해짐", "주위산만", "집중못함", "집중부족", "공부집중안됨"
    ],
    "사고인지": [
        # 기본
        "생각", "멍해", "무의미", "망했", "비관", "쓰레기", "죽고 싶", "초조",
        "미워", "싫어", "부정적", "희망없", "절망", "쓸모없", "공허",
        # 확장
        "자살", "죽고싶다", "살기싫다", "끝내고싶다", "없어지고싶다",
        "내탓", "나는별로", "나는못남", "나는쓸모없다", "나는가치없다",
        "아무생각없음", "생각하기싫다", "비관적", "슬프다", "미래없다",
        "희망없다", "나사라지고싶다", "내잘못", "다망함", "헛됨", "의미없음"
    ],
    "자제력": [
        # 기본
        "충동", "부수", "때리고", "화", "술",
        # 확장
        "욱함", "참기힘듦", "조절안됨", "분노", "패고싶다", "부수고싶다",
        "박살내고싶다", "때리고싶다", "욕하고싶다", "소리지르고싶다",
        "감정조절안됨", "분노조절안됨", "주체안됨", "욕설", "화풀이"
    ],
    "신체": [
        # 기본
        "머리", "두통", "복통", "소화", "몸무게", "숨", "배아파", "토할",
        "소화불량", "피곤", "힘들어", "어지러", "무거워", "가빠", "체력",
        # 확장
        "속아픔", "위경련", "위통", "속쓰림", "체함", "더부룩", "답답",
        "소화안됨", "속불편", "구토", "토함", "메스꺼움", "현기증",
        "기절할것같아", "힘빠짐", "피곤함", "무기력함", "숨막힘", "숨안쉬어짐"
    ],
    "관계": [
        # 기본
        "친구", "가족", "싫어", "관심", "수근", "귀찮",
        # 확장
        "외로움", "왕따", "따돌림", "혼자", "같이놀기싫어", "대화하기싫어",
        "말하기싫어", "인간관계힘듦", "사람피곤", "사람싫어", "사람귀찮",
        "다들날싫어", "무시", "차별", "따돌려짐", "혼자있고싶다", "나혼자",
        "관계끊고싶다", "사람싫다", "사회불안", "대인불안"
    ]
}


# 카테고리별 질문 리스트 #여기부분을 수정해주시면 됩니다
questions = {
    "기분": [
        "요즘 하루하루를 보낼 때 가장 많이 느끼는 감정은 뭐야?",
        "최근에 웃었던 순간이나 즐거웠던 경험이 있었어?",
        "요즘 자주 떠오르는 생각이나 감정이 있다면 어떤 거야?",
        "마음이 무겁게 느껴질 때는 보통 어떤 상황이 많아?"
    ],
    "잠": [
        "요즘 잠은 잘 자?",
        "밤에 잠들기 어려울 때 보통 뭐해?",
        "잠을 잘 잤을 때랑 못 잤을 때 하루가 어떻게 달라?",
        "자주 피곤하다 느끼는 순간이 있어?"
    ],
    "밥": [
        "밥 먹는 게 요즘은 어때?",
        "식사 패턴이 달라진 걸 느낀 적 있어?",
        "밥 먹고 나면 보통 기분이 어때?",
        "요즘 자주 먹게 되는 음식이 있어?"
    ],
    "집중": [
        "공부할 때 집중이 잘 안 될 때가 많아?",
        "집중을 조금이라도 유지할 수 있는 방법이 있을까?",
        "수업이 잘 안 들어올 때 너는 어떻게 해?",
        "집중하기 힘들 때 기분은 어때?"
    ],
    "사고인지": [
        "요즘 가장 자주 드는 생각은 뭐야?",
        "마음이 비관적으로 흐를 때 보통 어떤 상황이 많아?",
        "생각이 멈추지 않을 때 너는 어떻게 해?",
        "스스로를 돌아봤을 때 떠오르는 생각은 어떤 게 많아?"
    ],
    "자제력": [
        "화가 날 때 보통 어떻게 풀어?",
        "충동적으로 행동했던 경험이 최근에 있었어?",
        "기분이 격해졌을 때 스스로를 어떻게 진정시켜?",
        "화가 나면 바로 표현하는 편이야?"
    ],
    "신체": [
        "몸이 자주 불편하다고 느낄 때가 있어?",
        "피곤하거나 통증이 있을 때 하루가 어떻게 달라져?",
        "신체적인 불편함이 감정에도 영향을 주는 것 같아?",
        "가끔 숨쉬기 힘들 때는 언제야?"
    ],
    "관계": [
        "최근에 친구들이랑 있었던 일 중 기억에 남는 게 있어?",
        "가족들이랑 지내면서 편안했던 순간이 있었어?",
        "사람들과 어울릴 때 주로 어떤 기분이 들어?",
        "주변 사람들에게 쉽게 말 못하는 고민이 있니?"
    ]
}

# 어미 리스트 (자연스러운 변주 추가)
endings = [""]

# 기본 답변
default_responses = [
    "음… 잘 모르겠어.",
    "그렇구나~ 좀 더 얘기해줄래?",
    "흥미롭네 ",
    "재밌는 얘기야!"
]
# === 상태 관리 ===
current_category = None
question_index = 0
mode = None  # daily / diagnostic

def save_message(user_id, role, message):
    conn = sqlite3.connect("chat_history.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO chat_log (user_id, role, message) VALUES (?, ?, ?)",
                (user_id, role, message))
    conn.commit()
    conn.close()


def classify_and_respond(user_input, user_id):
    save_message(user_id, "user", user_input)

    # 기존 카테고리 기반 응답
    for category, keywords in daily_categories.items():
        for kw in keywords:
            if kw in user_input:
                reply = random.choice(daily_responses.get(category, default_responses))
                save_message(user_id, "bot", reply)
                return reply

    reply = random.choice(default_responses)
    save_message(user_id, "bot", reply)
    return reply


def save_message(user_id, role, message):
    conn = sqlite3.connect("chat_history.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO chat_log (user_id, role, message) VALUES (?, ?, ?)",
                (user_id, role, message))
    conn.commit()
    conn.close()

