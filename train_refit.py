"""
REFIT 영국 가정 실측 데이터 AI 학습 스크립트
실행: python train_refit.py
결과: dr_model_refit.pkl
"""
import pandas as pd
import numpy as np
import pickle
import os
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

print("=" * 55)
print("🤖 REFIT 영국 실측 데이터 AI 학습 시작")
print("=" * 55)

# ─── 1. 데이터 로드 ───
DATA_PATH  = os.path.join(os.path.dirname(__file__), "data", "REFIT_House_1_2_3_4_5_15min_AI_Dataset.csv")
MODEL_PATH = os.path.join(os.path.dirname(__file__), "dr_model_refit.pkl")

print(f"\n📂 데이터 로드 중...")
df = pd.read_csv(DATA_PATH, encoding='utf-8')
print(f"✅ 원본: {len(df):,}행")

# ─── 2. 필터링 ───
print("\n🔧 데이터 필터링...")
df_clean = df[
    (df['Missing_Flag'] == 0) &       # 실제 측정값만
    (df['Total_Power_W'] <= 15000) &  # 이상치 제거
    (df['Total_Power_W'] >= 0)        # 음수 제거
].copy()

print(f"✅ Missing_Flag=0 + 이상치 제거 후: {len(df_clean):,}행")
print(f"   제거된 행: {len(df)-len(df_clean):,}개")

# ─── 3. 피처 생성 ───
print("\n🔧 피처 생성...")

# House_ID → 숫자로 변환
df_clean['House_Num'] = df_clean['House_ID'].str.extract(r'(\d+)').astype(int)

# 요일 → 숫자
day_map = {'Monday':0,'Tuesday':1,'Wednesday':2,'Thursday':3,
           'Friday':4,'Saturday':5,'Sunday':6}
df_clean['Day_Num'] = df_clean['Day_of_Week'].map(day_map)

# 사용량(kWh) 컬럼
df_clean['사용량_kwh'] = df_clean['Energy_kWh_15min']

# ─── 4. 피크 기준 설정 ───
peak_threshold = df_clean['Total_Power_W'].quantile(0.75)
df_clean['피크여부'] = (df_clean['Total_Power_W'] >= peak_threshold).astype(int)

print(f"⚡ 피크 기준: {peak_threshold:.1f}W 이상 (상위 25%)")
print(f"   피크 비율: {df_clean['피크여부'].mean()*100:.1f}%")

# ─── 5. 학습 ───
FEATURES = [
    'Hour',        # 시간대 (0~23)
    'Minute',      # 분 (0,15,30,45)
    'Month',       # 월 (1~12)
    'Is_Weekend',  # 주말여부
    'Day_Num',     # 요일 (0~6)
    'Day_of_Year', # 연중 일수 (1~365)
    'House_Num',   # 가정 번호 (1~5)
]
TARGET = 'Total_Power_W'

X = df_clean[FEATURES]
y = df_clean[TARGET]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

print(f"\n📚 학습 데이터: {len(X_train):,}행")
print(f"🧪 테스트 데이터: {len(X_test):,}행")
print("\n🤖 AI 모델 학습 중... (2~5분 소요)")

model = GradientBoostingRegressor(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    random_state=42,
    verbose=1,
)
model.fit(X_train, y_train)

# ─── 6. 평가 ───
y_pred = model.predict(X_test)
mae = mean_absolute_error(y_test, y_pred)
r2  = r2_score(y_test, y_pred)

print(f"\n📈 모델 성능")
print(f"   MAE (평균 오차): {mae:.1f} W")
print(f"   R²  (정확도):    {r2:.4f} ({r2*100:.1f}%)")

importance = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)
print("\n🔍 예측에 중요한 요소:")
for feat, imp in importance.items():
    print(f"   {feat}: {imp*100:.1f}%")

# ─── 7. 시간대별 평균 저장 ───
hourly_avg = df_clean.groupby('Hour')['Total_Power_W'].mean().to_dict()
monthly_avg = df_clean.groupby('Month')['Total_Power_W'].mean().to_dict()
house_avg = df_clean.groupby('House_Num')['Total_Power_W'].mean().to_dict()

# ─── 8. 모델 저장 ───
with open(MODEL_PATH, 'wb') as f:
    pickle.dump({
        'model':           model,
        'features':        FEATURES,
        'peak_threshold':  peak_threshold,
        'mae':             mae,
        'r2':              r2,
        'data_source':     'REFIT UK 5가정 실측 (2013-2015)',
        'total_rows':      len(df_clean),
        'hourly_avg':      hourly_avg,
        'monthly_avg':     monthly_avg,
        'house_avg':       house_avg,
    }, f)

print(f"\n✅ 모델 저장 완료 → dr_model_refit.pkl")
print(f"   학습 완료! streamlit run apped3.py 실행하세요")
print("=" * 55)
