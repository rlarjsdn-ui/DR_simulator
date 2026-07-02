"""
DR 전력 어드바이저 v4 — Premium Dashboard UI
"""
import streamlit as st
import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime
import time
import requests
import plotly.graph_objects as go

# ─────────────────────────────────────────
# 외부 계산 모듈 연결
# billing.py / scheduler.py가 같은 폴더에 있으면 자동 사용하고,
# 없으면 기존 UI 내부 임시 계산 로직으로 fallback합니다.
# ─────────────────────────────────────────
try:
    from billing import (
        simulate_monthly_bills as billing_simulate_monthly_bills,
        calculate_progressive_bill as billing_calculate_progressive_bill,
        calc_appliance_tou as billing_calc_appliance_tou,
        calc_appliance_dr as billing_calc_appliance_dr,
        simulate_recent_pattern_bills as billing_simulate_recent_pattern_bills,
    )
    BILLING_READY = True
except Exception:
    try:
        from billing_clean import (
            simulate_monthly_bills as billing_simulate_monthly_bills,
            calculate_progressive_bill as billing_calculate_progressive_bill,
            calc_appliance_tou as billing_calc_appliance_tou,
            calc_appliance_dr as billing_calc_appliance_dr,
            simulate_recent_pattern_bills as billing_simulate_recent_pattern_bills,
        )
        BILLING_READY = True
    except Exception:
        billing_simulate_monthly_bills = None
        billing_calculate_progressive_bill = None
        billing_calc_appliance_tou = None
        billing_calc_appliance_dr = None
        billing_simulate_recent_pattern_bills = None
        BILLING_READY = False

try:
    from scheduler import optimize_appliance_schedule
    SCHEDULER_READY = True
except Exception:
    optimize_appliance_schedule = None
    SCHEDULER_READY = False

REFIT_BILLING_DATA_FILE = "REFIT_House_1_2_3_4_5_15min_AI_Dataset.csv"
REFIT_BILLING_DATA_FILE_GZ = REFIT_BILLING_DATA_FILE + ".gz"

@st.cache_data(show_spinner=False)
def load_refit_billing_data():
    search_paths = [
        os.path.join("data", REFIT_BILLING_DATA_FILE),
        REFIT_BILLING_DATA_FILE,
        os.path.join(os.getcwd(), "data", REFIT_BILLING_DATA_FILE),
        os.path.join(os.getcwd(), REFIT_BILLING_DATA_FILE),
        # 용량 문제로 gzip 압축본을 올린 경우도 자동으로 찾아 읽습니다. (pandas가 .gz 확장자면 자동 압축 해제)
        os.path.join("data", REFIT_BILLING_DATA_FILE_GZ),
        REFIT_BILLING_DATA_FILE_GZ,
        os.path.join(os.getcwd(), "data", REFIT_BILLING_DATA_FILE_GZ),
        os.path.join(os.getcwd(), REFIT_BILLING_DATA_FILE_GZ),
    ]
    for fp in search_paths:
        if os.path.exists(fp):
            return pd.read_csv(fp), fp
    return None, None

def get_home_billing_summary():
    """Home 카드와 Billing 탭의 월간 환산 요금을 같은 계산 기준으로 맞춥니다."""
    default_bill, default_saving = 58058, 6967
    if not (BILLING_READY and billing_simulate_recent_pattern_bills is not None):
        return default_bill, default_saving
    df_refit, _ = load_refit_billing_data()
    if df_refit is None:
        return default_bill, default_saving
    try:
        result = billing_simulate_recent_pattern_bills(
            df_refit,
            recent_days=30,
            dr_hours=list(range(16, 19)),
            incentive_rate=150,
            dr_participation_rate=0.60,
            month=datetime.now().month,
            household_count=5,
        )
        return int(result.get("TOU_DR최종", default_bill)), int(result.get("누진제대비DR절약", default_saving))
    except Exception:
        return default_bill, default_saving

