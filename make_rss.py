import feedparser
from datetime import datetime, timedelta
from urllib.parse import quote
import re
import html
from rfeed import Item, Feed, Guid
from googlenewsdecoder import gnewsdecoder

# 방화벽 우회용 브라우저 위장
feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def gnews(query, lang="en"):
    """Google News RSS 검색 URL 생성. 공식 RSS가 없거나 불안정한 매체(Reuters, AP 등)용."""
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"


# (URL, 키워드 필터 적용 여부)
#   False = 전체 수집  → 외교·국제관계 전문 매체 (기사 대부분이 주제에 부합)
#   True  = 선별 수집  → 종합 매체 국제면 (외교 키워드가 있는 기사만)
# ※ NYT, WaPo, FT, Economist, Foreign Affairs 등 유료 매체는 제외했습니다.
feeds = [
    # ── 외교·국제관계 전문 매체 / 싱크탱크 (전체 수집, 무료) ──
    ("https://thediplomat.com/feed/", False),                            # 아시아태평양 외교·안보
    ("https://warontherocks.com/feed/", False),                          # 안보·전략 분석
    ("https://www.crisisgroup.org/rss", False),                          # 국제위기그룹: 분쟁 지역 해설
    ("https://www.lowyinstitute.org/the-interpreter/rss.xml", False),    # 호주 로위연구소: 짧은 해설글
    ("https://www.38north.org/feed/", False),                            # 북한 전문
    ("https://news.un.org/feed/subscribe/en/news/all/rss.xml", False),   # UN 뉴스
    ("https://www.rferl.org/api/ajj_uqtl-vomx-tpeb_tuqr", False),        # RFE/RL: 동유럽·러시아·중앙아
    (gnews("site:cfr.org"), False),                                      # 미 외교협회(CFR): 배경 설명 글이 많음
    (gnews("site:carnegieendowment.org"), False),                        # 카네기 국제평화재단

    # ── 영어 종합 매체 국제면 (선별 수집, 무료) ──
    ("http://feeds.bbci.co.uk/news/world/rss.xml", True),
    ("https://www.theguardian.com/world/rss", True),
    ("https://www.aljazeera.com/xml/rss/all.xml", True),
    ("https://rss.dw.com/xml/rss-en-world", True),                       # 독일 DW
    ("https://www.france24.com/en/rss", True),
    ("https://feeds.npr.org/1004/rss.xml", True),                        # NPR World
    ("https://www.politico.eu/feed/", True),                             # 유럽 정치·외교
    (gnews("site:reuters.com/world"), True),                             # Reuters (공식 RSS 없음)
    (gnews("site:apnews.com"), True),                                    # AP (공식 RSS 없음)

    # ── 한국어 매체 (선별 수집) ──
    ("https://www.voakorea.com/api/ajmjpil-vomx-tpeb-bpm", False),       # VOA 코리아 한반도 (외교 비중 높음)
    ("https://www.yna.co.kr/rss/international.xml", True),               # 연합뉴스 국제
    ("https://www.hani.co.kr/rss/international/", True),                 # 한겨레 국제

    # ── 키워드 전용 피드 (이미 키워드로 검색된 결과이므로 전체 수집) ──
    (gnews('"정상회담" OR "외교부" OR "안보리" OR "한미동맹" OR "북핵" OR "한일관계" OR "한중관계"', "ko"), False),
    (gnews('"State Department" OR "foreign minister" OR "Security Council" OR "peace talks" OR "bilateral summit"'), False),
]

# ── 외교 키워드 (선별 수집 피드에 적용) ──
actor_keywords = [
    # 기관·행위자
    'diplomacy', 'diplomat', 'diplomatic', 'ambassador', 'embassy', 'envoy',
    'foreign minister', 'foreign ministry', 'State Department', 'Secretary of State',
    'United Nations', 'UN', 'Security Council', 'NATO', 'G7', 'G20', 'EU', 'European Union',
    'ASEAN', 'BRICS', 'IAEA', 'WTO', 'ICJ', 'ICC',
    '외교', '외교부', '대사', '대사관', '특사', '국무부', '국무장관',
    '유엔', '안보리', '나토', '유럽연합', '아세안', '브릭스',
]

event_keywords = [
    # 사건·행위
    'summit', 'bilateral', 'multilateral', 'treaty', 'accord', 'ceasefire', 'truce',
    'peace talks', 'negotiation', 'sanctions', 'alliance', 'geopolitics', 'geopolitical',
    'trade war', 'tariffs', 'export controls', 'nuclear', 'denuclearization',
    'humanitarian', 'refugees', 'annexation', 'sovereignty', 'territorial',
    '정상회담', '양자', '다자', '조약', '협정', '휴전', '평화협상', '협상', '제재',
    '동맹', '지정학', '관세', '무역전쟁', '수출통제', '핵', '비핵화',
    '인도적', '난민', '주권', '영토',
]

