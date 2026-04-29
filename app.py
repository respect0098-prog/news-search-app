"""
뉴스 키워드 검색 & AI 요약 앱
================================
키워드를 입력하면 최신 뉴스 5개를 검색하고,
Google Gemini API로 각 기사를 요약해 줍니다.
결과를 CSV로 다운로드할 수도 있습니다.
"""

import os
import csv
import io
import time
import streamlit as st

# ──────────────────────────────────────────────
# 1. 환경변수 확인
# ──────────────────────────────────────────────
# Codespaces Secrets에서 자동 주입된 GEMINI_API_KEY를 사용합니다.
# 로컬 실행 시에는 사이드바에서 직접 입력할 수도 있습니다.

# ──────────────────────────────────────────────
# 2. 페이지 기본 설정
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="뉴스 검색 & AI 요약",
    page_icon="📰",
    layout="wide",
)

st.title("📰 뉴스 키워드 검색 & AI 요약")
st.caption("키워드를 입력하면 최신 뉴스 5개를 가져와 Gemini로 요약합니다.")


# ──────────────────────────────────────────────
# 3. Gemini API 초기화
# ──────────────────────────────────────────────
def init_gemini():
    """Gemini API 클라이언트를 초기화합니다."""
    api_key = os.getenv("GEMINI_API_KEY")

    # API key가 없으면 사이드바에서 입력받기
    if not api_key:
        api_key = st.sidebar.text_input(
            "🔑 Gemini API Key",
            type="password",
            help="AI Studio(https://aistudio.google.com/)에서 발급받은 API key를 입력하세요.",
        )

    if not api_key:
        return None

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        # gemini-2.0-flash 모델 사용 (빠르고 저렴)
        model = genai.GenerativeModel("gemini-2.0-flash")
        return model
    except Exception as e:
        st.error(f"❌ Gemini API 초기화 실패: {e}")
        return None


# ──────────────────────────────────────────────
# 4. 뉴스 검색 함수
# ──────────────────────────────────────────────
def search_news(keyword, num_results=5):
    """
    GoogleNews 라이브러리를 사용하여 뉴스를 검색합니다.

    Args:
        keyword: 검색할 키워드
        num_results: 가져올 기사 수 (기본값 5)

    Returns:
        기사 정보 딕셔너리 리스트 [{"title": ..., "url": ..., "desc": ...}, ...]
    """
    from GoogleNews import GoogleNews

    # GoogleNews 객체 생성 — 최근 7일, 한국어
    gn = GoogleNews(lang="ko", region="KR", period="7d")
    gn.clear()  # 이전 검색 결과 초기화
    gn.search(keyword)

    raw_results = gn.results()

    if not raw_results:
        return []

    articles = []
    for item in raw_results[:num_results]:
        title = item.get("title", "제목 없음")
        link = item.get("link", "")
        desc = item.get("desc", "")

        # GoogleNews가 가끔 상대 URL을 반환하므로 보정
        if link and not link.startswith("http"):
            link = "https://" + link

        articles.append({
            "title": title,
            "url": link,
            "desc": desc,  # 기본 설명 (요약 전)
        })

    return articles


# ──────────────────────────────────────────────
# 5. 기사 본문 가져오기 (선택적)
# ──────────────────────────────────────────────
def fetch_article_text(url, max_chars=3000):
    """
    newspaper3k를 사용하여 기사 본문을 추출합니다.
    실패하면 빈 문자열을 반환합니다.

    Args:
        url: 기사 URL
        max_chars: 최대 문자 수 (Gemini 입력 제한 고려)

    Returns:
        기사 본문 텍스트 (최대 max_chars 글자)
    """
    try:
        from newspaper import Article

        article = Article(url, language="ko")
        article.download()
        article.parse()
        text = article.text.strip()
        return text[:max_chars] if text else ""
    except Exception:
        # 본문 추출 실패 시 빈 문자열 반환 (에러 무시)
        return ""