st.set_page_config(
    page_title="DR 전력 어드바이저",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── 토스 스타일 CSS ───
st.markdown("""
<style>
:root{
    --ink:#202124;
    --muted:#5f6873;
    --muted2:#7b838c;
    --glass:rgba(242,236,224,.70);
    --glass-strong:rgba(242,236,224,.66);
    --line:rgba(255,255,255,.50);
    --yellow:#FFE476;
    --yellow2:#F7D957;
    --shadow:0 24px 64px rgba(0,0,0,.15);
}
*{box-sizing:border-box;}
html, body, [class*="css"]{
    font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR","Segoe UI",sans-serif !important;
}
.stApp{
    background:
        linear-gradient(rgba(8,12,20,.16), rgba(8,12,20,.20)),
        var(--home-bg, radial-gradient(circle at 50% 40%, #e9e5db, #a8b0ba)) !important;
    background-size:cover !important;
    background-position:center 66% !important;
    background-attachment:fixed !important;
}
[data-testid="stHeader"]{background:transparent !important;}
.main .block-container{
    max-width:1500px !important;
    padding:0 1.15rem 1.8rem !important;
}

/* 지역 선택 박스 */
.floating-city-label{
    display:none !important;
}

/* HOME 상단 지역 선택 박스: 날씨 카드와 같은 폭 */
div[data-testid="stSelectbox"]{
    width:390px !important;
    margin-top:0 !important;
    margin-bottom:0 !important;
    position:relative;
    z-index:80;
    transform:translate(25px, -70px);
}

/* 선택 박스 외곽 */
div[data-testid="stSelectbox"] > div{
    background:rgba(242,236,224,.58) !important;
    border-radius:15px !important;
    border:1px solid rgba(255,255,255,.50) !important;
    box-shadow:0 18px 48px rgba(0,0,0,.12) !important;
    backdrop-filter:blur(18px) !important;
    -webkit-backdrop-filter:blur(18px) !important;
}

/* 선택 박스 내부 흰색 제거 */
div[data-testid="stSelectbox"] div[data-baseweb="select"]{
    background:transparent !important;
}

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div{
    background:rgba(242,236,224,.58) !important;
    border:none !important;
    box-shadow:none !important;
}

div[data-testid="stSelectbox"] input{
    color:#202124 !important;
}

div[data-testid="stSelectbox"] svg{
    color:#202124 !important;
}

/* Schedule/Billing/Forecast 탭 안 selectbox는 HOME 위치/폭 이동 적용하지 않기 */
div[data-testid="stTabs"] div[data-testid="stSelectbox"]{
    width:auto !important;
    transform:none !important;
}

/* HOME */
.home-bg-shell{
    width:min(1480px, calc(100vw - 54px));
    margin:-138px auto 1.2rem auto; /* HOME 전체 위치: 더 위로 -155px, 아래로 -115px */
    padding:0;
    background:transparent;
}
.home-dashboard-grid{
    display:grid;
    grid-template-columns:440px minmax(600px,1fr) 390px;
    grid-template-rows:128px 292px;
    gap:20px 24px; /* 카드 간격: 세로 / 가로 */
    width:100%;
    align-items:stretch;
}
.glass-panel{
    background:var(--glass);
    border:1px solid var(--line);
    box-shadow:var(--shadow);
    backdrop-filter:blur(18px);
    -webkit-backdrop-filter:blur(18px);
    color:var(--ink);
}

/* 왼쪽 카드: 위쪽까지 올리고 숫자 정보 중심 */
.left-ref-panel{
    grid-column:1;
    grid-row:1 / span 2;
    min-height:560px;
    padding:1.22rem 1.34rem 1.15rem;
    border-radius:34px;
    transform:translateX(-50px);
}
.left-ref-title{
    font-size:34px;
    line-height:1.13;
    letter-spacing:-.05em;
    font-weight:780;
    margin-bottom:7px;
}
.left-ref-date{
    font-size:10.8px;
    color:var(--muted);
    font-weight:590;
    margin-bottom:12px;
}
.left-status-chip{
    display:inline-flex;
    width:max-content;
    padding:5px 10px;
    border-radius:12px;
    background:rgba(255,228,118,.80);
    color:#2e2b22;
    font-size:10.2px;
    font-weight:690;
    margin-bottom:12px;
}
.left-status-text{
    font-size:13px;
    color:#4e5968;
    font-weight:680;
    margin-bottom:7px;
}
.left-main-price{
    font-size:38px;
    line-height:1;
    letter-spacing:-.055em;
    font-weight:780;
    margin-bottom:9px;
}
.left-main-price span{
    font-size:20px;
    font-weight:690;
    letter-spacing:-.035em;
}
.left-peak-chip{
    display:inline-flex;
    padding:6px 10px;
    border-radius:999px;
    background:rgba(255,255,255,.48);
    color:#4e5968;
    font-size:10.3px;
    font-weight:630;
    margin-bottom:13px;
}
.left-ref-divider{
    height:1px;
    background:rgba(48,50,54,.10);
    margin:0 -1.34rem 15px;
}
.left-summary-grid{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:12px;
}
.summary-tile{
    min-height:84px;
    border-radius:24px;
    background:rgba(255,255,255,.30);
    border:1px solid rgba(255,255,255,.36);
    padding:13px 13px 12px;
}
.summary-label{
    font-size:11px;
    color:#59636f;
    font-weight:680;
    margin-bottom:12px;
}
.summary-value{
    font-size:28px;
    line-height:1;
    letter-spacing:-.05em;
    font-weight:780;
    color:#202124;
}
.summary-value span{
    font-size:10px;
    font-weight:630;
    margin-left:2px;
}
.summary-hint{
    margin-top:9px;
    font-size:9.7px;
    color:#68717a;
    font-weight:540;
    line-height:1.25;
}
.summary-tile.accent{
    background:rgba(255,228,118,.28);
}
.summary-tile.wide{
    grid-column:1 / span 2;
    min-height:92px;
}
.summary-pair-wrap{
    display:grid;
    grid-template-columns:1fr 1px 1fr;
    gap:14px;
    align-items:center;
}
.summary-divider{
    height:44px;
    background:rgba(48,50,54,.13);
}

/* 가운데 카피: 하늘 위쪽 중앙 */
.center-copy{
    grid-column:2;
    grid-row:1;
    width:430px;
    padding-top:25px; /* 가운데 영어 문구 위치: 숫자를 줄이면 더 위로 올라감 */
    justify-self:center;
    text-align:center;
    color:rgba(255,255,255,.94);
    text-shadow:0 2px 16px rgba(0,0,0,.30);
}
.center-copy-title{
    font-size:42px;
    font-weight:780;
    letter-spacing:-.035em;
    margin-bottom:10px;
}
.center-copy-sub{
    font-size:19px;
    line-height:1.55;
    font-weight:540;
    color:rgba(255,255,255,.80);
}
.home-spacer{grid-column:2;grid-row:2;}

/* 날씨: 오른쪽 상단, 지역 선택과 가까이 */
.top-weather-card{
    grid-column:3;
    grid-row:1;
    min-height:170px;
    margin-top:62px; /* 날씨 카드 위치: 지역 선택 박스와 10~16px 정도 간격 유지 */
    border-radius:30px;
    padding:.92rem 1.12rem;
    display:flex;
    flex-direction:column;
    justify-content:space-between;
    overflow:hidden;
}
.weather-card-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    font-size:14px;
    font-weight:700;
    color:#4e5968;
}
.weather-mini-icon{
    width:36px;
    height:36px;
    border-radius:13px;
    background:rgba(255,228,118,.78);
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:18px;
    flex:0 0 auto;
}
.weather-region-pill{
    width:max-content;
    max-width:100%;
    padding:5px 10px;
    border-radius:999px;
    font-size:10.5px;
    line-height:1;
    white-space:nowrap;
    background:rgba(255,255,255,.45);
    color:#4e5968;
    font-weight:630;
}
.weather-card-body{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:14px;
    align-items:end;
}
.weather-main-temp{
    font-size:28px;
    line-height:.95;
    white-space:nowrap;
    color:#202124;
    font-weight:760;
}
.weather-main-desc{
    margin-top:7px;
    font-size:11px;
    max-width:150px;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
    color:#5f6873;
    font-weight:540;
}
.weather-detail-grid{
    display:grid;
    gap:6px;
    padding-left:12px;
    border-left:1px solid rgba(48,50,54,.14);
}
.weather-detail-grid div{
    display:flex;
    justify-content:space-between;
    gap:10px;
    font-size:10.2px;
    line-height:1;
    white-space:nowrap;
    color:#5f6873;
    font-weight:540;
}
.weather-detail-grid strong{
    color:#303236;
    font-weight:660;
}

/* AI: 오른쪽 아래 */
.right-ai-panel{
    grid-column:3;
    grid-row:2;
    min-height:300px;
    margin-top:104px; /* AI 카드 위치: 줄이면 위로, 키우면 아래로 */
    padding:1.15rem 1.18rem;
    border-radius:34px;
}
.right-ai-top{
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-bottom:14px;
}
.right-ai-label{
    font-size:12.3px;
    font-weight:700;
    color:#202124;
}
.ai-badge{
    width:36px;
    height:36px;
    border-radius:13px;
    background:var(--yellow);
    display:flex;
    align-items:center;
    justify-content:center;
    font-weight:700;
}
.right-ai-main{
    font-size:34px;
    line-height:1;
    letter-spacing:-.05em;
    font-weight:780;
    margin-bottom:8px;
}
.ai-status-row{
    display:grid;
    grid-template-columns:1fr 120px;
    gap:12px;
    align-items:end;
    margin-bottom:16px;
}

.ai-load-box{
    padding:12px 13px;
    border-radius:20px;
    background:rgba(255,255,255,.25);
    border:1px solid rgba(255,255,255,.34);
}

.ai-load-label{
    font-size:10.5px;
    color:#5f6873;
    font-weight:680;
    margin-bottom:7px;
}

.ai-load-value{
    font-size:22px;
    line-height:1;
    color:#202124;
    font-weight:800;
    letter-spacing:-.04em;
}
.right-ai-sub{
    color:#4e5968;
    font-size:13px;
    line-height:1.45;
    font-weight:540;
}
.right-ai-sub strong{
    font-weight:680;
    color:#303236;
}
.right-ai-chart{
    min-height:108px;
    margin-top:9px;
    display:flex;
    align-items:center;
}
.right-ai-chart svg{
    width:100%;
    height:108px;
}
.right-ai-times{
    display:grid;
    grid-template-columns:repeat(5,1fr);
    font-size:9.4px;
    color:#5f6873;
    text-align:center;
    font-weight:540;
    margin-top:-6px;
}
.ai-slider-dots{
    display:flex;
    gap:6px;
    margin-top:9px;
}
.ai-slider-dots span{
    width:7px;
    height:7px;
    border-radius:999px;
    background:rgba(48,50,54,.20);
}
.ai-slider-dots span:first-child{
    background:var(--yellow);
}


/* AI 피크 위험도 게이지 */
.ai-risk-box{
    margin-top:10px;
    padding:14px;
    border-radius:24px;
    background:rgba(255,255,255,.26);
    border:1px solid rgba(255,255,255,.36);
}

.ai-risk-top{
    display:flex;
    justify-content:space-between;
    align-items:center;
    font-size:12px;
    color:#4e5968;
    font-weight:700;
    margin-bottom:10px;
}

.ai-risk-top strong{
    font-size:20px;
    color:#202124;
    font-weight:800;
}

.ai-risk-bar{
    height:11px;
    border-radius:999px;
    background:rgba(255,255,255,.48);
    overflow:hidden;
    margin-bottom:13px;
}

.ai-risk-fill{
    height:100%;
    border-radius:999px;
    background:#FFE476;
}

.ai-action-text{
    font-size:11px;
    line-height:1.45;
    color:#4e5968;
    font-weight:560;
    word-break:keep-all;
}


.summary-tile.min-wide{
    grid-column:1 / span 2;
    min-height:92px;
    background:rgba(255,228,118,.28);
}
.dr-notice-card{
    grid-column:3;
    grid-row:2;
    margin-top:435px;
    min-height:132px;
    border-radius:34px;
    padding:1.15rem 1.22rem;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:14px;
    text-decoration:none !important;
    color:var(--ink) !important;
    position:relative;
    z-index:14;
}
.dr-notice-left{
    display:flex;
    align-items:center;
    gap:12px;
}
.dr-notice-icon{
    width:52px;
    height:52px;
    border-radius:17px;
    background:rgba(255,228,118,.82);
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:23px;
    flex:0 0 auto;
}
.dr-notice-title{
    font-size:16px;
    font-weight:820;
    letter-spacing:-.04em;
    margin-bottom:6px;
}
.dr-notice-sub{
    font-size:10.5px;
    color:#5f6873;
    font-weight:560;
}
.dr-notice-meta{
    margin-top:6px;
    font-size:10.2px;
    color:#68717a;
    font-weight:540;
    line-height:1.35;
}
.dr-notice-arrow{
    font-size:18px;
    font-weight:760;
    opacity:.75;
}

/* 이전 요약 카드 제거 */
.right-combined-card{display:none !important;}
.bottom-weather-card{display:none !important;}

/* 하단 스케줄: 더 아래로 내려 집을 덜 가림 */
.bottom-dashboard-row{
    display:grid;
    grid-template-columns:440px minmax(600px,1fr) 390px;
    gap:24px;
    width:100%;
    margin-top:150px; /* 스케줄 바 위치: 키우면 더 아래로, 줄이면 위로 */
    margin-left:-50px;
    align-items:stretch;
}
.schedule-dock{
    grid-column:1 / span 2;
    min-height:132px;
    border-radius:34px;
    background:var(--glass);
    border:1px solid rgba(255,255,255,.54);
    box-shadow:var(--shadow);
    backdrop-filter:blur(18px);
    -webkit-backdrop-filter:blur(18px);
    padding:1.16rem 1.26rem;
    display:grid;
    grid-template-columns:270px minmax(360px,1fr) 128px;
    gap:18px;
    align-items:center;
    overflow:visible;
}
.schedule-dock-title{
    display:flex;
    align-items:center;
    gap:12px;
    font-size:16px;
    line-height:1;
    margin-bottom:12px;
    white-space:nowrap;
    letter-spacing:-.035em;
    font-weight:760;
}
.schedule-calendar-icon{
    width:44px;
    height:44px;
    border-radius:14px;
    background:rgba(255,228,118,.78);
    display:inline-flex;
    align-items:center;
    justify-content:center;
    font-size:21px;
    flex:0 0 auto;
}
.schedule-dock-desc{
    font-size:11.1px;
    line-height:1.5;
    max-width:250px;
    font-weight:540;
    color:#4e5968;
    word-break:keep-all;
}
.dock-timeline{
    position:relative;
    padding-top:30px;
}
.best-time-chip{
    position:absolute;
    top:2px;
    left:10%;
    transform:translateX(-50%);
    background:rgba(255,228,118,.86);
    color:#2e2b22;
    border-radius:999px;
    padding:4px 10px;
    font-size:10.8px;
    font-weight:680;
    white-space:nowrap;
}
.dock-hours{
    display:grid;
    grid-template-columns:repeat(8,1fr);
    font-size:9.7px;
    color:#5f6873;
    font-weight:540;
    margin-bottom:7px;
}
.dock-line{
    height:2px;
    background:rgba(255,255,255,.72);
    position:relative;
    margin-bottom:7px;
}
.dock-line::after{
    content:"";
    position:absolute;
    left:10%;
    top:50%;
    width:13px;
    height:13px;
    border-radius:999px;
    background:var(--yellow);
    border:2px solid rgba(255,255,255,.85);
    transform:translate(-50%,-50%);
}
.appliance-row{
    display:grid;
    grid-template-columns:repeat(auto-fit,minmax(62px,1fr));
    gap:8px;
    min-height:24px;
}
.app-marker{
    text-align:center;
    color:#303236;
    font-size:10px;
    font-weight:540;
}
.app-marker .emoji{
    display:block;
    font-size:16px;
    margin-bottom:2px;
}
.schedule-button{
    width:118px;
    height:46px;
    display:flex;
    align-items:center;
    justify-content:center;
    border-radius:14px;
    background:rgba(255,255,255,.48);
    color:#303236 !important;
    text-decoration:none !important;
    font-size:12px;
    font-weight:660;
}

/* 탭 영역 */
.section-lbl{
    font-size:24px;
    font-weight:850;
    margin:1.4rem 0 .9rem;
    color:#ffffff;
    text-shadow:0 2px 12px rgba(0,0,0,.45);
    letter-spacing:-.04em;
}
.badge-green,.badge-amber,.badge-red,.badge-gray{
    display:inline-flex;
    padding:4px 10px;
    border-radius:999px;
    font-size:12px;
    font-weight:660;
}
.badge-green{background:#EAF3DE;color:#2F6B12;}
.badge-amber{background:#FFF2C2;color:#7A5600;}
.badge-red{background:#FCEBEB;color:#A32D2D;}
.badge-gray{background:#F2F4F6;color:#5f6873;}
.stButton>button{
    border-radius:14px !important;
    border:1px solid rgba(32,33,36,.10) !important;
}


/* 하단 탭 가독성 강화 */
div[data-testid="stTabs"] > div[role="tablist"]{
    width:max-content !important;
    padding:10px 18px 8px !important;
    margin:0 0 22px 0 !important;
    border-radius:22px !important;
    background:rgba(242,236,224,.78) !important;
    border:1px solid rgba(255,255,255,.62) !important;
    box-shadow:0 14px 38px rgba(0,0,0,.18) !important;
    backdrop-filter:blur(16px) !important;
    -webkit-backdrop-filter:blur(16px) !important;
    display:flex !important;
    gap:28px !important;
}

button[data-baseweb="tab"]{
    padding:9px 20px !important;
    min-width:120px !important;
}

button[data-baseweb="tab"] p{
    color:#202124 !important;
    font-weight:850 !important;
    font-size:17px !important;
    text-shadow:none !important;
}

button[data-baseweb="tab"][aria-selected="true"] p{
    color:#202124 !important;
    font-weight:920 !important;
}

div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{
    background:#FFE476 !important;
    height:5px !important;
    border-radius:999px !important;
}


/* 부연 설명 텍스트 가독성 강화 */
.left-ref-date,
.left-status-text,
.left-peak-chip,
.summary-hint,
.weather-main-desc,
.weather-detail-grid div,
.right-ai-sub,
.ai-action-text,
.dr-notice-sub,
.dr-notice-meta,
.schedule-dock-desc,
.dock-hours,
.weather-region-pill{
    color:#3f4852 !important;
    font-weight:620 !important;
}

.summary-label,
.ai-risk-top,
.ai-load-label,
.weather-card-head,
.right-ai-label{
    color:#2f3740 !important;
    font-weight:740 !important;
}

/* DR 알림 제목 강조 */
.dr-notice-title{
    font-size:16px !important;
    font-weight:820 !important;
    color:#202124 !important;
    letter-spacing:-.04em;
    margin-bottom:6px;
}

.dr-notice-sub{
    font-size:11.4px !important;
}

.dr-notice-meta{
    font-size:10.8px !important;
}

@media(max-width:900px){
    .home-dashboard-grid,
    .bottom-dashboard-row{
        width:100%;
        grid-template-columns:1fr;
        grid-template-rows:auto;
        margin-left:0;
    }
    .left-ref-panel,
    .center-copy,
    .top-weather-card,
    .right-ai-panel{
        grid-column:1;
        grid-row:auto;
        min-height:0;
    }
    .center-copy{padding-top:10px;}
    .schedule-dock{grid-template-columns:1fr;}
}

/* 지역 선택 박스 위치 보정 */
div[data-testid="stSelectbox"]{position:relative; z-index:60;}
.floating-city-label{position:relative; z-index:60;}
.top-weather-card{position:relative; z-index:10;}
.right-ai-panel{position:relative; z-index:10;}
.schedule-dock{position:relative; z-index:12;}


/* Schedule 탭 UI/UX 가독성 강화 */
div[data-testid="stTabs"]{
    margin-top:8px;
}

/* 탭 내부의 기본 글씨를 진하게 */
div[data-testid="stTabs"] label p,
div[data-testid="stTabs"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stTabs"] [data-testid="stCaptionContainer"],
div[data-testid="stTabs"] [data-testid="stCaptionContainer"] p{
    color:#2f3740 !important;
    font-weight:670 !important;
}

/* Expander를 카드처럼 보이게 */
div[data-testid="stTabs"] div[data-testid="stExpander"]{
    background:rgba(242,236,224,.86) !important;
    border:1px solid rgba(255,255,255,.66) !important;
    border-radius:24px !important;
    box-shadow:0 18px 48px rgba(0,0,0,.16) !important;
    backdrop-filter:blur(18px) !important;
    -webkit-backdrop-filter:blur(18px) !important;
    overflow:hidden !important;
}

/* Expander 제목 */
div[data-testid="stTabs"] div[data-testid="stExpander"] summary{
    color:#202124 !important;
    font-weight:780 !important;
    font-size:15px !important;
}

/* 입력창 글씨 */
div[data-testid="stTabs"] input,
div[data-testid="stTabs"] textarea{
    color:#202124 !important;
    font-weight:680 !important;
}

/* 숫자 입력창 */
div[data-testid="stTabs"] div[data-baseweb="input"]{
    background:rgba(255,255,255,.90) !important;
    border-radius:14px !important;
    border:1px solid rgba(32,33,36,.14) !important;
    box-shadow:0 8px 20px rgba(0,0,0,.06) !important;
}

/* 셀렉트 박스 */
div[data-testid="stTabs"] div[data-baseweb="select"] > div{
    background:rgba(255,255,255,.90) !important;
    color:#202124 !important;
    border-radius:14px !important;
    border:1px solid rgba(32,33,36,.14) !important;
    box-shadow:0 8px 20px rgba(0,0,0,.06) !important;
}

div[data-testid="stTabs"] div[data-baseweb="select"] span,
div[data-testid="stTabs"] div[data-baseweb="select"] input{
    color:#202124 !important;
    font-weight:680 !important;
}

/* number input의 + - 버튼 */
div[data-testid="stTabs"] button[aria-label="Increment"],
div[data-testid="stTabs"] button[aria-label="Decrement"]{
    color:#202124 !important;
    background:rgba(255,255,255,.70) !important;
}

/* 체크박스 라벨 */
div[data-testid="stTabs"] [data-testid="stCheckbox"] label,
div[data-testid="stTabs"] [data-testid="stCheckbox"] label p{
    color:#2f3740 !important;
    font-weight:700 !important;
}

/* 탭 내부 버튼 */
div[data-testid="stTabs"] .stButton > button{
    background:rgba(255,255,255,.92) !important;
    color:#202124 !important;
    font-weight:740 !important;
    border-radius:16px !important;
    border:1px solid rgba(32,33,36,.14) !important;
    min-height:46px;
    box-shadow:0 10px 24px rgba(0,0,0,.09) !important;
}

div[data-testid="stTabs"] .stButton > button:hover{
    background:#FFE476 !important;
    color:#202124 !important;
    border-color:rgba(255,228,118,.90) !important;
}

/* 토글 */
div[data-testid="stTabs"] [data-testid="stToggle"] label,
div[data-testid="stTabs"] [data-testid="stToggle"] label p{
    color:#2f3740 !important;
    font-weight:740 !important;
}

/* Schedule 탭의 알림/정보 박스 */
div[data-testid="stTabs"] div[data-testid="stAlert"]{
    background:rgba(242,236,224,.88) !important;
    color:#202124 !important;
    border-radius:18px !important;
    border:1px solid rgba(255,255,255,.65) !important;
}

/* 구분선 */
div[data-testid="stTabs"] hr{
    border-color:rgba(255,255,255,.34) !important;
}

/* DR 이벤트 안내 카드 */
.dr-alert-card,
.dr-summary-card{
    background:rgba(242,236,224,.86);
    border:1px solid rgba(255,255,255,.66);
    border-radius:24px;
    padding:18px 20px;
    box-shadow:0 18px 48px rgba(0,0,0,.14);
    backdrop-filter:blur(18px);
    -webkit-backdrop-filter:blur(18px);
    color:#202124;
    margin:.7rem 0 1rem;
}

.dr-alert-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin-bottom:10px;
}

.dr-alert-title{
    font-size:18px;
    font-weight:830;
    letter-spacing:-.04em;
    color:#202124;
}

.dr-alert-chip{
    padding:6px 12px;
    border-radius:999px;
    background:rgba(255,228,118,.86);
    color:#202124;
    font-size:12px;
    font-weight:760;
    white-space:nowrap;
}

.dr-alert-desc,
.dr-summary-text{
    font-size:13px;
    line-height:1.55;
    font-weight:650;
    color:#3f4852;
    word-break:keep-all;
}

/* 가전 추가/결과 영역의 일반 텍스트 */
div[data-testid="stTabs"] [data-testid="stHorizontalBlock"]{
    color:#202124 !important;
}

/* 작은 화면에서도 입력 폼이 밀리지 않도록 */
@media(max-width:900px){
    div[data-testid="stTabs"] div[data-testid="stExpander"]{
        border-radius:20px !important;
    }
    .section-lbl{
        font-size:22px;
    }
}


/* 상단 탭 버튼 가독성 재조정 */
div[data-testid="stTabs"] > div[role="tablist"]{
    width:max-content !important;
    padding:10px 18px 6px !important;
    border-radius:20px !important;
    background:rgba(8,12,20,.42) !important;
    border:1px solid rgba(255,255,255,.20) !important;
    box-shadow:0 12px 34px rgba(0,0,0,.22) !important;
    backdrop-filter:blur(14px) !important;
    -webkit-backdrop-filter:blur(14px) !important;
}

button[data-baseweb="tab"]{
    padding:8px 16px !important;
}

button[data-baseweb="tab"] p{
    color:rgba(255,255,255,.88) !important;
    font-weight:780 !important;
    font-size:15px !important;
    text-shadow:0 2px 8px rgba(0,0,0,.35) !important;
}

button[data-baseweb="tab"][aria-selected="true"] p{
    color:#FFE476 !important;
    font-weight:850 !important;
}

div[data-testid="stTabs"] [data-baseweb="tab-highlight"]{
    background:#FFE476 !important;
    height:4px !important;
    border-radius:999px !important;
}


/* Schedule 탭 아래 영역 전체 가독성 강화 */
div[data-testid="stTabs"] [data-testid="stVerticalBlock"] > div:has(.section-lbl),
div[data-testid="stTabs"] [data-testid="stVerticalBlock"] > div:has(#dr-event-section){
    color:#202124 !important;
}

/* 탭 내부 일반 텍스트 전체 보정 */
/* 탭 버튼은 제외하고, 탭 내용 영역에만 적용 */
div[data-testid="stTabs"] div[role="tabpanel"] label,
div[data-testid="stTabs"] div[role="tabpanel"] p,
div[data-testid="stTabs"] div[role="tabpanel"] span,
div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stMarkdownContainer"]{
    color:#202124 !important;
    font-weight:700 !important;
}

/* 탭 제목은 배경 위에서도 잘 보이게 */
.section-lbl{
    font-size:25px !important;
    font-weight:880 !important;
    margin:1.6rem 0 1rem !important;
    color:#ffffff !important;
    text-shadow:0 3px 14px rgba(0,0,0,.62) !important;
    letter-spacing:-.045em !important;
}

/* Expander 내부 라벨/소제목 */
div[data-testid="stTabs"] div[data-testid="stExpander"] label p,
div[data-testid="stTabs"] div[data-testid="stExpander"] [data-testid="stMarkdownContainer"] p{
    color:#202124 !important;
    font-weight:760 !important;
    font-size:16px !important;
}

/* DR 이벤트 설정 설명 문구 */
div[data-testid="stTabs"] [data-testid="stCaptionContainer"],
div[data-testid="stTabs"] [data-testid="stCaptionContainer"] p{
    color:#ffffff !important;
    font-weight:720 !important;
    font-size:14px !important;
    text-shadow:0 2px 10px rgba(0,0,0,.58) !important;
}

/* Expander 카드 더 밝고 진하게 */
div[data-testid="stTabs"] div[data-testid="stExpander"]{
    background:rgba(242,236,224,.90) !important;
    border:1px solid rgba(255,255,255,.72) !important;
    border-radius:26px !important;
    box-shadow:0 22px 58px rgba(0,0,0,.20) !important;
}

/* Expander 헤더 */
div[data-testid="stTabs"] div[data-testid="stExpander"] summary,
div[data-testid="stTabs"] div[data-testid="stExpander"] summary p,
div[data-testid="stTabs"] div[data-testid="stExpander"] summary span{
    color:#202124 !important;
    font-weight:830 !important;
    font-size:16px !important;
}

/* 입력창과 선택창 확대/강조 */
div[data-testid="stTabs"] input,
div[data-testid="stTabs"] textarea{
    color:#202124 !important;
    font-weight:760 !important;
    font-size:15px !important;
}

div[data-testid="stTabs"] div[data-baseweb="input"],
div[data-testid="stTabs"] div[data-baseweb="select"] > div{
    background:rgba(255,255,255,.94) !important;
    border-radius:15px !important;
    border:1px solid rgba(32,33,36,.18) !important;
    box-shadow:0 10px 26px rgba(0,0,0,.08) !important;
}

div[data-testid="stTabs"] div[data-baseweb="select"] span,
div[data-testid="stTabs"] div[data-baseweb="select"] input{
    color:#202124 !important;
    font-weight:760 !important;
    font-size:15px !important;
}

/* 체크박스 / 토글 */
div[data-testid="stTabs"] [data-testid="stCheckbox"] label,
div[data-testid="stTabs"] [data-testid="stCheckbox"] label p,
div[data-testid="stTabs"] [data-testid="stToggle"] label,
div[data-testid="stTabs"] [data-testid="stToggle"] label p{
    color:#202124 !important;
    font-weight:790 !important;
    font-size:15px !important;
    text-shadow:none !important;
}

/* 버튼 강화 */
div[data-testid="stTabs"] .stButton > button{
    background:rgba(255,255,255,.95) !important;
    color:#202124 !important;
    font-weight:790 !important;
    font-size:15px !important;
    border-radius:17px !important;
    border:1px solid rgba(32,33,36,.18) !important;
    min-height:50px !important;
    box-shadow:0 12px 28px rgba(0,0,0,.12) !important;
}

div[data-testid="stTabs"] .stButton > button:hover{
    background:#FFE476 !important;
    color:#202124 !important;
}

/* DR 이벤트 안내 카드 */
.dr-alert-card,
.dr-summary-card{
    background:rgba(242,236,224,.92) !important;
    border:1px solid rgba(255,255,255,.72) !important;
    border-radius:26px !important;
    padding:20px 22px !important;
    box-shadow:0 22px 58px rgba(0,0,0,.18) !important;
    backdrop-filter:blur(18px) !important;
    -webkit-backdrop-filter:blur(18px) !important;
    color:#202124 !important;
    margin:.9rem 0 1.2rem !important;
}

.dr-alert-title{
    font-size:20px !important;
    font-weight:880 !important;
    color:#202124 !important;
}

.dr-alert-desc,
.dr-summary-text{
    font-size:15px !important;
    line-height:1.6 !important;
    font-weight:720 !important;
    color:#2f3740 !important;
}

/* info/alert 박스 */
div[data-testid="stTabs"] div[data-testid="stAlert"]{
    background:rgba(242,236,224,.92) !important;
    color:#202124 !important;
    border-radius:20px !important;
    border:1px solid rgba(255,255,255,.72) !important;
}

/* 가전 추가 및 결과 영역 텍스트 */
div[data-testid="stTabs"] [data-testid="stHorizontalBlock"] p,
div[data-testid="stTabs"] [data-testid="stHorizontalBlock"] span,
div[data-testid="stTabs"] [data-testid="stHorizontalBlock"] div{
    color:#202124 !important;
}

/* 구분선 */
div[data-testid="stTabs"] hr{
    border-color:rgba(255,255,255,.42) !important;
    margin:2rem 0 !important;
}





/* 탭 콘텐츠 영역만 큰 반투명 카드로 처리 */
/* 주의: Schedule/Billing/Forecast 탭 버튼 바는 건드리지 않음 */
div[data-testid="stTabs"] div[role="tabpanel"]{
    background:rgba(242,236,224,.88) !important;
    border:1px solid rgba(255,255,255,.72) !important;
    border-radius:30px !important;
    box-shadow:0 24px 64px rgba(0,0,0,.20) !important;
    backdrop-filter:blur(20px) !important;
    -webkit-backdrop-filter:blur(20px) !important;
    padding:28px 30px 34px !important;
    margin-top:22px !important;
    color:#202124 !important;
    overflow:visible !important;
}

/* 큰 카드 안에서는 제목/설명 글씨를 검정 계열로 고정 */
div[data-testid="stTabs"] div[role="tabpanel"] .section-lbl{
    color:#202124 !important;
    text-shadow:none !important;
    font-size:26px !important;
    font-weight:900 !important;
    margin:1.1rem 0 1rem !important;
    letter-spacing:-.045em !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] label,
div[data-testid="stTabs"] div[role="tabpanel"] label p,
div[data-testid="stTabs"] div[role="tabpanel"] p,
div[data-testid="stTabs"] div[role="tabpanel"] span,
div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stMarkdownContainer"]{
    color:#202124 !important;
    font-weight:700 !important;
}

/* 설명/캡션 */
div[data-testid="stTabs"] div[role="tabpanel"] [data-testid="stCaptionContainer"],
div[data-testid="stTabs"] div[role="tabpanel"] [data-testid="stCaptionContainer"] p{
    color:#3f4852 !important;
    font-size:14px !important;
    font-weight:720 !important;
    text-shadow:none !important;
}

/* 생활패턴 expander는 큰 카드 안의 내부 카드처럼 */
div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stExpander"]{
    background:rgba(255,255,255,.28) !important;
    border:1px solid rgba(255,255,255,.48) !important;
    border-radius:24px !important;
    box-shadow:none !important;
    backdrop-filter:blur(8px) !important;
    -webkit-backdrop-filter:blur(8px) !important;
    overflow:hidden !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stExpander"] summary,
div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stExpander"] summary p,
div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stExpander"] summary span{
    color:#202124 !important;
    font-size:16px !important;
    font-weight:850 !important;
}

/* 입력창 / 선택창 */
div[data-testid="stTabs"] div[role="tabpanel"] input,
div[data-testid="stTabs"] div[role="tabpanel"] textarea{
    color:#202124 !important;
    font-size:15px !important;
    font-weight:760 !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] div[data-baseweb="input"],
div[data-testid="stTabs"] div[role="tabpanel"] div[data-baseweb="select"] > div{
    background:rgba(255,255,255,.94) !important;
    border:1px solid rgba(32,33,36,.18) !important;
    border-radius:15px !important;
    box-shadow:0 8px 20px rgba(0,0,0,.07) !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] div[data-baseweb="select"] span,
div[data-testid="stTabs"] div[role="tabpanel"] div[data-baseweb="select"] input{
    color:#202124 !important;
    font-weight:760 !important;
}

/* number input의 +, - 버튼 */
div[data-testid="stTabs"] div[role="tabpanel"] button[aria-label="Increment"],
div[data-testid="stTabs"] div[role="tabpanel"] button[aria-label="Decrement"]{
    color:#202124 !important;
    background:rgba(255,255,255,.70) !important;
}

/* 체크박스/토글 */
div[data-testid="stTabs"] div[role="tabpanel"] [data-testid="stCheckbox"] label p,
div[data-testid="stTabs"] div[role="tabpanel"] [data-testid="stToggle"] label p{
    color:#202124 !important;
    font-size:15px !important;
    font-weight:780 !important;
}

/* 버튼 */
div[data-testid="stTabs"] div[role="tabpanel"] .stButton > button{
    background:rgba(255,255,255,.94) !important;
    color:#202124 !important;
    font-size:15px !important;
    font-weight:820 !important;
    border-radius:17px !important;
    border:1px solid rgba(32,33,36,.18) !important;
    min-height:50px !important;
    box-shadow:0 10px 24px rgba(0,0,0,.09) !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] .stButton > button:hover{
    background:#FFE476 !important;
    color:#202124 !important;
    border-color:rgba(255,228,118,.95) !important;
}

/* DR 이벤트 알림/요약 카드는 내부 강조 카드 */
div[data-testid="stTabs"] div[role="tabpanel"] .dr-alert-card,
div[data-testid="stTabs"] div[role="tabpanel"] .dr-summary-card{
    background:rgba(255,255,255,.32) !important;
    border:1px solid rgba(255,255,255,.52) !important;
    border-radius:24px !important;
    box-shadow:none !important;
    color:#202124 !important;
    padding:20px 22px !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] .dr-alert-title{
    color:#202124 !important;
    font-size:20px !important;
    font-weight:900 !important;
}

div[data-testid="stTabs"] div[role="tabpanel"] .dr-alert-desc,
div[data-testid="stTabs"] div[role="tabpanel"] .dr-summary-text{
    color:#2f3740 !important;
    font-size:15px !important;
    line-height:1.6 !important;
    font-weight:720 !important;
}

/* 정보 박스 */
div[data-testid="stTabs"] div[role="tabpanel"] div[data-testid="stAlert"]{
    background:rgba(255,255,255,.34) !important;
    color:#202124 !important;
    border-radius:20px !important;
    border:1px solid rgba(255,255,255,.56) !important;
}

/* 구분선은 카드 내부에서 은은하게 */
div[data-testid="stTabs"] div[role="tabpanel"] hr{
    border-color:rgba(32,33,36,.14) !important;
    margin:2rem 0 !important;
}
/* 탭 버튼 글씨 최종 보정 */
div[data-testid="stTabs"] > div[role="tablist"] button[data-baseweb="tab"] p{
    color:rgba(255,255,255,.92) !important;
    font-weight:850 !important;
    font-size:16px !important;
    text-shadow:0 2px 8px rgba(0,0,0,.45) !important;
}

div[data-testid="stTabs"] > div[role="tablist"] button[data-baseweb="tab"][aria-selected="true"] p{
    color:#FFE476 !important;
    font-weight:900 !important;
}

/* Schedule 결과 UI v3: 레퍼런스 기반 클린 타임트래커 */
.schedule-result-panel{
    margin-top:18px;
    padding:24px 24px 26px;
    border-radius:32px;
    background:
        radial-gradient(circle at 92% 8%, rgba(255,228,118,.22), transparent 34%),
        rgba(242,236,224,.72);
    border:1px solid rgba(255,255,255,.68);
    box-shadow:0 24px 64px rgba(0,0,0,.16);
    color:#202124;
}
.schedule-result-head{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:18px;
    margin-bottom:20px;
}
.schedule-result-title{
    font-size:28px;
    font-weight:900;
    letter-spacing:-.055em;
    color:#202124;
    margin-bottom:8px;
}
.schedule-result-sub{
    font-size:14px;
    line-height:1.55;
    color:#3f4852;
    font-weight:680;
    word-break:keep-all;
}
.schedule-result-kpis{
    display:grid;
    grid-template-columns:repeat(3, minmax(120px,1fr));
    gap:10px;
    min-width:430px;
}
.schedule-result-kpi{
    padding:14px 15px;
    border-radius:22px;
    background:rgba(255,255,255,.44);
    border:1px solid rgba(255,255,255,.62);
}
.schedule-result-kpi-label{
    font-size:11px;
    font-weight:760;
    color:#5b6570;
    margin-bottom:8px;
}
.schedule-result-kpi-value{
    font-size:21px;
    line-height:1;
    font-weight:900;
    color:#202124;
    letter-spacing:-.04em;
}
.schedule-result-kpi-value.yellow{color:#d6a800;}

.smart-schedule-board{
    border-radius:28px;
    background:rgba(255,255,255,.26);
    border:1px solid rgba(255,255,255,.58);
    overflow:hidden;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.50);
}
.smart-schedule-hours{
    display:grid;
    grid-template-columns:168px repeat(24, minmax(28px,1fr));
    background:rgba(255,255,255,.34);
    border-bottom:1px solid rgba(32,33,36,.10);
}
.smart-schedule-corner{
    padding:13px 14px;
    font-size:12px;
    color:#4d5661;
    font-weight:850;
    border-right:1px solid rgba(32,33,36,.10);
}
.smart-hour-cell{
    min-height:44px;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:10px;
    color:#65707a;
    font-weight:800;
    border-right:1px dashed rgba(32,33,36,.085);
}
.smart-hour-cell.dr{
    background:rgba(120,185,145,.30) !important;
    color:#202124;
}
.smart-schedule-row{
    display:grid;
    grid-template-columns:168px 1fr;
    min-height:74px;
    border-bottom:1px solid rgba(32,33,36,.08);
}
.smart-schedule-row:last-child{border-bottom:none;}
.smart-device-label{
    padding:15px 14px;
    border-right:1px solid rgba(32,33,36,.10);
    display:flex;
    flex-direction:column;
    justify-content:center;
    gap:5px;
}
.smart-device-name{
    font-size:15px;
    font-weight:900;
    color:#202124;
    letter-spacing:-.04em;
}
.smart-device-meta{
    font-size:11px;
    font-weight:720;
    color:#5d6670;
}
.smart-track{
    position:relative;
    display:grid;
    grid-template-columns:repeat(24, minmax(28px,1fr));
    min-height:74px;
    overflow:visible;
}
.smart-track-bg{
    border-right:1px dashed rgba(32,33,36,.075);
    min-height:74px;
}
.smart-track-bg.dr{
    background:
      repeating-linear-gradient(135deg, rgba(70,78,88,.105) 0 6px, rgba(70,78,88,.035) 6px 12px);
}
.smart-event{
    align-self:center;
    margin:10px 4px;
    min-height:48px;
    min-width:96px;
    border-radius:18px;
    background:linear-gradient(135deg, rgba(255,228,118,.98), rgba(255,237,150,.94));
    border:1px solid rgba(255,255,255,.82);
    box-shadow:0 13px 28px rgba(0,0,0,.14);
    display:flex;
    flex-direction:column;
    justify-content:center;
    padding:9px 12px;
    overflow:visible;
    z-index:3;
}
.smart-event.high{
    background:linear-gradient(135deg, rgba(255,228,118,.98), rgba(255,203,94,.94));
}
.smart-event.air{
    background:linear-gradient(135deg, rgba(36,42,52,.96), rgba(68,74,84,.92));
    border-color:rgba(255,255,255,.20);
}
.smart-event.direct{
    background:linear-gradient(135deg, rgba(255,255,255,.92), rgba(235,238,242,.90));
}
.smart-event-name{
    font-size:12.2px;
    font-weight:930;
    color:#202124;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.smart-event.air .smart-event-name,
.smart-event.air .smart-event-time{color:#ffffff;}
.smart-event-time{
    margin-top:4px;
    font-size:10.7px;
    font-weight:820;
    color:#3f4852;
    white-space:nowrap;
}
.smart-schedule-legend{
    display:flex;
    gap:14px;
    align-items:center;
    flex-wrap:wrap;
    padding:13px 14px 0;
    font-size:12px;
    color:#4d5661;
    font-weight:740;
}
.legend-dot{
    width:10px;
    height:10px;
    border-radius:999px;
    display:inline-block;
    margin-right:6px;
    vertical-align:-1px;
    background:#FFE476;
}
.legend-dot.dr{
    background:rgba(120,185,145,.80);
    border-radius:999px;
}

.result-card-grid{
    margin-top:18px;
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:14px;
}
.result-mini-card{
    padding:18px 18px;
    border-radius:24px;
    background:rgba(255,255,255,.36);
    border:1px solid rgba(255,255,255,.56);
}
.result-mini-label{
    font-size:12px;
    font-weight:760;
    color:#5a6470;
    margin-bottom:9px;
}
.result-mini-value{
    font-size:25px;
    font-weight:900;
    color:#202124;
    letter-spacing:-.05em;
}
.result-mini-note{
    margin-top:9px;
    font-size:12px;
    font-weight:680;
    color:#4a535d;
    line-height:1.4;
}
.top3-grid.v2{
    margin-top:14px;
    display:grid;
    grid-template-columns:repeat(3,1fr);
    gap:14px;
}
.top3-grid.v2 .top3-card{
    background:rgba(255,255,255,.38);
    border:1px solid rgba(255,255,255,.58);
    border-radius:24px;
    padding:18px 18px;
    color:#202124;
    box-shadow:none;
}
.top3-grid.v2 .top3-card.primary{
    background:rgba(255,228,118,.32);
}
.schedule-chip{
    display:inline-flex;
    padding:5px 10px;
    border-radius:999px;
    background:rgba(255,228,118,.76);
    font-size:11px;
    font-weight:850;
    color:#202124;
    margin-bottom:12px;
}
.schedule-time{
    font-size:24px;
    font-weight:900;
    letter-spacing:-.045em;
    color:#202124;
}
.schedule-meta{
    margin-top:8px;
    font-size:13px;
    font-weight:760;
    color:#3f4852;
}
.schedule-note{
    margin-top:8px;
    font-size:12px;
    line-height:1.45;
    font-weight:680;
    color:#5b6570;
}
.schedule-detail-grid{
    margin-top:14px;
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:14px;
}
.schedule-detail-card{
    padding:17px 18px;
    border-radius:22px;
    background:rgba(255,255,255,.34);
    border:1px solid rgba(255,255,255,.56);
}
.schedule-detail-top{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:10px;
    margin-bottom:9px;
}
.schedule-detail-name{
    font-size:16px;
    font-weight:900;
    color:#202124;
}
.schedule-detail-tag{
    padding:5px 10px;
    border-radius:999px;
    background:rgba(255,228,118,.72);
    color:#202124;
    font-size:11px;
    font-weight:820;
    white-space:nowrap;
}
.schedule-detail-time{
    font-size:18px;
    font-weight:900;
    letter-spacing:-.035em;
    color:#202124;
    margin-bottom:8px;
}
.schedule-detail-desc{
    font-size:12.5px;
    line-height:1.55;
    font-weight:680;
    color:#4d5661;
    word-break:keep-all;
}
@media(max-width:900px){
    .schedule-result-head{display:block;}
    .schedule-result-kpis{min-width:0;grid-template-columns:1fr;margin-top:14px;}
    .smart-schedule-hours{grid-template-columns:92px repeat(24, minmax(18px,1fr));}
    .smart-schedule-row{grid-template-columns:92px 1fr;}
    .smart-device-name{font-size:12px;}
    .smart-device-meta{font-size:10px;}
    .smart-hour-cell{font-size:8px;}
    .top3-grid.v2,.result-card-grid,.schedule-detail-grid{grid-template-columns:1fr;}
}


/* Schedule table compact fix: 한눈에 보이도록 행 높이 축소 + DR 시간대 통일 */
.smart-schedule-board{
    border-radius:24px !important;
}

.smart-schedule-hours{
    grid-template-columns:148px repeat(24, minmax(24px,1fr)) !important;
}

.smart-schedule-corner{
    padding:10px 12px !important;
    font-size:11.5px !important;
}

.smart-hour-cell{
    min-height:34px !important;
    font-size:9.5px !important;
}

.smart-hour-cell.dr{
    background:
      repeating-linear-gradient(135deg, rgba(70,78,88,.13) 0 5px, rgba(70,78,88,.04) 5px 10px) !important;
}

.smart-schedule-row{
    grid-template-columns:148px 1fr !important;
    min-height:48px !important;
}

.smart-device-label{
    padding:10px 12px !important;
    gap:3px !important;
}

.smart-device-name{
    font-size:13.5px !important;
}

.smart-device-meta{
    font-size:10.2px !important;
}

.smart-track{
    grid-template-columns:repeat(24, minmax(24px,1fr)) !important;
    min-height:48px !important;
    overflow:visible !important;
}

.smart-track-bg{
    min-height:48px !important;
}

.smart-track-bg.dr{
    background:transparent !important;
}

.smart-dr-window{
    align-self:stretch;
    margin:0 !important;
    min-height:48px;
    height:100%;
    background:rgba(120,185,145,.24);
    border-left:1px solid rgba(75,145,105,.20);
    border-right:1px solid rgba(75,145,105,.20);
    z-index:1;
    pointer-events:none;
}

.smart-event{
    min-height:32px !important;
    min-width:82px !important;
    margin:9px 4px !important;
    border-radius:16px !important;
    padding:7px 10px !important;
    z-index:3 !important;
}

.smart-event-name{
    font-size:11.2px !important;
    max-width:100%;
}

.smart-event-time{
    font-size:9.7px !important;
    margin-top:3px !important;
}

.smart-schedule-legend{
    padding:10px 12px 0 !important;
    font-size:11.5px !important;
}

@media(max-width:1200px){
    .smart-schedule-hours{
        grid-template-columns:130px repeat(24, minmax(22px,1fr)) !important;
    }
    .smart-schedule-row{
        grid-template-columns:130px 1fr !important;
    }
}


/* Schedule table final clean fix: compact + green DR full fill */
.schedule-result-panel{
    padding:22px 22px 24px !important;
    border-radius:30px !important;
}

.schedule-result-head{
    margin-bottom:18px !important;
}

.smart-schedule-board{
    border-radius:24px !important;
    overflow:hidden !important;
    background:rgba(255,255,255,.28) !important;
}

.smart-schedule-hours{
    grid-template-columns:142px repeat(24, minmax(23px,1fr)) !important;
    background:rgba(255,255,255,.36) !important;
}

.smart-schedule-corner{
    padding:9px 11px !important;
    font-size:11.2px !important;
}

.smart-hour-cell{
    min-height:32px !important;
    font-size:9.2px !important;
    border-right:1px dashed rgba(32,33,36,.075) !important;
}

/* DR 시간대 헤더: 초록색으로 통일 */
.smart-hour-cell.dr{
    background:rgba(120,185,145,.30) !important;
    color:#202124 !important;
    font-weight:850 !important;
}

/* 행 높이 축소 */
.smart-schedule-row{
    grid-template-columns:142px 1fr !important;
    min-height:44px !important;
    border-bottom:1px solid rgba(32,33,36,.075) !important;
}

.smart-device-label{
    padding:7px 11px !important;
    gap:2px !important;
}

.smart-device-name{
    font-size:13px !important;
    line-height:1.15 !important;
}

.smart-device-meta{
    font-size:9.6px !important;
    line-height:1.15 !important;
}

.smart-track{
    grid-template-columns:repeat(24, minmax(23px,1fr)) !important;
    min-height:44px !important;
    overflow:visible !important;
}

.smart-track-bg{
    min-height:44px !important;
    border-right:1px dashed rgba(32,33,36,.065) !important;
}

/* 기존 사선 DR 배경 완전 제거 */
.smart-track-bg.dr{
    background:transparent !important;
}

/* DR 시간대: 각 행의 16~19시 칸 전체를 초록색으로 꽉 채움 */
.smart-dr-window{
    align-self:stretch !important;
    height:100% !important;
    min-height:44px !important;
    margin:0 !important;
    background:rgba(120,185,145,.22) !important;
    border-left:1px solid rgba(75,145,105,.18) !important;
    border-right:1px solid rgba(75,145,105,.18) !important;
    z-index:1 !important;
    pointer-events:none !important;
}

/* 추천 사용 블록: 행 높이에 맞게 축소 */
.smart-event{
    min-height:30px !important;
    min-width:78px !important;
    margin:7px 4px !important;
    border-radius:14px !important;
    padding:5px 8px !important;
    z-index:3 !important;
}

.smart-event-name{
    font-size:10.7px !important;
    line-height:1.1 !important;
}

.smart-event-time{
    font-size:9px !important;
    margin-top:2px !important;
    line-height:1.1 !important;
}

/* 범례 */
.smart-schedule-legend{
    padding:9px 11px 0 !important;
    font-size:11.2px !important;
    gap:12px !important;
}

.legend-dot.dr{
    background:rgba(120,185,145,.85) !important;
    border-radius:999px !important;
}

@media(max-width:1200px){
    .smart-schedule-hours{
        grid-template-columns:126px repeat(24, minmax(21px,1fr)) !important;
    }
    .smart-schedule-row{
        grid-template-columns:126px 1fr !important;
    }
}
/* DR 시간대 높이/색상 최종 보정 */
.smart-schedule-row{
    min-height:46px !important;
    height:46px !important;
}

.smart-track{
    min-height:50px !important;
    height:50px !important;
    align-items:stretch !important;
}

.smart-track-bg{
    min-height:50px !important;
    height:50px !important;
}

.smart-dr-window{
    align-self:stretch !important;
    height:100% !important;
    min-height:50px !important;
    margin:0 !important;
    background:rgba(120,185,145,.14) !important;
    border-left:1px solid rgba(75,145,105,.12) !important;
    border-right:1px solid rgba(75,145,105,.12) !important;
    z-index:1 !important;
    pointer-events:none !important;
}

.smart-hour-cell.dr{
    background:rgba(120,185,145,.18) !important;
    color:#202124 !important;
}




/* Schedule result lower section cleanup */
.schedule-result-head.clean{
    display:block !important;
    margin-bottom:16px !important;
}

.schedule-result-kpis{
    display:none !important;
}

.saving-summary-card{
    margin:18px 0 22px;
    padding:20px 22px;
    border-radius:26px;
    background:rgba(255,255,255,.36);
    border:1px solid rgba(255,255,255,.60);
    box-shadow:0 14px 34px rgba(0,0,0,.08);
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:18px;
    color:#202124;
}

.saving-summary-label{
    font-size:13px;
    font-weight:850;
    color:#5b6570;
    margin-bottom:9px;
}

.saving-summary-main{
    font-size:23px;
    line-height:1.2;
    font-weight:850;
    letter-spacing:-.045em;
    color:#202124;
}

.saving-summary-main strong{
    font-size:28px;
    font-weight:930;
    color:#202124;
}

.saving-arrow{
    display:inline-flex;
    margin:0 10px;
    color:#7b838c;
    font-weight:850;
}

.saving-summary-sub{
    margin-top:9px;
    font-size:12.5px;
    font-weight:720;
    color:#5f6873;
}

.saving-summary-right{
    min-width:180px;
    padding:14px 18px;
    border-radius:22px;
    background:rgba(255,228,118,.28);
    border:1px solid rgba(255,255,255,.56);
    text-align:right;
}

.saving-summary-chip{
    display:inline-flex;
    padding:5px 10px;
    border-radius:999px;
    background:rgba(255,228,118,.84);
    color:#202124;
    font-size:11px;
    font-weight:850;
    margin-bottom:8px;
}

.saving-summary-save{
    font-size:30px;
    font-weight:930;
    letter-spacing:-.055em;
    color:#d6a800;
    line-height:1;
}

.saving-summary-rate{
    margin-top:8px;
    font-size:12px;
    color:#4d5661;
    font-weight:760;
}

.reason-title{
    margin-top:1.1rem !important;
}

.reason-card-grid{
    display:grid;
    grid-template-columns:repeat(2, minmax(0, 1fr));
    gap:12px;
    margin-top:12px;
}

.reason-card{
    position:relative;
    padding:16px 18px;
    border-radius:22px;
    background:rgba(255,255,255,.34);
    border:1px solid rgba(255,255,255,.58);
    color:#202124;
    min-height:138px;
    box-shadow:0 10px 24px rgba(0,0,0,.06);
}

.reason-card-main{
    display:flex;
    justify-content:space-between;
    align-items:flex-start;
    gap:12px;
    margin-bottom:10px;
}

.reason-device{
    font-size:18px;
    font-weight:920;
    letter-spacing:-.045em;
    color:#202124;
}

.reason-time{
    font-size:15px;
    font-weight:900;
    color:#202124;
    white-space:nowrap;
}

.reason-metrics{
    display:flex;
    gap:8px;
    flex-wrap:wrap;
    margin-bottom:9px;
}

.reason-metrics span{
    display:inline-flex;
    padding:5px 9px;
    border-radius:999px;
    background:rgba(255,255,255,.45);
    border:1px solid rgba(255,255,255,.55);
    color:#3f4852 !important;
    font-size:12px;
    font-weight:800;
}

.reason-desc{
    max-width:calc(100% - 86px);
    color:#4d5661 !important;
    font-size:12.5px;
    line-height:1.45;
    font-weight:720;
    word-break:keep-all;
}

.reason-tag{
    position:absolute;
    right:16px;
    bottom:15px;
    padding:6px 11px;
    border-radius:999px;
    background:rgba(255,228,118,.76);
    color:#202124;
    font-size:11px;
    font-weight:850;
    white-space:nowrap;
}

.top3-grid.v2{
    display:none !important;
}

.schedule-detail-grid{
    display:none !important;
}

@media(max-width:900px){
    .saving-summary-card{
        display:block;
    }
    .saving-summary-right{
        margin-top:14px;
        text-align:left;
        min-width:0;
    }
    .reason-card-grid{
        grid-template-columns:1fr;
    }
    .reason-desc{
        max-width:100%;
    }
    .reason-tag{
        position:static;
        margin-top:10px;
        width:max-content;
    }
}


/* Schedule final layout: larger readable table + action row */
.smart-schedule-hours{
    grid-template-columns:152px repeat(24, minmax(24px,1fr)) !important;
}

.smart-hour-cell{
    min-height:36px !important;
    font-size:10px !important;
    font-weight:830 !important;
}

.smart-schedule-row{
    grid-template-columns:152px 1fr !important;
    min-height:58px !important;
    height:58px !important;
}

.smart-track{
    grid-template-columns:repeat(24, minmax(24px,1fr)) !important;
    min-height:58px !important;
    height:58px !important;
    align-items:stretch !important;
}

.smart-track-bg{
    min-height:58px !important;
    height:58px !important;
}

.smart-dr-window{
    min-height:58px !important;
    height:100% !important;
    background:rgba(120,185,145,.11) !important;
    border-left:1px solid rgba(75,145,105,.09) !important;
    border-right:1px solid rgba(75,145,105,.09) !important;
}

.smart-hour-cell.dr{
    background:rgba(120,185,145,.15) !important;
}

.smart-device-label{
    padding:9px 13px !important;
    gap:4px !important;
}

.smart-device-name{
    font-size:14.5px !important;
    line-height:1.2 !important;
}

.smart-device-meta{
    font-size:10.8px !important;
    line-height:1.2 !important;
}

.smart-event{
    min-height:38px !important;
    min-width:88px !important;
    margin:10px 5px !important;
    border-radius:16px !important;
    padding:7px 10px !important;
}

.smart-event-name{
    font-size:11.8px !important;
    line-height:1.14 !important;
}

.smart-event-time{
    font-size:10px !important;
    line-height:1.14 !important;
}

/* 최적 시간 계산 / 전체 초기화 버튼을 같은 선상에서 자연스럽게 */
div[data-testid="stTabs"] div[role="tabpanel"] .stButton > button{
    min-height:52px !important;
}

@media(max-width:1200px){
    .smart-schedule-hours{
        grid-template-columns:138px repeat(24, minmax(22px,1fr)) !important;
    }
    .smart-schedule-row{
        grid-template-columns:138px 1fr !important;
    }
}
/* 절감 요약 카드 가시성 강화 */
.saving-summary-card{
    margin:22px 0 26px !important;
    padding:24px 28px !important;
    border-radius:30px !important;
    background:
        radial-gradient(circle at 72% 28%, rgba(255,228,118,.20), transparent 34%),
        rgba(255,255,255,.34) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 18px 46px rgba(0,0,0,.10) !important;

    display:grid !important;
    grid-template-columns:minmax(520px, 680px) 230px !important;
    justify-content:center !important;
    align-items:center !important;
    gap:42px !important;
}

.saving-summary-label{
    font-size:14px !important;
    font-weight:900 !important;
    color:#4d5661 !important;
    margin-bottom:12px !important;
}

.saving-summary-main{
    font-size:28px !important;
    line-height:1.15 !important;
    font-weight:900 !important;
    color:#202124 !important;
    letter-spacing:-.055em !important;
}

.saving-summary-main strong{
    font-size:34px !important;
    font-weight:950 !important;
    color:#202124 !important;
}

.saving-arrow{
    margin:0 14px !important;
    font-size:28px !important;
    color:#202124 !important;
    opacity:.72 !important;
}

.saving-summary-sub{
    margin-top:14px !important;
    font-size:14px !important;
    font-weight:780 !important;
    color:#4d5661 !important;
}

.saving-summary-right{
    min-width:0 !important;
    padding:20px 22px !important;
    border-radius:26px !important;
    background:rgba(255,228,118,.34) !important;
    border:1px solid rgba(255,255,255,.72) !important;
    text-align:center !important;
    box-shadow:0 14px 34px rgba(214,168,0,.12) !important;
}

.saving-summary-chip{
    padding:6px 13px !important;
    font-size:12px !important;
    font-weight:900 !important;
    background:rgba(255,228,118,.92) !important;
    margin-bottom:12px !important;
}

.saving-summary-save{
    font-size:38px !important;
    font-weight:960 !important;
    color:#d6a800 !important;
    letter-spacing:-.06em !important;
}

.saving-summary-rate{
    margin-top:10px !important;
    font-size:13px !important;
    font-weight:850 !important;
    color:#4d5661 !important;
}
/* DR 이벤트 토글 ON 색상 강제 변경 */
div[data-testid="stToggle"] div[role="switch"][aria-checked="true"]{
    background-color:rgba(255,228,118,.90) !important;
    border-color:rgba(255,228,118,.95) !important;
}

/* OFF 상태 */
div[data-testid="stToggle"] div[role="switch"][aria-checked="false"]{
    background-color:rgba(255,255,255,.45) !important;
    border-color:rgba(32,33,36,.18) !important;
}

/* 토글 손잡이 */
div[data-testid="stToggle"] div[role="switch"] > div{
    background-color:#ffffff !important;
    box-shadow:0 2px 8px rgba(0,0,0,.18) !important;
}





/* Billing 탭 상단 리포트 UI v4: Streamlit HTML 안전 렌더링 + 컴팩트 가독성 */
.billing-report-head{
    margin:2px 0 14px !important;
    padding:24px 30px !important;
    border-radius:28px !important;
    background:radial-gradient(circle at 92% 10%, rgba(255,228,118,.07), transparent 38%), rgba(255,255,255,.42) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 14px 34px rgba(0,0,0,.06) !important;
    color:#202124 !important;
}
.billing-report-title{
    font-size:34px !important;
    line-height:1.08 !important;
    font-weight:960 !important;
    letter-spacing:-.065em !important;
    color:#202124 !important;
    margin-bottom:12px !important;
}
.billing-report-desc{
    font-size:14.5px !important;
    line-height:1.58 !important;
    font-weight:740 !important;
    color:#4d5661 !important;
    word-break:keep-all !important;
}
.billing-mode-note{
    margin:0 0 12px !important;
    font-size:13.2px !important;
    font-weight:780 !important;
    color:#4d5661 !important;
}
.billing-overview-grid{
    display:grid !important;
    grid-template-columns:minmax(500px,1.25fr) minmax(210px,.42fr) minmax(390px,.74fr) !important;
    gap:12px !important;
    align-items:stretch !important;
    margin:12px 0 12px !important;
}
.billing-bill-card{
    min-height:188px !important;
    padding:24px 28px !important;
    border-radius:26px !important;
    background:radial-gradient(circle at 92% 8%, rgba(255,228,118,.07), transparent 38%), rgba(255,255,255,.48) !important;
    border:1px solid rgba(255,255,255,.70) !important;
    box-shadow:0 14px 32px rgba(0,0,0,.065) !important;
    color:#202124 !important;
    display:grid !important;
    grid-template-columns:minmax(0,1fr) 1px 220px !important;
    gap:24px !important;
    align-items:center !important;
}
.billing-card-label{
    font-size:16px !important;
    font-weight:940 !important;
    color:#202124 !important;
    margin-bottom:13px !important;
    letter-spacing:-.035em !important;
}
.billing-bill-value{
    font-size:50px !important;
    line-height:.92 !important;
    font-weight:980 !important;
    letter-spacing:-.08em !important;
    color:#202124 !important;
    margin-bottom:18px !important;
}
.billing-card-sub{
    font-size:14.5px !important;
    line-height:1.45 !important;
    font-weight:800 !important;
    color:#3f4852 !important;
    word-break:keep-all !important;
}
.billing-divider{
    width:1px !important;
    height:128px !important;
    background:rgba(32,33,36,.13) !important;
}
.billing-save-title{
    font-size:13.5px !important;
    font-weight:920 !important;
    color:#4d5661 !important;
    margin-bottom:12px !important;
}
.billing-save-value{
    font-size:40px !important;
    line-height:1 !important;
    font-weight:980 !important;
    letter-spacing:-.065em !important;
    color:#202124 !important;
    margin-bottom:12px !important;
}
.billing-save-value.good{color:#d6a800 !important;}
.billing-save-pill{
    display:inline-flex !important;
    padding:8px 17px !important;
    border-radius:999px !important;
    background:rgba(255,228,118,.30) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    font-size:14px !important;
    font-weight:900 !important;
    color:#202124 !important;
}
.billing-side-stack{
    display:grid !important;
    grid-template-rows:1fr 1fr !important;
    gap:12px !important;
}
.billing-side-card{
    padding:18px 20px !important;
    border-radius:22px !important;
    background:rgba(255,255,255,.46) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 10px 24px rgba(0,0,0,.055) !important;
    color:#202124 !important;
}
.billing-side-card.soft{
    background:rgba(255,228,118,.14) !important;
}
.billing-side-label{
    font-size:13px !important;
    font-weight:920 !important;
    color:#4d5661 !important;
    margin-bottom:10px !important;
}
.billing-side-value{
    font-size:34px !important;
    line-height:1 !important;
    font-weight:980 !important;
    letter-spacing:-.06em !important;
    color:#202124 !important;
    margin-bottom:10px !important;
}
.billing-side-value span{
    font-size:18px !important;
    font-weight:880 !important;
    letter-spacing:-.025em !important;
    margin-left:4px !important;
}
.billing-side-note{
    font-size:12.8px !important;
    line-height:1.45 !important;
    font-weight:760 !important;
    color:#4d5661 !important;
    word-break:keep-all !important;
}
.billing-chart-card{
    padding:18px 20px 16px !important;
    border-radius:22px !important;
    background:rgba(255,255,255,.46) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 10px 24px rgba(0,0,0,.055) !important;
    color:#202124 !important;
}
.billing-chart-head{
    display:flex !important;
    justify-content:space-between !important;
    align-items:center !important;
    gap:12px !important;
    margin-bottom:12px !important;
}
.billing-chart-title{
    font-size:15.5px !important;
    font-weight:940 !important;
    color:#202124 !important;
    letter-spacing:-.04em !important;
}
.billing-chart-legend{
    display:flex !important;
    gap:12px !important;
    align-items:center !important;
    font-size:11.5px !important;
    color:#4d5661 !important;
    font-weight:800 !important;
    white-space:nowrap !important;
}
.billing-legend-dot{
    width:9px !important;
    height:9px !important;
    border-radius:3px !important;
    display:inline-block !important;
    margin-right:4px !important;
    vertical-align:-1px !important;
}
.billing-legend-dot.gray{background:rgba(32,33,36,.20) !important;}
.billing-legend-dot.yellow{background:rgba(255,188,56,.78) !important;}
.billing-bar-area{
    height:132px !important;
    display:grid !important;
    grid-template-columns:repeat(6,1fr) !important;
    gap:10px !important;
    align-items:end !important;
    padding:6px 4px 0 !important;
    border-bottom:1px solid rgba(32,33,36,.10) !important;
}
.billing-bar-group{
    height:100% !important;
    display:flex !important;
    align-items:flex-end !important;
    justify-content:center !important;
    gap:5px !important;
    position:relative !important;
}
.billing-bar{
    width:16px !important;
    min-height:8px !important;
    border-radius:7px 7px 0 0 !important;
    position:relative !important;
}
.billing-bar.gray{background:rgba(32,33,36,.16) !important;}
.billing-bar.yellow{background:linear-gradient(180deg, rgba(255,199,78,.80), rgba(255,228,118,.40)) !important;}
.billing-bar.current{background:linear-gradient(180deg, rgba(255,188,56,.92), rgba(255,228,118,.54)) !important;}
.billing-bar-value{
    position:absolute !important;
    top:-18px !important;
    left:50% !important;
    transform:translateX(-50%) !important;
    font-size:9.5px !important;
    font-weight:860 !important;
    color:#4d5661 !important;
    white-space:nowrap !important;
}
.billing-month-row{
    display:grid !important;
    grid-template-columns:repeat(6,1fr) !important;
    gap:10px !important;
    padding:8px 4px 0 !important;
    font-size:11px !important;
    font-weight:820 !important;
    color:#4d5661 !important;
    text-align:center !important;
}
.billing-lower-grid{
    display:grid !important;
    grid-template-columns:minmax(0,2.04fr) minmax(300px,.82fr) !important;
    gap:12px !important;
    margin:12px 0 16px !important;
    align-items:stretch !important;
}
.billing-compare-wrap{
    padding:18px !important;
    border-radius:24px !important;
    background:rgba(255,255,255,.36) !important;
    border:1px solid rgba(255,255,255,.64) !important;
    box-shadow:0 12px 28px rgba(0,0,0,.055) !important;
}
.billing-section-title{
    display:flex !important;
    align-items:baseline !important;
    gap:12px !important;
    font-size:18px !important;
    font-weight:960 !important;
    letter-spacing:-.05em !important;
    color:#202124 !important;
    margin-bottom:14px !important;
}
.billing-section-title span{
    font-size:12px !important;
    font-weight:800 !important;
    color:#6b747e !important;
    letter-spacing:-.02em !important;
}
.billing-compare-grid{
    display:grid !important;
    grid-template-columns:repeat(3,1fr) !important;
    gap:12px !important;
}
.billing-plan-card{
    padding:18px 18px !important;
    min-height:146px !important;
    border-radius:20px !important;
    background:rgba(255,255,255,.50) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    color:#202124 !important;
}
.billing-plan-card.recommend{
    background:rgba(255,228,118,.13) !important;
    border-color:rgba(255,188,56,.54) !important;
}
.billing-plan-label{
    font-size:13.2px !important;
    font-weight:930 !important;
    color:#4d5661 !important;
    margin-bottom:12px !important;
}
.billing-plan-value{
    font-size:31px !important;
    line-height:1 !important;
    font-weight:980 !important;
    letter-spacing:-.065em !important;
    color:#202124 !important;
    margin-bottom:12px !important;
}
.billing-plan-sub{
    font-size:12.6px !important;
    line-height:1.45 !important;
    font-weight:760 !important;
    color:#4d5661 !important;
    word-break:keep-all !important;
}
.billing-plan-chip{
    display:inline-flex !important;
    margin-top:13px !important;
    padding:7px 12px !important;
    border-radius:999px !important;
    background:rgba(255,255,255,.56) !important;
    color:#4d5661 !important;
    font-size:11.8px !important;
    font-weight:880 !important;
}
.billing-plan-chip.good{
    color:#1673d1 !important;
    background:rgba(55,138,221,.10) !important;
}
.billing-plan-chip.best{
    color:#d68100 !important;
    background:rgba(255,188,56,.16) !important;
}
.billing-point-card{
    padding:20px 22px !important;
    border-radius:24px !important;
    background:rgba(255,255,255,.40) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 12px 28px rgba(0,0,0,.055) !important;
    color:#202124 !important;
}
.billing-point-title{
    font-size:18px !important;
    font-weight:960 !important;
    letter-spacing:-.05em !important;
    color:#202124 !important;
    margin-bottom:16px !important;
}
.billing-point-list{
    display:grid !important;
    gap:12px !important;
    margin-bottom:20px !important;
}
.billing-point-item{
    display:flex !important;
    align-items:flex-start !important;
    gap:9px !important;
    font-size:13px !important;
    line-height:1.45 !important;
    font-weight:780 !important;
    color:#4d5661 !important;
}
.billing-point-check{
    width:18px !important;
    height:18px !important;
    border-radius:999px !important;
    flex:0 0 auto !important;
    display:inline-flex !important;
    align-items:center !important;
    justify-content:center !important;
    border:1.5px solid rgba(255,188,56,.82) !important;
    color:#d68100 !important;
    font-size:11px !important;
    font-weight:900 !important;
    margin-top:1px !important;
}
.billing-progress-box{
    padding:15px 17px !important;
    border-radius:18px !important;
    background:rgba(255,255,255,.42) !important;
    border:1px solid rgba(255,255,255,.62) !important;
}
.billing-progress-text{
    display:flex !important;
    justify-content:space-between !important;
    gap:10px !important;
    font-size:13px !important;
    font-weight:880 !important;
    color:#202124 !important;
    margin-bottom:12px !important;
}
.billing-progress-track{
    height:11px !important;
    border-radius:999px !important;
    background:rgba(32,33,36,.08) !important;
    overflow:hidden !important;
}
.billing-progress-fill{
    height:100% !important;
    border-radius:999px !important;
    background:linear-gradient(90deg, rgba(255,188,56,.86), rgba(255,228,118,.78)) !important;
}
div[role="tabpanel"] div[data-testid="stRadio"] label{
    padding:9px 14px !important;
    border-radius:999px !important;
    background:rgba(255,255,255,.42) !important;
    border:1px solid rgba(255,255,255,.64) !important;
    margin-right:8px !important;
}
div[role="tabpanel"] div[data-testid="stRadio"] label:has(input:checked){
    background:rgba(255,228,118,.66) !important;
    border-color:rgba(255,228,118,.82) !important;
}
@media(max-width:1200px){
    .billing-overview-grid,
    .billing-lower-grid{grid-template-columns:1fr !important;}
    .billing-bill-card{grid-template-columns:1.15fr 1px 1fr !important;}
    .billing-divider{display:none !important;}
}
@media(max-width:900px){
    .billing-compare-grid{grid-template-columns:1fr !important;}
    .billing-bill-value{font-size:48px !important;}
}


/* Simulator 탭: 최적화 적용 전후 비용 비교 v2 */
.sim-report-head{
    margin:4px 0 16px !important;
    padding:26px 30px !important;
    border-radius:30px !important;
    background:
        radial-gradient(circle at 92% 10%, rgba(255,228,118,.10), transparent 38%),
        rgba(255,255,255,.40) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 16px 38px rgba(0,0,0,.065) !important;
    color:#202124 !important;
}
.sim-report-title{
    font-size:34px !important;
    line-height:1.08 !important;
    font-weight:960 !important;
    letter-spacing:-.065em !important;
    color:#202124 !important;
    margin-bottom:12px !important;
}
.sim-report-desc{
    font-size:14.5px !important;
    line-height:1.58 !important;
    font-weight:740 !important;
    color:#4d5661 !important;
    word-break:keep-all !important;
}

/* 상단 결과 요약: 카드 4개 대신 전후 흐름형 */
.sim-flow-card{
    margin:14px 0 16px !important;
    padding:24px 26px !important;
    border-radius:30px !important;
    background:
        linear-gradient(135deg, rgba(255,255,255,.48), rgba(255,255,255,.28)),
        radial-gradient(circle at 72% 28%, rgba(255,228,118,.16), transparent 36%) !important;
    border:1px solid rgba(255,255,255,.70) !important;
    box-shadow:0 16px 36px rgba(0,0,0,.065) !important;
    color:#202124 !important;
}
.sim-flow-top{
    display:grid !important;
    grid-template-columns:minmax(190px,1fr) 52px minmax(190px,1fr) 52px minmax(230px,1.15fr) minmax(160px,.78fr) !important;
    gap:14px !important;
    align-items:center !important;
}
.sim-flow-node{
    padding:18px 20px !important;
    min-height:124px !important;
    border-radius:24px !important;
    background:rgba(255,255,255,.46) !important;
    border:1px solid rgba(255,255,255,.68) !important;
}
.sim-flow-node.after{
    background:rgba(255,228,118,.105) !important;
}
.sim-flow-node.save{
    background:rgba(255,228,118,.21) !important;
    border-color:rgba(255,188,56,.50) !important;
}
.sim-flow-label{
    font-size:13px !important;
    font-weight:900 !important;
    color:#4d5661 !important;
    margin-bottom:12px !important;
}
.sim-flow-value{
    font-size:35px !important;
    line-height:1 !important;
    font-weight:980 !important;
    letter-spacing:-.065em !important;
    color:#202124 !important;
    margin-bottom:10px !important;
}
.sim-flow-value.save{
    font-size:46px !important;
    color:#d6a800 !important;
}
.sim-flow-note{
    font-size:12.7px !important;
    line-height:1.45 !important;
    font-weight:760 !important;
    color:#4d5661 !important;
    word-break:keep-all !important;
}
.sim-flow-arrow{
    height:48px !important;
    border-radius:999px !important;
    background:rgba(255,255,255,.38) !important;
    border:1px solid rgba(255,255,255,.62) !important;
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    color:#d6a800 !important;
    font-size:25px !important;
    font-weight:980 !important;
}
.sim-peak-mini{
    padding:18px 18px !important;
    min-height:124px !important;
    border-radius:24px !important;
    background:rgba(255,255,255,.42) !important;
    border:1px solid rgba(255,255,255,.66) !important;
}
.sim-peak-value{
    font-size:34px !important;
    line-height:1 !important;
    font-weight:980 !important;
    color:#202124 !important;
    margin-bottom:10px !important;
}

/* 본문: 분석 대시보드 */
.sim-main-grid{
    display:grid !important;
    grid-template-columns:minmax(0,1.46fr) minmax(330px,.54fr) !important;
    gap:14px !important;
    align-items:stretch !important;
    margin:14px 0 18px !important;
}
.sim-chart-card,
.sim-rank-card{
    padding:22px 24px !important;
    border-radius:28px !important;
    background:rgba(255,255,255,.40) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 14px 32px rgba(0,0,0,.06) !important;
    color:#202124 !important;
}
.sim-section-title{
    display:flex !important;
    align-items:baseline !important;
    justify-content:space-between !important;
    gap:12px !important;
    font-size:20px !important;
    font-weight:960 !important;
    letter-spacing:-.05em !important;
    color:#202124 !important;
    margin-bottom:16px !important;
}
.sim-section-title span{
    font-size:12px !important;
    font-weight:800 !important;
    color:#6b747e !important;
    letter-spacing:-.02em !important;
}
.sim-legend{
    display:flex !important;
    align-items:center !important;
    gap:14px !important;
    margin:4px 0 18px !important;
    font-size:12px !important;
    font-weight:820 !important;
    color:#4d5661 !important;
}
.sim-dot{
    width:11px !important;
    height:11px !important;
    border-radius:4px !important;
    display:inline-block !important;
    margin-right:5px !important;
    vertical-align:-1px !important;
}
.sim-dot.before{background:rgba(70,78,88,.34) !important;}
.sim-dot.after{background:rgba(255,188,56,.72) !important;}

.sim-horizontal-chart{
    display:grid !important;
    gap:16px !important;
}
.sim-bar-row{
    display:grid !important;
    grid-template-columns:150px 1fr 154px !important;
    gap:15px !important;
    align-items:center !important;
    padding-bottom:2px !important;
}
.sim-bar-name{
    font-size:13.2px !important;
    font-weight:920 !important;
    color:#202124 !important;
    white-space:nowrap !important;
}
.sim-bar-pair{
    display:grid !important;
    gap:7px !important;
}
.sim-bar-track{
    position:relative !important;
    height:34px !important;
    border-radius:999px !important;
    background:rgba(32,33,36,.065) !important;
    overflow:hidden !important;
}
.sim-bar-fill{
    height:100% !important;
    border-radius:999px !important;
    min-width:18px !important;
}
.sim-bar-fill.before{
    background:linear-gradient(90deg, rgba(70,78,88,.18), rgba(70,78,88,.35)) !important;
}
.sim-bar-fill.after{
    background:linear-gradient(90deg, rgba(255,228,118,.50), rgba(255,188,56,.78)) !important;
}
.sim-bar-value{
    font-size:13px !important;
    font-weight:920 !important;
    color:#202124 !important;
    text-align:right !important;
    white-space:nowrap !important;
}
.sim-bar-value strong{
    color:#d6a800 !important;
    font-size:14px !important;
}

.sim-rank-list{
    display:grid !important;
    gap:8px !important;
}
.sim-rank-row{
    display:grid !important;
    grid-template-columns:30px 1fr 92px !important;
    gap:10px !important;
    align-items:center !important;
    padding:11px 0 !important;
    border-bottom:1px solid rgba(32,33,36,.07) !important;
}
.sim-rank-row:last-child{
    border-bottom:0 !important;
}
.sim-rank-num{
    width:26px !important;
    height:26px !important;
    border-radius:999px !important;
    display:flex !important;
    align-items:center !important;
    justify-content:center !important;
    background:rgba(255,228,118,.38) !important;
    color:#202124 !important;
    font-size:12px !important;
    font-weight:940 !important;
}
.sim-rank-name{
    font-size:13.4px !important;
    font-weight:920 !important;
    color:#202124 !important;
    margin-bottom:6px !important;
}
.sim-rank-sub{
    font-size:11.5px !important;
    line-height:1.35 !important;
    font-weight:760 !important;
    color:#6b747e !important;
}
.sim-rank-save{
    font-size:15.5px !important;
    font-weight:960 !important;
    color:#d6a800 !important;
    text-align:right !important;
    white-space:nowrap !important;
}
.sim-progress-track{
    margin-top:8px !important;
    height:8px !important;
    border-radius:999px !important;
    background:rgba(32,33,36,.08) !important;
    overflow:hidden !important;
}
.sim-progress-fill{
    height:100% !important;
    border-radius:999px !important;
    background:linear-gradient(90deg, rgba(255,188,56,.86), rgba(255,228,118,.78)) !important;
}
@media(max-width:1200px){
    .sim-flow-top,
    .sim-main-grid{grid-template-columns:1fr !important;}
    .sim-flow-arrow{display:none !important;}
    .sim-bar-row{grid-template-columns:120px 1fr 130px !important;}
}



/* UI text refinement */
.ai-action-text span{display:block; margin-top:4px;}
.ai-action-text .main{font-weight:760;color:#202124;}
.ai-action-text .sub{font-weight:620;color:#4e5968;}
.appliance-option-hint{font-size:12px;color:#4e5968;font-weight:650;margin-top:2px;}


/* Final tidy: Billing/Home/Schedule readability */
.left-ref-title{font-size:36px !important; line-height:1.08 !important; letter-spacing:-.06em !important;}
.center-copy{width:560px !important; padding-top:12px !important;}
.center-copy-title{font-size:50px !important; line-height:1.05 !important; font-weight:900 !important;}
.center-copy-sub{font-size:20px !important; font-weight:680 !important; line-height:1.42 !important;}
.billing-mode-note{display:none !important;}
.billing-overview-grid{grid-template-columns:minmax(520px,1.18fr) minmax(240px,.46fr) minmax(470px,.90fr) !important; gap:16px !important;}
.billing-side-note{font-size:12.3px !important; line-height:1.38 !important; max-width:260px !important; overflow-wrap:break-word !important;}
.billing-chart-card{padding:20px 24px 18px !important; overflow:hidden !important;}
.billing-chart-head{align-items:flex-start !important; gap:14px !important;}
.billing-chart-title{font-size:17px !important; line-height:1.35 !important; max-width:260px !important;}
.billing-chart-legend{font-size:11px !important; gap:10px !important; flex-wrap:wrap !important; justify-content:flex-end !important;}
.billing-bar-area{height:140px !important; gap:12px !important; padding-top:10px !important; overflow:visible !important;}
.billing-bar-value{font-size:10.5px !important; top:-18px !important;}
.appliance-option-hint{font-size:11px !important;color:#5b6570 !important;font-weight:700 !important;margin-top:4px !important;white-space:nowrap !important;}
div[data-testid="stTabs"] div[role="tabpanel"] [data-testid="stCheckbox"] label p{font-size:15px !important; font-weight:850 !important;}
.saving-summary-card{align-items:center !important; gap:26px !important;}
.saving-summary-main{font-size:28px !important; line-height:1.2 !important; word-break:keep-all !important;}
.saving-summary-sub{font-size:14.2px !important; line-height:1.45 !important; max-width:780px !important; word-break:keep-all !important;}
@media(max-width:1200px){.billing-overview-grid{grid-template-columns:1fr !important;}.center-copy{width:auto !important;}}

/* Final request: option hint removal + Billing wording/spacing */
.appliance-option-hint{display:none !important;}
.billing-compare-wrap{
    min-height:250px !important;
    padding:24px 24px 26px !important;
}
.billing-section-title{
    margin-bottom:18px !important;
}
.billing-compare-grid{
    gap:16px !important;
    align-items:stretch !important;
}
.billing-plan-card{
    min-height:178px !important;
    padding:22px 22px !important;
    display:flex !important;
    flex-direction:column !important;
    justify-content:space-between !important;
}
.billing-plan-label{font-size:14px !important;}
.billing-plan-value{font-size:34px !important; margin-bottom:10px !important;}
.billing-plan-sub{font-size:13px !important; line-height:1.48 !important; min-height:38px !important;}
.billing-plan-chip{margin-top:10px !important; width:max-content !important;}
.billing-lower-grid{align-items:stretch !important;}
.billing-point-card{min-height:250px !important;}



/* Billing UI polish update: cleaner cards, structured notes, larger chart */
.billing-overview-grid{
    grid-template-columns:minmax(540px,1.14fr) minmax(260px,.42fr) minmax(560px,1.02fr) !important;
    gap:18px !important;
    align-items:stretch !important;
}
.billing-bill-card{
    min-height:230px !important;
    padding:30px 34px !important;
    grid-template-columns:minmax(0,1fr) 1px 245px !important;
}
.billing-card-sub{
    font-size:14px !important;
    line-height:1.55 !important;
    max-width:360px !important;
}
.billing-sub-arrow{
    display:inline-flex !important;
    margin:2px 8px 0 0 !important;
    color:#d6a800 !important;
    font-weight:950 !important;
}
.billing-save-value{
    font-size:46px !important;
    line-height:1.02 !important;
}
.billing-side-card{
    padding:22px 22px !important;
}
.billing-side-label{
    font-size:14px !important;
    line-height:1.25 !important;
}
.billing-side-value{
    font-size:40px !important;
    margin-bottom:12px !important;
}
.billing-side-note{
    display:grid !important;
    gap:5px !important;
    font-size:12.6px !important;
    line-height:1.42 !important;
    max-width:100% !important;
}
.billing-side-note span{
    display:block !important;
}
.billing-chart-card{
    min-height:260px !important;
    padding:26px 30px 22px !important;
}
.billing-chart-head{
    margin-bottom:16px !important;
    align-items:flex-start !important;
}
.billing-chart-title{
    font-size:22px !important;
    line-height:1.25 !important;
    max-width:360px !important;
}
.billing-chart-title span{
    font-size:13px !important;
}
.billing-chart-legend{
    font-size:12px !important;
    gap:14px !important;
    padding-top:3px !important;
}
.billing-bar-area{
    height:178px !important;
    gap:14px !important;
    padding:18px 8px 0 !important;
}
.billing-bar{
    width:22px !important;
    border-radius:9px 9px 0 0 !important;
}
.billing-bar-group{
    gap:8px !important;
}
.billing-bar-value{
    font-size:11.5px !important;
    top:-22px !important;
    font-weight:900 !important;
}
.billing-month-row{
    font-size:12px !important;
    padding-top:10px !important;
}
.billing-lower-grid{
    grid-template-columns:minmax(0,2.18fr) minmax(330px,.78fr) !important;
    gap:16px !important;
}
.billing-compare-wrap{
    min-height:330px !important;
    padding:28px 30px 30px !important;
}
.billing-section-title{
    align-items:center !important;
    gap:14px !important;
    font-size:22px !important;
    margin-bottom:24px !important;
}
.billing-section-title span{
    font-size:13px !important;
    line-height:1.3 !important;
    padding:6px 12px !important;
    border-radius:999px !important;
    background:rgba(255,255,255,.45) !important;
    color:#4d5661 !important;
    white-space:nowrap !important;
}
.billing-compare-grid{
    gap:18px !important;
}
.billing-plan-card{
    min-height:218px !important;
    padding:26px 26px 24px !important;
    display:flex !important;
    flex-direction:column !important;
    justify-content:space-between !important;
}
.billing-plan-top{
    display:block !important;
}
.billing-plan-label{
    font-size:15px !important;
    line-height:1.25 !important;
    margin-bottom:14px !important;
    color:#3f4852 !important;
}
.billing-plan-value{
    font-size:44px !important;
    line-height:.98 !important;
    margin-bottom:16px !important;
}
.billing-plan-sub{
    font-size:13.2px !important;
    line-height:1.55 !important;
    min-height:48px !important;
    color:#4d5661 !important;
}
.billing-plan-chip{
    width:max-content !important;
    max-width:100% !important;
    margin-top:14px !important;
    padding:9px 14px !important;
    font-size:12.5px !important;
    line-height:1.2 !important;
    display:inline-flex !important;
    gap:7px !important;
    align-items:center !important;
}
.billing-plan-chip span{
    display:inline-block !important;
    padding-left:7px !important;
    border-left:1px solid rgba(32,33,36,.16) !important;
}
.billing-point-card{
    padding:26px 28px !important;
}
.billing-point-item{
    font-size:13.2px !important;
    line-height:1.55 !important;
}
@media(max-width:1200px){
    .billing-overview-grid,.billing-lower-grid{grid-template-columns:1fr !important;}
    .billing-compare-grid{grid-template-columns:1fr !important;}
    .billing-section-title{align-items:flex-start !important; flex-direction:column !important;}
    .billing-section-title span{white-space:normal !important;}
}


/* Billing final compact polish: amount one-line + cleaner plan notes */
.billing-overview-grid{
    grid-template-columns:minmax(500px,1.05fr) minmax(250px,.44fr) minmax(500px,.86fr) !important;
    gap:16px !important;
    align-items:stretch !important;
}
.billing-bill-card{
    min-height:212px !important;
    padding:28px 32px !important;
    grid-template-columns:minmax(245px,1fr) 1px 225px !important;
    gap:20px !important;
}
.billing-card-label{
    font-size:15px !important;
    margin-bottom:12px !important;
}
.billing-bill-value{
    font-size:42px !important;
    line-height:1.02 !important;
    letter-spacing:-0.065em !important;
    white-space:nowrap !important;
    word-break:keep-all !important;
    margin-bottom:16px !important;
}
.billing-card-sub{
    font-size:13.2px !important;
    line-height:1.5 !important;
    max-width:320px !important;
    word-break:keep-all !important;
}
.billing-save-title{
    font-size:13px !important;
    margin-bottom:11px !important;
}
.billing-save-value{
    font-size:38px !important;
    line-height:1.02 !important;
    letter-spacing:-0.06em !important;
    white-space:nowrap !important;
}
.billing-save-pill{
    font-size:12.5px !important;
    padding:7px 14px !important;
}
.billing-divider{
    height:112px !important;
}
.billing-chart-card{
    min-height:232px !important;
    padding:22px 26px 18px !important;
}
.billing-chart-head{
    margin-bottom:10px !important;
}
.billing-chart-title{
    font-size:20px !important;
    line-height:1.25 !important;
    max-width:330px !important;
}
.billing-chart-legend{
    font-size:11.2px !important;
    gap:10px !important;
}
.billing-bar-area{
    height:148px !important;
    gap:12px !important;
    padding:14px 6px 0 !important;
}
.billing-bar{
    width:18px !important;
    border-radius:8px 8px 0 0 !important;
}
.billing-bar-value{
    font-size:10px !important;
    top:-17px !important;
}
.billing-month-row{
    margin-top:9px !important;
    font-size:12px !important;
}
.billing-compare-wrap{
    padding:24px 26px 28px !important;
}
.billing-compare-grid{
    gap:18px !important;
    align-items:stretch !important;
}
.billing-plan-card{
    min-height:190px !important;
    padding:24px 26px !important;
    justify-content:space-between !important;
}
.billing-plan-label{
    font-size:15px !important;
    line-height:1.25 !important;
    margin-bottom:13px !important;
}
.billing-plan-value{
    font-size:40px !important;
    line-height:1.02 !important;
    letter-spacing:-0.06em !important;
    white-space:nowrap !important;
    margin-bottom:14px !important;
}
.billing-plan-sub{
    font-size:13px !important;
    line-height:1.55 !important;
    min-height:44px !important;
    max-width:300px !important;
    word-break:keep-all !important;
    color:#4d5661 !important;
}
.billing-plan-chip{
    margin-top:12px !important;
    font-size:12.5px !important;
    line-height:1.25 !important;
    padding:8px 13px !important;
    white-space:nowrap !important;
}
@media(max-width:1200px){
    .billing-overview-grid{grid-template-columns:1fr !important;}
    .billing-bill-card{grid-template-columns:1fr !important;}
    .billing-divider{display:none !important;}
}



/* DR 알림/계산 기준 문구 간결화 */
.dr-alert-desc{
    display:grid !important;
    gap:6px !important;
    line-height:1.55 !important;
}
.dr-alert-subline{
    color:#3f4852 !important;
    font-weight:720 !important;
}
.billing-point-list{
    gap:16px !important;
}
.billing-point-item span:last-child{
    line-height:1.48 !important;
    word-break:keep-all !important;
}



/* DR ON/OFF 절감액 분리 표시 */
.dr-split-summary .saving-summary-sub{
    display:grid !important;
    gap:6px !important;
    max-width:820px !important;
    line-height:1.45 !important;
}
.dr-split-summary .saving-summary-sub div{
    color:#4d5661 !important;
    font-size:13px !important;
    font-weight:720 !important;
    word-break:keep-all !important;
}
.dr-split-summary .saving-summary-sub strong,
.dr-split-summary .saving-summary-sub b{
    color:#202124 !important;
    font-weight:900 !important;
}
.saving-summary-rate.tiny{
    font-size:10.5px !important;
    line-height:1.35 !important;
    color:#5f6873 !important;
    max-width:210px !important;
}


/* ===== Final UI patch: Schedule saving summary readability + replace billing graph ===== */
.dr-split-summary{
    padding:26px 30px !important;
    gap:32px !important;
}
.dr-split-summary .saving-summary-label{
    font-size:15px !important;
    margin-bottom:12px !important;
}
.dr-split-summary .saving-summary-main{
    font-size:30px !important;
    line-height:1.24 !important;
    letter-spacing:-.055em !important;
}
.dr-split-summary .saving-summary-main strong{
    font-size:34px !important;
    white-space:nowrap !important;
}
.dr-split-summary .saving-summary-sub{
    margin-top:14px !important;
    display:grid !important;
    gap:8px !important;
    max-width:900px !important;
}
.dr-split-summary .saving-summary-sub div{
    display:block !important;
    padding:8px 12px !important;
    border-radius:14px !important;
    background:rgba(255,255,255,.34) !important;
    border:1px solid rgba(255,255,255,.45) !important;
    color:#3f4852 !important;
    font-size:15px !important;
    line-height:1.42 !important;
    font-weight:760 !important;
    word-break:keep-all !important;
}
.dr-split-summary .saving-summary-sub strong{
    display:inline-block !important;
    min-width:138px !important;
    color:#202124 !important;
    font-weight:930 !important;
}
.dr-split-summary .saving-summary-sub b{
    color:#202124 !important;
    font-weight:930 !important;
}
.dr-split-summary .saving-summary-right{
    min-width:245px !important;
    text-align:center !important;
    padding:18px 22px !important;
}
.dr-split-summary .saving-summary-save{
    font-size:36px !important;
    white-space:nowrap !important;
}
.dr-split-summary .saving-summary-rate{
    font-size:14px !important;
}
.dr-split-summary .saving-summary-rate.tiny{
    margin-top:10px !important;
    font-size:12.5px !important;
    line-height:1.45 !important;
    max-width:220px !important;
}

.billing-overview-grid{
    grid-template-columns:minmax(520px,1.08fr) minmax(245px,.42fr) minmax(420px,.72fr) !important;
    gap:18px !important;
}
.billing-tou-card{
    padding:24px 26px !important;
    border-radius:24px !important;
    background:rgba(255,255,255,.46) !important;
    border:1px solid rgba(255,255,255,.68) !important;
    box-shadow:0 10px 24px rgba(0,0,0,.055) !important;
    color:#202124 !important;
    min-height:238px !important;
}
.billing-tou-title{
    font-size:22px !important;
    line-height:1.25 !important;
    font-weight:950 !important;
    letter-spacing:-.045em !important;
    margin-bottom:16px !important;
    color:#202124 !important;
}
.billing-tou-grid{
    display:grid !important;
    grid-template-columns:repeat(3,1fr) !important;
    gap:10px !important;
    margin-bottom:14px !important;
}
.billing-tou-item{
    padding:13px 12px !important;
    border-radius:18px !important;
    background:rgba(255,255,255,.42) !important;
    border:1px solid rgba(255,255,255,.60) !important;
}
.billing-tou-item.peak{
    background:rgba(255,228,118,.25) !important;
    border-color:rgba(255,205,64,.45) !important;
}
.billing-tou-name{
    font-size:12px !important;
    font-weight:880 !important;
    color:#5a6470 !important;
    margin-bottom:7px !important;
}
.billing-tou-time{
    font-size:15px !important;
    font-weight:930 !important;
    color:#202124 !important;
    margin-bottom:7px !important;
    white-space:nowrap !important;
}
.billing-tou-rate{
    font-size:20px !important;
    line-height:1 !important;
    font-weight:980 !important;
    color:#202124 !important;
    letter-spacing:-.04em !important;
    white-space:nowrap !important;
}
.billing-tou-rate span{
    font-size:11px !important;
    font-weight:830 !important;
    margin-left:2px !important;
}
.billing-dr-rule{
    display:grid !important;
    grid-template-columns:1fr 1fr !important;
    gap:10px !important;
    margin-top:12px !important;
}
.billing-dr-rule div{
    padding:11px 12px !important;
    border-radius:16px !important;
    background:rgba(255,228,118,.24) !important;
    border:1px solid rgba(255,255,255,.56) !important;
    font-size:13px !important;
    line-height:1.45 !important;
    font-weight:800 !important;
    color:#3f4852 !important;
    word-break:keep-all !important;
}
.billing-dr-rule strong{
    color:#202124 !important;
    font-weight:940 !important;
}
.billing-bill-value,
.billing-save-value{
    white-space:nowrap !important;
}
@media(max-width:1200px){
    .billing-overview-grid{grid-template-columns:1fr !important;}
    .billing-tou-grid{grid-template-columns:1fr !important;}
    .billing-dr-rule{grid-template-columns:1fr !important;}
}
/* Billing 상단 2열 레이아웃 최종 보정 */
.billing-overview-grid{
    display:grid !important;
    grid-template-columns:minmax(0, 2.15fr) minmax(300px, .85fr) !important;
    gap:18px !important;
    align-items:stretch !important;
    width:100% !important;
    margin:12px 0 16px !important;
}

/* 왼쪽 큰 요금 카드 */
.billing-bill-card{
    width:100% !important;
    min-height:240px !important;
    padding:34px 38px !important;
    grid-template-columns:minmax(0, 1fr) 1px minmax(230px, .72fr) !important;
    gap:26px !important;
}

/* 오른쪽 보조 카드 묶음 */
.billing-side-stack{
    width:100% !important;
    display:grid !important;
    grid-template-rows:1fr 1fr !important;
    gap:14px !important;
}

/* 오른쪽 카드가 너무 좁아 보이지 않도록 */
.billing-side-card{
    min-height:112px !important;
    padding:22px 24px !important;
}

/* 큰 금액 한 줄 유지 */
.billing-bill-value{
    font-size:46px !important;
    line-height:1.02 !important;
    letter-spacing:-0.065em !important;
    white-space:nowrap !important;
    word-break:keep-all !important;
}

/* 절감액도 한 줄 유지 */
.billing-save-value{
    font-size:40px !important;
    line-height:1.02 !important;
    white-space:nowrap !important;
}

/* 오른쪽 작은 카드 숫자 정리 */
.billing-side-value{
    font-size:38px !important;
    line-height:1.02 !important;
    white-space:nowrap !important;
}

.billing-side-value span{
    font-size:18px !important;
    margin-left:4px !important;
}

/* 태블릿/좁은 화면에서는 세로 배치 */
@media(max-width:1200px){
    .billing-overview-grid{
        grid-template-columns:1fr !important;
    }

    .billing-bill-card{
        grid-template-columns:1fr !important;
    }

    .billing-divider{
        display:none !important;
    }
}
/* ===============================
   Tablet responsive layout
   768px ~ 1200px
================================ */
@media (max-width: 1200px) {
    .main .block-container{
        max-width:100% !important;
        padding:0.8rem 1rem 1.5rem !important;
    }

    .home-bg-shell{
        width:100% !important;
        margin:-80px auto 1rem auto !important;
    }

    .home-dashboard-grid{
        grid-template-columns:1fr 1fr !important;
        grid-template-rows:auto !important;
        gap:18px !important;
    }

    .left-ref-panel{
        grid-column:1 / span 2 !important;
        grid-row:auto !important;
        transform:none !important;
        min-height:auto !important;
    }

    .center-copy{
        grid-column:1 / span 2 !important;
        grid-row:auto !important;
        width:100% !important;
        padding-top:10px !important;
    }

    .top-weather-card{
        grid-column:1 !important;
        grid-row:auto !important;
        margin-top:0 !important;
    }

    .right-ai-panel{
        grid-column:2 !important;
        grid-row:auto !important;
        margin-top:0 !important;
    }

    .bottom-dashboard-row{
        grid-template-columns:1fr !important;
        margin-left:0 !important;
        margin-top:40px !important;
    }

    .schedule-dock{
        grid-template-columns:1fr !important;
    }

    div[data-testid="stSelectbox"]{
        width:100% !important;
        transform:none !important;
    }

    .billing-overview-grid{
        grid-template-columns:1fr !important;
    }

    .billing-bill-card{
        grid-template-columns:1fr !important;
        min-height:auto !important;
    }

    .billing-divider{
        display:none !important;
    }

    .billing-side-stack{
        grid-template-columns:1fr 1fr !important;
        grid-template-rows:auto !important;
    }

    .billing-tou-grid{
        grid-template-columns:1fr !important;
    }

    .reason-card-grid{
        grid-template-columns:1fr !important;
    }
}
/* ===============================
   Mobile responsive layout
   below 768px
================================ */
@media (max-width: 768px) {
    .main .block-container{
        padding:0.6rem 0.7rem 1.2rem !important;
    }

    .home-bg-shell{
        width:100% !important;
        margin:-40px auto 1rem auto !important;
    }

    .home-dashboard-grid{
        display:block !important;
    }

    .left-ref-panel,
    .top-weather-card,
    .right-ai-panel,
    .schedule-dock,
    .dr-notice-card{
        width:100% !important;
        min-height:auto !important;
        margin:0 0 16px 0 !important;
        transform:none !important;
        border-radius:24px !important;
    }

    .center-copy{
        width:100% !important;
        padding:10px 0 16px !important;
    }

    .center-copy-title{
        font-size:30px !important;
        line-height:1.15 !important;
    }

    .center-copy-sub{
        font-size:15px !important;
        line-height:1.45 !important;
    }

    .left-ref-title{
        font-size:28px !important;
    }

    .left-main-price{
        font-size:32px !important;
    }

    .summary-value{
        font-size:24px !important;
    }

    .weather-card-body{
        grid-template-columns:1fr !important;
    }

    .ai-status-row{
        grid-template-columns:1fr !important;
    }

    .bottom-dashboard-row{
        display:block !important;
        margin:20px 0 0 !important;
    }

    div[data-testid="stTabs"] div[role="tabpanel"]{
        padding:18px 14px 24px !important;
        border-radius:24px !important;
    }

    div[data-testid="stTabs"] > div[role="tablist"]{
        width:100% !important;
        overflow-x:auto !important;
        gap:12px !important;
        padding:8px 10px !important;
    }

    button[data-baseweb="tab"]{
        min-width:auto !important;
        padding:8px 12px !important;
    }

    button[data-baseweb="tab"] p{
        font-size:14px !important;
    }

    .section-lbl{
        font-size:22px !important;
    }

    .billing-overview-grid{
        grid-template-columns:1fr !important;
        gap:14px !important;
    }

    .billing-bill-card{
        grid-template-columns:1fr !important;
        padding:24px 22px !important;
        min-height:auto !important;
    }

    .billing-bill-value{
        font-size:42px !important;
        white-space:nowrap !important;
    }

    .billing-save-value{
        font-size:36px !important;
        white-space:nowrap !important;
    }

    .billing-side-stack{
        grid-template-columns:1fr !important;
    }

    .billing-side-value{
        font-size:34px !important;
    }

    .billing-tou-grid{
        grid-template-columns:1fr !important;
    }

    .billing-plan-card{
        min-height:auto !important;
        padding:22px !important;
    }

    .saving-summary-card{
        display:block !important;
        padding:18px !important;
    }

    .saving-summary-main{
        font-size:20px !important;
    }

    .saving-summary-main strong{
        font-size:24px !important;
    }

    .saving-summary-right{
        margin-top:16px !important;
        text-align:left !important;
        width:100% !important;
    }

    .saving-summary-save{
        font-size:32px !important;
        white-space:nowrap !important;
    }

    .reason-card-grid{
        grid-template-columns:1fr !important;
    }

    .reason-card{
        min-height:auto !important;
    }

    .reason-desc{
        max-width:100% !important;
    }

    .reason-tag{
        position:static !important;
        margin-top:12px !important;
        display:inline-flex !important;
    }

    .smart-schedule-board{
        overflow-x:auto !important;
        -webkit-overflow-scrolling:touch !important;
    }

    .smart-schedule-hours,
    .smart-schedule-row{
        min-width:900px !important;
    }
}
</style>

""", unsafe_allow_html=True)
# ─── 탭 버튼 글씨 색상 최종 고정 ───
st.markdown("""
<style>
/* Schedule / Billing / Forecast 탭 글씨 최종 고정 */
div[data-testid="stTabs"] [role="tablist"] [role="tab"],
div[data-testid="stTabs"] [role="tablist"] [role="tab"] *,
div[data-testid="stTabs"] button[data-baseweb="tab"],
div[data-testid="stTabs"] button[data-baseweb="tab"] *,
div[data-testid="stTabs"] button[role="tab"],
div[data-testid="stTabs"] button[role="tab"] *{
    color:rgba(255,255,255,.94) !important;
    -webkit-text-fill-color:rgba(255,255,255,.94) !important;
    font-weight:850 !important;
    text-shadow:0 2px 8px rgba(0,0,0,.55) !important;
}

/* 선택된 탭은 노란색 */
div[data-testid="stTabs"] [role="tablist"] [role="tab"][aria-selected="true"],
div[data-testid="stTabs"] [role="tablist"] [role="tab"][aria-selected="true"] *,
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"],
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] *,
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"],
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] *{
    color:#FFE476 !important;
    -webkit-text-fill-color:#FFE476 !important;
    font-weight:900 !important;
    text-shadow:0 2px 9px rgba(0,0,0,.60) !important;
}
</style>
""", unsafe_allow_html=True)
# ─── HOME 배경 이미지 설정 ───
# 로컬 파일을 찾아 base64로 인코딩하지 않고, GitHub raw 주소를 직접 CSS에 넣습니다.
# (아이콘과 동일한 방식 — 파일 존재 여부/경로 문제와 무관하게 항상 같은 주소로 로드)
BG_IMAGE_URL = "https://raw.githubusercontent.com/rlarjsdn-ui/DR_simulator/main/home_bg_web.png"

st.markdown(f"""
<style>
.stApp {{
    background-image:
        linear-gradient(rgba(10,15,24,.20), rgba(10,15,24,.22)),
        url("{BG_IMAGE_URL}") !important;
    background-size: cover !important;
    background-position: center 62% !important;
    background-attachment: fixed !important;
}}
</style>
""", unsafe_allow_html=True)


# ─── 도시 목록 (옵션2: 17개) ───
CITIES = {
    "서울":  {"lat": 37.5665, "lon": 126.9780},
    "부산":  {"lat": 35.1796, "lon": 129.0756},
    "대구":  {"lat": 35.8714, "lon": 128.6014},
    "인천":  {"lat": 37.4563, "lon": 126.7052},
    "광주":  {"lat": 35.1595, "lon": 126.8526},
    "대전":  {"lat": 36.3504, "lon": 127.3845},
    "울산":  {"lat": 35.5384, "lon": 129.3114},
    "세종":  {"lat": 36.4800, "lon": 127.2890},
    "수원":  {"lat": 37.2636, "lon": 127.0286},
    "청주":  {"lat": 36.6424, "lon": 127.4890},
    "전주":  {"lat": 35.8242, "lon": 127.1480},
    "창원":  {"lat": 35.2280, "lon": 128.6811},
    "춘천":  {"lat": 37.8813, "lon": 127.7298},
    "제주":  {"lat": 33.4996, "lon": 126.5312},
    "포항":  {"lat": 36.0190, "lon": 129.3435},
    "강릉":  {"lat": 37.7519, "lon": 128.8761},
    "천안":  {"lat": 36.8151, "lon": 127.1139},
}

WEATHER_CODE_MAP = {
    0:"맑음 ☀️", 1:"대체로 맑음 🌤️", 2:"구름 조금 ⛅",
    3:"흐림 ☁️", 45:"안개 🌫️", 48:"안개 🌫️",
    51:"이슬비 🌦️", 53:"이슬비 🌦️", 55:"이슬비 🌦️",
    61:"비 🌧️", 63:"비 🌧️", 65:"폭우 ⛈️",
    71:"눈 🌨️", 73:"눈 🌨️", 75:"폭설 ❄️",
    80:"소나기 🌦️", 81:"소나기 🌦️", 82:"폭우 ⛈️",
    95:"천둥번개 ⛈️",
}

@st.cache_data(ttl=300)  # 5분 캐시
def get_weather(city_name):
    try:
        city = CITIES[city_name]
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":  city["lat"],
            "longitude": city["lon"],
            "current":   ["temperature_2m","relative_humidity_2m",
                         "precipitation","weathercode","windspeed_10m"],
            "timezone":  "Asia/Seoul",
        }
        res  = requests.get(url, params=params, timeout=5)
        data = res.json()["current"]
        return {
            "temp":     round(data["temperature_2m"], 1),
            "humidity": round(data["relative_humidity_2m"]),
            "precip":   round(data["precipitation"], 1),
            "wind":     round(data["windspeed_10m"], 1),
            "desc":     WEATHER_CODE_MAP.get(data["weathercode"], "알 수 없음"),
            "code":     data["weathercode"],
        }
    except:
        return None

