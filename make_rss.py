import feedparser
from datetime import datetime, timedelta
import re
import html
from rfeed import Item, Feed, Guid
from googlenewsdecoder import gnewsdecoder

# 방화벽 우회용 브라우저 위장
feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

urls = [
    # 모빌리티 & EV 전문 매체 (전체수집)
    "https://carapp-news.com/feed/",
    "https://electrek.co/feed/",
    "https://www.notateslaapp.com/rss/",
    "https://cleantechnica.com/feed/",
    "https://www.greencarreports.com/news/rss-feed",
    "https://news.google.com/rss/search?q=site:greencarcongress.com&hl=en-US&gl=US&ceid=US:en",
    
    # 종합 자동차 및 테크 전문 매체 (선별 수집)
    "https://www.autonews.com/arc/outboundfeeds/sitemap-news/",
    "https://techcrunch.com/category/transportation/feed/",
    "https://www.smartcitiesdive.com/feeds/news/",
    
    # 종합 기술 동향 매체 (선별 수집)
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/harvardbusinessreview",
    "https://www.technologyreview.com/feed/",
    "https://news.google.com/rss/search?q=site:news.naver.com/main/read.nhn%20OR%20site:news.naver.com/article%20%22sid=105%22&hl=ko&gl=KR&ceid=KR:ko",
    
    # 종합 앱 동향 매체 (선별 수집)
    "https://news.google.com/rss/search?q=site:surfit.io&hl=ko&gl=KR&ceid=KR:ko",
    "https://techcrunch.com/category/apps/feed/",
    "https://www.lennysnewsletter.com/feed",
    "https://productmindset.substack.com/feed",
    "https://uxdesign.cc/feed",
    
    # 키워드 기반 및 전용 앱 피드
    "https://news.google.com/rss/search?q=%22카카오모빌리티%22%20OR%20%22티맵%22%20OR%20%22커넥티드카%22%20OR%20%22쏘카%22&hl=ko&gl=KR&ceid=KR:ko",
    "https://9to5mac.com/guides/carplay/feed",
    "https://9to5google.com/guides/android-auto/feed/",
    "https://www.teslarati.com/category/tesla-software-updates/feed/",
    "https://news.google.com/rss/search?q=%22Mercedes+me%22+OR+%22myVW%22+OR+%22myAudi%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22Stellantis+app%22+OR+%22My+Jeep%22+OR+%22My+Ram%22+OR+%22Connect+ONE%22&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=%22My+BMW+app%22+OR+%22BMW+ConnectedDrive%22&hl=en-US&gl=US&ceid=US:en"
]

mobility_keywords = [
    # Vehicle & HW
    'EV', 'Electric Vehicle', 'Automotive', 'Battery', 'NACS', 'CCS',
    '전기차', '배터리', '충전 표준',
    
    # AV & Connected (SDV 핵심 영역)
    'AV', 'Autonomous Driving', 'Robotaxi', 'Autonomous Vehicle', 
    'Telematics', 'OTA', 'Over-the-Air', 'Connected Car',
    '자율주행', '로보택시', '커넥티드카', '텔레매틱스', '무선 업데이트',
    
    # MaaS & Players
    'Mobility', 'MaaS', 'Fleet', 'Kakao Mobility', 'Socar', 'Tmap',
    '모빌리티', '카카오모빌리티', '쏘카', '티맵', '차량공유'
]

technology_keywords = [
    # Platform & App Architecture
    'Superapp', 'Platform', 'OS', 'In-vehicle Infotainment', 'IVI',
    '슈퍼앱', '플랫폼', '인포테인먼트',
    
    # BM & Commerce
    'FoD', 'Feature on Demand', 'Fintech', 'Payment', 'Subscription', 'Membership',
    '핀테크', '결제', '구독', '멤버십',
    
    # AI & Personalization
    'AI Agent', 'Artificial Intelligence', 'LLM', 'Large Language Model', 'Personalization', 'Recommendation Engine',
    '인공지능', 'AI 에이전트', '개인화', '추천 엔진',
    
    # UX/UI
    'UX', 'User Experience', 'HMI', 'Human-Machine Interface',
    '사용자경험', '인터랙션 디자인'
]

all_target_keywords = mobility_keywords + technology_keywords

# 🚨 에러 원천 차단: 정규식을 버리고 가장 안전한 텍스트 파싱 방식으로 변경
def clean_text(raw_text):
    if not raw_text: return ""
    
    # 1. HTML 태그 제거 및 특수문자 해독
    text = re.sub(r'<[^>]+>', '', raw_text)
    text = html.unescape(text).replace('\xa0', ' ').strip()
    
    # 2. 다양한 대시 기호들과 파이프 기호를 표준 공백 분할용으로 정리
    for dash in ['—', '–', '-', '|']:
        if dash in text:
            parts = text.rsplit(dash, 1)  # 맨 오른쪽 대시를 기준으로 분할
            last_part = parts[1].lower().strip()
            # 분할된 뒷부분이 '네이버'나 'naver' 관련 단어라면 앞부분만 취함
            if 'naver' in last_part or '네이버' in last_part:
                text = parts[0].strip()
                
    # 3. 만약 정리 후 껍데기만 남았거나 네이버 텍스트 자체라면 제외하기 위해 빈값 리턴
    if text.lower().strip() in ['naver', '네이버', '']:
        return ""
        
    return re.sub(r'\s+', ' ', text).strip()

raw_items = []
now_utc = datetime.utcnow()
retention_days = now_utc - timedelta(days=14)

print(f"[{now_utc.strftime('%Y-%m-%d %H:%M:%S')}] RSS 피드 무손실 수집 시작...")

for url in urls:
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try: 
                published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
                
                if published_parsed:
                    published_dt = datetime(*published_parsed[:6])
                    
                    if published_dt > retention_days:
                        raw_title = entry.get("title", "")
                        raw_summary = entry.get("summary", "") or entry.get("description", "")
                        content_text = (raw_title + " " + raw_summary).lower()
                        
                        filter_required_domains = ["autonews.com", "techcrunch.com", "smartcitiesdive.com", "theverge.com", "harvardbusinessreview", "technologyreview.com", "news.naver.com", "surfit", "news.google.com"]
                        
                        if any(domain in url for domain in filter_required_domains):
                            is_mobility_news = any(keyword in content_text for keyword in all_target_keywords)
                        else:
                            is_mobility_news = True
                        
                        if is_mobility_news:
                            clean_title = clean_text(raw_title)
                            safe_description = clean_text(raw_summary if raw_summary else raw_title)
                            
                            if not clean_title:
                                continue
                                
                            final_link = entry.get("link", "https://github.com")
                            if "news.google.com" in final_link:
                                try:
                                    decoded = gnewsdecoder(final_link)
                                    if decoded and decoded.get("status"):
                                        final_link = decoded.get("decoded_url", final_link)
                                except Exception:
                                    pass
                            
                            item = Item(
                                title=clean_title,
                                link=final_link,
                                description=safe_description,
                                pubDate=published_dt,
                                guid=Guid(final_link)
                            )
                            raw_items.append((published_dt, item))
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
    title="Custom Mobility App and Technology News",
    link="https://mobilityapptrendtracker.com",
    description="Strictly valid mobility & tech news feed",
    language="ko",
    items=items
)

output_filename = "trend_feed.xml"
try:
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(new_feed.rss())
    print(f"✅ 성공: 총 {len(items)}개의 표준 RSS 항목이 '{output_filename}'에 저장되었습니다.")
except Exception as e:
    print(f"❌ 파일 저장 실패: {e}")