# ──────────────────────────────────────────────
# 6. Gemini 요약 함수
# ──────────────────────────────────────────────
def summarize_with_gemini(model, title, text):
    """
    Gemini API를 사용하여 기사를 3~4문장으로 요약합니다.

    Args:
        model: Gemini 모델 객체
        title: 기사 제목
        text: 기사 본문 또는 설명

    Returns:
        요약 문자열
    """
    if not text:
        return "⚠️ 기사 본문을 가져올 수 없어 요약할 수 없습니다."

    prompt = f"""다음 뉴스 기사를 한국어로 3~4문장으로 요약해 주세요.
핵심 내용을 간결하고 객관적으로 전달해 주세요.

[기사 제목]
{title}

[기사 내용]
{text}

[요약]"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"⚠️ 요약 생성 실패: {e}"


# ──────────────────────────────────────────────
# 7. CSV 변환 함수
# ──────────────────────────────────────────────
def results_to_csv(results):
    """
    검색 결과를 CSV 형식 문자열로 변환합니다.

    Args:
        results: [{"title": ..., "url": ..., "summary": ...}, ...]

    Returns:
        CSV 형식의 문자열 (UTF-8 BOM 포함, 엑셀 호환)
    """
    output = io.StringIO()
    # UTF-8 BOM 추가 (엑셀에서 한글 깨짐 방지)
    output.write("\ufeff")
    writer = csv.DictWriter(output, fieldnames=["제목", "URL", "요약"])
    writer.writeheader()
    for r in results:
        writer.writerow({
            "제목": r["title"],
            "URL": r["url"],
            "요약": r["summary"],
        })
    return output.getvalue()


# ──────────────────────────────────────────────
# 8. 메인 UI
# ──────────────────────────────────────────────

# Gemini 모델 초기화
model = init_gemini()

if model is None:
    st.info(
        "🔑 Gemini API Key가 설정되지 않았습니다.\n\n"
        "**Codespaces 사용 시:** GitHub Settings → Codespaces → Secrets에서 "
        "`GEMINI_API_KEY`를 등록하세요.\n\n"
        "**로컬 사용 시:** 왼쪽 사이드바에서 API Key를 직접 입력하세요.\n\n"
        "API Key 발급: [AI Studio](https://aistudio.google.com/) → Get API Key"
    )

# 검색 입력 폼
with st.form("search_form"):
    keyword = st.text_input(
        "🔍 검색 키워드",
        placeholder="예: 인공지능, 반도체, 부동산 등",
    )
    submitted = st.form_submit_button("검색하기", type="primary")

# 검색 실행
if submitted and keyword:
    if model is None:
        st.error("❌ Gemini API Key가 설정되지 않았습니다. Codespaces Secrets를 확인하거나 사이드바에서 입력해 주세요.")
    else:
        # ── 뉴스 검색 ──
        with st.spinner(f"'{keyword}' 관련 뉴스를 검색 중..."):
            articles = search_news(keyword, num_results=5)

        if not articles:
            st.warning(f"😥 '{keyword}'에 대한 검색 결과가 없습니다. 다른 키워드를 시도해 보세요.")
        else:
            st.success(f"✅ {len(articles)}개의 기사를 찾았습니다. 요약을 생성 중...")

            # ── 각 기사 요약 생성 ──
            results = []
            progress_bar = st.progress(0)

            for i, article in enumerate(articles):
                progress_bar.progress((i) / len(articles), text=f"기사 {i+1}/{len(articles)} 요약 중...")

                # 기사 본문 추출 시도
                body_text = fetch_article_text(article["url"])

                # 본문 추출 실패 시 GoogleNews 설명문 사용
                text_for_summary = body_text if body_text else article["desc"]

                # Gemini로 요약
                summary = summarize_with_gemini(model, article["title"], text_for_summary)

                results.append({
                    "title": article["title"],
                    "url": article["url"],
                    "summary": summary,
                })

                # API 요청 간 짧은 대기 (rate limit 방지)
                time.sleep(0.5)

            progress_bar.progress(1.0, text="완료!")
            time.sleep(0.3)
            progress_bar.empty()

            # ── 결과 표시 ──
            st.divider()
            st.subheader(f"📋 '{keyword}' 검색 결과")

            for idx, r in enumerate(results, 1):
                with st.container(border=True):
                    st.markdown(f"### {idx}. {r['title']}")
                    st.markdown(f"🔗 [원문 보기]({r['url']})")
                    st.markdown(f"**요약:** {r['summary']}")

            # ── CSV 다운로드 버튼 ──
            st.divider()
            csv_data = results_to_csv(results)
            st.download_button(
                label="📥 CSV 파일 다운로드",
                data=csv_data,
                file_name=f"뉴스검색_{keyword}.csv",
                mime="text/csv",
                type="primary",
            )

            # 세션에 결과 저장 (재사용 가능)
            st.session_state["last_results"] = results


# ──────────────────────────────────────────────
# 9. 사이드바 안내
# ──────────────────────────────────────────────
with st.sidebar:
    st.divider()
    st.markdown("### ℹ️ 사용 방법")
    st.markdown(
        """
1. Codespaces Secrets 또는 사이드바에서 API Key 설정
2. 검색 키워드를 입력하고 **검색하기** 클릭
3. AI가 각 기사를 요약합니다
4. **CSV 다운로드** 버튼으로 결과 저장
"""
    )
    st.divider()
    st.markdown(
        "Made with [Streamlit](https://streamlit.io) + "
        "[Gemini API](https://aistudio.google.com/)"
    )