# ─── 데이터 & 함수 ───
# 제주 주택용 계시별 선택요금제 시간대 구분 기반 3단계 시간대별 요금제(TOU)
# 경부하 22~08시 107.0원/kWh, 중간부하 08~16시 153.0원/kWh, 최대부하 16~22시 188.8원/kWh
HOURLY_PRICES = [107.0]*8 + [153.0]*8 + [188.8]*6 + [107.0]*2
# 가전 기본 소비전력은 "순간 최대 정격"이 아니라 스케줄/요금 계산에 쓰는
# 현실적인 평균 운전전력 기준입니다. 사용자가 직접 기기 사양에 맞게 수정할 수 있습니다.
APPLIANCES = [
    {"name":"세탁기",      "icon":"🫧",  "watt":600,  "cheap":107,"normal":153},  # 일반 세탁 평균 운전전력
    {"name":"건조기",      "icon":"🌬️",  "watt":1400, "cheap":107,"normal":153},  # 히트펌프/전기식 건조 평균
    {"name":"식기세척기",  "icon":"🍽️",  "watt":1200, "cheap":107,"normal":153},  # 세척+가열/건조 포함 평균
    {"name":"전기차 충전", "icon":"🚗",  "watt":7000, "cheap":107,"normal":153},  # 가정용 완속 충전기 기준
    {"name":"에어컨",      "icon":"❄️",  "watt":1800, "cheap":107,"normal":153},  # 인버터 냉방 중부하 평균
    {"name":"청소기",      "icon":"🌀",  "watt":1000, "cheap":107,"normal":153},  # 유선/고출력 청소 평균
]
APPLIANCE_WATT = {a["name"]:a["watt"] for a in APPLIANCES}
APPLIANCE_ICONS = {a["name"]:a["icon"] for a in APPLIANCES}

