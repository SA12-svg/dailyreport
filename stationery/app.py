"""
기념굿즈(데코소품) 선제대응 대시보드 — 독립형 웹앱 (포트 10050)
- 완전 독립. 기존 sku_server(10040)/daily-report(10030) 등과 별개, 어떤 기존 파일도 수정하지 않음.
- 검증된 매출 쿼리만 read-only 재사용 (analytics.py → build_sku_daily import)

목적: 데일리 주문 현황을 넘어 "선제적 대응"을 가능케 하는 예측 지표 + 기획전 추천 제공.
  http://127.0.0.1:10050/          대시보드
  http://127.0.0.1:10050/health    상태
실행: python app.py   (SKU_OPEN_BROWSER=0 면 자동 오픈 생략)
"""
import os, sys, io, json, time, threading, traceback, unicodedata
from datetime import date, datetime
from urllib.parse import quote

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from flask import Flask, Response, jsonify, request
import analytics

PORT = int(os.getenv("DECO_PORT", "10050"))
CACHE_TTL = 600  # 10분

app = Flask(__name__)
_cache = {"html": None, "ts": 0, "building": False, "promos": None}
_lock = threading.Lock()


def _build_html():
    """무거운 compute()+렌더 (1~2분). 백그라운드에서 실행해 캐시에 저장."""
    with _lock:
        if _cache["building"]:
            return
        _cache["building"] = True
    try:
        data = analytics.compute()
        html = render_page(data)
        with _lock:
            _cache["html"] = html
            _cache["ts"] = time.time()
            _cache["promos"] = data.get("promos") or {}
    except Exception:
        traceback.print_exc()
    finally:
        with _lock:
            _cache["building"] = False


_WAIT_PAGE = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
    "<meta http-equiv='refresh' content='4'><title>준비 중</title></head>"
    "<body style='font-family:system-ui,\"Malgun Gothic\",sans-serif;text-align:center;padding:70px;color:#333'>"
    "<h2>📊 대시보드 생성 중…</h2><p>DB 조회로 1~2분 걸립니다. 4초마다 자동 새로고침됩니다.</p>"
    "<p style='color:#999;font-size:.9em'>이후에는 즉시 표시됩니다.</p></body></html>")


def won(v):
    return f"{int(v):,}"


def _md(s):
    """YYYY-MM-DD -> MM/DD"""
    return s[5:].replace("-", "/")


def delta_badge(pct, good_high=True):
    """모멘텀/증감 뱃지 (status 색 + 아이콘 + 라벨, 색만으로 의미 전달 안 함)."""
    if pct is None:
        return '<span class="badge nu">– 데이터 없음</span>'
    if pct > 0:
        cls = "good" if good_high else "crit"
        ico = "▲"
        return f'<span class="badge {cls}">{ico} +{pct:.0f}%</span>'
    if pct < 0:
        cls = "crit" if good_high else "good"
        return f'<span class="badge {cls}">▼ {pct:.0f}%</span>'
    return '<span class="badge nu">— 0%</span>'


def sparkline(vals, w=96, h=26):
    if not vals:
        return ""
    mx = max(vals) or 1
    n = len(vals)
    step = w / (n - 1) if n > 1 else w
    pts = " ".join(f"{i*step:.1f},{h - (v/mx)*(h-4) - 2:.1f}" for i, v in enumerate(vals))
    last_x = (n-1)*step
    last_y = h - (vals[-1]/mx)*(h-4) - 2
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline points="{pts}" fill="none" stroke="var(--s1)" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.2" fill="var(--s1)"/></svg>')


def render_recs(recs):
    if not recs:
        return '<p class="empty">추천할 액션이 없습니다.</p>'
    cards = []
    for r in recs:
        extra = ""
        if r.get("promo_name"):
            extra += f'<div class="rec-promo">🎪 추천 기획전: <b>{r["promo_name"]}</b></div>'
        prods = [p for p in (r.get("products") or []) if p]
        if prods:
            chips = "".join(f'<span class="chip">{p}</span>' for p in prods)
            extra += f'<div class="rec-prod"><span class="pl">🛍️ 추천 상품</span>{chips}</div>'
        cta = f'<div class="rec-cta">{r.get("cta","기획전 페이지 보기")} →</div>' if r.get("link") else ""
        inner = (
            f'<div class="rec-top"><span class="rec-ico">{r["icon"]}</span>'
            f'<span class="rec-tag {r["level"]}">{r["tag"]}</span>'
            f'<span class="rec-metric {r["level"]}">{r["metric"]}</span></div>'
            f'<div class="rec-title">{r["title"]}</div>'
            f'<div class="rec-body">{r["body"]}</div>{extra}{cta}'
        )
        if r.get("link"):
            href = f'promo?cat={quote(r["link"])}'
            cards.append(f'<a class="rec {r["level"]} clickable" href="{href}" target="_blank" rel="noopener">{inner}</a>')
        else:
            cards.append(f'<div class="rec {r["level"]}">{inner}</div>')
    return '<div class="recgrid">' + "".join(cards) + "</div>"


def _promo_copy(cat):
    """카테고리별 기획전 카피(꾸밈어). 바른손카드 이벤트 톤."""
    base = {
        "tagline": "결혼식의 여운을 오래 간직하는 특별한 방법",
        "story_h": "우리의 하루를, 오래도록 곁에",
        "story_p": [
            "청첩장을 건네는 순간부터 예식이 끝난 뒤까지 — 결혼의 모든 장면에는 작은 디테일이 함께합니다.",
            "바른손카드가 제안하는 {cat}로 그 특별함을 조금 더 오래, 조금 더 감각적으로 남겨보세요.",
        ],
        "points": [
            ("🎨", "감각적인 디자인", "트렌드를 담은 유니크한 디자인으로, 어디에 두어도 분위기가 완성됩니다."),
            ("✨", "프리미엄 퀄리티", "소재부터 마감까지 꼼꼼하게. 소장하고 싶은 완성도로 만나보세요."),
            ("🙌", "간편한 셀프 제작", "원하는 문구와 사진으로 직접 디자인 — 세상에 하나뿐인 우리만의 굿즈."),
        ],
        "recommend": [
            "결혼 준비의 디테일까지 챙기고 싶은 예비부부",
            "하객에게 특별한 감동을 전하고 싶은 분",
            "예식이 끝난 뒤에도 오래 간직할 기념품을 찾는 분",
        ],
        "captions": ["감성 가득", "포토존 완성", "디테일까지"],
        "md_quote": "작은 소품 하나가 결혼식의 분위기를 완성합니다. 지금 가장 사랑받는 {cat}를 만나보세요.",
    }
    overrides = [
        (("포스터", "등신대", "아크릴"),
         {"tagline": "공간을 채우는 우리의 웨딩 무드", "captions": ["포토존의 주인공", "공간을 채우는", "우리만의 무드"]}),
        (("스티커",),
         {"tagline": "디테일을 완성하는 작은 정성", "captions": ["디테일 완성", "붙이는 재미", "센스 한 스푼"]}),
        (("스탬프",),
         {"tagline": "손끝으로 남기는 정성 한 번", "captions": ["손끝의 정성", "반복되는 감성", "나만의 마크"]}),
        (("포장", "선물"),
         {"tagline": "마음까지 포장하는 특별한 순간", "captions": ["설레는 언박싱", "마음을 담아", "선물의 완성"]}),
        (("사진", "인화", "포토"),
         {"tagline": "그날의 순간을 오래 간직하는 방법", "captions": ["그날의 미소", "인화의 감성", "오래 남길 한 장"]}),
        (("엽서", "캘린더"),
         {"tagline": "일상 속에서 매일 만나는 기념", "captions": ["매일의 기념", "책상 위 감성", "계절을 담아"]}),
        (("꽃",),
         {"tagline": "화사함으로 완성하는 그날", "captions": ["화사한 순간", "향기까지", "오래 남는"]}),
        (("퍼즐", "신문"),
         {"tagline": "우리 이야기를 특별하게 담다", "captions": ["우리 이야기", "맞춰가는 재미", "기록의 감성"]}),
    ]
    for keys, ov in overrides:
        if any(k in cat for k in keys):
            base = {**base, **ov}
            break
    # {cat} 치환
    base["story_p"] = [s.format(cat=cat) for s in base["story_p"]]
    base["md_quote"] = base["md_quote"].format(cat=cat)
    return base