region_keywords = [
    # 지역·현안
    'North Korea', 'Pyongyang', 'Korean Peninsula', 'Taiwan', 'Indo-Pacific',
    'South China Sea', 'Ukraine', 'Kremlin', 'Gaza', 'Middle East', 'Iran', 'Israel',
    '북한', '평양', '한반도', '한미', '한일', '한중', '대만', '인도태평양',
    '남중국해', '우크라이나', '크렘린', '가자', '중동', '이란', '이스라엘',
]

all_target_keywords = actor_keywords + event_keywords + region_keywords


def build_matcher(keywords):
    """영어 키워드는 단어 경계(\\b) 매칭(UN이 'sun'에 걸리는 것 방지), 한글은 부분 문자열 매칭."""
    korean = [k.lower() for k in keywords if re.search(r'[가-힣]', k)]
    english = [re.escape(k.lower()) for k in keywords if not re.search(r'[가-힣]', k)]
    pattern = re.compile(r'\b(?:' + '|'.join(english) + r')\b') if english else None

    def match(text):
        text = text.lower()
        if pattern and pattern.search(text):
            return True
        return any(k in text for k in korean)
    return match


is_diplomacy_news = build_matcher(all_target_keywords)


def clean_text(raw_text, strip_source=False):
    """HTML 태그 제거·특수문자 해독. Google News 제목의 ' - 매체명' 꼬리표 제거."""
    if not raw_text:
        return ""
    text = re.sub(r'<[^>]+>', '', raw_text)
    text = html.unescape(text).replace('\xa0', ' ').strip()
    if strip_source:
        for dash in [' - ', ' – ', ' — ', ' | ']:
            if dash in text:
                text = text.rsplit(dash, 1)[0].strip()
                break
    return re.sub(r'\s+', ' ', text).strip()


raw_items = []
seen_links = set()
now_utc = datetime.utcnow()
retention_days = now_utc - timedelta(days=14)

print(f"[{now_utc.strftime('%Y-%m-%d %H:%M:%S')}] 국제·외교 뉴스 RSS 수집 시작...")

for url, needs_filter in feeds:
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            print(f"⚠️  항목 없음 ({url})")
        is_gnews = "news.google.com" in url

        for entry in feed.entries:
            try:
                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                if not published_parsed:
                    continue
                published_dt = datetime(*published_parsed[:6])
                if published_dt <= retention_days:
                    continue

                raw_title = entry.get("title", "")
                raw_summary = entry.get("summary", "") or entry.get("description", "")

                if needs_filter and not is_diplomacy_news(raw_title + " " + raw_summary):
                    continue

                clean_title = clean_text(raw_title, strip_source=is_gnews)
                if not clean_title:
                    continue
                # Google News의 summary는 링크 목록이라 쓸모없음 → 제목으로 대체
                safe_description = clean_title if is_gnews else clean_text(raw_summary or raw_title)

                final_link = entry.get("link", "https://github.com")
                if is_gnews:
                    try:
                        decoded = gnewsdecoder(final_link)
                        if decoded and decoded.get("status"):
                            final_link = decoded.get("decoded_url", final_link)
                    except Exception:
                        pass

                if final_link in seen_links:   # 여러 피드에 겹친 기사 중복 제거
                    continue
                seen_links.add(final_link)

                raw_items.append((published_dt, Item(
                    title=clean_title,
                    link=final_link,
                    description=safe_description,
                    pubDate=published_dt,
                    guid=Guid(final_link)
                )))
            except Exception:
                continue

    except Exception as e:
        print(f"❌ 사이트 접근 실패 ({url}): {e}")

raw_items.sort(key=lambda x: x[0], reverse=True)
items = [target[1] for target in raw_items]

if len(items) == 0:
    items.append(Item(
        title="[안내] 현재 수집된 최신 기사가 없습니다.",
        link="https://github.com",
        description="최근 14일 내 조건에 맞는 기사가 없거나 일시적으로 사이트 접근이 지연되었습니다.",
        pubDate=now_utc,
        guid=Guid("empty_fallback_item", isPermaLink=False)
    ))

new_feed = Feed(
    title="International Affairs & Diplomacy News",
    link="https://github.com/twochaemi-dotcom/trend-tracker",
    description="외교 현안과 국제관계 기초를 위한 무료 국제뉴스 피드",
    language="ko",
    items=items
)

output_filename = "trend_feed.xml"   # 기존 GitHub Actions 워크플로와 호환되도록 파일명 유지
try:
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(new_feed.rss())
    print(f"✅ 성공: 총 {len(items)}개의 RSS 항목이 '{output_filename}'에 저장되었습니다.")
except Exception as e:
    print(f"❌ 파일 저장 실패: {e}")