def get_status(price):
    if price <= 107.0: return "cheap"
    if price <= 153.0: return "normal"
    if price <= 188.8: return "expensive"
    return "peak"

def get_rate(hour, dr=False, dr_hour_list=None, dr_reward_per_kwh=150):
    """
    제주 주택용 계시별 선택요금제 시간대 구분 기반 3단계 시간대별 요금제(TOU) 단가.
    - 경부하: 22~08시, 107.0원/kWh
    - 중간부하: 08~16시, 153.0원/kWh
    - 최대부하: 16~22시, 188.8원/kWh
    """
    h = int(hour) % 24
    if h >= 22 or h < 8:
        rate = 107.0
    elif 8 <= h < 16:
        rate = 153.0
    else:
        rate = 188.8
    # DR은 사용 시간대 요금을 직접 할인하는 방식이 아니라,
    # DR 시간대 사용량을 줄였을 때 별도 보상으로 계산합니다.
    # 따라서 스케줄 최적화의 단가 계산에서는 TOU 단가를 그대로 사용합니다.
    return rate

def calc_progressive(kwh):
    """
    Billing 탭용 누진제 계산.
    billing.py가 있으면 기본요금/부가세/전력산업기반기금이 포함된 계산을 사용합니다.
    """
    if BILLING_READY and billing_calculate_progressive_bill is not None:
        return billing_calculate_progressive_bill(kwh, month=datetime.now().month)["합계"]

    # fallback: 기존 단순 계산
    if kwh <= 200:
        return round(kwh * 120)
    if kwh <= 400:
        return round(200 * 120 + (kwh - 200) * 220)
    return round(200 * 120 + 200 * 220 + (kwh - 400) * 300)