def render_promo(cat, p):
    """바른손카드 이벤트 페이지(www.barunsoncard.com/Event) 톤·문구의 기획전 랜딩(예시).
    카피/단어: NEW!, 만나보세요, 소장하고 싶은, 유니크·프리미엄·한정판·셀프·콜라보,
    장바구니 담기, 직접 디자인, 샘플 무료 / 운영시간 AM 9:00~PM 6:00(공휴일 휴무)."""
    color = p.get("color", "#3949ab"); bg = p.get("bg", "#EEF"); icon = p.get("icon", "🎁")
    mom = p.get("mom", 0)
    top = p.get("top", [])
    TAGS = ["유니크", "프리미엄", "한정판", "셀프제작", "포토", "콜라보"]
    disc_cycle = [15, 20, 10, 25, 12, 18]
    cards = []
    for i, t in enumerate(top):
        d = disc_cycle[i % len(disc_cycle)]
        tag = TAGS[i % len(TAGS)]
        cnt = t.get("cnt", 0)
        unit = max(1000, int(round((t.get("amt", 0) / cnt) / 100.0) * 100)) if cnt else 0
        sale = int(unit * (1 - d / 100.0))
        hot = '<span class="hot">인기</span>' if i < 3 else ''
        price_html = (
            f'<div class="pprice"><span class="orig">{unit:,}원</span>'
            f'<span class="rate">{d}%</span><span class="sale">{sale:,}원</span></div>'
        ) if unit else '<div class="pprice"><span class="pp">가격 문의</span></div>'
        cards.append(
            f'<div class="pcard">'
            f'<div class="pthumb" style="background:{bg};color:{color}">{icon}{hot}</div>'
            f'<div class="ptag">{tag}</div>'
            f'<div class="pname">{t["name"]}</div>'
            f'<div class="pcode">{t["code"]}</div>'
            f'<div class="pproof">이번 주 <b>{cnt}</b>건 주문 · 지금 사랑받는 상품</div>'
            f'{price_html}'
            f'<div class="pbtns"><button class="pbtn buy" style="background:{color}">장바구니 담기</button>'
            f'<button class="pbtn self">직접 디자인</button></div>'
            f'</div>'
        )
    if not cards:
        cards.append('<p style="color:#888;grid-column:1/-1">아직 이번 주 대표 상품이 준비되지 않았습니다.</p>')

    attach = p.get("attach", 0)
    mom_txt = f'+{mom:.0f}%' if mom >= 0 else f'{mom:.0f}%'
    bundle = "청첩장과 함께 준비하면 더 완성도 있게" if attach < 50 else "청첩장 세트로 더 특별하게"

    co = _promo_copy(cat)
    story_p = "".join(f'<p>{s}</p>' for s in co["story_p"])
    points_html = "".join(
        f'<div class="pt"><div class="pt-i">{ic}</div><div class="pt-h">{h}</div><div class="pt-p">{txt}</div></div>'
        for ic, h, txt in co["points"])
    tiles_html = "".join(
        f'<div class="vtile" style="background:linear-gradient(150deg,{color},{color}99)">'
        f'<span class="vico">{icon}</span><span class="vcap">{cap}</span></div>'
        for cap in co["captions"])
    rec_html = "".join(f'<li>{r}</li>' for r in co["recommend"])

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{cat} 기획전 | barunson card</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;background:#fff;color:#222;font-family:system-ui,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14px;line-height:1.6}}
  a{{text-decoration:none;color:inherit}}
  .mock{{background:#222;color:#fff;text-align:center;font-size:11px;padding:5px}}
  .gnb{{display:flex;align-items:center;justify-content:space-between;max-width:1120px;margin:0 auto;padding:14px 20px;border-bottom:1px solid #eee}}
  .logo{{font-size:20px;font-weight:800;letter-spacing:-.5px}}
  .gnb .util{{display:flex;gap:16px;color:#888;font-size:12px}}
  .hero{{background:linear-gradient(135deg,{color},{color}dd);color:#fff;text-align:center;padding:60px 24px 54px}}
  .eyebrow{{font-size:13px;letter-spacing:2px;font-weight:700;opacity:.95}}
  .hero h1{{margin:12px 0 8px;font-size:34px;font-weight:800;letter-spacing:-1px}}
  .hero .lead{{font-size:17px;opacity:.95}}
  .benefit{{margin-top:20px;display:flex;gap:8px;justify-content:center;flex-wrap:wrap}}
  .benefit span{{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.45);border-radius:24px;padding:5px 15px;font-size:13px;font-weight:600}}
  .infobar{{background:#faf7f3;border-bottom:1px solid #eee;text-align:center;font-size:12px;color:#777;padding:9px}}
  .infobar b{{color:#555}}
  .wrap{{max-width:1120px;margin:0 auto;padding:34px 20px 70px}}
  .back{{display:inline-block;margin-bottom:16px;color:{color};font-size:13px;font-weight:600}}
  .sec-h{{text-align:center;margin:8px 0 26px}}
  .sec-h h2{{font-size:23px;margin:0 0 6px;font-weight:800}}
  .sec-h p{{color:#888;margin:0;font-size:14px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(212px,1fr));gap:18px}}
  .pcard{{border:1px solid #eee;border-radius:16px;padding:16px;background:#fff;transition:box-shadow .15s}}
  .pcard:hover{{box-shadow:0 6px 20px rgba(0,0,0,.09)}}
  .pthumb{{position:relative;height:132px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:52px;margin-bottom:12px}}
  .hot{{position:absolute;top:8px;left:8px;background:#e34948;color:#fff;font-size:10px;font-weight:800;border-radius:20px;padding:2px 9px}}
  .ptag{{display:inline-block;background:#f2eee9;color:{color};font-size:11px;font-weight:700;border-radius:6px;padding:2px 8px;margin-bottom:6px}}
  .pname{{font-weight:700;font-size:15px}}
  .pcode{{color:#aaa;font-size:11px;margin:2px 0 8px}}
  .pproof{{color:#777;font-size:12px;margin-bottom:10px}}
  .pprice{{display:flex;align-items:baseline;gap:7px;margin-bottom:12px}}
  .pprice .orig{{color:#bbb;text-decoration:line-through;font-size:12px}}
  .pprice .rate{{color:#e34948;font-weight:800;font-size:17px}}
  .pprice .sale{{font-weight:800;font-size:17px}}
  .pprice .pp{{color:#999;font-size:12px}}
  .pbtns{{display:flex;gap:6px}}
  .pbtn{{flex:1;border:none;border-radius:10px;padding:10px;font-size:13px;font-weight:700;cursor:pointer}}
  .pbtn.buy{{color:#fff}}
  .pbtn.self{{background:#fff;border:1px solid #ddd;color:#555}}
  .hero-tag{{margin-top:10px;font-size:13px;opacity:.9;font-weight:600}}
  .story{{display:grid;grid-template-columns:1fr 1.2fr;gap:26px;align-items:center;margin:8px 0 34px}}
  .story-visual{{position:relative;border-radius:18px;min-height:230px;display:flex;flex-direction:column;
    align-items:center;justify-content:center;color:#fff;overflow:hidden}}
  .story-visual .sv-ico{{font-size:74px}}
  .story-visual .sv-tag{{margin-top:12px;font-size:15px;font-weight:700;background:rgba(0,0,0,.16);
    padding:6px 16px;border-radius:24px}}
  .story-copy .eyebrow2{{color:{color};font-weight:800;letter-spacing:2px;font-size:12px}}
  .story-copy h2{{font-size:26px;margin:6px 0 12px;font-weight:800;letter-spacing:-.5px}}
  .story-copy p{{color:#555;margin:0 0 10px;font-size:15px}}
  .points{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:0 0 34px}}
  .pt{{background:#faf9f7;border:1px solid #eee;border-radius:14px;padding:20px}}
  .pt-i{{font-size:30px}}
  .pt-h{{font-weight:800;font-size:16px;margin:8px 0 5px}}
  .pt-p{{color:#666;font-size:13px}}
  .tiles{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 34px}}
  .vtile{{position:relative;border-radius:14px;height:170px;display:flex;flex-direction:column;
    align-items:center;justify-content:center;color:#fff}}
  .vtile .vico{{font-size:52px}}
  .vtile .vcap{{margin-top:10px;font-weight:700;font-size:15px;text-shadow:0 1px 4px rgba(0,0,0,.25)}}
  .recbox{{background:#fff;border:1px solid #eee;border-radius:16px;padding:22px 24px;margin:0 0 40px}}
  .recbox .rec-h{{font-weight:800;font-size:17px;margin-bottom:12px}}
  .rec-list{{margin:0;padding:0;list-style:none;display:grid;gap:9px}}
  .rec-list li{{position:relative;padding-left:26px;color:#444;font-size:14px}}
  .rec-list li::before{{content:"✓";position:absolute;left:0;color:{color};font-weight:800}}
  .mdq{{margin:38px 0 0;padding:22px 26px;border-left:4px solid {color};background:#faf9f7;
    border-radius:0 12px 12px 0;font-size:16px;font-weight:600;color:#333}}
  .mdq cite{{display:block;margin-top:8px;font-size:13px;color:#999;font-weight:400;font-style:normal}}
  .divider{{text-align:center;color:#ccc;letter-spacing:6px;margin:6px 0 24px}}
  @media(max-width:720px){{.story{{grid-template-columns:1fr}}.points,.tiles{{grid-template-columns:1fr}}}}
  .planbox{{margin:30px 0 0;background:#faf9f7;border:1px solid #eee;border-radius:14px;padding:18px 20px}}
  .planbox h3{{margin:0 0 8px;font-size:15px}}
  .planbox p{{margin:0;color:#666;font-size:13px}}
  .notice{{margin-top:26px;color:#999;font-size:12px;line-height:1.9;border-top:1px solid #eee;padding-top:16px}}
</style></head><body>
  <div class="mock">이 페이지는 대시보드 추천으로 <b>자동 생성된 기획전 예시</b>입니다 · 가격·할인·기간은 예시값입니다</div>
  <div class="gnb"><div class="logo">barunson <span style="color:{color}">card</span></div>
    <div class="util"><span>고객센터</span><span>로그인</span><span>장바구니</span></div></div>

  <div class="hero">
    <div class="eyebrow">NEW ! · 이번 주 MD PICK</div>
    <h1>{icon} 소장하고 싶은 유니크함, {cat}</h1>
    <div class="lead">지금 가장 사랑받는 {cat}를 만나보세요</div>
    <div class="hero-tag">{co['tagline']}</div>
    <div class="benefit"><span>🎁 샘플 무료</span><span>🏷️ 기획전 쿠폰</span><span>🚚 무료배송</span><span>🔥 인기 급상승 {mom_txt}</span></div>
  </div>
  <div class="infobar">기획전 기간 <b>이번 주 한정</b> · 상담 운영시간 <b>AM 9:00 ~ PM 6:00</b> (공휴일 휴무)</div>

  <div class="wrap">
    <a class="back" href="./">← 대시보드로 돌아가기</a>

    <div class="story">
      <div class="story-visual" style="background:linear-gradient(140deg,{color},{color}bb)">
        <span class="sv-ico">{icon}</span>
        <span class="sv-tag">{co['tagline']}</span>
      </div>
      <div class="story-copy">
        <div class="eyebrow2">STORY</div>
        <h2>{co['story_h']}</h2>
        {story_p}
      </div>
    </div>

    <div class="points">{points_html}</div>

    <div class="divider">◦ ◦ ◦</div>
    <div class="tiles">{tiles_html}</div>

    <div class="recbox">
      <div class="rec-h">이런 분께 추천해요 🤍</div>
      <ul class="rec-list">{rec_html}</ul>
    </div>

    <div class="sec-h">
      <h2>이번 주 인기 {cat} 🔥</h2>
      <p>실시간 주문이 몰리는 대표 상품만 모았어요 · {bundle}</p>
    </div>
    <div class="grid">{''.join(cards)}</div>

    <blockquote class="mdq">“{co['md_quote']}”<cite>— 바른손카드 MD</cite></blockquote>

    <div class="planbox">
      <h3>🧭 MD 참고 (내부)</h3>
      <p>· <b>{cat}</b>는 최근 7일 <b>{mom_txt}</b> 모멘텀으로 주문이 몰리고 있어, 지금 상단 배너·기획전 노출을 집중할 타이밍입니다.<br>
         · 위 대표 상품은 최근 7일 매출 상위 상품(추천 상품)입니다. · 청첩장 동반율 {attach:.0f}%.</p>
    </div>

    <div class="notice">
      · 본 페이지는 기념굿즈 선제대응 대시보드 추천에 따라 자동 생성된 <b>기획전 예시(목업)</b>입니다. 실제 판매 페이지가 아니며 가격·할인율·기간은 예시값입니다.<br>
      · 데이터 기준: 결제완료·취소제외 · 상담 운영시간 평일 09:00 ~ 18:00 (공휴일 휴무)
    </div>
  </div>
</body></html>"""


def _wow(cur, prev):
    """WoW 셀. prev=0 & cur>0 → '신규', 둘 다 0 → 공란, 그 외 증감%."""
    if not prev:
        return '<span class="wnew">신규</span>' if cur else ''
    p = (cur - prev) / prev * 100
    cls = "wup" if p >= 0 else "wdn"
    sg = "+" if p >= 0 else ""
    return f'<span class="{cls}">{sg}{p:.0f}%</span>'


# 주간 리포트 지표 열 순서 (첨부 이미지: 수량 | 주문 | 금액). vec9 인덱스.
_WCOLS = [("수량", 1), ("주문", 0), ("금액", 2)]


def _num(mi, v):
    return f"{v:,}" if mi == 2 else f"{v}"


def render_weekly(w):
    """첨부 이미지 포맷의 주간 리포트 표 (서버 렌더). 지표=열, 데일리=금액. 맨 끝에 상품별 금액 WoW 열 포함."""
    weeks = w["weeks"]; wa, wb, wc = weeks[0], weeks[1], weeks[2]
    dd = w["daily_dates"]; dwd = w["daily_wd"]; dwe = w["daily_weekend"]
    ncol_daily = len(dd)
    today = w.get("today")
    cur_badge = ' <span class="curwk">진행중</span>' if wc.get("current") else ''

    def sum_cells(obj_key, o, mkclass=""):
        """한 주(wa/wb/wc/tot)의 수량·주문·금액 3칸."""
        vec = o[obj_key]
        return "".join(f'<td class="num {mkclass}">{_num(mi, vec[mi])}</td>' for _, mi in _WCOLS)

    def daily_cells(o):
        """W(n) 일별 금액 7칸. 첫 칸(기준주 시작)에 wkline로 빨간 구분선."""
        h = ""
        for i in range(ncol_daily):
            v = o["daily"][i][2]  # 금액
            cls = ("num" + (" wkline" if i == 0 else "") + (" weekend" if dwe[i] else "")
                   + (" wtoday" if dd[i] == today else "") + ("" if v else " zero"))
            h += f'<td class="{cls}">{_num(2, v)}</td>'
        return h

    def wow_row_cells(o):
        """WoW 행 — 모든 칸: W(a)=vs 직전주, W(b)=vs W(a), 일별=vs 전주 같은요일(금액),
        W(c)=vs W(b). 미래 일자는 공란."""
        c = ""
        for _, mi in _WCOLS:                                   # W(a)
            c += f'<td class="num wowc">{_wow(o["wa"][mi], o["pre"][mi])}</td>'
        for _, mi in _WCOLS:                                   # W(b)
            c += f'<td class="num wowc">{_wow(o["wb"][mi], o["wa"][mi])}</td>'
        for i in range(ncol_daily):                            # 일별(금액)
            wl = " wkline" if i == 0 else ""
            if today and dd[i] > today:
                c += f'<td class="num{wl}"></td>'
            else:
                c += f'<td class="num wowc{wl}">{_wow(o["daily"][i][2], o["daily_prev"][i][2])}</td>'
        for _, mi in _WCOLS:                                   # W(c)
            c += f'<td class="num wowc">{_wow(o["wc"][mi], o["wb"][mi])}</td>'
        return c

    def amt_wow_cell(o, cls="num wowc wowamt"):
        """맨 끝 '금액 WoW' 열 — 기준주(W(c)) 금액 vs 직전주(W(b)) 금액."""
        return f'<td class="{cls}">{_wow(o["wc"][2], o["wb"][2])}</td>'

    def chan_cells(o, cls="num mut"):
        """바른손카드/바른손몰 매출 2칸 — 카테고리 합계·총합계 행에만 채움(3주 전체 합)."""
        chan = o.get("chan", {"card": 0, "mall": 0})
        return f'<td class="{cls}">{won(chan["card"])}</td><td class="{cls}">{won(chan["mall"])}</td>'

    def chan_cells_blank():
        return '<td class="num"></td><td class="num"></td>'

    # ---- 헤더 ----
    h1 = (
        '<tr>'
        '<th rowspan="2" class="lbl">카테고리</th>'
        '<th rowspan="2" class="lbl">상품코드</th>'
        '<th rowspan="2" class="lbl">상품명</th>'
        f'<th colspan="3" class="wg">W{wa["n"]} 합산<br><small>{_md(wa["from"])}~{_md(wa["to"])}</small></th>'
        f'<th colspan="3" class="wg">W{wb["n"]} 합산<br><small>{_md(wb["from"])}~{_md(wb["to"])}</small></th>'
        f'<th colspan="{ncol_daily}" class="wg dailyg">W{wc["n"]} 데일리(금액){cur_badge}<br><small>{_md(wc["from"])}~{_md(wc["to"])}</small></th>'
        f'<th colspan="3" class="wg">W{wc["n"]} 합산{cur_badge}<br><small>{_md(wc["from"])}~{_md(wc["to"])}</small></th>'
        '<th rowspan="2" class="wg wowamt">금액 WoW</th>'
        '<th rowspan="2" class="wg">바른손카드<br><small>3주 합계</small></th>'
        '<th rowspan="2" class="wg">바른손몰<br><small>3주 합계</small></th>'
        '</tr>'
    )
    h2 = '<tr>'
    for _ in range(2):
        for lbl, _mi in _WCOLS:
            h2 += f'<th class="num">{lbl}</th>'
    for i in range(ncol_daily):
        cls = ("num day" + (" wkline" if i == 0 else "") + (" weekend" if dwe[i] else "")
               + (" wtoday" if dd[i] == today else ""))
        h2 += f'<th class="{cls}"><div class="wd">{dwd[i]}</div>{_md(dd[i])}</th>'
    for lbl, _mi in _WCOLS:
        h2 += f'<th class="num">{lbl}</th>'
    h2 += '</tr>'

    # ---- 본문 ----
    body = []
    for cat in w["cats"]:
        skus = cat["skus"]; K = len(skus)
        for i, s in enumerate(skus):
            tds = ""
            if i == 0:
                tds += (f'<td class="lbl catcell" rowspan="{K}" '
                        f'style="background:{cat["bg"]};color:{cat["color"]}">{cat["icon"]} {cat["name"]}</td>')
            disc = " disc" if s["disc"] else ""
            tds += f'<td class="lbl code{disc}">{s["code"]}</td>'
            tds += f'<td class="lbl name{disc}">{s["name"]}</td>'
            tds += (sum_cells("wa", s) + sum_cells("wb", s) + daily_cells(s) + sum_cells("wc", s)
                    + amt_wow_cell(s) + chan_cells_blank())
            rowcls = "pr catstart" if i == 0 else "pr"
            body.append(f'<tr class="{rowcls}">{tds}</tr>')
        # 카테고리 합계
        sub = cat["sub"]
        st = ('<td class="lbl subL" colspan="2"></td><td class="lbl subL">합계</td>'
              + sum_cells("wa", sub, "subc") + sum_cells("wb", sub, "subc")
              + daily_cells(sub) + sum_cells("wc", sub, "subc totc")
              + amt_wow_cell(sub, "num subc wowc wowamt") + chan_cells(sub, "num subc mut"))
        body.append(f'<tr class="subr">{st}</tr>')
        # 카테고리 WoW
        wt = ('<td class="lbl subL" colspan="2"></td><td class="lbl subL wowL">WoW</td>' + wow_row_cells(sub)
              + '<td class="num wowc wowamt"></td>' + chan_cells_blank())
        body.append(f'<tr class="wowr">{wt}</tr>')

    # ---- 총합계 + WoW ----
    g = w["grand"]
    gt = ('<td class="lbl grandL" colspan="3">총합계</td>'
          + sum_cells("wa", g, "grandc") + sum_cells("wb", g, "grandc")
          + daily_cells(g) + sum_cells("wc", g, "grandc totc")
          + amt_wow_cell(g, "num grandc wowc wowamt") + chan_cells(g, "num grandc mut"))
    body.append(f'<tr class="grandr">{gt}</tr>')
    gw = ('<td class="lbl grandL" colspan="3">WoW</td>' + wow_row_cells(g)
          + '<td class="num wowc wowamt"></td>' + chan_cells_blank())
    body.append(f'<tr class="grandr wowr">{gw}</tr>')

    nsku = sum(len(c["skus"]) for c in w["cats"])
    cur_note = " (진행중)" if wc.get("current") else ""
    note = (f'<div class="wnote">W{wa["n"]} ~ W{wc["n"]}{cur_note} · 기준주=W{wc["n"]}({_md(wc["from"])}~{_md(wc["to"])}) 일별 · '
            f'3주간 판매 상품 {nsku}개 · WoW=합계 기준(수량/주문/금액) · 맨 끝 금액 WoW=W{wc["n"]} vs W{wb["n"]} 금액 · '
            f'바른손카드/바른손몰=3주(W{wa["n"]}~W{wc["n"]}) 합계 매출, 카테고리 합계·총합계 행에서만 표시</div>')
    return (note + '<div class="dbox"><table id="wtbl" class="gt wk">'
            '<thead>' + h1 + h2 + '</thead><tbody>' + "".join(body) + '</tbody></table></div>'
            + render_weekly_channel(w))


def render_weekly_channel(w):
    """주차별 바른손카드/바른손몰 수량·주문·금액 + 청첩장 동반주문비율(동반율)·단독주문비율(단독율) 요약표.
    기존 #wtbl 은 그대로 두고 같은 주간 리포트 영역에 별도 표로 추가 — #wcopy 복사 버튼이 두 표를 함께 복사한다."""
    weeks = w["weeks"]; cw = w.get("chan_weeks") or {}
    wa, wb, wc = weeks[0], weeks[1], weeks[2]
    zero = {"cnt": 0, "qty": 0, "amt": 0, "wi_cnt": 0, "st_cnt": 0}

    def ratio(a, key):
        tot = a["wi_cnt"] + a["st_cnt"]
        return (a[key] / tot * 100.0) if tot else None

    def cell_pct(pct):
        return f'<td class="num">{pct:.0f}%</td>' if pct is not None else '<td class="num mut">–</td>'

    def chan_cells9(a):
        return (f'<td class="num">{a["qty"]}</td><td class="num">{a["cnt"]}</td><td class="num">{won(a["amt"])}</td>'
                + cell_pct(ratio(a, "wi_cnt")) + cell_pct(ratio(a, "st_cnt")))

    def row(sub, wk_key, badge=""):
        a = cw.get(wk_key, {}).get("card", zero)
        m = cw.get(wk_key, {}).get("mall", zero)
        return (f'<tr><td class="lbl">W{sub["n"]}{badge}<br><small>{_md(sub["from"])}~{_md(sub["to"])}</small></td>'
                + chan_cells9(a) + chan_cells9(m) + '</tr>')

    cur_badge = ' <span class="curwk">진행중</span>' if wc.get("current") else ''
    rows_html = row(wa, "wa") + row(wb, "wb") + row(wc, "wc", cur_badge)

    tot = {"card": dict(zero), "mall": dict(zero)}
    for wk_key in ("wa", "wb", "wc"):
        for ch in ("card", "mall"):
            src = cw.get(wk_key, {}).get(ch, zero)
            for k in tot[ch]:
                tot[ch][k] += src.get(k, 0)
    total_row = ('<tr class="grandr"><td class="lbl grandL">총합계</td>'
                 + chan_cells9(tot["card"]) + chan_cells9(tot["mall"]) + '</tr>')

    subhead = ('<th class="num">수량</th><th class="num">주문</th><th class="num">금액</th>'
               '<th class="num">동반율<br><small>청첩장</small></th><th class="num">단독율</th>')
    head = ('<tr><th rowspan="2" class="lbl">주차</th>'
            '<th colspan="5" class="wg">바른손카드</th>'
            '<th colspan="5" class="wg">바른손몰</th></tr>'
            '<tr>' + subhead + subhead + '</tr>')

    note = (f'<div class="wnote">💳 채널별(바른손카드=sales_Gubun SB · 바른손몰=B/H) 주차별 수량·주문·금액 + '
            f'청첩장 동반주문비율(동반율)·단독주문비율(단독율, 주문건수 기준) · W{wa["n"]}~W{wc["n"]}</div>')
    return (note + '<div class="dbox"><table id="wchantbl" class="gt wk">'
            '<thead>' + head + '</thead><tbody>' + rows_html + total_row + '</tbody></table></div>')


def render_momentum(cat_rows):
    # 활성(최근28일 주문>=1) 우선, 모멘텀 내림차순
    rows = [c for c in cat_rows if c["total28"] >= 1]
    rows.sort(key=lambda x: -x["mom"])
    trs = []
    for c in rows:
        badge = delta_badge(c["mom"])
        attach_txt = f'{c["attach"]:.0f}%' if c["r7_cnt"] else "—"
        trs.append(
            f'<tr>'
            f'<td class="lbl">{c["icon"]} {c["name"]}</td>'
            f'<td class="sp">{sparkline(c["spark"])}</td>'
            f'<td class="n">{c["r7_cnt"]}</td>'
            f'<td class="n mut">{c["b28_avg7"]}</td>'
            f'<td class="n">{badge}</td>'
            f'<td class="n">{won(c["r7_amt"])}</td>'
            f'<td class="n mut">{won(c.get("card_r7_amt",0))}</td>'
            f'<td class="n mut">{won(c.get("mall_r7_amt",0))}</td>'
            f'<td class="n">{attach_txt}</td>'
            f'</tr>'
        )
    return (
        '<table class="mom"><thead><tr>'
        '<th class="lbl">카테고리</th><th>최근 14일 추이</th>'
        '<th class="n">최근7일<br><span class="sub">주문</span></th>'
        '<th class="n">평소<br><span class="sub">주/28일평균</span></th>'
        '<th class="n">모멘텀<br><span class="sub">vs 평소</span></th>'
        '<th class="n">최근7일<br><span class="sub">매출(전체)</span></th>'
        '<th class="n">바른손카드<br><span class="sub">최근7일 매출</span></th>'
        '<th class="n">바른손몰<br><span class="sub">최근7일 매출</span></th>'
        '<th class="n">동반율<br><span class="sub">청첩장</span></th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table>'
    )


def render_attach(cat_rows):
    """카테고리별 청첩장 동반율 + 크로스셀 액션 가이드."""
    rows = [c for c in cat_rows if c["total28"] >= 1]
    enough = sorted([c for c in rows if c["r7_cnt"] >= 3], key=lambda x: x["attach"])
    thin = sorted([c for c in rows if c["r7_cnt"] < 3], key=lambda x: x["name"])

    def tier(c):
        a = c["attach"]
        if a < 35:
            return ("crit", "🎁 크로스셀 기회 큼", "청첩장 결제단계에 번들·추천으로 노출 검토")
        if a < 60:
            return ("warn", "🔎 여지 있음", "결제완료 페이지 추천 상품 우선순위를 높여보세요")
        return ("good", "✅ 잘 붙는 중", "단독 유입(검색·SNS) 확대가 매출 확장에 더 유리")

    def row_html(c, thin_row=False):
        if thin_row:
            cls, tag, action = "nu", "표본 부족", "최근 7일 주문 3건 미만 — 판단 보류"
        else:
            cls, tag, action = tier(c)
        return (
            '<tr>'
            f'<td class="lbl">{c["icon"]} {c["name"]}</td>'
            f'<td class="n">{c["r7_cnt"]}</td>'
            f'<td class="n">{c["r7_wi"]}</td>'
            f'<td class="n mut">{c["r7_st"]}</td>'
            f'<td class="n">{c["attach"]:.0f}%</td>'
            f'<td class="n"><span class="badge {cls}">{tag}</span></td>'
            f'<td class="act">{action}</td>'
            '</tr>'
        )

    trs = "".join(row_html(c) for c in enough) + "".join(row_html(c, True) for c in thin)
    if not trs:
        return '<p class="empty">활성 카테고리가 없습니다.</p>'
    return (
        '<table class="mom attach"><thead><tr>'
        '<th class="lbl">카테고리</th>'
        '<th class="n">최근7일<br><span class="sub">주문</span></th>'
        '<th class="n">동반<br><span class="sub">청첩장과 함께</span></th>'
        '<th class="n">단독<br><span class="sub">이 상품만</span></th>'
        '<th class="n">동반율</th>'
        '<th class="n">상태</th>'
        '<th class="act">액션 가이드</th>'
        '</tr></thead><tbody>' + trs + '</tbody></table>'
    )


def _pp_badge(diff):
    """%p(퍼센트 포인트) 차이 배지 — 동반율 WoW 처럼 두 비율의 차이를 표시할 때."""
    if diff is None:
        return '<span class="badge nu">–</span>'
    if diff == 0:
        return '<span class="badge nu">— 0%p</span>'
    cls = "good" if diff > 0 else "crit"
    ico = "▲" if diff > 0 else "▼"
    sign = "+" if diff > 0 else ""
    return f'<span class="badge {cls}">{ico} {sign}{diff:.0f}%p</span>'


def render_channel(channel):
    """오늘/최근7일/이번달 × 전체/바른손카드/바른손몰 매출 요약 표 (sales_Gubun 기준)."""
    rows = [("오늘", channel["today"]), ("최근 7일", channel["r7"]), ("이번달(MTD)", channel["mtd"])]
    trs = []
    for label, c in rows:
        card_pct = (c["card_amt"] / c["all_amt"] * 100.0) if c["all_amt"] else 0.0
        mall_pct = (c["mall_amt"] / c["all_amt"] * 100.0) if c["all_amt"] else 0.0
        trs.append(
            f'<tr><td class="lbl">{label}</td>'
            f'<td class="n">{c["all_cnt"]}건 · {won(c["all_amt"])}원</td>'
            f'<td class="n">{c["card_cnt"]}건 · {won(c["card_amt"])}원 <span class="mut">({card_pct:.0f}%)</span></td>'
            f'<td class="n">{c["mall_cnt"]}건 · {won(c["mall_amt"])}원 <span class="mut">({mall_pct:.0f}%)</span></td>'
            f'</tr>'
        )
    return (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">구분</th><th class="n">전체</th><th class="n">바른손카드</th><th class="n">바른손몰</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )


def render_stationery(s):
    """문구류(메시지카드/엽서·캘린더) 스포트라이트: 최근7일 매출·주문·수량, 모멘텀, 동반율, 취소율."""
    if not s.get("codes"):
        return ('<p class="empty">문구류(메시지 카드/엽서·캘린더)로 등록된 상품이 없습니다 — '
                'categories.json의 해당 카테고리 erp_patterns 확인이 필요합니다.</p>')
    badge = delta_badge(s["mom"])
    return (
        '<div class="wistbox">'
        f'<div class="wist-row"><span class="wist-k">최근 7일 매출</span>'
        f'<span class="wist-v">{won(s["r7_amt"])}원 · {s["r7_cnt"]}건 · {s["r7_qty"]}개</span></div>'
        f'<div class="wist-row"><span class="wist-k">평소(28일 평균) 대비</span><span class="wist-v">{badge}</span></div>'
        f'<div class="wist-row"><span class="wist-k">🎀 청첩장 동반율</span>'
        f'<span class="wist-v">{s["attach"]:.0f}% <span class="mut">(동반 {s["r7_wi"]}건 · 단독 {s["r7_st"]}건)</span></span></div>'
        f'<div class="wist-row"><span class="wist-k">🚫 취소율(최근 28일)</span>'
        f'<span class="wist-v">{s["cancel_rate"]:.1f}% <span class="mut">(취소 {s["cancel_cnt"]}건 / 유효 {s["valid28"]}건)</span></span></div>'
        + render_sf_poster(s.get("sf_poster")) +
        '</div>'
    )


def render_sf_poster(p):
    """문구류 스포트라이트 안 sf_ 포스터(셀프 포스터) 수량 줄."""
    if not p or not p.get("codes"):
        return ''
    return (
        f'<div class="wist-row"><span class="wist-k">🖼️ sf_ 포스터 (최근 7일)</span>'
        f'<span class="wist-v">{p["r7_qty"]}개 · {p["r7_cnt"]}건 · {won(p["r7_amt"])}원 '
        f'<span class="mut">(출시 {p["since"]} 이후 누적 {p["total_qty"]}개 · {", ".join(p["codes"])})</span></span></div>'
    )


def render_best(items, empty_msg="데이터 없음"):
    """상품 랭킹 표 (최근7일 매출순) — 전체/문구류 공용."""
    if not items:
        return f'<p class="empty">{empty_msg}</p>'
    trs = []
    for i, p in enumerate(items, 1):
        trs.append(
            '<tr>'
            f'<td class="n mut">{i}</td>'
            f'<td class="lbl">{p["name"]}<span class="code" style="margin-left:6px">{p["code"]}</span></td>'
            f'<td class="lbl mut">{p.get("cat","")}</td>'
            f'<td class="n">{won(p["amt"])}</td>'
            f'<td class="n mut">{p["cnt"]}건</td>'
            '</tr>'
        )
    return (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="n">#</th><th class="lbl">상품</th><th class="lbl">카테고리</th>'
        '<th class="n">최근7일 매출</th><th class="n">주문수</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )


def render_cancel(cancel):
    """카테고리별 취소 현황 (최근 28일, 결제 후 취소 vs 유효주문)."""
    rows = [r for r in cancel["rows"] if (r["valid"] + r["cancel"]) > 0]
    if not rows:
        return '<p class="empty">데이터 없음</p>'
    trs = []
    for r in rows:
        cls = "crit" if r["rate"] >= 15 else ("warn" if r["rate"] >= 8 else "good")
        trs.append(
            '<tr>'
            f'<td class="lbl">{r["icon"]} {r["name"]}</td>'
            f'<td class="n">{r["valid"]}</td>'
            f'<td class="n mut">{r["cancel"]}</td>'
            f'<td class="n"><span class="badge {cls}">{r["rate"]:.1f}%</span></td>'
            '</tr>'
        )
    overall = (f'<div class="wist-row"><span class="wist-k">전체</span>'
               f'<span class="wist-v">{cancel["overall_rate"]:.1f}% '
               f'<span class="mut">(취소 {cancel["overall_cancel"]}건 / 유효 {cancel["overall_valid"]}건)</span></span></div>')
    table = (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">카테고리</th><th class="n">유효주문<br><span class="sub">최근28일</span></th>'
        '<th class="n">취소건수</th><th class="n">취소율</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )
    return f'<div class="wistbox">{overall}</div>' + table


def _pct_badge(rate, good=60, warn=40):
    """비율(%) 자체를 절대 구간으로 평가하는 배지 — delta_badge(증감%)와 달리 결제전환율처럼
    '얼마나 좋은 수준인가'를 절대값으로 봐야 하는 지표용."""
    if rate is None:
        return '<span class="badge nu">데이터 없음</span>'
    cls = "good" if rate >= good else ("warn" if rate >= warn else "crit")
    return f'<span class="badge {cls}">{rate:.0f}%</span>'


def render_funnel(funnel):
    """결제 전환 퍼널 — 카테고리별 주문생성(장바구니) 대비 결제완료 비율. 이탈률 높은 순(전환율 낮은 순)."""
    rows = [r for r in funnel["rows"] if (r["paid"] + r["unpaid"]) > 0]
    if not rows:
        return '<p class="empty">데이터 없음</p>'
    trs = []
    for r in rows:
        trs.append(
            '<tr>'
            f'<td class="lbl">{r["icon"]} {r["name"]}</td>'
            f'<td class="n">{r["paid"]}</td>'
            f'<td class="n mut">{r["unpaid"]}</td>'
            f'<td class="n">{_pct_badge(r["rate"])}</td>'
            '</tr>'
        )
    overall = (f'<div class="wist-row"><span class="wist-k">전체 결제 전환율</span>'
               f'<span class="wist-v">{_pct_badge(funnel["overall_rate"])} '
               f'<span class="mut">(결제완료 {funnel["overall_paid"]}건 / 미결제(이탈) {funnel["overall_unpaid"]}건)</span></span></div>')
    table = (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">카테고리</th><th class="n">결제완료</th><th class="n">미결제(이탈)</th><th class="n">결제전환율</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )
    note = (f'<div class="wnote">최근 {funnel["window_days"]}일 · 주문 생성(장바구니 담김) 후 '
            f'{funnel["stale_days"]}일 이상 지나도 결제가 안 된 건만 이탈로 집계(결제 진행 중인 최근 주문은 제외) · '
            f'결제 후 취소된 건은 결제 성공(퍼널 통과)으로 집계 — 취소는 별도(취소 현황) 지표 참고</div>')
    return f'<div class="wistbox">{overall}</div>' + table + note


def render_crosssell(cs):
    """청첩장 → 굿즈 Cross-sell 전환율 — 전체 청첩장 판매 대비 카테고리별 동반 비율(최근 7일).
    render_attach(카테고리 관점의 동반율)와 반대 방향: 청첩장 전체 판매 관점의 업셀 전환율."""
    rows = [r for r in cs["rows"] if r["r7_wi"] > 0]
    if not rows:
        return '<p class="empty">최근 7일 청첩장과 함께 팔린 부가상품이 없습니다.</p>'
    trs = []
    for r in rows:
        trs.append(
            '<tr>'
            f'<td class="lbl">{r["icon"]} {r["name"]}</td>'
            f'<td class="n">{r["r7_wi"]}건</td>'
            f'<td class="n">{r["rate"]:.1f}%</td>'
            '</tr>'
        )
    table = (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">카테고리</th><th class="n">동반건수<br><span class="sub">최근7일</span></th>'
        '<th class="n">청첩장 대비 비율</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )
    note = (f'<div class="wnote">최근 7일 결제완료 청첩장 전체 <b>{cs["total_invites_r7"]}건</b> 대비 '
            f'각 카테고리가 함께 팔린 비율(청첩장 100건당 몇 건에 이 카테고리가 추가됐는지) · '
            f'낮을수록 아직 덜 알려진 업셀 여지가 큰 카테고리</div>')
    return table + note


def render_aov(cat_rows):
    """카테고리별 평균 객단가(AOV) 추이 — 최근7일 vs 직전7일."""
    rows = [c for c in cat_rows if c["r7_cnt"] > 0]
    if not rows:
        return '<p class="empty">데이터 없음</p>'
    rows.sort(key=lambda x: -x["aov_r7"])
    trs = []
    for c in rows:
        badge = delta_badge(c["aov_delta"]) if c["aov_delta"] is not None else '<span class="badge nu">–</span>'
        trs.append(
            '<tr>'
            f'<td class="lbl">{c["icon"]} {c["name"]}</td>'
            f'<td class="n">{won(c["aov_r7"])}원</td>'
            f'<td class="n mut">{won(c["aov_p7"])}원</td>'
            f'<td class="n">{badge}</td>'
            '</tr>'
        )
    return (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">카테고리</th><th class="n">평균객단가<br><span class="sub">최근7일</span></th>'
        '<th class="n">직전7일</th><th class="n">증감</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )


def render_pareto(p):
    """매출 집중도(ABC/파레토) — 최근 28일 SKU 기준."""
    if not p["rows"]:
        return '<p class="empty">데이터 없음</p>'
    head = (
        '<div class="wistbox">'
        f'<div class="wist-row"><span class="wist-k">매출 집중도</span>'
        f'<span class="wist-v">상품 <b>{p["top_n_80"]}개</b>({p["top_n_80_pct"]:.0f}%)가 매출의 80%를 차지</span></div>'
        f'<div class="wist-row"><span class="wist-k">상위 20% 상품 매출 비중</span>'
        f'<span class="wist-v">{p["top20_n"]}개 · {p["top20_share"]:.0f}%</span></div>'
        f'<div class="wist-row"><span class="wist-k">전체</span>'
        f'<span class="wist-v mut">최근 {p["window_days"]}일 · SKU {p["total_skus"]}개 · 매출 {won(p["total_amt"])}원</span></div>'
        '</div>'
    )
    trs = []
    for i, r in enumerate(p["rows"], 1):
        trs.append(
            '<tr>'
            f'<td class="n mut">{i}</td>'
            f'<td class="lbl">{r["name"]}<span class="code" style="margin-left:6px">{r["code"]}</span></td>'
            f'<td class="lbl mut">{r["cat"]}</td>'
            f'<td class="n">{won(r["amt"])}</td>'
            f'<td class="n mut">{r["pct"]:.1f}%</td>'
            f'<td class="n">{r["cum_pct"]:.1f}%</td>'
            '</tr>'
        )
    table = (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="n">#</th><th class="lbl">상품</th><th class="lbl">카테고리</th>'
        '<th class="n">매출</th><th class="n">비중</th><th class="n">누적비중</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )
    return head + table


def render_newproducts(items):
    """신상품 성과 스포트라이트 — 출시(added_at) 후 일정 기간 이내 상품의 누적 판매·일평균 매출.
    매출 0인 상품을 별도로 모아 노출/기획전 점검이 필요한 상품을 바로 알아볼 수 있게 한다."""
    if not items:
        return '<p class="empty">최근 출시된 신상품이 없습니다.</p>'
    perf = [it for it in items if it["amt"] > 0][:10]
    zero = sorted([it for it in items if it["amt"] == 0], key=lambda x: -x["days_live"])
    head = ('<tr><th class="lbl">상품</th><th class="lbl">카테고리</th><th class="n">출시일</th>'
            '<th class="n">누적주문</th><th class="n">누적매출</th><th class="n">일평균매출</th></tr>')

    def rows_html(lst):
        trs = []
        for it in lst:
            trs.append(
                '<tr>'
                f'<td class="lbl">{it["name"]}<span class="code" style="margin-left:6px">{it["code"]}</span></td>'
                f'<td class="lbl mut">{it["cat"]}</td>'
                f'<td class="n mut">{it["added_at"]} (D+{it["days_live"]})</td>'
                f'<td class="n">{it["cnt"]}건</td>'
                f'<td class="n">{won(it["amt"])}원</td>'
                f'<td class="n mut">{won(it["avg_daily_amt"])}원/일</td>'
                '</tr>'
            )
        return "".join(trs)

    out = ""
    if perf:
        out += (f'<div class="trend-h">🏆 성과 TOP{len(perf)}</div>'
                f'<div class="tblwrap"><table class="mom"><thead>{head}</thead><tbody>{rows_html(perf)}</tbody></table></div>')
    else:
        out += '<p class="empty">아직 판매된 신상품이 없습니다.</p>'
    if zero:
        out += (f'<div class="trend-h" style="margin-top:14px">⚠️ 매출 0 · 출시 후 경과일 많은 순 ({len(zero)}개) — 노출·기획전 점검 필요</div>'
                f'<div class="tblwrap"><table class="mom"><thead>{head}</thead><tbody>{rows_html(zero[:15])}</tbody></table></div>')
    note = f'<div class="wnote">출시(added_at) 후 {analytics.NEW_PRODUCT_WINDOW_DAYS}일 이내 상품만 · 홈페이지 자동동기화(products.json) 기준</div>'
    return out + note


def render_pairs(pairs):
    """청첩장 × 문구류 동반구매 페어링 TOP N (최근 90일)."""
    if not pairs:
        return ('<p class="empty">최근 90일 내 청첩장과 함께 팔린 문구류 조합이 없습니다 '
                '(문구류로 매칭된 상품이 적거나 동반구매 자체가 없을 수 있습니다).</p>')
    trs = []
    for p in pairs:
        trs.append(
            '<tr>'
            f'<td class="lbl">{p["invite_name"]}<span class="code" style="margin-left:6px">{p["invite_code"]}</span></td>'
            f'<td class="lbl">{p["item_name"]}<span class="code" style="margin-left:6px">{p["item_code"]}</span></td>'
            f'<td class="n">{p["cnt"]}건</td>'
            '</tr>'
        )
    return (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">청첩장</th><th class="lbl">문구류 상품</th><th class="n">동반주문건수</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )


def render_pairs_all(pairs):
    """청첩장 × 전체 기념굿즈 동반구매 페어링 TOP N (최근 90일, 카테고리 무관 — ERP코드 조합·건수/수량/금액)."""
    if not pairs:
        return '<p class="empty">최근 90일 내 청첩장과 함께 팔린 기념굿즈 조합이 없습니다.</p>'
    trs = []
    for i, p in enumerate(pairs, 1):
        trs.append(
            '<tr>'
            f'<td class="n mut">{i}</td>'
            f'<td class="lbl">{p["invite_name"]}<span class="code" style="margin-left:6px">{p["invite_code"]}</span></td>'
            f'<td class="lbl">{p["item_name"]}<span class="code" style="margin-left:6px">{p["item_code"]}</span></td>'
            f'<td class="lbl mut">{p.get("item_cat","")}</td>'
            f'<td class="n">{p["cnt"]}건</td>'
            f'<td class="n mut">{p["qty"]}</td>'
            f'<td class="n">{won(p["amt"])}</td>'
            '</tr>'
        )
    return (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="n">#</th><th class="lbl">청첩장</th><th class="lbl">기념굿즈 상품</th><th class="lbl">카테고리</th>'
        '<th class="n">동반주문건수</th><th class="n">수량</th><th class="n">금액</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )


def render_daily_channel(rows):
    """데일리 표 기본뷰(최근 21일) 카테고리별 채널(카드/몰) 매출 참고 표 — 날짜 피커에 반응하지 않는 정적 요약."""
    if not rows:
        return '<p class="empty">데이터 없음</p>'
    trs = []
    for r in rows:
        trs.append(
            '<tr>'
            f'<td class="lbl">{r["icon"]} {r["name"]}</td>'
            f'<td class="n">{won(r["card"])}</td>'
            f'<td class="n">{won(r["mall"])}</td>'
            '</tr>'
        )
    return (
        '<div class="tblwrap"><table class="mom"><thead><tr>'
        '<th class="lbl">카테고리</th><th class="n">바른손카드</th><th class="n">바른손몰</th>'
        '</tr></thead><tbody>' + "".join(trs) + '</tbody></table></div>'
    )


def render_wist(k):
    """청첩장 동반 / 단독 주문 전사 요약 (최근 7일) + 동반율 추세."""
    total = k["r7_cnt"] or 0
    wi_cnt, st_cnt = k["r7_wi_cnt"], k["r7_st_cnt"]
    wi_pct = (wi_cnt / total * 100.0) if total else 0.0
    st_pct = (st_cnt / total * 100.0) if total else 0.0
    badge = _pp_badge(k["attach_all"] - k["attach_prev"])
    return (
        '<div class="wistbox">'
        f'<div class="wist-row"><span class="wist-k">🎀 청첩장 동반</span>'
        f'<span class="wist-v">{wi_cnt}건 <span class="mut">({wi_pct:.0f}%)</span> · {won(k["r7_wi_amt"])}원</span></div>'
        f'<div class="wist-row"><span class="wist-k">📦 단독 주문</span>'
        f'<span class="wist-v">{st_cnt}건 <span class="mut">({st_pct:.0f}%)</span> · {won(k["r7_st_amt"])}원</span></div>'
        f'<div class="wist-row"><span class="wist-k">동반율 추세</span>'
        f'<span class="wist-v">{k["attach_all"]:.0f}% {badge} <span class="mut">(직전 7일 {k["attach_prev"]:.0f}%)</span></span></div>'
        '</div>'
    )


def render_leadtime(lt):
    """주문일 → 배송일 평균 리드타임 (동반/단독), 직전 동일기간 대비 추세."""
    def row(label, cur, prev):
        if cur is None:
            return (f'<div class="wist-row"><span class="wist-k">{label}</span>'
                    f'<span class="wist-v mut">데이터 없음</span></div>')
        diff_pct = ((cur - prev) / prev * 100.0) if prev else None
        badge = delta_badge(diff_pct, good_high=False) if diff_pct is not None else '<span class="badge nu">–</span>'
        prev_txt = f'{prev:.1f}일' if prev is not None else '–'
        return (f'<div class="wist-row"><span class="wist-k">{label}</span>'
                f'<span class="wist-v">{cur:.1f}일 {badge} <span class="mut">(직전 {prev_txt})</span></span></div>')
    return (
        '<div class="wistbox">'
        + row("🎀 동반주문 리드타임", lt.get("wi_cur"), lt.get("wi_prev"))
        + row("📦 단독주문 리드타임", lt.get("st_cur"), lt.get("st_prev"))
        + '<div class="wist-row"><span class="wist-v mut" style="font-size:11px">주문일→배송완료일 평균(영업일 아님) · '
          '배송이 확정됐을 시점(15~45일 전 주문)만 집계해 미배송 편향 방지</span></div>'
        + '</div>'
    )


def render_events(events):
    """향후 90일 이내 명절/기념일/결혼 성수기 시작 등 캘린더 이벤트 + 주문 마감 권장일."""
    if not events:
        return '<p class="empty">향후 90일 이내 예정된 캘린더 이벤트가 없습니다.</p>'
    cards = []
    for e in events:
        level = "critical" if e["d_day"] <= 14 else ("warning" if e["d_day"] <= 30 else "info")
        deadline_html = (f'<div class="rec-cta">📮 주문 마감 권장 {e["deadline"]}까지</div>'
                          if e.get("deadline") else '')
        cards.append(
            f'<div class="rec {level}">'
            f'<div class="rec-top"><span class="rec-ico">📅</span>'
            f'<span class="rec-tag {level}">D-{e["d_day"]}</span>'
            f'<span class="rec-metric {level}">{e["date"]}</span></div>'
            f'<div class="rec-title">{e["name"]}</div>'
            f'<div class="rec-body">{e.get("action","")}</div>'
            f'{deadline_html}'
            '</div>'
        )
    return '<div class="recgrid">' + "".join(cards) + '</div>'


def _trend_rows(items, sign):
    if not items:
        return '<tr><td colspan="5" class="empty">데이터 없음</td></tr>'
    trs = []
    for t in items:
        trs.append(
            '<tr>'
            f'<td class="lbl">{t["name"]}</td>'
            f'<td class="lbl mut">{t["cat"]}</td>'
            f'<td class="n">{t["r7"]}</td>'
            f'<td class="n mut">{t["p7"]}</td>'
            f'<td class="n">{sign}{t["delta"]}건</td>'
            '</tr>'
        )
    return "".join(trs)


def render_trend(rising, declining):
    """SKU 단위 급상승/급하락 TOP5 (최근7일 vs 직전7일)."""
    head = ('<tr><th class="lbl">상품</th><th class="lbl">카테고리</th>'
            '<th class="n">최근7일</th><th class="n">직전7일</th><th class="n">증감</th></tr>')
    up = f'<div class="tblwrap"><table class="mom"><thead>{head}</thead><tbody>{_trend_rows(rising, "+")}</tbody></table></div>'
    down = f'<div class="tblwrap"><table class="mom"><thead>{head}</thead><tbody>{_trend_rows(declining, "-")}</tbody></table></div>'
    return (
        '<div class="trendgrid">'
        f'<div><div class="trend-h">🔥 급상승 TOP5</div>{up}</div>'
        f'<div><div class="trend-h">📉 급하락 TOP5</div>{down}</div>'
        '</div>'
    )


def render_forecast(f):
    yoy_proj = delta_badge(f["yoy_proj"]) if f["yoy_proj"] is not None else '<span class="badge nu">작년 동월 실적 없음(신상품)</span>'
    yoy_pace = delta_badge(f["yoy_pace"]) if f["yoy_pace"] is not None else '<span class="badge nu">–</span>'
    conf = "낮음 (월초, 표본 적음)" if f["elapsed"] <= 8 else ("보통" if f["elapsed"] <= 18 else "높음")
    return (
        '<div class="fc">'
        f'<div class="fc-row"><span class="fc-k">이번달({f["month"]}, {f["season"]})</span>'
        f'<span class="fc-v">MTD 매출 <b>{won(f["mtd_amt"])}</b>원 · 주문 <b>{f["mtd_cnt"]}</b>건 '
        f'<span class="mut">({f["elapsed"]}/{f["dim"]}일 경과)</span></span></div>'
        f'<div class="fc-row big"><span class="fc-k">월말 예상 매출 <span class="mut">런레이트</span></span>'
        f'<span class="fc-v proj"><b>{won(f["proj_amt"])}</b>원</span></div>'
        f'<div class="fc-row"><span class="fc-k">작년 동월 대비(예상)</span><span class="fc-v">{yoy_proj} '
        f'<span class="mut">작년 {f["month"][:4]} 동월 {won(f["ly_full_amt"])}원</span></span></div>'
        f'<div class="fc-row"><span class="fc-k">같은 시점 페이스(MTD)</span><span class="fc-v">{yoy_pace}</span></div>'
        f'<div class="fc-note">예측 신뢰도: <b>{conf}</b> · 런레이트 = MTD ÷ 경과일 × 월일수. '
        f'초반일수록 변동 큼 — 경과일이 쌓일수록 정확해집니다.</div>'
        '</div>'
    )


def render_page(d):
    k = d["kpi"]
    today_delta = None
    if k["lw_cnt"]:
        today_delta = (k["today_cnt"] - k["lw_cnt"]) / k["lw_cnt"] * 100.0
    kpi_today = delta_badge(today_delta) if today_delta is not None else '<span class="badge nu">지난주 0</span>'
    kpi_mom = delta_badge(k["mom_all"])

    daily_json = json.dumps(d["daily"], ensure_ascii=False)

    return _PAGE.replace("__DAILY__", daily_json) \
        .replace("__WEEKLY_TABLE__", render_weekly(d["weekly"])) \
        .replace("__TODAY_ISO__", d["today"]) \
        .replace("__TODAY__", f'{d["today"]} ({d["weekday"]})') \
        .replace("__GEN__", datetime.now().strftime("%Y-%m-%d %H:%M")) \
        .replace("__K_TODAY__", str(k["today_cnt"])) \
        .replace("__K_TODAY_D__", kpi_today) \
        .replace("__K_R7__", str(k["r7_cnt"])) \
        .replace("__K_MOM__", kpi_mom) \
        .replace("__K_ATTACH__", f'{k["attach_all"]:.0f}%') \
        .replace("__K_MTD__", won(k["mtd_amt"])) \
        .replace("__K_PROJ__", won(k["proj_amt"])) \
        .replace("__RECS__", render_recs(d["recs"])) \
        .replace("__MOMENTUM__", render_momentum(d["cat_rows"])) \
        .replace("__ATTACH__", render_attach(d["cat_rows"])) \
        .replace("__STATIONERY__", render_stationery(d["stationery"])) \
        .replace("__BEST__", render_best(d["best_products"]) +
                 '<div class="trend-h" style="margin-top:14px">✉️ 문구류 한정</div>' +
                 render_best(d["best_products_stationery"], "문구류 매출 데이터가 없습니다.")) \
        .replace("__CANCEL__", render_cancel(d["cancel"])) \
        .replace("__PAIRS__", render_pairs(d["pairs"])) \
        .replace("__PAIRS_ALL__", render_pairs_all(d["pairs_all"])) \
        .replace("__DAILY_CHANNEL__", render_daily_channel(d["daily_channel"])) \
        .replace("__FORECAST__", render_forecast(d["forecast"])) \
        .replace("__EVENTS__", render_events(d["events"])) \
        .replace("__FUNNEL__", render_funnel(d["funnel"])) \
        .replace("__CROSSSELL__", render_crosssell(d["cross_sell"])) \
        .replace("__LEADTIME__", render_leadtime(d["leadtime"])) \
        .replace("__WIST__", render_wist(d["kpi"])) \
        .replace("__CHANNEL__", render_channel(d["channel"])) \
        .replace("__AOV__", render_aov(d["cat_rows"])) \
        .replace("__PARETO__", render_pareto(d["pareto"])) \
        .replace("__TREND__", render_trend(d["rising"], d["declining"])) \
        .replace("__NEWPRODUCTS__", render_newproducts(d["new_products"]))


@app.route("/")
def index():
    """캐시된 화면을 즉시 응답. 없거나 오래되면 백그라운드로 재생성(응답 지연 없음)."""
    now = time.time()
    force = request.args.get("refresh") == "1"
    with _lock:
        html = _cache["html"]
        age = now - _cache["ts"] if _cache["ts"] else None
        building = _cache["building"]
    stale = (age is None) or (age > CACHE_TTL) or force
    if stale and not building:
        threading.Thread(target=_build_html, daemon=True).start()
    if html is None:
        # 아직 최초 생성 전 — 대기 안내 페이지 (자동 새로고침)
        return Response(_WAIT_PAGE, mimetype="text/html; charset=utf-8")
    resp = Response(html, mimetype="text/html; charset=utf-8")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@app.route("/api/daily")
def api_daily():
    """데일리 표 데이터만 반환 (기간 지정, 경량). 모멘텀/예측 재계산 없음."""
    d_from = request.args.get("from")
    d_to = request.args.get("to")
    if not d_from or not d_to:
        return jsonify({"error": "from/to 필요 (YYYY-MM-DD)"}), 400
    try:
        data = analytics.compute_daily(d_from, d_to)
        return jsonify(data)
    except Exception:
        return jsonify({"error": traceback.format_exc()}), 500


@app.route("/api/weekly")
def api_weekly():
    """지정 기준일이 속한 주 + 직전 2주 주간 리포트 표(HTML 조각) 반환."""
    ds = request.args.get("date")
    if not ds:
        return Response("date 필요 (YYYY-MM-DD)", status=400, mimetype="text/plain; charset=utf-8")
    try:
        w = analytics.compute_weekly(ds)
        return Response(render_weekly(w), mimetype="text/html; charset=utf-8")
    except Exception:
        return Response(
            f"<div style='padding:20px;color:#b00'>주간 조회 실패<pre>{traceback.format_exc()}</pre></div>",
            status=500, mimetype="text/html; charset=utf-8")


@app.route("/promo")
def promo():
    """카테고리별 임의 생성 기획전 페이지 (모멘텀 급상승 추천 클릭 대상)."""
    cat = request.args.get("cat", "")
    with _lock:
        promos = _cache.get("promos")
        building = _cache["building"]
    if not promos:
        if not building:
            threading.Thread(target=_build_html, daemon=True).start()
        return Response(_WAIT_PAGE, mimetype="text/html; charset=utf-8")
    catn = unicodedata.normalize("NFC", cat)
    norm = {unicodedata.normalize("NFC", k): v for k, v in promos.items()}
    p = norm.get(catn)
    if not p:
        avail = ", ".join(sorted(promos.keys()))
        return Response(
            f"<div style='font-family:sans-serif;padding:40px'><h3>기획전 데이터 없음: {cat}</h3>"
            f"<p style='color:#888'>가능한 카테고리: {avail}</p><a href='./'>← 대시보드</a></div>",
            mimetype="text/html; charset=utf-8")
    return Response(render_promo(cat, p), mimetype="text/html; charset=utf-8")


@app.route("/health")
def health():
    return jsonify({"ok": True, "port": PORT, "now": datetime.now().isoformat(timespec="seconds"),
                    "cache_age": int(time.time() - _cache["ts"]) if _cache["ts"] else None})


_PAGE = r"""<!doctype html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>기념굿즈 선제대응 대시보드</title>
<style>
:root{
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --baseline:#c3c2b7; --border:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#1baf7a;                     /* 청첩장동반 / 단독 */
  --good:#0ca30c; --good-ink:#006300; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --today:#fff7d6;
}
@media (prefers-color-scheme: dark){
 :root{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
   --grid:#2c2c2a;--baseline:#383835;--border:rgba(255,255,255,.10);
   --s1:#3987e5;--s2:#199e70;--good:#0ca30c;--good-ink:#0ca30c;--today:#3a3410;}
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI","Malgun Gothic",sans-serif;font-size:13px;line-height:1.5}
.wrap{max-width:1280px;margin:0 auto;padding:18px 20px 70px}
h1{font-size:20px;margin:0 0 3px;display:flex;align-items:center;gap:9px}
.badge1{background:var(--s1);color:#fff;border-radius:6px;padding:2px 10px;font-size:12px;font-weight:600}
.sub{color:var(--muted);font-size:12px;margin-bottom:16px}
h2{font-size:14px;margin:26px 0 10px;display:flex;align-items:center;gap:7px;
  padding-bottom:6px;border-bottom:1px solid var(--grid)}
h2 .h-note{font-size:11px;color:var(--muted);font-weight:400}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;
  box-shadow:0 1px 2px rgba(0,0,0,.03)}

/* KPI */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 16px}
.kpi .k{font-size:11px;color:var(--muted);letter-spacing:.02em}
.kpi .v{font-size:26px;font-weight:700;margin:3px 0 2px}
.kpi .v .u{font-size:13px;font-weight:600;color:var(--ink2)}
.kpi .foot{font-size:11px;color:var(--ink2)}

/* badges */
.badge{display:inline-flex;align-items:center;gap:3px;font-size:11px;font-weight:700;
  padding:1px 7px;border-radius:20px;white-space:nowrap}
.badge.good{color:#fff;background:var(--good)} .badge.crit{color:#fff;background:var(--critical)}
.badge.nu{color:var(--ink2);background:var(--grid)}
.badge.warn{color:#fff;background:var(--warning)}

/* recommendations */
.recgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
.rec{background:var(--surface);border:1px solid var(--border);border-left-width:4px;border-radius:10px;padding:12px 14px}
.rec.good{border-left-color:var(--good)} .rec.critical{border-left-color:var(--critical)}
.rec.warning{border-left-color:var(--warning)} .rec.info{border-left-color:var(--s1)}
.rec-top{display:flex;align-items:center;gap:7px;margin-bottom:5px}
.rec-ico{font-size:16px}
.rec-tag{font-size:10px;font-weight:700;padding:1px 7px;border-radius:20px;text-transform:none;color:#fff}
.rec-tag.good{background:var(--good)} .rec-tag.critical{background:var(--critical)}
.rec-tag.warning{background:var(--serious)} .rec-tag.info{background:var(--s1)}
.rec-metric{margin-left:auto;font-weight:800;font-size:14px}
.rec-metric.good{color:var(--good-ink)} .rec-metric.critical{color:var(--critical)}
.rec-metric.warning{color:var(--serious)} .rec-metric.info{color:var(--s1)}
.rec-title{font-weight:700;font-size:13px;margin-bottom:3px}
.rec-body{font-size:12px;color:var(--ink2)}
a.rec{display:block;text-decoration:none;color:inherit}
.rec.clickable{cursor:pointer;transition:box-shadow .12s,transform .12s}
.rec.clickable:hover{box-shadow:0 4px 14px rgba(0,0,0,.12);transform:translateY(-1px)}
.rec-promo{margin-top:8px;font-size:12px;color:var(--ink)}
.rec-prod{margin-top:6px;font-size:11px;display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.rec-prod .pl{color:var(--muted);margin-right:2px}
.chip{background:var(--grid);border-radius:20px;padding:1px 8px;font-size:11px;color:var(--ink)}
.rec-cta{margin-top:9px;font-size:12px;font-weight:700;color:var(--s1)}
.rec.good .rec-cta{color:var(--good-ink)}

/* momentum table */
table{border-collapse:separate;border-spacing:0;width:100%;font-variant-numeric:tabular-nums}
.mom th,.mom td{padding:7px 10px;border-bottom:1px solid var(--grid);text-align:right;white-space:nowrap}
.mom th{font-size:11px;color:var(--ink2);font-weight:600;vertical-align:bottom}
.mom th .sub{font-size:9px;color:var(--muted);font-weight:400}
.mom th.lbl,.mom td.lbl{text-align:left}
.mom td.lbl{font-weight:600}
.mom td.mut{color:var(--muted)}
.mom td.sp{text-align:center}
.spark{vertical-align:middle}
.mom tbody tr:hover{background:rgba(42,120,214,.05)}
.mom td.act,.mom th.act{text-align:left;white-space:normal;font-size:12px;color:var(--ink2);max-width:260px}

/* forecast */
.fc-row{display:flex;justify-content:space-between;align-items:baseline;gap:16px;
  padding:7px 0;border-bottom:1px dashed var(--grid)}
.fc-row.big{border-bottom:none}
.fc-k{color:var(--ink2);font-size:12px}
.fc-v{font-size:13px;text-align:right}
.fc-row.big .fc-v.proj{font-size:28px;font-weight:800;color:var(--s1)}
.fc-row.big .fc-v.proj b{font-weight:800}
.mut{color:var(--muted);font-size:11px;font-weight:400}
.fc-note{margin-top:9px;font-size:11px;color:var(--muted);line-height:1.6}

/* daily table */
.dtoolbar{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:9px}
.tg{display:flex;align-items:center;gap:5px}.tg>span{font-size:11px;color:var(--muted)}
.btn{border:1px solid var(--border);background:var(--surface);border-radius:7px;padding:4px 11px;
  font-size:12px;cursor:pointer;color:var(--ink);font-weight:500}
.btn.on{background:var(--s1);color:#fff;border-color:var(--s1)}
.btn.on.wi{background:var(--s1);border-color:var(--s1)}
.btn.on.st{background:var(--s2);border-color:var(--s2)}
.chk{font-size:12px;color:var(--ink2);display:flex;align-items:center;gap:4px;cursor:pointer}
.drange{display:flex;gap:14px;flex-wrap:wrap;align-items:center;margin-bottom:9px}
.drange input[type=date]{border:1px solid var(--border);background:var(--surface);color:var(--ink);
  border-radius:7px;padding:4px 8px;font-size:12px;font-family:inherit}
.drange .tilde{color:var(--muted)}
.drange .presets{gap:5px}
.btn.apply{background:var(--s1);color:#fff;border-color:var(--s1);font-weight:600}
.btn.ps.on{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.rstat{font-size:11px;color:var(--muted)}
.rstat.load{color:var(--s1);font-weight:600}
.dbox{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:auto;max-height:70vh}
.wow{font-size:9px;font-weight:700;padding:0 4px;border-radius:10px;margin-left:3px;white-space:nowrap}
.wow.good{color:#fff;background:var(--good)} .wow.crit{color:#fff;background:var(--critical)}
#wtbl th.wkgrp{text-align:center;background:rgba(42,120,214,.06)}
#wtbl th small,#wtbl small{font-weight:400;color:var(--muted);font-size:9px}
#wtbl small.cur{color:var(--serious);font-weight:700}
#wtbl td.sum{min-width:78px}
.gt td.mcol,.gt th.mcol{text-align:left;color:var(--ink2);font-size:11px;white-space:nowrap}
.gt td.metric-2{font-weight:700;color:var(--ink)}      /* 매출 강조 */
.gt td.metric-0{color:var(--s1)}                       /* 주문수 */
.gt td.metric-1{color:var(--muted)}                    /* 수량 */
.gt tr.catrow>td{background:rgba(42,120,214,.04)}
.gt td.catlbl{vertical-align:top;position:sticky;left:0;z-index:5}
.gt td.skulbl{vertical-align:top}
.gt td.skulbl.disc{color:#aaa;text-decoration:line-through}
.gt tr.gstart>td{border-top:2px solid var(--grid)}
.note-inline{font-size:11px;color:var(--muted)}
.gt th,.gt td{padding:5px 8px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--grid);font-size:12px}
.gt thead th{position:sticky;top:0;background:var(--surface);z-index:10;font-size:11px;color:var(--ink2)}
.gt th.lbl,.gt td.lbl{text-align:left;position:sticky;left:0;background:var(--surface);z-index:5;min-width:230px}
.gt thead th.lbl{z-index:15}
.gt th.day .wd{font-size:9px;color:var(--muted)}
.gt th.sum,.gt td.sum{background:rgba(42,120,214,.06);font-weight:700;border-left:2px solid var(--grid)}
.gt th.today,.gt td.today{background:var(--today)}
.gt td.zero{color:#cfd3da}
.gt tr.cat>td{background:var(--catbg,#eef);font-weight:700;border-top:2px solid var(--grid)}
.gt tr.cat td.lbl{background:var(--catbg,#eef)}
.gt .fold{cursor:pointer;border:none;background:transparent;font-size:11px;margin-right:3px;color:#555}
.gt .scount{font-size:9px;color:var(--muted);font-weight:500;margin-left:5px}
.gt tr.sku td.lbl{padding-left:24px;font-weight:400}
.gt tr.sku.disc td.lbl{color:#aaa;text-decoration:line-through}
.gt tr.sku .code{color:var(--muted);font-size:9px;margin-left:5px}
.gt tr.grand>td{background:var(--ink);color:var(--surface);font-weight:700;position:sticky;bottom:0}
.gt tr.grand td.lbl{background:var(--ink);color:var(--surface)}
/* 주간 리포트(서버 렌더) — 스프레드시트 스타일, 라이트 고정 */
.wnote{font-size:11px;color:var(--muted);margin:2px 0 8px}
#wtbl.wk{background:#fff;color:#1f2430;font-variant-numeric:tabular-nums}
#wtbl.wk th,#wtbl.wk td{border:1px solid #d8dce3;padding:4px 7px;font-size:11px;text-align:right;white-space:nowrap}
#wtbl.wk thead th{position:static;background:#eef1f6;color:#3a4150;font-weight:600;text-align:center}
#wtbl.wk th.lbl,#wtbl.wk td.lbl{text-align:left}
#wtbl.wk th.wg{background:#e8eef8;border-bottom:2px solid #cfd8e8}
#wtbl.wk th.dailyg{background:#e9f5ef}
#wtbl.wk th.tot{background:#f0e9fb}
#wtbl.wk th small{font-weight:400;color:#8a8f99;font-size:9px}
#wtbl.wk th.day .wd{font-size:9px;color:#8a8f99;font-weight:400}
#wtbl.wk td{background:#fff;color:#2a2f3a}
#wtbl.wk td.zero{color:#c4c8d0}
#wtbl.wk td.weekend{background:#fafafa}
#wtbl.wk td.catcell{font-weight:700;vertical-align:middle;text-align:left;font-size:11px}
#wtbl.wk td.code{color:#5a6270;font-size:10px}
#wtbl.wk td.name{color:#2a2f3a}
#wtbl.wk td.disc{color:#aaa;text-decoration:line-through}
#wtbl.wk td.totc{background:#f7f3fd;font-weight:600}
#wtbl.wk tr.subr>td{background:#e9eff8;font-weight:700;color:#1f2430}
#wtbl.wk tr.subr td.totc{background:#e3e0f2}
#wtbl.wk tr.wowr>td{background:#f5f7fb;font-size:10px}
#wtbl.wk td.subL{text-align:right;color:#5a6270;font-weight:700}
#wtbl.wk .wnew{color:#2a78d6;font-weight:700}
#wtbl.wk .wup{color:#067a2e;font-weight:700}
#wtbl.wk .wdn{color:#c0271f;font-weight:700}
#wtbl.wk tr.grandr>td{background:#1f2430;color:#fff;font-weight:700}
#wtbl.wk tr.grandr td.totc{background:#2b3242}
#wtbl.wk tr.grandr.wowr>td{background:#363b47}
#wtbl.wk tr.grandr .wup{color:#7be495}
#wtbl.wk tr.grandr .wdn{color:#ff9b9b}
#wtbl.wk td.grandL{text-align:right}
#wtbl.wk .curwk{background:#ec835a;color:#fff;border-radius:8px;padding:0 6px;font-size:9px;font-weight:700}
#wtbl.wk th.wtoday{background:#fff3d6}
#wtbl.wk td.wtoday{background:#fffaf0;font-weight:700}
#wtbl.wk th.wowamt{background:#fff3b0;color:#5a4a00}
#wtbl.wk td.wowamt{background:#fffdf3}
/* 카테고리 합계/WoW 행 — 짙은 회색 */
#wtbl.wk tr.subr>td,#wtbl.wk tr.wowr:not(.grandr)>td{background:#dcdcdc;color:#3a3a3a}
#wtbl.wk tr.subr td.totc{background:#cfcfcf}
#wtbl.wk tr.subr td.wowamt{background:#e6dfb0}
#wtbl.wk tr.grandr td.wowamt{background:#4a4324}
/* 기준주(W(c)) 시작 지점 — 빨간 세로 구분선 */
#wtbl.wk th.dailyg,#wtbl.wk th.wkline,#wtbl.wk td.wkline{border-left:3px solid #d03b3b}
/* 금액 WoW 열 강조 — 배경/테두리만, 글자색은 wup/wdn 그대로 유지 */
#wtbl.wk th.wowamt,#wtbl.wk td.wowamt{border-left:3px solid #d03b3b;border-right:3px solid #000}
/* 카테고리 블록을 검은 굵은 박스로 감싸기 */
#wtbl.wk td.catcell{border-left:3px solid #000}
#wtbl.wk tr.subr>td:first-child,#wtbl.wk tr.wowr:not(.grandr)>td:first-child{border-left:3px solid #000}
#wtbl.wk tr.catstart>td{border-top:3px solid #000}
#wtbl.wk tr.wowr:not(.grandr)>td{border-bottom:3px solid #000}
/* 주차별 채널(바른손카드/바른손몰) 요약표 — #wtbl.wk 와 동일 톤, 별도 표라 id 스코프만 새로 추가 */
#wchantbl{background:#fff;color:#1f2430;font-variant-numeric:tabular-nums;margin-top:10px}
#wchantbl th,#wchantbl td{border:1px solid #d8dce3;padding:4px 7px;font-size:11px;text-align:right;white-space:nowrap}
#wchantbl thead th{position:static;background:#eef1f6;color:#3a4150;font-weight:600;text-align:center}
#wchantbl th.lbl,#wchantbl td.lbl{text-align:left}
#wchantbl th.wg{background:#e8eef8;border-bottom:2px solid #cfd8e8}
#wchantbl th small{font-weight:400;color:#8a8f99;font-size:9px}
#wchantbl td{background:#fff;color:#2a2f3a}
#wchantbl tr.grandr>td{background:#1f2430;color:#fff;font-weight:700}
#wchantbl td.grandL{text-align:right}
#wchantbl tr.grandr td.mut{color:#9aa0ac}
#wchantbl .curwk{background:#ec835a;color:#fff;border-radius:8px;padding:0 6px;font-size:9px;font-weight:700}
.btn.wps.on{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.foot{color:var(--muted);font-size:11px;margin-top:22px;line-height:1.7;border-top:1px solid var(--grid);padding-top:12px}

/* 보조 지표 */
.secgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.sec-block{padding:12px 14px;min-width:0}          /* 그리드 아이템 기본 min-width:auto가 표를 밀어내는 것 방지 */
.sec-block.sec-wide{grid-column:1/-1}               /* 표가 들어가는 블록은 한 행 전체 폭 사용 */
.sec-h2{font-weight:700;font-size:13px;margin-bottom:9px;display:flex;align-items:center;gap:6px}
.wistbox{display:flex;flex-direction:column;gap:8px}
.wist-row{display:flex;justify-content:space-between;align-items:baseline;gap:10px;font-size:12px}
.wist-k{color:var(--ink2);white-space:nowrap}
.wist-v{font-weight:600;text-align:right}
.tblwrap{overflow-x:auto}                            /* 표가 카드보다 넓어져도 카드 안에서만 스크롤 */
.trendgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px;min-width:0}
.trendgrid>div{min-width:0}
.trend-h{font-size:12px;font-weight:700;margin-bottom:4px;color:var(--ink2)}
@media(max-width:900px){.trendgrid{grid-template-columns:1fr}}

/* 탭 네비게이션 */
.tabnav{display:flex;gap:4px;flex-wrap:wrap;margin:18px 0 4px;border-bottom:2px solid var(--grid)}
.tabbtn{border:1px solid transparent;border-bottom:none;background:transparent;color:var(--ink2);
  font-size:13px;font-weight:600;padding:9px 14px;border-radius:8px 8px 0 0;cursor:pointer;margin-bottom:-2px}
.tabbtn:hover{background:var(--surface)}
.tabbtn.on{color:var(--s1);background:var(--surface);border-color:var(--grid);border-bottom:2px solid var(--s1)}
.tabpanel[hidden]{display:none}
@media(max-width:700px){.tabbtn{font-size:12px;padding:8px 10px}}
</style></head>
<body><div class="wrap">
  <h1><span class="badge1">기념굿즈 · 1depth</span> 선제대응 대시보드</h1>
  <div class="sub">기준일 <b>__TODAY__</b> · 생성 __GEN__ · 홈페이지 MdSeq=137 카테고리 기준 ·
    검증된 매출 쿼리 재사용(결제완료·취소제외·set환산·쿠폰반영) · 데이터는 10분 캐시</div>

  <div class="kpis">
    <div class="kpi"><div class="k">오늘 주문수</div><div class="v">__K_TODAY__<span class="u">건</span></div>
      <div class="foot">지난주 같은 요일 대비 __K_TODAY_D__</div></div>
    <div class="kpi"><div class="k">최근 7일 주문수</div><div class="v">__K_R7__<span class="u">건</span></div>
      <div class="foot">직전 7일 대비 __K_MOM__</div></div>
    <div class="kpi"><div class="k">이번달 매출(MTD) → 월말 예상</div>
      <div class="v" style="font-size:19px">__K_MTD__<span class="u">원</span></div>
      <div class="foot">월말 예상 <b style="color:var(--s1)">__K_PROJ__원</b> · 런레이트</div></div>
    <div class="kpi"><div class="k">청첩장 동반율 (최근 7일)</div><div class="v">__K_ATTACH__</div>
      <div class="foot">부가상품이 청첩장 주문에 함께 담긴 비율</div></div>
  </div>

  <nav class="tabnav">
    <button class="tabbtn" id="tabbtn-summary" data-tab="summary">🏠 요약</button>
    <button class="tabbtn" id="tabbtn-funnel" data-tab="funnel">🔻 퍼널 &amp; 청첩장 연계</button>
    <button class="tabbtn" id="tabbtn-products" data-tab="products">📈 카테고리 · 상품</button>
    <button class="tabbtn" id="tabbtn-weekly" data-tab="weekly">📅 주간 리포트</button>
    <button class="tabbtn" id="tabbtn-daily" data-tab="daily">📋 데일리 주문</button>
  </nav>

  <section class="tabpanel" id="tab-summary">
    <h2>🎯 선제 대응 &amp; 기획전 추천 <span class="h-note">— 룰 기반, 각 카드에 근거 수치 포함</span></h2>
    __RECS__

    <h2>🔮 이번달 매출 예측 <span class="h-note">— 런레이트 기반 월말 착지 + 작년 대비</span></h2>
    <div class="card" style="max-width:640px">__FORECAST__</div>

    <h2>📅 다가오는 캘린더 이벤트 <span class="h-note">— 명절·기념일·성수기 + 주문 마감 권장일 + 액션</span></h2>
    __EVENTS__
  </section>

  <section class="tabpanel" id="tab-funnel" hidden>
    <h2>🔻 결제 전환율(퍼널) <span class="h-note">— 주문생성(장바구니) → 결제완료 · 카테고리별 이탈 많은 순</span></h2>
    <div class="card sec-wide">__FUNNEL__</div>

    <h2>💌 청첩장 → 굿즈 Cross-sell 전환율 <span class="h-note">— 청첩장 전체 판매 대비, 카테고리별 업셀 비율</span></h2>
    <div class="card sec-wide">__CROSSSELL__</div>

    <h2>🎁 청첩장 동반율 &amp; 크로스셀 액션 <span class="h-note">— 카테고리별 동반/단독 비중 · 동반율 구간별 다음 액션</span></h2>
    <div class="card" style="padding:4px 6px">__ATTACH__</div>

    <h2>💌 청첩장 × 문구류 동반구매 페어링 <span class="h-note">— 최근 90일, 어떤 청첩장에 어떤 문구류가 잘 팔리는지 TOP15</span></h2>
    <div class="card sec-wide">__PAIRS__</div>

    <h2>🎁 청첩장 × 기념굿즈 전체 동반구매 페어링 <span class="h-note">— 최근 90일, 카테고리 무관 전체 ERP코드 조합 TOP30 · 동반주문건수순</span></h2>
    <div class="card sec-wide">__PAIRS_ALL__</div>

    <div class="secgrid" style="margin-top:26px">
      <div class="card sec-block"><div class="sec-h2">🚚 리드타임 <span class="h-note">— 주문 → 배송</span></div>__LEADTIME__</div>
      <div class="card sec-block"><div class="sec-h2">🎀 동반 / 단독 주문 <span class="h-note">— 최근 7일 전사 요약</span></div>__WIST__</div>
      <div class="card sec-block sec-wide"><div class="sec-h2">💳 채널별 매출 <span class="h-note">— 바른손카드 / 바른손몰</span></div>__CHANNEL__</div>
    </div>
  </section>

  <section class="tabpanel" id="tab-products" hidden>
    <h2>📈 카테고리 모멘텀 <span class="h-note">— 최근 7일을 평소(직전 28일 주간평균)와 비교 · 뜨는/식는 카테고리 조기 포착</span></h2>
    <div class="card" style="padding:4px 6px">__MOMENTUM__</div>

    <h2>💰 평균 객단가(AOV) <span class="h-note">— 카테고리별, 최근7일 vs 직전7일</span></h2>
    <div class="card sec-wide">__AOV__</div>

    <h2>📊 매출 집중도 <span class="h-note">— ABC/파레토, 최근 28일 SKU 기준</span></h2>
    <div class="card sec-wide">__PARETO__</div>

    <h2>🏆 베스트 품목 TOP10 <span class="h-note">— 최근 7일 매출순, 전체 / 문구류</span></h2>
    <div class="card sec-wide">__BEST__</div>

    <h2>📈 상품 판매 추이 <span class="h-note">— SKU 단위 급상승/급하락</span></h2>
    <div class="card sec-wide">__TREND__</div>

    <h2>✉️ 문구류 스포트라이트 <span class="h-note">— 메시지 카드 · 엽서/캘린더</span></h2>
    <div class="card">__STATIONERY__</div>

    <h2>🆕 신상품 성과 스포트라이트 <span class="h-note">— 출시 후 45일 이내 상품의 누적 판매</span></h2>
    <div class="card sec-wide">__NEWPRODUCTS__</div>

    <h2>🚫 취소 현황 <span class="h-note">— 최근 28일, 결제 후 취소된 주문 비율</span></h2>
    <div class="card sec-wide">__CANCEL__</div>
  </section>

  <section class="tabpanel" id="tab-weekly" hidden>
    <h2>📅 주간 리포트 (WoW) <span class="h-note">— 카테고리·상품코드·상품명 / 주차 합산(수량·주문·금액) + 기준주 일별(금액) + 총 누적 + 금액 WoW · 3주간 판매 상품만</span></h2>
    <div class="drange">
      <div class="tg"><span>기준 주</span>
        <input type="date" id="wdate"> <button class="btn apply" id="wapply">조회</button></div>
      <div class="tg presets">
        <button class="btn wps" data-p="this">이번주</button>
        <button class="btn wps" data-p="last">지난주</button>
        <button class="btn wps" data-p="prev2">2주 전</button>
        <button class="btn wps" data-p="prev3">3주 전</button>
      </div>
      <div class="tg"><button class="btn" id="wcopy" type="button">📋 표 복사</button></div>
      <span class="rstat" id="wkstat"></span>
    </div>
    <div id="wkwrap">__WEEKLY_TABLE__</div>
  </section>

  <section class="tabpanel" id="tab-daily" hidden>
    <h2>📋 데일리 주문 현황 <span class="h-note">— 카테고리 × 일자 · 청첩장동반/단독 · 지표 전환 · 기간 선택</span></h2>
    <div class="sec-h2" style="margin-bottom:6px">💳 카테고리별 채널 매출 <span class="h-note">— 최근 21일(기본뷰) 참고용, 아래 기간 선택에 연동되지 않음</span></div>
    <div class="card sec-wide" style="margin-bottom:14px">__DAILY_CHANNEL__</div>
    <div class="drange">
      <div class="tg"><span>기간</span>
        <input type="date" id="df"> <span class="tilde">~</span> <input type="date" id="dt">
        <button class="btn apply" id="apply">조회</button></div>
      <div class="tg presets">
        <button class="btn ps" data-p="7">최근 7일</button>
        <button class="btn ps" data-p="21">최근 21일</button>
        <button class="btn ps" data-p="month">이번달</button>
        <button class="btn ps" data-p="lastmonth">지난달</button>
        <button class="btn ps" data-p="ytd">올해 전체</button>
      </div>
      <span class="rstat" id="rstat"></span>
    </div>
    <div class="dtoolbar">
      <div class="tg"><span>지표</span><span class="note-inline">매출·주문수·수량 동시 표시(항목당 3줄)</span></div>
      <div class="tg"><span>청첩장여부</span>
        <button class="btn src on" data-s="0">전체</button>
        <button class="btn src" data-s="3">청첩장동반</button>
        <button class="btn src" data-s="6">단독</button></div>
      <label class="chk"><input type="checkbox" id="hz"> 매출 0 카테고리 숨기기</label>
      <label class="chk"><input type="checkbox" id="ss" checked> 상품(SKU) 펼치기</label>
    </div>
    <div class="dbox"><table id="dtbl" class="gt"><thead id="dh"></thead><tbody id="db"></tbody></table></div>
  </section>

  <div class="foot">
    · <b>청첩장동반</b> = 청첩장 주문에 부가상품이 함께 담김 / <b>단독</b> = 부가상품만 주문 ·
      동반율↑ = 크로스셀 잘됨, 동반율↓ + 단독 볼륨 = 번들 노출 기회<br>
    · 매출: 결제완료(settle_date)·미취소만 집계, pearl/커스텀스티커 set 환산·쿠폰 비례배분 반영(검증된 쿼리 재사용) ·
      기존 시스템은 읽기 전용 참조, 이 앱은 독립 실행(포트 10050)<br>
    · <b>다음 단계</b>: 3depth(세부 카테고리) 분해 · WoW/MoM/YoY 정식 비교 · 주문자(주문 상세) 드릴다운 · MoM 기반 예측 정교화
  </div>
</div>
<script>
// ---- 탭 네비게이션 (URL 해시로 딥링크 지원) ----
const TABS=['summary','funnel','products','weekly','daily'];
function showTab(id){
  if(!TABS.includes(id))id=TABS[0];
  TABS.forEach(t=>{
    document.getElementById('tab-'+t).hidden = (t!==id);
    document.getElementById('tabbtn-'+t).classList.toggle('on', t===id);
  });
  if(location.hash.slice(1)!==id)history.replaceState(null,'','#'+id);
}
document.querySelectorAll('.tabbtn').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
window.addEventListener('hashchange',()=>showTab(location.hash.slice(1)));
showTab((location.hash||'#summary').slice(1));

let D = __DAILY__;
let dsrc=0; const folded=new Set();
const DMETRICS=[['매출',2],['주문수',0],['수량',1]];   // [라벨, vec 인덱스]
const fmtv=v=>v?v.toLocaleString():'';
function head(){
  const t=['<tr>','<th class="lbl">카테고리 / 상품</th>','<th class="mcol">지표</th>'];
  D.dates.forEach((d,i)=>{const md=d.slice(5).replace('-','/');
    let c='day';if(D.is_weekend[i])c+=' weekend';if(d===D.today)c+=' today';
    t.push(`<th class="${c}"><div class="wd">${D.weekdays[i]}</div>${md}</th>`);});
  t.push('<th class="sum">합계</th></tr>');
  document.getElementById('dh').innerHTML=t.join('');
}
function catTot(cat){const nD=D.dates.length;
  const days=Array.from({length:nD},()=>[0,0,0,0,0,0,0,0,0]);const tot=[0,0,0,0,0,0,0,0,0];
  cat.skus.forEach(s=>{s.days.forEach((v,i)=>{for(let k=0;k<9;k++)days[i][k]+=v[k];});
    for(let k=0;k<9;k++)tot[k]+=s.total[k];});return{days,tot};}
function dMetricRows(days,tot,labelCell,rowClass){
  let out='';
  DMETRICS.forEach(([mlabel,mi],ri)=>{
    let tds = (ri===0 ? labelCell : '') + `<td class="mcol metric-${mi}">${mlabel}</td>`;
    days.forEach((v,i)=>{const val=v[dsrc+mi];let c=val>0?'':'zero';if(D.dates[i]===D.today)c+=' today';
      tds+=`<td class="${c}">${fmtv(val)}</td>`;});
    tds+=`<td class="sum">${fmtv(tot[dsrc+mi])}</td>`;
    out+=`<tr class="${rowClass}${ri===0?' gstart':''}${ri===2?' mend':''}">${tds}</tr>`;
  });
  return out;
}
function render(){
  const hz=document.getElementById('hz').checked, ss=document.getElementById('ss').checked;
  const rows=[];const nD=D.dates.length;
  const gDays=Array.from({length:nD},()=>[0,0,0,0,0,0,0,0,0]);const gTot=[0,0,0,0,0,0,0,0,0];
  D.cats.forEach(cat=>{if(hz&&!cat.has)return;const{days,tot}=catTot(cat);
    for(let i=0;i<nD;i++)for(let k=0;k<9;k++)gDays[i][k]+=days[i][k];
    for(let k=0;k<9;k++)gTot[k]+=tot[k];
    const fo=folded.has(cat.name);
    const label=`<td class="lbl catlbl" rowspan="3" style="background:${cat.bg};color:${cat.color}">`+
      `<button class="fold" onclick="tc('${cat.name}')">${fo?'▶':'▼'}</button>${cat.icon} ${cat.name}`+
      `<span class="scount">${cat.skus.length} SKU</span></td>`;
    rows.push(dMetricRows(days,tot,label,'catrow'));
    if(ss&&!fo)cat.skus.forEach(s=>{if(hz&&s.total[0]===0)return;
      const lb=`<td class="lbl skulbl${s.disc?' disc':''}" rowspan="3">${s.name}<span class="code">${s.code}</span></td>`;
      rows.push(dMetricRows(s.days,s.total,lb,'sku'));});
  });
  rows.push(dMetricRows(gDays,gTot,`<td class="lbl" rowspan="3">💰 전체 합계</td>`,'grand'));
  document.getElementById('db').innerHTML=rows.join('');
}
function tc(n){folded.has(n)?folded.delete(n):folded.add(n);render();}
document.querySelectorAll('.btn.src').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('.btn.src').forEach(x=>x.classList.remove('on','wi','st'));
  b.classList.add('on');if(b.dataset.s==='3')b.classList.add('wi');if(b.dataset.s==='6')b.classList.add('st');
  dsrc=+b.dataset.s;render();});
document.getElementById('hz').onchange=render;document.getElementById('ss').onchange=render;

// ---- 기간 선택 ----
function ymd(dt){return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0');}
function presetRange(p){
  const t=new Date(D.today+'T00:00:00');let from,to=t;
  if(p==='7'){from=new Date(t);from.setDate(t.getDate()-6);}
  else if(p==='21'){from=new Date(t);from.setDate(t.getDate()-20);}
  else if(p==='month'){from=new Date(t.getFullYear(),t.getMonth(),1);}
  else if(p==='lastmonth'){from=new Date(t.getFullYear(),t.getMonth()-1,1);to=new Date(t.getFullYear(),t.getMonth(),0);}
  else if(p==='ytd'){from=new Date(t.getFullYear(),0,1);}
  return [ymd(from),ymd(to)];
}
async function loadRange(from,to,psEl){
  const rs=document.getElementById('rstat');
  rs.textContent='⏳ 조회 중… (기간이 길면 수십 초 걸립니다)';rs.classList.add('load');
  try{
    const r=await fetch(`api/daily?from=${from}&to=${to}`);
    const j=await r.json();
    if(j.error){rs.textContent='오류: '+String(j.error).slice(0,120);rs.classList.remove('load');return;}
    D=j;
    document.getElementById('df').value=D.date_from;
    document.getElementById('dt').value=D.date_to;
    head();render();
    rs.textContent=`✔ ${D.date_from} ~ ${D.date_to} · ${D.dates.length}일`;rs.classList.remove('load');
    document.querySelectorAll('.btn.ps').forEach(b=>b.classList.remove('on'));
    if(psEl)psEl.classList.add('on');
  }catch(e){rs.textContent='조회 실패: '+e;rs.classList.remove('load');}
}
document.querySelectorAll('.btn.ps').forEach(b=>b.onclick=()=>{const[f,t]=presetRange(b.dataset.p);loadRange(f,t,b);});
document.getElementById('apply').onclick=()=>{const f=document.getElementById('df').value,t=document.getElementById('dt').value;
  if(f&&t)loadRange(f,t,null);else document.getElementById('rstat').textContent='시작/종료 날짜를 모두 선택하세요';};
document.getElementById('df').value=D.date_from;
document.getElementById('dt').value=D.date_to;
document.getElementById('rstat').textContent=`${D.date_from} ~ ${D.date_to} · ${D.dates.length}일`;
const _p21=document.querySelector('.btn.ps[data-p="21"]');if(_p21)_p21.classList.add('on');

head();render();

// ---- 주간 리포트 기준 주 선택 ----
const WK_TODAY="__TODAY_ISO__";
function wkYmd(dt){return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0');}
async function wkLoad(dstr,el){
  const st=document.getElementById('wkstat');st.textContent='⏳ 조회 중… (수십 초 걸릴 수 있음)';st.classList.add('load');
  try{
    const r=await fetch('api/weekly?date='+dstr);
    const html=await r.text();
    document.getElementById('wkwrap').innerHTML=html;
    document.getElementById('wdate').value=dstr;
    st.textContent='';st.classList.remove('load');
    document.querySelectorAll('.btn.wps').forEach(b=>b.classList.remove('on'));
    if(el)el.classList.add('on');
  }catch(e){st.textContent='조회 실패: '+e;st.classList.remove('load');}
}
function wkPreset(p){const t=new Date(WK_TODAY+'T00:00:00');
  if(p==='last')t.setDate(t.getDate()-7);
  else if(p==='prev2')t.setDate(t.getDate()-14);
  else if(p==='prev3')t.setDate(t.getDate()-21);
  return wkYmd(t);}
document.querySelectorAll('.btn.wps').forEach(b=>b.onclick=()=>wkLoad(wkPreset(b.dataset.p),b));
document.getElementById('wapply').onclick=()=>{const v=document.getElementById('wdate').value;
  if(v)wkLoad(v,null);else document.getElementById('wkstat').textContent='기준 날짜를 선택하세요';};

// ---- 주간 리포트 표 복사 (엑셀/시트 붙여넣기용, 병합셀 유지 + 화면 서식 그대로) ----
// #wchantbl(주차별 채널 요약표)이 있으면 메인 표(#wtbl)와 함께 이어 붙여 복사한다.
function _tblPlain(t){return [...t.rows].map(r=>[...r.cells].map(c=>c.textContent.trim()).join('\t')).join('\n');}
function _tblStyledHtml(t){
  // 클래스 기반 CSS는 엑셀/시트 붙여넣기 시 무시되는 경우가 많아, 셀별 계산된 스타일을 그대로 인라인으로 굽는다.
  const clone=t.cloneNode(true);
  const origCells=[...t.querySelectorAll('th,td')];
  const cloneCells=[...clone.querySelectorAll('th,td')];
  const props=['background-color','color','font-weight','border-top','border-right','border-bottom','border-left','text-align','padding','white-space'];
  origCells.forEach((el,i)=>{
    const cs=getComputedStyle(el);
    cloneCells[i].setAttribute('style', props.map(p=>p+':'+cs.getPropertyValue(p)).join(';'));
  });
  return '<table style="border-collapse:collapse">'+clone.innerHTML+'</table>';
}
async function copyWeeklyTable(btn){
  const tbl=document.getElementById('wtbl');
  if(!tbl){alert('표를 찾을 수 없습니다');return;}
  const tbl2=document.getElementById('wchantbl');
  const plain=_tblPlain(tbl) + (tbl2 ? '\n\n'+_tblPlain(tbl2) : '');
  const htmlStr=_tblStyledHtml(tbl) + (tbl2 ? '<br>'+_tblStyledHtml(tbl2) : '');
  const old=btn.textContent;
  try{
    if(navigator.clipboard && window.ClipboardItem){
      await navigator.clipboard.write([new ClipboardItem({
        'text/html': new Blob([htmlStr], {type:'text/html'}),
        'text/plain': new Blob([plain], {type:'text/plain'})
      })]);
    }else{
      await navigator.clipboard.writeText(plain);
    }
    btn.textContent='✅ 복사됨';
  }catch(e){
    try{await navigator.clipboard.writeText(plain);btn.textContent='✅ 복사됨(텍스트만)';}
    catch(e2){alert('복사 실패: '+e2);return;}
  }
  setTimeout(()=>{btn.textContent=old;},1500);
}
document.getElementById('wcopy').onclick=()=>copyWeeklyTable(document.getElementById('wcopy'));
(function(){const wd=document.getElementById('wdate');if(wd){wd.value=wkPreset('last');wd.max=WK_TODAY;}
  const t=document.querySelector('.btn.wps[data-p="last"]');if(t)t.classList.add('on');})();
</script>
</body></html>
"""

if __name__ == "__main__":
    print("="*54)
    print(f"  기념굿즈 선제대응 대시보드  (port {PORT})")
    print(f"  홈:   http://127.0.0.1:{PORT}/")
    print(f"  상태: http://127.0.0.1:{PORT}/health")
    print(f"  종료: Ctrl+C")
    print("="*54)
    # 시작 시 캐시 미리 생성 (백그라운드) — 첫 요청부터 즉시 응답되도록
    threading.Thread(target=_build_html, daemon=True, name="warm").start()

    if os.environ.get("SKU_OPEN_BROWSER", "1") == "1":
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)