def calc_tou(kwh, dr=False):
    """
    Billing 탭용 시간대별 요금제(TOU)/시간대별 요금제(TOU)+DR 계산.
    billing.py가 있으면 실제 요금 모듈의 월간 비교 계산을 사용합니다.
    """
    if BILLING_READY and billing_simulate_monthly_bills is not None:
        result = billing_simulate_monthly_bills(
            monthly_kwh=kwh,
            dr_hours=list(range(16, 19)),
            incentive_rate=150,
            month=datetime.now().month,
        )
        return result["TOU_DR최종"] if dr else result["TOU"]

    # fallback: 기존 임시 계산
    base = calc_progressive(kwh)
    tou_rate = min(0.18, max(0.03, 0.035 + (kwh - 300) / 3000))
    tou_bill = int(round(base * (1 - tou_rate) / 10) * 10)
    if not dr:
        return tou_bill
    dr_rate = min(0.07, max(0.025, 0.025 + (kwh - 300) / 6000))
    dr_discount = int(round(base * dr_rate / 10) * 10)
    return max(0, tou_bill - dr_discount)
def to_24h(h, ampm):
    if ampm=="오전": return 0 if h==12 else h
    else:            return h if h==12 else h+12

def get_appliance_status(price, a):
    if price<=a["cheap"]:  return "recommended"
    if price<=a["normal"]: return "caution"
    return "avoid"

def fmt_time(hour_float, with_ampm=False):
    """0~24 범위 시간을 24시간 기준으로 변환. 필요 시 오전/오후도 함께 표시"""
    hour_float = hour_float % 24
    hh = int(hour_float)
    mm = int(round((hour_float - hh) * 60))
    if mm == 60:
        hh = (hh + 1) % 24
        mm = 0
    base = f"{hh:02d}:{mm:02d}"
    if not with_ampm:
        return base
    ampm = "오전" if hh < 12 else "오후"
    hour12 = hh % 12
    if hour12 == 0:
        hour12 = 12
    return f"{base} ({ampm} {hour12}시{f' {mm}분' if mm else ''})"

def calc_appliance_cost(watt, hours, start_hour, dr=False, dr_hours=None, dr_reward=150):
    """가전 1개를 특정 시작 시간에 사용했을 때 예상 요금"""
    cost = 0
    full_half_hours = int(hours * 2)
    for off in range(full_half_hours):
        h = int((start_hour + off / 2) % 24)
        cost += (watt / 1000 * 0.5) * get_rate(h, dr, dr_hours, dr_reward)
    rem = hours - full_half_hours * 0.5
    if rem > 0:
        h = int((start_hour + full_half_hours / 2) % 24)
        cost += (watt / 1000 * rem) * get_rate(h, dr, dr_hours, dr_reward)
    return round(cost)

def schedule_hours(start_hour, hours):
    """사용 시간에 포함되는 정수 시간대 목록"""
    used = set()
    steps = max(1, int(hours * 2))
    for off in range(steps):
        used.add(int((start_hour + off / 2) % 24))
    return used

def overlaps_dr(start_hour, hours, dr_hours):
    if not dr_hours:
        return False
    return bool(schedule_hours(start_hour, hours) & set(dr_hours))

def is_allowed_schedule(start_hour, hours, allowed_hours):
    if not allowed_hours:
        return True
    return schedule_hours(start_hour, hours).issubset(set(allowed_hours))

def best_start_for_appliance(name, watt, hours, candidate_hours, dr_mode=False, dr_hours=None, dr_reward=150, avoid_dr=True):
    """가전별 후보 시간 중 최저 비용 시작 시간 계산"""
    candidates = candidate_hours[:] if candidate_hours else list(range(24))

    # DR 참여 시 가능하면 DR 이벤트와 겹치는 후보 제외
    if dr_mode and avoid_dr and dr_hours:
        filtered = [h for h in candidates if not overlaps_dr(h, hours, dr_hours)]
        if filtered:
            candidates = filtered

    scored = []
    for h in candidates:
        base_cost = calc_appliance_cost(watt, hours, h, False, dr_hours, dr_reward)
        dr_cost = calc_appliance_cost(watt, hours, h, dr_mode, dr_hours, dr_reward)

        # DR 시간대와 겹치면 추천 우선순위에서 불리하게 처리
        penalty = 999999 if (dr_mode and avoid_dr and overlaps_dr(h, hours, dr_hours)) else 0
        scored.append({
            "start": h,
            "cost": dr_cost if dr_mode else base_cost,
            "base_cost": base_cost,
            "score": (dr_cost if dr_mode else base_cost) + penalty,
        })

    if not scored:
        return {"start": 0, "cost": 0, "base_cost": 0, "score": 0}
    return min(scored, key=lambda x: x["score"])

def recommend_aircon_schedule(hours, current_hour, available, direct_available, dr_mode, dr_start, dr_end, dr_hours, dr_reward, df_forecast, weather):
    """외기온도와 예보를 반영한 에어컨 추천"""
    temp_now = weather.get("temp", 20) if isinstance(weather, dict) else 20
    remain = None
    max_temp = temp_now
    max_temp_hour = current_hour

    if df_forecast is not None and not df_forecast.empty:
        remain = df_forecast[df_forecast["시간"] >= current_hour].copy()
        if not remain.empty:
            max_temp = float(remain["기온"].max())
            max_temp_hour = int(remain.loc[remain["기온"].idxmax(), "시간"])

    # 냉방 부하가 큰 날: DR/피크 전 사전 냉방 우선
    if max_temp >= 33:
        if dr_mode and dr_hours:
            pre_duration = min(max(hours, 1), 2)
            start = max(0, dr_start - int(np.ceil(pre_duration)))
            return {
                "start": start,
                "display_hours": pre_duration,
                "tag": "사전 냉방",
                "reason": f"예보 최고 {max_temp:.1f}℃로 냉방 부하가 큽니다. DR 시작 전 실내 온도를 미리 낮추고, {fmt_time(dr_start)}–{fmt_time(dr_end)}에는 사용을 최소화하세요.",
                "variant": "air",
            }
        start = max(0, max_temp_hour - 2)
        return {
            "start": start,
            "display_hours": min(max(hours, 1), 2),
            "tag": "고온 대응",
            "reason": f"예보 최고 {max_temp:.1f}℃로 냉방 사용 증가가 예상됩니다. 최고기온 시간 전 미리 냉방하는 것을 추천합니다.",
            "variant": "air",
        }

    # 더운 날: 피크 전 또는 피크 이후로 유도
    if max_temp >= 28:
        if dr_mode and dr_hours:
            start = max(0, dr_start - 1)
            return {
                "start": start,
                "display_hours": min(max(hours, 1), 1.5),
                "tag": "피크 회피",
                "reason": f"예보 최고 {max_temp:.1f}℃입니다. DR/피크 시간 전 짧게 냉방하고, 피크 이후 필요 시 재냉방하는 방식이 적합합니다.",
                "variant": "air",
            }
        candidate = [h for h in (direct_available or available or list(range(24))) if h <= max_temp_hour]
        if not candidate:
            candidate = direct_available or available or list(range(24))
        start = min(candidate, key=lambda h: get_rate(h, False))
        return {
            "start": start,
            "display_hours": min(max(hours, 1), 2),
            "tag": "냉방 증가",
            "reason": f"예보 최고 {max_temp:.1f}℃로 냉방 수요가 증가할 수 있어, 생활 가능 시간 중 낮은 요금 시간대를 추천합니다.",
            "variant": "air",
        }

    # 쾌적한 날: 필요 낮음
    candidate = direct_available or available or list(range(24))
    start = min(candidate, key=lambda h: get_rate(h, False))
    return {
        "start": start,
        "display_hours": min(hours, 1),
        "tag": "필요 낮음",
        "reason": f"현재 {temp_now:.1f}℃로 냉방 부하가 크지 않습니다. 필요할 때만 짧게 사용하고 피크 시간대는 피하는 것을 추천합니다.",
        "variant": "air",
    }

def build_lifestyle_baseline_starts(selected, current_hour):
    """일반 가정의 기존 생활패턴 기준 시작 시간을 생성합니다.

    목적은 현재 시각에 모든 가전을 동시에 켜는 비현실적 기준 대신,
    가정에서 흔히 사용하는 기본 시간대와 비교하기 위함입니다.
    """
    starts = {}

    # 고부하/예약 가전은 보통 귀가 후 또는 야간에 사용한다고 가정
    if "전기차 충전" in selected:
        starts["전기차 충전"] = 20

    # 세탁-건조는 하나의 연속 작업으로 가정
    if "세탁기" in selected:
        starts["세탁기"] = 18
    if "건조기" in selected:
        if "세탁기" in selected:
            washer_hours = float(selected["세탁기"].get("hours", 2))
            starts["건조기"] = int(round(starts["세탁기"] + washer_hours)) % 24
        else:
            starts["건조기"] = 20

    if "청소기" in selected:
        starts["청소기"] = 19
    if "식기세척기" in selected:
        starts["식기세척기"] = 21

    # 에어컨은 더울 때 사용자가 현재 또는 낮 시간대부터 사용하는 가전으로 가정
    if "에어컨" in selected:
        h = int(current_hour) % 24
        starts["에어컨"] = h if 10 <= h < 23 else 12

    # 기타 가전은 저녁 사용을 기본값으로 둠
    for name in selected:
        starts.setdefault(name, 19)
    return starts


def apply_lifestyle_baseline_costs(appliance_recs, selected, current_hour, dr_hours=None, dr_reward=150):
    """추천 결과에 기존 생활패턴 기준 비용과 절감액을 붙입니다."""
    baseline_starts = build_lifestyle_baseline_starts(selected, current_hour)
    updated = []
    for rec in appliance_recs:
        name = rec.get("name")
        info = selected.get(name, {})
        watt = float(info.get("watt", 0))
        hours = float(info.get("hours", rec.get("hours", 0)))
        baseline_start = baseline_starts.get(name, int(current_hour) % 24)
        baseline_cost = calc_appliance_cost(watt, hours, baseline_start, False, dr_hours, dr_reward)
        rec = dict(rec)
        rec["baseline_start"] = baseline_start
        rec["baseline_cost"] = int(round(baseline_cost))
        rec["now_cost"] = rec["baseline_cost"]  # 기존 표시 로직 호환용
        rec["saving"] = max(rec["baseline_cost"] - int(round(rec.get("cost", 0))), 0)
        updated.append(rec)
    return updated


def _dr_overlap_kwh(watt, hours, start_hour, dr_hours):
    """특정 가전 사용 구간 중 DR 시간대와 겹치는 전력량(kWh)."""
    if not dr_hours:
        return 0.0
    dr_set = set(int(h) % 24 for h in dr_hours)
    total = 0.0
    full_half_hours = int(float(hours) * 2)
    for off in range(full_half_hours):
        h = int((float(start_hour) + off / 2) % 24)
        if h in dr_set:
            total += (float(watt) / 1000.0) * 0.5
    rem = float(hours) - full_half_hours * 0.5
    if rem > 0:
        h = int((float(start_hour) + full_half_hours / 2) % 24)
        if h in dr_set:
            total += (float(watt) / 1000.0) * rem
    return total


def calculate_schedule_dr_bonus(appliance_recs, selected, dr_mode, dr_hours, dr_reward, participation_rate=0.60, cap_ratio=0.10):
    """
    Schedule 탭용 DR 추가 보상금.
    DR OFF이면 0원, DR ON이면 기존 생활패턴 기준 대비 DR 시간대에서 회피된 전력량만 보상 대상으로 봅니다.
    에어컨은 완전 차단이 아니라 완화 운전 대상으로 보아 보상 산정에서 제외합니다.
    """
    if not dr_mode or not dr_hours:
        return {"available_kwh": 0.0, "recognized_kwh": 0.0, "bonus": 0, "cap_kwh": 0.0}

    avoided_kwh = 0.0
    total_schedulable_kwh = 0.0
    for rec in appliance_recs:
        name = rec.get("name")
        if name == "에어컨":
            continue
        info = selected.get(name, {})
        watt = float(info.get("watt", 0))
        hours = float(info.get("hours", rec.get("hours", 0)))
        total_schedulable_kwh += (watt / 1000.0) * hours

        baseline_start = float(rec.get("baseline_start", 0))
        rec_start = float(rec.get("start", 0))
        baseline_dr_kwh = _dr_overlap_kwh(watt, hours, baseline_start, dr_hours)
        rec_dr_kwh = _dr_overlap_kwh(watt, hours, rec_start, dr_hours)
        avoided_kwh += max(baseline_dr_kwh - rec_dr_kwh, 0.0)

    cap_kwh = total_schedulable_kwh * cap_ratio
    recognized_kwh = min(avoided_kwh * participation_rate, cap_kwh)
    bonus = int(round(recognized_kwh * float(dr_reward)))
    return {"available_kwh": avoided_kwh, "recognized_kwh": recognized_kwh, "bonus": bonus, "cap_kwh": cap_kwh}


def make_appliance_recommendations(selected, available, direct_available, dr_mode, dr_hours, dr_reward, current_hour, df_forecast, weather, dr_start=16, dr_end=19):
    """등록된 가전별로 개별 스케줄 추천 생성"""
    recs = []

    for name, info in selected.items():
        watt = info["watt"]
        hours = info["hours"]
        icon = APPLIANCE_ICONS.get(name, "⚡")
        now_cost = calc_appliance_cost(watt, hours, current_hour, dr_mode, dr_hours, dr_reward)

        if name == "에어컨":
            air = recommend_aircon_schedule(hours, current_hour, available, direct_available, dr_mode, dr_start, dr_end, dr_hours, dr_reward, df_forecast, weather)
            start = air["start"]
            display_hours = air["display_hours"]
            cost = calc_appliance_cost(watt, display_hours, start, dr_mode, dr_hours, dr_reward)
            recs.append({
                "name": name,
                "icon": icon,
                "start": start,
                "hours": display_hours,
                "cost": cost,
                "saving": max(now_cost - cost, 0),
                "tag": air["tag"],
                "reason": air["reason"],
                "variant": air["variant"],
            })
            continue

        if name in ["전기차 충전", "건조기"]:
            candidate = available if available else list(range(24))
            result = best_start_for_appliance(name, watt, hours, candidate, dr_mode, dr_hours, dr_reward, avoid_dr=True)
            tag = "고부하 이동"
            reason = "소비전력과 사용 시간이 커서, DR 시간대를 피하고 심야·경부하 시간대로 이동할 때 절감 효과가 큽니다."
            variant = "high"

        elif name in ["세탁기", "식기세척기"]:
            candidate = available if available else list(range(24))
            result = best_start_for_appliance(name, watt, hours, candidate, dr_mode, dr_hours, dr_reward, avoid_dr=True)
            tag = "예약 가능"
            reason = "예약 가능한 가전으로 보고, 취침·외출 허용 조건 안에서 가장 저렴한 시간대를 추천합니다."
            variant = ""

        elif name == "청소기":
            candidate = direct_available if direct_available else available
            result = best_start_for_appliance(name, watt, hours, candidate, dr_mode, dr_hours, dr_reward, avoid_dr=True)
            tag = "직접 사용"
            reason = "직접 사용하는 가전이므로 취침 시간과 외출 시간을 제외한 생활 가능 시간 안에서 추천합니다."
            variant = "direct"

        else:
            candidate = available if available else list(range(24))
            result = best_start_for_appliance(name, watt, hours, candidate, dr_mode, dr_hours, dr_reward, avoid_dr=True)
            tag = "자동 추천"
            reason = "생활패턴과 시간대별 요금을 반영해 사용 가능한 경부하 시간대를 추천합니다."
            variant = ""

        recs.append({
            "name": name,
            "icon": icon,
            "start": result["start"],
            "hours": hours,
            "cost": result["cost"],
            "saving": max(now_cost - result["cost"], 0),
            "tag": tag,
            "reason": reason,
            "variant": variant,
        })

    return recs

# ─── 도시 선택 + 날씨 (메인화면) ───
if "selected_city" not in st.session_state:
    st.session_state.selected_city = "서울"
alert_threshold = 150

# ─── AI 모델 로드 ───
MODEL_PATH = os.path.join(os.path.dirname(__file__), "dr_model_refit.pkl")

@st.cache_data(ttl=1800)  # 30분 캐시
def get_hourly_forecast(city_name):
    """오늘 시간별 기온/습도/강수확률 예보"""
    try:
        city = CITIES[city_name]
        url  = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude":  city["lat"],
            "longitude": city["lon"],
            "hourly": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation_probability",
            ],
            "timezone":     "Asia/Seoul",
            "forecast_days": 1,
        }
        res  = requests.get(url, params=params, timeout=5)
        data = res.json()["hourly"]
        df   = pd.DataFrame({
            "시간":   list(range(24)),
            "기온":   data["temperature_2m"],
            "습도":   data["relative_humidity_2m"],
            "강수확률": data["precipitation_probability"],
        })
        return df
    except:
        return None

def get_weather_alert(df_forecast, current_hour):
    """날씨 기반 가전 사용 경고 생성"""
    alerts = []
    remaining = df_forecast[df_forecast["시간"] > current_hour]
    if remaining.empty:
        return alerts

    max_temp    = remaining["기온"].max()
    max_temp_h  = remaining.loc[remaining["기온"].idxmax(), "시간"]
    min_temp    = remaining["기온"].min()
    max_rain_h  = remaining.loc[remaining["강수확률"].idxmax(), "시간"]
    max_rain    = remaining["강수확률"].max()

    # 에어컨 경고
    if max_temp >= 33:
        alerts.append({
            "type":  "danger",
            "icon":  "❄️",
            "title": f"{int(max_temp_h)}시 {max_temp:.1f}도 예상 — 에어컨 사용 급증 예상",
            "desc":  f"입력하신 에어컨 사용 시간보다 실제로 더 쓸 수 있어요. 새벽 시간대로 미리 냉방하세요.",
            "device": "에어컨"
        })
    elif max_temp >= 28:
        alerts.append({
            "type":  "warn",
            "icon":  "❄️",
            "title": f"{int(max_temp_h)}시 {max_temp:.1f}도 예상 — 에어컨 사용 증가 가능",
            "desc":  f"더운 날씨가 예상됩니다. 피크 시간 전에 미리 냉방하는 것을 추천해요.",
            "device": "에어컨"
        })

    # 히터 경고
    if min_temp <= 3:
        alerts.append({
            "type":  "danger",
            "icon":  "🔥",
            "title": f"최저 {min_temp:.1f}도 예상 — 히터 사용 급증 예상",
            "desc":  f"매우 추운 날씨가 예상됩니다. 심야 저렴한 시간대에 미리 예열하세요.",
            "device": "히터"
        })
    elif min_temp <= 8:
        alerts.append({
            "type":  "warn",
            "icon":  "🔥",
            "title": f"최저 {min_temp:.1f}도 예상 — 난방 수요 증가 가능",
            "desc":  f"쌀쌀한 날씨가 예상됩니다. 저녁 피크 전에 미리 난방하세요.",
            "device": "히터"
        })

    # 강수 경고
    if max_rain >= 70:
        alerts.append({
            "type":  "info",
            "icon":  "🌧️",
            "title": f"{int(max_rain_h)}시 강수 확률 {max_rain}% — 실내 활동 증가 예상",
            "desc":  "비 오는 날은 실내 전력 사용량이 평소보다 증가할 수 있어요.",
            "device": None
        })

    return alerts

@st.cache_resource
def load_model():
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH,'rb') as f:
            return pickle.load(f)
    return None

model_data = load_model()
ai_loaded  = model_data is not None

def predict_now(month, hour, weekday, is_weekend, avg_temp=20, max_temp=25, min_temp=15, humidity=60, rain=0):
    if not ai_loaded: return None, None
    model     = model_data['model']
    threshold = model_data['peak_threshold']
    features  = model_data['features']

    # REFIT 모델 피처로 변환
    # weekday: Python 0=월~6=일 그대로 사용
    # House_Num: 평균 가정(3) 기준
    # Day_of_Year: 월/일로 근사 계산
    import datetime as dt_module
    today = dt_module.date.today()
    day_of_year = today.timetuple().tm_yday
    minute = 0  # 현재 분은 0으로 기본

    X = pd.DataFrame([{
        'Hour':        hour,
        'Minute':      minute,
        'Month':       month,
        'Is_Weekend':  int(is_weekend),
        'Day_Num':     weekday,
        'Day_of_Year': day_of_year,
        'House_Num':   3,  # 평균 가정 기준
    }])[features]
    pred = model.predict(X)[0]
    # W 단위로 반환 (기존 kWh와 구분)
    pred_w = round(pred, 1)
    pred_kwh = round(pred * 0.25 / 1000, 3)  # 15분 기준 kWh
    return pred_w, pred_w >= threshold

# ─── 현재 상태 ───
now           = datetime.now()
current_hour  = now.hour
current_month = now.month
current_price = HOURLY_PRICES[current_hour]
status        = get_status(current_price)
peak_price    = max(HOURLY_PRICES)
saving_pct    = round((1-current_price/peak_price)*100)
is_weekend    = now.weekday()>=5

# 날씨는 도시 선택 이후에 로드되므로 여기선 기본값 사용
# (실제 날씨 연동은 도시 선택 후 아래에서 처리)
ai_usage, ai_is_peak = predict_now(
    current_month, current_hour, now.weekday(), is_weekend
)

status_info = {
    "cheap":     ("지금 · 저렴한 요금",     "전기 저렴해요!",        "대형 가전 지금 돌리세요"),
    "normal":    ("지금 · 보통 요금",        "평상시 수준이에요",      "일반 가전 사용은 괜찮아요"),
    "expensive": ("지금 · 높은 요금",        "요금이 높은 시간대예요", "대형 가전 사용을 미뤄주세요"),
    "peak":      ("지금 · 피크 요금",     "최대 피크 시간이에요",  "에어컨·건조기 즉시 중단 권장"),
}
s_tag, s_main, s_desc = status_info[status]

# ─── 메인 화면 CLEAN ───
city_list = list(CITIES.keys())
cur_idx = city_list.index(st.session_state.selected_city)
sel_l, sel_c, sel_r = st.columns([5.2, 2.2, 2.6])
with sel_r:
    st.markdown('<div class="floating-city-label">실시간 기상 지역</div>', unsafe_allow_html=True)
    chosen = st.selectbox("실시간 기상 지역", city_list, index=cur_idx, key="city_main", label_visibility="collapsed")
    if chosen != st.session_state.selected_city:
        st.session_state.selected_city = chosen
        st.rerun()

selected_city = st.session_state.selected_city
weather = get_weather(selected_city)
if weather is None:
    weather = {"temp": 20.0, "humidity": 60, "precip": 0.0, "wind": 0.0, "desc": "알 수 없음 ❓"}

_temp = weather["temp"]
_humi = weather["humidity"]
_prec = weather["precip"]
ai_usage, ai_is_peak = predict_now(
    current_month, current_hour, now.weekday(), is_weekend,
    avg_temp=_temp, max_temp=_temp+3, min_temp=_temp-3,
    humidity=_humi, rain=_prec
)

ai_txt = f"{ai_usage}W" if ai_usage else "미실행"
ai_is_safe = (not ai_is_peak) if (ai_is_peak is not None) else True
ai_hint_txt = "피크 위험 낮음" if ai_is_safe else "피크 위험 높음"

# AI 피크 위험도 계산
if ai_usage is not None and ai_loaded:
    peak_threshold = model_data.get("peak_threshold", 700)
    ai_risk_pct = min(round(ai_usage / peak_threshold * 100), 100)
else:
    peak_threshold = 700
    ai_risk_pct = 0

if ai_risk_pct >= 80:
    ai_status_text = "주의"
    ai_status_desc = "피크 위험 높음"
    ai_action_text = '<span class="main">현재 사용량이 피크 기준에 가까워요.</span><span class="sub">고전력 가전은 DR 이후 또는 경부하 시간대로 이동하는 것을 권장합니다.</span>'
elif ai_risk_pct >= 60:
    ai_status_text = "관심"
    ai_status_desc = "피크 위험 보통"
    ai_action_text = '<span class="main">전력 사용량이 증가하는 구간이에요.</span><span class="sub">건조기·전기차 충전은 저요금 시간대로 미뤄보세요.</span>'
else:
    ai_status_text = "안전"
    ai_status_desc = "피크 위험 낮음"
    ai_action_text = '<span class="main">현재는 피크 위험이 낮아요.</span><span class="sub">일반 가전 사용은 무리 없습니다.</span>'


min_price = min(HOURLY_PRICES)
min_hour = HOURLY_PRICES.index(min_price)
monthly_fee_est, monthly_saving_est = get_home_billing_summary()

ai_marker_x = round(8 + (current_hour / 24) * 250, 1)
ai_marker_y = round(78 - (current_hour / 24) * 38 + (6 if 9 <= current_hour <= 15 else 0), 1)
ai_label_x = round(max(22, min(238, ai_marker_x)), 1)
ai_label_rect_x = round(max(4, min(214, ai_label_x - 21)), 1)

dr_start_home = to_24h(
    st.session_state.get("dr_sh", 4),
    st.session_state.get("dr_sa", "오후")
)
dr_end_home = to_24h(
    st.session_state.get("dr_eh", 7),
    st.session_state.get("dr_ea", "오후")
)
dr_time_home = f"{dr_start_home:02d}:00–{dr_end_home:02d}:00"
dr_reward_home = st.session_state.get("dr_reward", 150)

home_apps = st.session_state.get("app_list3", [])
home_app_html = ""
if home_apps:
    seen_home_apps = []
    for item in home_apps:
        name = item.get("name", "")
        if name and name not in seen_home_apps:
            seen_home_apps.append(name)
    for name in seen_home_apps[:5]:
        icon = APPLIANCE_ICONS.get(name, "⚡")
        home_app_html += f'<div class="app-marker"><span class="emoji">{icon}</span>{name}</div>'
    schedule_desc = f"{min_hour:02d}:00 이후 등록 가전의 저렴 시간대 사용을 추천드려요."
else:
    schedule_desc = "등록된 가전이 없습니다. Schedule 탭에서 사용할 가전을 추가해보세요."

st.markdown(f"""
<div class="home-bg-shell">
<div class="home-dashboard-grid">

<div class="glass-panel left-ref-panel">
<div class="left-ref-title">오늘의 전기 사용,<br>가장 좋은 시간은?</div>
<div class="left-ref-date">{now.strftime("%Y년 %m월 %d일 %H:%M")}</div>
<div class="left-status-chip">{s_tag.replace("지금 · ", "")}</div>
<div class="left-status-text">{s_main}</div>
<div class="left-main-price">{current_price}<span>원/kWh</span></div>
<div class="left-peak-chip">최대부하 대비 {saving_pct}% 낮음 ↓</div>
<div class="left-ref-divider"></div>

<div class="left-summary-grid">
<div class="summary-tile min-wide">
<div class="summary-label">오늘 최저 요금</div>
<div class="summary-value">{min_price}<span>원/kWh</span></div>
<div class="summary-hint">{min_hour:02d}:00 이후 가장 저렴해요</div>
</div>
<div class="summary-tile wide">
<div class="summary-pair-wrap">
<div>
<div class="summary-label">월 예상 요금</div>
<div class="summary-value">{monthly_fee_est:,}<span>원</span></div>
<div class="summary-hint">300kWh 기준 시뮬레이션</div>
</div>
<div class="summary-divider"></div>
<div>
<div class="summary-label">절감 가능액</div>
<div class="summary-value">{monthly_saving_est:,}<span>원</span></div>
<div class="summary-hint">스케줄 최적화 적용 시</div>
</div>
</div>
</div>
</div>
</div>

<div class="center-copy">
<div class="center-copy-title">Smart DR Home Scheduler</div>
<div class="center-copy-sub">실시간으로 전기 사용 현황을 확인하고,<br>최적의 사용 시간을 추천받아 보세요.</div>
</div>
<div class="home-spacer"></div>

<div class="glass-panel top-weather-card">
<div class="weather-card-head">
<span>실시간 날씨</span>
<span class="weather-mini-icon">🌤️</span>
</div>
<div class="weather-region-pill">현재 지역 · {selected_city}</div>
<div class="weather-card-body">
<div class="weather-left">
<div class="weather-main-temp">{weather['temp']}°C</div>
<div class="weather-main-desc">{weather['desc']}</div>
</div>
<div class="weather-detail-grid">
<div><span>습도</span><strong>{weather['humidity']}%</strong></div>
<div><span>바람</span><strong>{weather['wind']}m/s</strong></div>
<div><span>강수량</span><strong>{weather['precip']}mm</strong></div>
</div>
</div>
</div>

<div class="glass-panel right-ai-panel">
<div class="right-ai-top">
<div class="right-ai-label">AI 피크 예측</div>
<div class="ai-badge">AI</div>
</div>
<div class="ai-status-row">
<div>
<div class="right-ai-main">{ai_status_text}</div>
<div class="right-ai-sub">{ai_status_desc}</div>
</div>
<div class="ai-load-box">
<div class="ai-load-label">예상 부하</div>
<div class="ai-load-value">{ai_txt}</div>
</div>
</div>
<div class="ai-risk-box">
<div class="ai-risk-top">
<span>피크 위험도</span>
<strong>{ai_risk_pct}%</strong>
</div>
<div class="ai-risk-bar">
<div class="ai-risk-fill" style="width:{ai_risk_pct}%;"></div>
</div>
<div class="ai-action-text">{ai_action_text}</div>
</div>
</div>

<a class="glass-panel dr-notice-card" href="#dr-event-section">
<div class="dr-notice-left">
<span class="dr-notice-icon">🔔</span>
<div>
<div class="dr-notice-title">전력회사 DR 알림</div>
<div class="dr-notice-sub">{dr_time_home} 감축 요청 확인하기</div>
<div class="dr-notice-meta">DR 이벤트 시간대 · {dr_reward_home}원/kWh 인센티브</div>
</div>
</div>
<span class="dr-notice-arrow">→</span>
</a>

</div>

<div class="bottom-dashboard-row">
<div class="schedule-dock">
<div>
<div class="schedule-dock-title"><span class="schedule-calendar-icon">📅</span>추천 사용 스케줄</div>
<div class="schedule-dock-desc">{schedule_desc}</div>
</div>
<div class="dock-timeline">
<div class="best-time-chip">{min_hour:02d}:00 가장 저렴해요</div>
<div class="dock-hours"><span>00:00</span><span>03:00</span><span>06:00</span><span>09:00</span><span>12:00</span><span>15:00</span><span>18:00</span><span>24:00</span></div>
<div class="dock-line"></div>
<div class="appliance-row">{home_app_html}</div>
</div>
<a class="schedule-button" href="#schedule-section">스케줄 보기 →</a>
</div>
</div>

</div>
""", unsafe_allow_html=True)

st.markdown('<div id="schedule-section"></div>', unsafe_allow_html=True)

# ─── 탭 ───
tab2, tab3, tab_sim = st.tabs(["Schedule", "Billing", "Simulator"])

# ══════════════════════════════════════════
# 탭1 — 가전 추천
# ══════════════════════════════════════════
# ══════════════════════════════════════════
# 탭2 — 스케줄 최적화
# ══════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-lbl">생활패턴 설정</div>', unsafe_allow_html=True)

    with st.expander("⚙️ 생활패턴 입력하기", expanded=True):
        lc1, lc2 = st.columns(2)
        with lc1:
            st.markdown("**기상 시간**")
            w1,w2 = st.columns(2)
            wh = w1.number_input("시", 1, 12, 7, key="wake_h", label_visibility="collapsed")
            wa = w2.selectbox("오전/오후", ["오전","오후"], key="wake_ap", label_visibility="collapsed")
            wake_hour = to_24h(wh, wa)

            st.markdown("**취침 시간**")
            s1,s2 = st.columns(2)
            sh = s1.number_input("시", 1, 12, 11, key="sleep_h", label_visibility="collapsed")
            sa = s2.selectbox("오전/오후", ["오전","오후"], index=1, key="sleep_ap", label_visibility="collapsed")
            sleep_hour = to_24h(sh, sa)

        with lc2:
            st.markdown("**외출 시작 시간**")
            ws1,ws2 = st.columns(2)
            wsh = ws1.number_input("시", 1, 12, 9,  key="ws_h", label_visibility="collapsed")
            wsa = ws2.selectbox("오전/오후", ["오전","오후"], key="ws_ap", label_visibility="collapsed")
            work_start = to_24h(wsh, wsa)

            st.markdown("**귀가 시간**")
            we1,we2 = st.columns(2)
            weh = we1.number_input("시", 1, 12, 6,  key="we_h", label_visibility="collapsed")
            wea = we2.selectbox("오전/오후", ["오전","오후"], index=1, key="we_ap", label_visibility="collapsed")
            work_end = to_24h(weh, wea)

            st.caption("일반 가정을 기준으로 기상·취침·외출 시간만 반영합니다. 예약 허용 여부는 가전 추가 단계에서 기기별로 선택합니다.")

    # 전체 후보 시간은 24시간으로 두고, 취침/외출 허용 여부는 가전별 옵션에서 판단
    commute = "일반 가정"
    available = list(range(24))
    direct_available = []
    for h in range(24):
        sleeping = (h>=sleep_hour or h<wake_hour)
        away = work_start <= h < work_end
        # 직접 사용하는 가전은 사용자가 깨어 있고 집에 있는 시간만 후보로 사용
        if (not sleeping) and (not away):
            direct_available.append(h)

    st.divider()



    st.markdown('<div class="section-lbl">사용할 가전기기 추가</div>', unsafe_allow_html=True)
	
    if "app_list3" not in st.session_state:
        st.session_state.app_list3 = []

    ac1, ac2, ac3, ac4, ac5 = st.columns([3.05, 1.28, 1.45, 1.45, 0.95])
    new_app = ac1.selectbox("가전기기", list(APPLIANCE_WATT.keys()),
                             format_func=lambda x: f"{APPLIANCE_ICONS[x]} {x} ({APPLIANCE_WATT[x]}W)",
                             label_visibility="collapsed")
    new_hrs = ac2.number_input("사용 시간(시간)", 0.5, 12.0, 1.0, 0.5, label_visibility="collapsed")
    new_allow_sleep = ac3.checkbox("취침 중 사용 허용", value=True, key="new_allow_sleep", help="체크하면 취침 시간에도 이 가전을 예약 운전할 수 있습니다.")
    new_allow_away = ac4.checkbox("외출 중 사용 허용", value=True, key="new_allow_away", help="체크하면 외출 시간에도 이 가전을 예약 운전할 수 있습니다.")
    if ac5.button("➕ 추가", width="stretch"):
        st.session_state.app_list3.append({
            "name":new_app,"watt":APPLIANCE_WATT[new_app],
            "hours":new_hrs,"icon":APPLIANCE_ICONS[new_app],
            "allow_sleep":new_allow_sleep,"allow_away":new_allow_away,
        })
        st.rerun()

    if st.session_state.app_list3:
        for idx,item in enumerate(st.session_state.app_list3):
            ic1,ic2,ic3,ic4,ic5,ic6 = st.columns([2.2,1.05,1.45,1.45,1.1,0.55])
            ic1.markdown(f"{item['icon']} **{item['name']}**")
            ic2.markdown(f"⏱ {item['hours']}시간")
            ic3.markdown("🌙 취침 예약 " + ("허용" if item.get("allow_sleep", True) else "제외"))
            ic4.markdown("🏠 외출 예약 " + ("허용" if item.get("allow_away", True) else "제외"))
            ic5.markdown(f"🔋 {item['watt']/1000*item['hours']:.2f} kWh")
            if ic6.button("🗑", key=f"del3_{idx}"):
                st.session_state.app_list3.pop(idx)
                st.rerun()


    # ── DR 이벤트 입력 ──

    st.markdown('<div id="dr-event-section"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-lbl">DR 이벤트 설정</div>', unsafe_allow_html=True)
    st.caption("전력회사 DR 알림을 수신하면 해당 이벤트 시간과 보상 단가가 자동으로 반영됩니다.")

    if "dr_notice_received" not in st.session_state:
        st.session_state.dr_notice_received = False

    if "dr_msg" not in st.session_state:
        st.session_state.dr_msg = ""

    if "dr_participate_key" not in st.session_state:
        st.session_state.dr_participate_key = False

    notice_col1, notice_col2 = st.columns([2, 1])

    with notice_col1:
        if st.button("전력회사 DR 알림 수신", width="stretch"):
            st.session_state.dr_notice_received = True
            st.session_state.dr_participate_key = True

            st.session_state.dr_sh = 4
            st.session_state.dr_sa = "오후"
            st.session_state.dr_eh = 7
            st.session_state.dr_ea = "오후"
            st.session_state.dr_reward = 150

            st.session_state.dr_msg = (
                "오늘 16:00~19:00 전력 피크가 예상됩니다. "
                "해당 시간대 전력 사용을 줄이면 150원/kWh 인센티브가 지급됩니다."
            )
            st.rerun()

    with notice_col2:
        if st.button("DR 알림 초기화", width="stretch"):
            st.session_state.dr_notice_received = False
            st.session_state.dr_participate_key = False
            st.session_state.dr_msg = ""
            st.rerun()

    if st.session_state.dr_notice_received:
        st.markdown(f"""
        <div class="dr-alert-card">
          <div class="dr-alert-head">
            <div class="dr-alert-title">전력회사 DR 이벤트 알림</div>
            <div class="dr-alert-chip">16:00 – 19:00</div>
          </div>
          <div class="dr-alert-desc">
            <div>오늘 저녁 피크 시간대 전력 수요가 높을 것으로 예상됩니다. 등록 가전은 가능한 한 DR 시간대를 피해 자동 스케줄링됩니다.</div>
            <div class="dr-alert-subline">감축 실적은 <strong>{st.session_state.get("dr_reward", 150)}원/kWh</strong> 기준으로 계산하며, 월간 환산에는 DR 참여율 60%와 월 사용량 10% 보상 상한을 적용합니다.</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    dr_participate = st.toggle(
        "⚡ DR 이벤트 참여하기",
        key="dr_participate_key",
        help="DR 이벤트 참여 시 해당 시간대 전력 감축 → 인센티브 지급"
    )

    if dr_participate:
        dr_col1, dr_col2, dr_col3 = st.columns(3)
        with dr_col1:
            st.markdown("**DR 시작 시간**")
            dc1, dc2 = st.columns(2)
            dr_sh = dc1.number_input("시", 1, 12, 4, key="dr_sh", label_visibility="collapsed")
            dr_sa = dc2.selectbox("오전/오후", ["오전","오후"], index=1, key="dr_sa", label_visibility="collapsed")
            dr_start = to_24h(dr_sh, dr_sa)
        with dr_col2:
            st.markdown("**DR 종료 시간**")
            de1, de2 = st.columns(2)
            dr_eh = de1.number_input("시", 1, 12, 7, key="dr_eh", label_visibility="collapsed")
            dr_ea = de2.selectbox("오전/오후", ["오전","오후"], index=1, key="dr_ea", label_visibility="collapsed")
            dr_end = to_24h(dr_eh, dr_ea)
        with dr_col3:
            st.markdown("**보상 단가**")
            dr_reward = st.number_input(
                "원/kWh",
                min_value=50,
                max_value=500,
                value=150,
                step=10,
                key="dr_reward",
                label_visibility="collapsed"
            )

        dr_hours = list(range(dr_start, dr_end)) if dr_end > dr_start else []
        st.markdown(f"""
        <div class="dr-summary-card">
          <div class="dr-summary-text">
            DR 적용 시간: <strong>{dr_start:02d}:00 – {dr_end:02d}:00</strong>
            &nbsp;·&nbsp; 보상 단가: <strong>{dr_reward}원/kWh</strong>
            &nbsp;·&nbsp; 해당 시간대 사용을 최소화하도록 추천합니다.
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        dr_hours  = []
        dr_reward = 150
        dr_start  = 16
        dr_end    = 19
        st.caption("DR 이벤트에 참여하면 해당 시간대 전력을 줄인 만큼 인센티브를 받아요")

    dr_mode = dr_participate  # 기존 코드 호환

    selected = {}
    for item in st.session_state.app_list3:
        n=item["name"]
        if n in selected:
            selected[n]["hours"] += item["hours"]
            # 같은 가전을 중복 추가한 경우에는 더 보수적인 제약을 적용
            selected[n]["allow_sleep"] = selected[n].get("allow_sleep", True) and item.get("allow_sleep", True)
            selected[n]["allow_away"] = selected[n].get("allow_away", True) and item.get("allow_away", True)
        else:
            selected[n]={
                "watt":item["watt"],
                "hours":item["hours"],
                "allow_sleep":item.get("allow_sleep", True),
                "allow_away":item.get("allow_away", True),
            }

    if not selected:
        pass
    else:
        calc_col, reset_col = st.columns([4, 1])
        calc_clicked = calc_col.button("최적 시간 계산하기 →", width="stretch")
        if reset_col.button("전체 초기화", width="stretch"):
            st.session_state.app_list3 = []
            st.session_state.do_calc = False
            st.rerun()
        if calc_clicked:
            st.session_state.do_calc = True

        if calc_clicked or st.session_state.get("do_calc", False):
            # 추천 스케줄 계산에 필요한 날씨 예보를 먼저 준비
            df_forecast = get_hourly_forecast(selected_city)
            if df_forecast is None:
                df_forecast = pd.DataFrame()

            # 에어컨 최적화에 사용할 현재 기온·습도/시간별 예보를 scheduler.py로 전달
            current_temp_for_schedule = float(_temp) if _temp is not None else None
            current_humidity_for_schedule = float(_humi) if _humi is not None else None
            hourly_temps_for_schedule = None
            hourly_humidity_for_schedule = None
            if not df_forecast.empty and {"시간", "기온"}.issubset(df_forecast.columns):
                hourly_temps_for_schedule = {
                    int(row["시간"]): float(row["기온"])
                    for _, row in df_forecast[["시간", "기온"]].dropna().iterrows()
                }
            if not df_forecast.empty and {"시간", "습도"}.issubset(df_forecast.columns):
                hourly_humidity_for_schedule = {
                    int(row["시간"]): float(row["습도"])
                    for _, row in df_forecast[["시간", "습도"]].dropna().iterrows()
                }

            # 요금/스케줄 계산
            # scheduler.py가 있으면 현실 제약 기반 최적화 모듈을 사용하고,
            # 없으면 기존 내부 계산 로직으로 동작합니다.
            if SCHEDULER_READY and optimize_appliance_schedule is not None:
                schedule_result = optimize_appliance_schedule(
                    selected=selected,
                    current_hour=current_hour,
                    available_hours=available,
                    wake_hour=wake_hour,
                    sleep_hour=sleep_hour,
                    work_start=work_start,
                    work_end=work_end,
                    commute=commute,
                    dr_mode=dr_mode,
                    dr_hours=dr_hours,
                    dr_reward=dr_reward,
                    appliance_icons=APPLIANCE_ICONS,
                    rate_func=get_rate,
                    current_temp=current_temp_for_schedule,
                    hourly_temps=hourly_temps_for_schedule,
                    current_humidity=current_humidity_for_schedule,
                    hourly_humidity=hourly_humidity_for_schedule,
                )

                hourly_costs = schedule_result["hourly_costs"]
                now_cost = schedule_result["now_cost"]
                optimal = schedule_result["optimal"]
                opt_h = schedule_result["optimal_hour"]
                opt_cost = schedule_result["optimal_cost"]
                saving = max(schedule_result["saving"], 0)
                sav_pct = schedule_result["saving_pct"]
                now_tou_cost = hourly_costs[current_hour]["TOU요금"]
                opt_tou_cost = optimal["TOU요금"]
                dr_incentive = 0  # 스케줄 단계에서는 DR 단가 할인을 적용하지 않음
                avail_c = [h for h in hourly_costs if h["시작시간"] in available] or hourly_costs

                def fmt_hour_label(hour_float):
                    hour_float = hour_float % 24
                    hh = int(hour_float)
                    mm = int(round((hour_float - hh) * 60))
                    if mm == 60:
                        hh = (hh + 1) % 24
                        mm = 0
                    return f"{hh:02d}:{mm:02d}"

                display_duration = max([info["hours"] for info in selected.values()]) if selected else 1
                top3 = schedule_result["top3"]

                appliance_recs = []
                for pl in schedule_result["per_appliance_plan"]:
                    name = pl["name"]
                    hours = pl["hours"]
                    start_h = pl["start"]
                    cost = pl["cost"] if pl["cost"] is not None else calc_appliance_cost(
                        selected[name]["watt"], hours, start_h, dr_mode, dr_hours, dr_reward
                    )
                    now_one = calc_appliance_cost(
                        selected[name]["watt"], hours, current_hour, dr_mode, dr_hours, dr_reward
                    )

                    if name == "에어컨":
                        tag, variant = pl.get("constraint_note", "온습도 연동 냉방"), "air"
                        humi_txt = f", 습도 {current_humidity_for_schedule:.0f}%" if current_humidity_for_schedule is not None else ""
                        apparent_temp = current_temp_for_schedule
                        if current_temp_for_schedule is not None and current_humidity_for_schedule is not None:
                            apparent_temp = current_temp_for_schedule + min(max(current_humidity_for_schedule - 60.0, 0.0) * 0.07, 2.5)
                        if apparent_temp is not None and apparent_temp >= 30:
                            reason = f"현재 기온 {current_temp_for_schedule:.1f}℃{humi_txt}로 체감 냉방 필요도가 높아 쾌적성을 우선했습니다. DR 시간대 사용을 금지하지 않고, 필요 시 설정온도 상향·제습 중심의 완화 운전을 권장합니다."
                        elif apparent_temp is not None and apparent_temp >= 27:
                            reason = f"현재 기온 {current_temp_for_schedule:.1f}℃{humi_txt}를 반영해 냉방·제습 필요성이 있다고 판단했습니다. 온습도에 따른 쾌적성을 우선하고, DR 시간대에는 완화 운전으로 피크 부하를 낮추도록 안내합니다."
                        elif apparent_temp is not None and apparent_temp >= 24:
                            reason = f"현재 기온 {current_temp_for_schedule:.1f}℃{humi_txt}로 냉방 필요성이 크지는 않아, 전기요금 단가와 사용 편의성을 함께 고려해 추천했습니다."
                        elif current_temp_for_schedule is not None:
                            reason = f"현재 기온 {current_temp_for_schedule:.1f}℃{humi_txt}로 냉방 우선순위를 낮췄습니다. 무리한 에어컨 사용보다 자연 환기나 단시간 운전을 우선 고려하도록 판단했습니다."
                        else:
                            reason = "현재 온습도 데이터를 가져오지 못해 기본 냉방 시간대와 사용 편의성을 중심으로 추천했습니다."
                    elif name == "전기차 충전":
                        tag, variant = "고부하 이동", "high"
                        reason = "전기차 충전은 소비전력과 사용시간이 큰 고부하 가전입니다. 취침·외출 중 예약 사용이 가능하므로 DR 시간대와 최대부하 시간대(16~22시)를 피하고, 경부하 시간대(22~08시) 안에서 충전이 끝나도록 배치했습니다."
                    elif name == "건조기":
                        tag, variant = "세탁 후 건조", "high"
                        reason = "건조기는 세탁이 끝난 뒤 사용하는 가전으로 보고, 세탁기 종료 시각 이후에만 배치했습니다. 동시에 DR 시간대와 늦은 야간 소음 시간대를 피하면서 사용 가능한 시간 중 요금이 낮은 구간을 선택했습니다."
                    elif name == "청소기":
                        tag, variant = "직접 사용", "direct"
                        reason = "청소기는 사용자가 직접 조작하는 가전이므로 취침 시간과 외출 시간을 제외한 생활 가능 시간만 후보로 보았습니다. 그중 DR 시간대와 최대부하 시간대를 피하고 비용 차이가 작은 시간대를 선택했습니다."
                    elif name == "세탁기":
                        tag, variant = "예약 가능", ""
                        reason = "세탁기는 예약 가능한 가전이지만 소음이 발생할 수 있어 늦은 밤·새벽 사용은 피했습니다. DR 시간대와 최대부하 시간대를 피하면서, 건조기와 함께 등록된 경우 건조기가 뒤이어 배치될 수 있도록 낮 시간대 후보를 우선 검토했습니다."
                    elif name == "식기세척기":
                        tag, variant = "예약 가능", ""
                        reason = "식기세척기는 예약 가능한 가전으로 보고, 취침·외출 예약 허용 여부와 소음 시간대를 함께 반영했습니다. 사용 가능 시간 중 DR 시간대를 피하고 전기요금 단가가 낮은 구간을 선택했습니다."
                    else:
                        tag, variant = "자동 추천", ""
                        reason = "시간대별 요금제(TOU), DR 시간대, 취침·외출 예약 허용 여부를 함께 반영해 사용 가능한 시간 중 전기요금 부담이 낮은 구간을 선택했습니다."

                    if not pl.get("moved", True):
                        tag = "현재 유지"
                        if name == "에어컨":
                            reason = "현재 배치가 온도·습도에 따른 냉방 필요성과 생활패턴 조건을 만족하고, 다른 시간대로 옮겨도 절감 효과가 크지 않아 유지했습니다. DR 시간대에는 사용을 금지하기보다 설정온도 상향·제습 중심 운전으로 피크 부하를 완화하는 방식으로 판단했습니다."
                        elif name == "건조기":
                            reason = "세탁기 종료 이후라는 사용 순서 제약을 만족하면서, 현재 배치와 추천 후보 간 비용 차이가 작아 이동하지 않도록 판단했습니다."
                        else:
                            reason = "현재 배치가 취침·외출 예약 조건과 가전별 제약을 만족하고, 다른 시간대로 옮겨도 절감 효과가 작아 현재 사용을 유지하도록 판단했습니다."

                    appliance_recs.append({
                        "name": name,
                        "icon": pl.get("icon", APPLIANCE_ICONS.get(name, "⚡")),
                        "start": start_h,
                        "hours": hours,
                        "cost": int(round(cost)),
                        "now_cost": int(round(now_one)),
                        "saving": max(now_one - int(round(cost)), 0),
                        "tag": tag,
                        "reason": reason,
                        "variant": variant,
                    })

            else:
                hourly_costs=[]
                for start in range(24):
                    t_tou=0; t_dr=0; detail=[]
                    for name,info in selected.items():
                        watt=info["watt"]; hours=info["hours"]
                        c_tou=0; c_dr=0
                        full_half_hours = int(hours * 2)
                        for off in range(full_half_hours):
                            h=int((start + off/2) % 24)
                            c_tou+=(watt/1000*0.5)*get_rate(h,False,dr_hours,dr_reward)
                            c_dr +=(watt/1000*0.5)*get_rate(h,True,dr_hours,dr_reward)
                        rem = hours - full_half_hours * 0.5
                        if rem > 0:
                            h=int((start + full_half_hours/2) % 24)
                            c_tou+=(watt/1000*rem)*get_rate(h,False,dr_hours,dr_reward)
                            c_dr +=(watt/1000*rem)*get_rate(h,True,dr_hours,dr_reward)
                        t_tou+=c_tou; t_dr+=c_dr
                        detail.append({"기기":f"{APPLIANCE_ICONS.get(name,'⚡')} {name}",
                                       "사용시간":f"{hours}시간",
                                       "시간대별 요금제(TOU) 요금":round(c_tou),"시간대별 요금제(TOU)+DR":round(c_dr),
                                       "DR 절약":round(c_tou-c_dr)})
                    hourly_costs.append({"시작시간":start,"TOU요금":round(t_tou),
                                         "TOU_DR요금":round(t_dr),
                                         "총요금":round(t_dr if dr_mode else t_tou),
                                         "detail":detail})

                now_cost = hourly_costs[current_hour]["총요금"]
                avail_c  = [h for h in hourly_costs if h["시작시간"] in available] or hourly_costs
                optimal  = min(avail_c, key=lambda x: x["총요금"])
                opt_h    = optimal["시작시간"]
                opt_cost = optimal["총요금"]
                saving   = max(now_cost-opt_cost, 0)
                sav_pct  = round(saving/now_cost*100) if now_cost>0 else 0
                now_tou_cost = hourly_costs[current_hour]["TOU요금"]
                opt_tou_cost = optimal["TOU요금"]
                dr_incentive = 0  # 스케줄 단계에서는 DR 단가 할인을 적용하지 않음

                def fmt_hour_label(hour_float):
                    hour_float = hour_float % 24
                    hh = int(hour_float)
                    mm = int(round((hour_float - hh) * 60))
                    if mm == 60:
                        hh = (hh + 1) % 24
                        mm = 0
                    return f"{hh:02d}:{mm:02d}"

                display_duration = max([info["hours"] for info in selected.values()]) if selected else 1
                top3 = sorted(avail_c, key=lambda x: x["총요금"])[:3]

                appliance_recs = make_appliance_recommendations(
                    selected=selected,
                    available=available,
                    direct_available=direct_available,
                    dr_mode=dr_mode,
                    dr_hours=dr_hours,
                    dr_reward=dr_reward,
                    current_hour=current_hour,
                    df_forecast=df_forecast,
                    weather=weather,
                    dr_start=dr_start,
                    dr_end=dr_end,
                )

            # 절감 비교 기준을 "기존 생활패턴 기준"이 아니라 일반 가정의 기존 생활패턴 기준으로 바꿉니다.
            # 예: 세탁기 18시, 건조기 세탁 직후, 전기차 20시, 청소기 19시, 식기세척기 21시, 에어컨 현재/주간 사용.
            appliance_recs = apply_lifestyle_baseline_costs(
                appliance_recs,
                selected,
                current_hour=current_hour,
                dr_hours=dr_hours,
                dr_reward=dr_reward,
            )

            # 세탁기·건조기 세트 최종 보정: 어떤 계산 경로를 타더라도 건조기가 세탁기 직후에 오도록 강제합니다.
            def _enforce_washer_dryer_chain(recs, selected_map):
                names = {r.get("name"): r for r in recs}
                if "세탁기" not in names or "건조기" not in names:
                    return recs
                washer = names["세탁기"]
                dryer = names["건조기"]
                washer_start = float(washer.get("start", 0)) % 24
                washer_hours = float(washer.get("hours", selected_map.get("세탁기", {}).get("hours", 2)))
                dryer_hours = float(dryer.get("hours", selected_map.get("건조기", {}).get("hours", 2)))
                # 건조기는 세탁 종료 직후를 우선 적용합니다.
                dryer_start = (washer_start + washer_hours) % 24
                dryer["start"] = dryer_start
                dryer["hours"] = dryer_hours
                dryer["cost"] = int(calc_appliance_cost(selected_map["건조기"]["watt"], dryer_hours, dryer_start, dr_mode, dr_hours, dr_reward))
                dryer["saving"] = max(int(dryer.get("baseline_cost", dryer.get("now_cost", 0))) - dryer["cost"], 0)
                dryer["tag"] = "세탁 직후 건조"
                dryer["reason"] = "세탁기와 건조기를 하나의 세탁·건조 세트로 묶어, 세탁 종료 직후 건조기가 이어지도록 배치했습니다. 사용 순서를 우선 만족한 뒤, DR 시간대와 소음 시간대를 함께 고려했습니다."
                washer["tag"] = "세탁·건조 세트"
                washer["reason"] = "건조기와 함께 등록되어 세탁·건조를 하나의 연속 작업으로 판단했습니다. 세탁이 먼저 끝나야 건조가 가능하므로, 건조기가 바로 이어질 수 있는 시간대를 우선 선택했습니다."
                return recs

            appliance_recs = _enforce_washer_dryer_chain(appliance_recs, selected)
            dr_bonus_info = calculate_schedule_dr_bonus(
                appliance_recs,
                selected,
                dr_mode=dr_mode,
                dr_hours=dr_hours,
                dr_reward=dr_reward,
                participation_rate=0.60,
                cap_ratio=0.10,
            )
            st.session_state["last_schedule_recs"] = [dict(r) for r in appliance_recs]
            st.session_state["last_schedule_selected"] = {k: dict(v) for k, v in selected.items()}
            st.session_state["last_schedule_dr_bonus"] = dict(dr_bonus_info)
            st.session_state["last_schedule_dr_mode"] = bool(dr_mode)
            sorted_recs = sorted(appliance_recs, key=lambda r: (r["start"], r["name"]))

            # ── 1) 계산 직후 가장 먼저 보이는 추천 스케줄표 ──
            hour_header = '<div class="smart-schedule-corner">가전 / 시간</div>'
            for h in range(24):
                is_dr_h = dr_mode and (h in dr_hours)
                hour_header += f'<div class="smart-hour-cell{" dr" if is_dr_h else ""}">{h:02d}</div>'

            rows_html = ""
            for rec in sorted_recs:
                cells = "".join([
                    '<div class="smart-track-bg"></div>'
                    for h in range(24)
                ])
                dr_overlay = ""
                if dr_mode and dr_hours:
                    dr_overlay = f'<div class="smart-dr-window" style="grid-column:{dr_start+1} / span {max(1, dr_end-dr_start)};grid-row:1;"></div>' 
                s = int(rec["start"] % 24)
                span = max(1, int(np.ceil(rec["hours"])))
                variant = rec["variant"] if rec["variant"] else "normal"
                time_label = f'{fmt_time(rec["start"])} – {fmt_time(rec["start"] + rec["hours"])}'

                blocks = ""
                compact_cls = " compact" if span <= 1 else ""
                if s + span <= 24:
                    blocks += (
                        f'<div class="smart-event {variant}{compact_cls}" style="grid-column:{s+1} / span {span};grid-row:1;">'
                        f'<div class="smart-event-name">{rec["icon"]} {rec["name"]}</div>'
                        f'<div class="smart-event-time">{time_label}</div></div>'
                    )
                else:
                    first_span = 24 - s
                    second_span = span - first_span
                    first_compact = " compact" if first_span <= 1 else ""
                    second_compact = " compact" if second_span <= 1 else ""
                    blocks += (
                        f'<div class="smart-event {variant}{first_compact}" style="grid-column:{s+1} / span {first_span};grid-row:1;">'
                        f'<div class="smart-event-name">{rec["icon"]} {rec["name"]}</div>'
                        f'<div class="smart-event-time">{time_label}</div></div>'
                    )
                    blocks += (
                        f'<div class="smart-event {variant}{second_compact}" style="grid-column:1 / span {min(second_span,24)};grid-row:1;">'
                        f'<div class="smart-event-name">{rec["icon"]} {rec["name"]}</div>'
                        f'<div class="smart-event-time">다음날 이어짐</div></div>'
                    )

                rows_html += (
                    f'<div class="smart-schedule-row">'
                    f'<div class="smart-device-label"><div class="smart-device-name">{rec["icon"]} {rec["name"]}</div>'
                    f'<div class="smart-device-meta">{rec["hours"]}시간 · {rec["cost"]:,}원</div></div>'
                    f'<div class="smart-track">{cells}{dr_overlay}{blocks}</div>'
                    f'</div>'
                )

            best_range = f'{fmt_hour_label(opt_h)} – {fmt_hour_label(opt_h + display_duration)}'
            st.markdown(f'''
            <div class="schedule-result-panel">
              <div class="schedule-result-head clean">
                <div>
                  <div class="schedule-result-title">오늘 추천 스케줄표</div>
                  <div class="schedule-result-sub">등록한 가전과 생활패턴을 반영해 오늘 사용하기 좋은 시간대를 배치했습니다.</div>
                </div>
              </div>
              <div class="smart-schedule-board">
                <div class="smart-schedule-hours">{hour_header}</div>
                {rows_html}
              </div>
              <div class="smart-schedule-legend">
                <span><i class="legend-dot"></i>추천 사용 시간</span>
                <span><i class="legend-dot dr"></i>DR 시간대</span>
                <span>· 시간은 24시간 기준으로 표시됩니다.</span>
              </div>
            </div>
            ''', unsafe_allow_html=True)

            # ── 2) 절감 요약 카드 ──
            # 표시된 가전별 추천 시간표와 같은 기준으로 합산합니다.
            # 기존 생활패턴 기준: 일반 가정의 기본 사용 시간대에 사용한다고 가정한 총 요금
            # 추천 스케줄 적용: 위 추천 시간표에 배치된 가전별 추천 시간의 총 요금
            now_display_cost = int(sum(rec.get("baseline_cost", rec.get("now_cost", 0)) for rec in sorted_recs)) if sorted_recs else int(now_cost)
            recommend_display_cost = int(sum(rec.get("cost", 0) for rec in sorted_recs)) if sorted_recs else int(opt_cost)
            tou_saving = max(now_display_cost - recommend_display_cost, 0)
            dr_bonus_amount = int(dr_bonus_info.get("bonus", 0)) if dr_mode else 0
            total_saving = tou_saving + dr_bonus_amount
            recommend_net_cost = max(recommend_display_cost - dr_bonus_amount, 0)
            display_sav_pct = round(total_saving / now_display_cost * 100) if now_display_cost > 0 else 0
            dr_bonus_note = (
                f"DR 회피 인정량&nbsp;{dr_bonus_info.get('recognized_kwh', 0):.2f} kWh&nbsp;×&nbsp;{dr_reward}원/kWh"
                if dr_mode and dr_bonus_amount > 0
                else "DR 미참여 상태라 보상금은 반영하지 않았습니다."
            )
            st.markdown(f'''
            <div class="saving-summary-card dr-split-summary">
              <div class="saving-summary-left">
                <div class="saving-summary-label">절감 요약</div>
                <div class="saving-summary-main">
                  기존 생활패턴 기준 <strong>{now_display_cost:,}원</strong>
                  <span class="saving-arrow">→</span>
                  추천 스케줄 적용 <strong>{recommend_net_cost:,}원</strong>
                </div>
                <div class="saving-summary-sub">
                  <div><strong>DR 미참여 절감액</strong> · 시간대별 요금제(TOU) 최적화로 <b>{tou_saving:,}원</b> 절감</div>
                  <div><strong>DR 참여 추가 절감액</strong> · DR 회피 보상금 <b>{dr_bonus_amount:,}원</b> 반영</div>
                  <div><strong>총 절감액</strong> · TOU 절감액 + DR 보상금 = <b>{total_saving:,}원</b></div>
                </div>
              </div>
              <div class="saving-summary-right">
              <div class="saving-summary-chip">총 예상 절감</div>
              <div class="saving-summary-save">{total_saving:,}원</div>
              <div class="saving-summary-rate">약 {display_sav_pct}% 절감</div>
             </div>
            </div>
            ''', unsafe_allow_html=True)

            # ── 3) 가전별 상세 추천 이유 ──
            st.markdown('<div class="section-lbl reason-title">가전별 추천 이유</div>', unsafe_allow_html=True)
            detail_cards = ""
            for rec in sorted_recs:
                time_label = f'{fmt_time(rec["start"])} – {fmt_time(rec["start"] + rec["hours"])}'
                saving_txt = f'{rec["saving"]:,}원 절감' if rec["saving"] > 0 else "비용 차이 적음"

                short_reason = rec.get("reason", "시간대별 요금제(TOU), DR 시간대, 생활패턴 제약을 함께 반영해 추천했습니다.")

                detail_cards += (
                    f'<div class="reason-card">'
                    f'<div class="reason-card-main">'
                    f'<div class="reason-device">{rec["icon"]} {rec["name"]}</div>'
                    f'<div class="reason-time">{time_label}</div>'
                    f'</div>'
                    f'<div class="reason-metrics"><span>{rec["cost"]:,}원</span><span>{saving_txt}</span></div>'
                    f'<div class="reason-desc">{short_reason}</div>'
                    f'<div class="reason-tag">{rec["tag"]}</div>'
                    f'</div>'
                )
            st.markdown(f'<div class="reason-card-grid">{detail_cards}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════
# 탭3 — 요금 비교
# ══════════════════════════════════════════
with tab3:
    def _html_block(html: str):
        if hasattr(st, "html"):
            st.html(html)
        else:
            st.markdown(html, unsafe_allow_html=True)

    _html_block("""
    <div class="billing-report-head">
        <div class="billing-report-title">REFIT 5개 가구 평균 기반 요금 비교</div>
        <div class="billing-report-desc">
            REFIT House 1~5의 15분 단위 전력 데이터를 평균 사용량으로 환산하고, 최근 사용 패턴이 유지된다고 가정했을 때의 월간 환산 요금을 비교합니다.<br>
            실제 미래 요금을 단정하는 값이 아니라, 동일 사용 패턴에서 누진제·시간대별 요금제(TOU)·수요반응(DR) 참여에 따른 상대적 절감 효과를 보여주는 지표입니다.
        </div>
    </div>
    """)

    DATA_FILE_NAME = REFIT_BILLING_DATA_FILE

    billing_mode = st.radio(
        "사용량 산정 방식",
        ["REFIT 5개 가구 평균 기반", "직접 조정"],
        horizontal=True,
        label_visibility="collapsed",
        key="billing_mode",
    )

    df_refit, data_path = load_refit_billing_data()
    recent_days = 30
    dr_hours_for_billing = list(range(16, 19))
    incentive_rate_for_billing = 150
    dr_participation_rate_for_billing = 0.60

    billing_result = None
    usage_source = ""
    mode_note = ""
    monthly_usage_df = None
    data_period_note = ""

    if billing_mode == "REFIT 5개 가구 평균 기반" and df_refit is not None and BILLING_READY and billing_simulate_recent_pattern_bills is not None:
        try:
            billing_result = billing_simulate_recent_pattern_bills(
                df_refit,
                recent_days=recent_days,
                dr_hours=dr_hours_for_billing,
                incentive_rate=incentive_rate_for_billing,
                dr_participation_rate=dr_participation_rate_for_billing,
                month=datetime.now().month,
                household_count=5,
            )
            monthly_kwh = int(round(float(billing_result.get("월간환산사용량", billing_result.get("월간사용량", 300)))))
            prog = int(billing_result["누진제"])
            tou = int(billing_result["TOU"])
            dr = int(billing_result["TOU_DR최종"])
            monthly_usage_df = billing_result.get("월별사용량")
            data_start = billing_result.get("데이터시작")
            data_end = billing_result.get("데이터끝")
            recent_observed = billing_result.get("최근기간사용량", 0)
            recent_covered = billing_result.get("최근기간일수", recent_days)
            total_recent_observed = billing_result.get("최근기간전체사용량", 0)
            avg_house_count = billing_result.get("가구평균환산가구수", 5)
            usage_source = f"REFIT {avg_house_count}개 가구 평균 · 최근 {recent_covered}일 기준"
            data_period_note = f"데이터 기간: {pd.to_datetime(data_start).strftime('%Y-%m-%d')} ~ {pd.to_datetime(data_end).strftime('%Y-%m-%d')}" if data_start is not None and data_end is not None else ""
            mode_note = "REFIT House 1~5의 15분 누적 전력 데이터를 kWh로 변환한 뒤 5개 가구 평균으로 나누고, 최근 사용 패턴이 30일간 유지된다고 가정해 월간 환산 요금을 계산했습니다."
        except Exception as e:
            st.warning(f"REFIT 데이터 기반 요금 계산 중 오류가 발생해 직접 조정 방식으로 전환합니다: {e}")
            billing_mode = "직접 조정"

    if billing_mode == "REFIT 5개 가구 평균 기반" and df_refit is None:
        st.info(f"data 폴더에서 `{DATA_FILE_NAME}` 파일을 찾지 못했습니다. 파일을 `C:\\SmartEnergy\\Project\\data` 폴더에 넣으면 REFIT 데이터 기반 계산이 활성화됩니다.")
        billing_mode = "직접 조정"

    if billing_result is None:
        estimated_kwh = 300
        monthly_kwh = st.slider("월간 환산 사용량 (kWh)", 100, 600, estimated_kwh, 10)
        usage_source = "직접 조정한 월간 환산 사용량 기준"
        mode_note = "REFIT 데이터 파일이 없거나 직접 조정을 선택한 경우, 입력한 월간 사용량을 기준으로 요금제를 비교합니다."
        if BILLING_READY and billing_simulate_monthly_bills is not None:
            billing_result = billing_simulate_monthly_bills(
                monthly_kwh=monthly_kwh,
                dr_hours=dr_hours_for_billing,
                incentive_rate=incentive_rate_for_billing,
                dr_participation_rate=dr_participation_rate_for_billing,
                month=datetime.now().month,
            )
            prog = int(billing_result["누진제"])
            tou = int(billing_result["TOU"])
            dr = int(billing_result["TOU_DR최종"])
        else:
            prog = calc_progressive(monthly_kwh)
            tou  = calc_tou(monthly_kwh, False)
            dr   = calc_tou(monthly_kwh, True)

    expected_bill = dr
    monthly_effect = prog - dr
    annual_effect = monthly_effect * 12
    saving_rate = abs(monthly_effect) / prog * 100 if prog else 0

    if monthly_effect >= 0:
        effect_value = f"{monthly_effect:,}원"
        effect_label = "월간 환산 절감액"
        effect_pill = f"약 {saving_rate:.1f}% 절감"
        bill_sub = f"기존 누진제 대비 {monthly_effect:,}원 절감"
        save_class = "good"
        progress = min(100, max(12, int(round(saving_rate * 12))))
    else:
        effect_value = f"{abs(monthly_effect):,}원"
        effect_label = "월간 환산 추가 부담"
        effect_pill = f"약 {saving_rate:.1f}% 높음"
        bill_sub = f"현재 조건에서는 기존 누진제 대비 {abs(monthly_effect):,}원 높음"
        save_class = ""
        progress = 38

    tou_delta = prog - tou
    dr_delta = prog - dr
    tou_sub = f"기존 누진제 대비 {tou_delta:,}원 절감" if tou_delta >= 0 else f"기존 누진제 대비 {abs(tou_delta):,}원 높음"
    dr_sub = f"기존 누진제 대비 {dr_delta:,}원 절감" if dr_delta >= 0 else f"기존 누진제 대비 {abs(dr_delta):,}원 높음"
    tou_rate = abs(tou_delta) / prog * 100 if prog else 0
    dr_rate = abs(dr_delta) / prog * 100 if prog else 0
    tou_chip_class = "good" if tou_delta >= 0 else ""
    dr_chip_class = "best" if dr_delta >= 0 else ""

    # 월별 그래프: REFIT 데이터가 있으면 실제 월별 사용량, 없으면 월간 환산값 기반 예시 추이
    if monthly_usage_df is not None and len(monthly_usage_df) > 0:
        monthly_tail = monthly_usage_df.tail(6).copy()
        months = [str(m)[5:] + "월" if len(str(m)) >= 7 else str(m) for m in monthly_tail["월"].tolist()]
        usage_2025 = [int(round(float(v))) for v in monthly_tail["사용량(kWh)"].tolist()]
        # 일부 데이터프레임이 5가구 합산 월별 사용량을 담고 있으면 그래프도 평균으로 환산합니다.
        if usage_2025 and max(usage_2025) > max(int(monthly_kwh) * 1.8, 700):
            usage_2025 = [int(round(v / 5)) for v in usage_2025]
        avg_usage = int(round(sum(usage_2025) / len(usage_2025))) if usage_2025 else int(monthly_kwh)
        usage_2024 = [avg_usage for _ in usage_2025]
        chart_title = "REFIT 평균 월별 사용량"
        legend_left = "최근 6개월 평균"
        legend_right = "월별 평균"
    else:
        months = ["1월", "2월", "3월", "4월", "5월", "6월"]
        multipliers_2025 = [1.30, 1.17, 1.23, 1.07, .97, 1.00]
        usage_2025 = [int(round(monthly_kwh * m / 10) * 10) for m in multipliers_2025]
        usage_2025[-1] = int(monthly_kwh)
        usage_2024 = [int(round(v * r / 10) * 10) for v, r in zip(usage_2025, [1.09, 1.08, 1.10, 1.14, 1.11, 1.04])]
        chart_title = "월별 전기 사용량 추이"
        legend_left = "비교 기준"
        legend_right = "월간 환산"

    chart_max = max(1, max(usage_2024 + usage_2025) + 30)
    bar_html = ""
    for i, m in enumerate(months):
        h24 = max(8, usage_2024[i] / chart_max * 100)
        h25 = max(8, usage_2025[i] / chart_max * 100)
        current_cls = " current" if i == len(months) - 1 else ""
        bar_html += (
            f'<div class="billing-bar-group">'
            f'<div class="billing-bar gray" style="height:{h24:.1f}%"><span class="billing-bar-value">{usage_2024[i]}</span></div>'
            f'<div class="billing-bar yellow{current_cls}" style="height:{h25:.1f}%"><span class="billing-bar-value">{usage_2025[i]}</span></div>'
            f'</div>'
        )
    month_html = "".join([f"<div>{m}</div>" for m in months])

    last_month_kwh = usage_2025[-2] if len(usage_2025) >= 2 else int(monthly_kwh)
    kwh_diff = int(monthly_kwh) - int(last_month_kwh)
    if kwh_diff <= 0:
        usage_note = f"직전 월 {last_month_kwh} kWh 대비 ↓ {abs(kwh_diff)} kWh"
    else:
        usage_note = f"직전 월 {last_month_kwh} kWh 대비 ↑ {kwh_diff} kWh"

    carbon_reduction = max(0, round(abs(monthly_effect) / max(prog, 1) * monthly_kwh * 0.478, 1))
    tree_count = max(1, int(round(carbon_reduction / 6.6)))

    # 설명 문구는 계산 기준 카드에 통합되어 상단 중복 문구는 표시하지 않습니다.

    billing_top_html = f"""
    <div class="billing-overview-grid">
        <div class="billing-bill-card">
            <div>
                <div class="billing-card-label">평균 월간 환산 요금</div>
                <div class="billing-bill-value">{expected_bill:,}원</div>
                <div class="billing-card-sub">{bill_sub}</div>
            </div>
            <div class="billing-divider"></div>
            <div>
                <div class="billing-save-title">{effect_label}</div>
                <div class="billing-save-value {save_class}">{effect_value}</div>
                <div class="billing-save-pill">{effect_pill}</div>
                <div class="billing-card-sub" style="margin-top:14px;">기존 누진제 {prog:,}원<br><span class="billing-sub-arrow">↓</span> 환산 요금 {expected_bill:,}원</div>
            </div>
        </div>

        <div class="billing-side-stack">
            <div class="billing-side-card">
                <div class="billing-side-label">평균 월간 환산 사용량</div>
                <div class="billing-side-value">{monthly_kwh}<span>kWh</span></div>
                <div class="billing-side-note"><span>{usage_note}</span><span>{usage_source}</span></div>
            </div>
            <div class="billing-side-card soft">
                <div class="billing-side-label">예상 탄소 절감량</div>
                <div class="billing-side-value">{carbon_reduction}<span>kgCO₂e</span></div>
                <div class="billing-side-note">30년생 소나무 약 {tree_count}그루를 심는 효과</div>
            </div>
        </div>

    </div>
    """
    _html_block(billing_top_html)

    dr_incentive = int(billing_result.get("DR인센티브", 0)) if isinstance(billing_result, dict) else 0
    dr_reduced = billing_result.get("DR감축량", 0) if isinstance(billing_result, dict) else 0

    billing_bottom_html = f"""
    <div class="billing-lower-grid">
        <div class="billing-compare-wrap">
            <div class="billing-section-title">요금제별 월간 환산 요금 비교 <span>REFIT 평균 사용 패턴 · {monthly_kwh} kWh/월</span></div>
            <div class="billing-compare-grid">
                <div class="billing-plan-card">
                    <div class="billing-plan-top">
                        <div class="billing-plan-label">기존 누진제</div>
                        <div class="billing-plan-value">{prog:,}원</div>
                    </div>
                    <div class="billing-plan-sub">현행 주택용 누진제를 적용한<br>월간 환산 청구액입니다.</div>
                    <div class="billing-plan-chip">기존 요금</div>
                </div>
                <div class="billing-plan-card">
                    <div class="billing-plan-top">
                        <div class="billing-plan-label">시간대별 요금제(TOU)</div>
                        <div class="billing-plan-value">{tou:,}원</div>
                    </div>
                    <div class="billing-plan-sub">경부하·중간부하·최대부하 단가를 적용한<br>월간 환산 요금입니다.</div>
                    <div class="billing-plan-chip {tou_chip_class}">{tou_sub}<span>약 {tou_rate:.1f}%</span></div>
                </div>
                <div class="billing-plan-card recommend">
                    <div class="billing-plan-top">
                        <div class="billing-plan-label">시간대별 요금제(TOU) + DR 참여</div>
                        <div class="billing-plan-value">{dr:,}원</div>
                    </div>
                    <div class="billing-plan-sub">DR 참여율 60%와 보상 상한을 적용했습니다.<br>보상 {dr_incentive:,}원을 반영한 결과입니다.</div>
                    <div class="billing-plan-chip {dr_chip_class}">{dr_sub}<span>약 {dr_rate:.1f}%</span></div>
                </div>
            </div>
        </div>

        <div class="billing-point-card">
            <div class="billing-point-title">계산 기준</div>
            <div class="billing-point-list">
                <div class="billing-point-item"><span class="billing-point-check">✓</span><span>REFIT 5개 가구 데이터를 평균 사용량으로 환산했습니다.</span></div>
                <div class="billing-point-item"><span class="billing-point-check">✓</span><span>최근 사용 패턴이 유지된다고 가정해 30일 요금을 계산했습니다.</span></div>
                <div class="billing-point-item"><span class="billing-point-check">✓</span><span>시간대별 요금제(TOU)는 경부하·중간부하·최대부하 3단계 단가를 적용했습니다.</span></div>
                <div class="billing-point-item"><span class="billing-point-check">✓</span><span>DR 보상은 참여율 60%와 월 사용량 10% 상한을 반영했습니다.</span></div>
            </div>
            <div class="billing-progress-box">
                <div class="billing-progress-text"><span>월간 환산 절감 효과</span><strong>{progress}%</strong></div>
                <div class="billing-progress-track"><div class="billing-progress-fill" style="width:{progress}%"></div></div>
            </div>
        </div>
    </div>
    """
    _html_block(billing_bottom_html)


# ══════════════════════════════════════════
# 탭 Simulator — 최적화 적용 전후 비교
# ══════════════════════════════════════════
with tab_sim:
    def _sim_html(html: str):
        if hasattr(st, "html"):
            st.html(html)
        else:
            st.markdown(html, unsafe_allow_html=True)

    _sim_html("""
    <div class="sim-report-head">
        <div class="sim-report-title">최적화 시뮬레이터 적용 전후 비교</div>
        <div class="sim-report-desc">
            등록한 가전 중 스케줄 조정이 가능한 사용량을 기준으로 기존 사용 방식과 추천 스케줄 적용 후의 비용을 비교합니다.<br>
            집 전체 전기요금이 아니라, 등록 가전 중 스케줄 조정 가능한 사용량의 비용 절감 효과를 보여줍니다.
        </div>
    </div>
    """)

    schedule_recs = st.session_state.get("last_schedule_recs", [])

    if not schedule_recs:
        _sim_html("""
        <div class="sim-chart-card">
            <div class="sim-section-title">
                <div>등록 가전별 절감 효과</div>
                <span>Schedule 탭에서 가전을 등록하고 최적 시간 계산을 먼저 실행해 주세요.</span>
            </div>
            <div style="padding:24px 8px;color:#4e5968;font-weight:700;line-height:1.6;">
                이 화면은 Schedule 탭에서 계산된 가전별 추천 시간과 기존 생활패턴 기준 사용 시간을 비교해,<br>
                실제 등록한 가전별 절감액과 총 절감액만 보여줍니다.
            </div>
        </div>
        """)
    else:
        rows = []
        for rec in schedule_recs:
            before = int(round(rec.get("baseline_cost", rec.get("now_cost", 0))))
            after = int(round(rec.get("cost", 0)))
            saving = max(0, before - after)
            rate = saving / before * 100 if before else 0
            rows.append({
                "name": rec.get("name", "가전"),
                "icon": rec.get("icon", "⚡"),
                "before": before,
                "after": after,
                "saving": saving,
                "rate": rate,
                "start": rec.get("start", 0),
                "hours": rec.get("hours", 0),
            })

        total_before = sum(r["before"] for r in rows)
        total_after = sum(r["after"] for r in rows)
        total_saving = max(0, total_before - total_after)
        total_rate = total_saving / total_before * 100 if total_before else 0
        max_cost = max([total_before] + [r["before"] for r in rows]) or 1

        bar_html = ""
        for r in rows:
            before_w = max(8, r["before"] / max_cost * 100)
            after_w = max(8, r["after"] / max_cost * 100)
            bar_html += f"""
            <div class="sim-bar-row">
                <div class="sim-bar-name">{r['icon']} {r['name']}</div>
                <div class="sim-bar-pair">
                    <div class="sim-bar-track"><div class="sim-bar-fill before" style="width:{before_w:.1f}%"></div></div>
                    <div class="sim-bar-track"><div class="sim-bar-fill after" style="width:{after_w:.1f}%"></div></div>
                </div>
                <div class="sim-bar-value">기존 {r['before']:,}원<br>추천 {r['after']:,}원<br><strong>{r['saving']:,}원 절감</strong></div>
            </div>
            """

        ranked = sorted(rows, key=lambda x: x["saving"], reverse=True)
        max_saving = max([r["saving"] for r in ranked] + [1])
        rank_html = ""
        for idx, r in enumerate(ranked, 1):
            width = max(8, r["saving"] / max_saving * 100)
            rank_html += f"""
            <div class="sim-rank-row">
                <div class="sim-rank-num">{idx}</div>
                <div>
                    <div class="sim-rank-name">{r['icon']} {r['name']}</div>
                    <div class="sim-rank-sub">기존 {r['before']:,}원 → 추천 {r['after']:,}원 · 약 {r['rate']:.1f}% 절감</div>
                    <div class="sim-progress-track"><div class="sim-progress-fill" style="width:{width:.1f}%"></div></div>
                </div>
                <div class="sim-rank-save">{r['saving']:,}원</div>
            </div>
            """

        _sim_html(f"""
        <div class="sim-main-grid" style="margin-top:0;">
            <div class="sim-chart-card">
                <div class="sim-section-title">
                    <div>등록 가전별 절감 효과</div>
                    <span>Schedule 탭 추천 결과 기준 · 총 {total_saving:,}원 절감, 약 {total_rate:.1f}%</span>
                </div>
                <div class="sim-legend">
                    <span><i class="sim-dot before"></i>기존 생활패턴 기준</span>
                    <span><i class="sim-dot after"></i>추천 스케줄 적용</span>
                </div>
                <div class="sim-horizontal-chart">{bar_html}</div>
            </div>

            <div class="sim-rank-card">
                <div class="sim-section-title">
                    <div>가전별 절감액 합산</div>
                    <span>등록 가전만 반영</span>
                </div>
                <div class="sim-rank-list">{rank_html}</div>
                <div style="margin-top:18px;padding:18px 20px;border-radius:22px;background:rgba(255,228,118,.24);font-weight:900;color:#202124;display:flex;justify-content:space-between;">
                    <span>최종 합산 절감액</span><span>{total_saving:,}원</span>
                </div>
            </div>
        </div>
        """)

# ══════════════════════════════════════════
# 탭4 — 요금 예보
# ══════════════════════════════════════════
if False:
    st.markdown('<div class="section-lbl">오늘 24시간 요금 예보</div>', unsafe_allow_html=True)

    color_map = {"cheap":"#639922","normal":"#378ADD","expensive":"#D85A30","peak":"#E24B4A"}
    df_today  = pd.DataFrame({
        "시간":       [f"{h}시" for h in range(24)],
        "요금(원/kWh)": HOURLY_PRICES,
        "구간":       [get_status(p) for p in HOURLY_PRICES],
    })
    fig3 = go.Figure()
    for s,col in color_map.items():
        mask = df_today["구간"]==s
        label = {"cheap":"경부하","normal":"중간부하","expensive":"최대부하","peak":"피크"}[s]
        fig3.add_trace(go.Bar(
            x=df_today[mask]["시간"], y=df_today[mask]["요금(원/kWh)"],
            name=label, marker_color=col,
        ))
    fig3.add_vline(x=current_hour, line_dash="dash", line_color="#191F28",
                   annotation_text="지금", annotation_position="top")
    fig3.update_layout(
        height=340, plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        barmode="overlay", margin=dict(l=0,r=0,t=20,b=0),
        font=dict(color="#4E5968"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#F2F4F6"),
    )
    st.plotly_chart(fig3, width="stretch")

    # 구간 요약
    sc1,sc2,sc3,sc4 = st.columns(4)
    sc1.metric("경부하", f"{sum(1 for p in HOURLY_PRICES if get_status(p)=='cheap')}시간",  "107.0원")
    sc2.metric("중간부하", f"{sum(1 for p in HOURLY_PRICES if get_status(p)=='normal')}시간", "153.0원")
    sc3.metric("최대부하", f"{sum(1 for p in HOURLY_PRICES if get_status(p)=='expensive')}시간","188.8원")
    sc4.metric("DR/예외", f"{sum(1 for p in HOURLY_PRICES if get_status(p)=='peak')}시간",   "별도")
