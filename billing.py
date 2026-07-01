"""
전력 요금 계산 모듈 (누진제 vs 시간대별 요금제(TOU) vs 시간대별 요금제(TOU)+DR 비교)
- 누진제: 한국 주택용 저압 요금표 구조 기준 (계절 자동 감지)
- 시간대별 요금제(TOU): 제주 주택용 계시별 선택요금제 시간대 구분을 참고한 3단계 시뮬레이션 단가
  · 경부하 22~08시 107.0원/kWh
  · 중간부하 08~16시 153.0원/kWh
  · 최대부하 16~22시 188.8원/kWh
- DR: PTR(Peak Time Rebate) 방식, 감축 kWh × 보상단가 시뮬레이션
"""
import pandas as pd
from datetime import datetime

DEFAULT_DR_PARTICIPATION_RATE = 0.60  # 월간 Billing 계산에서 실제 DR 참여 가능률 60% 적용
DEFAULT_DR_REWARD_CAP_RATIO = 0.10      # DR 보상 대상 감축량은 월 사용량의 최대 10%로 제한
AIRCON_DR_REWARD_FACTOR = 0.0           # 에어컨은 쾌적성 가전이므로 DR 보상 대상에서 제외

def add_energy_kwh(df):
    """
    timestamp, power_W 컬럼을 기반으로 energy_kwh를 계산합니다.
    첫 행은 무조건 1시간으로 가정하지 않고, 데이터의 대표 시간 간격(중앙값)을 사용합니다.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["dt_hour"] = df["timestamp"].diff().dt.total_seconds() / 3600

    median_dt = df["dt_hour"].dropna().median()
    if pd.isna(median_dt) or median_dt <= 0:
        median_dt = 1

    df["dt_hour"] = df["dt_hour"].fillna(median_dt)
    df.loc[df["dt_hour"] <= 0, "dt_hour"] = median_dt
    df["energy_kwh"] = df["power_W"] * df["dt_hour"] / 1000
    return df

def get_progressive_params(month=None):
    if month is None:
        month = datetime.now().month
    if month in [7, 8]:
        return {"season":"하계","thresholds":[300,450],"rates":[120.0,214.6,307.3],"basic":[910,1600,7300]}
    else:
        return {"season":"기타계절","thresholds":[200,400],"rates":[120.0,214.6,307.3],"basic":[910,1600,7300]}

def calculate_progressive_bill(total_kwh, month=None):
    p = get_progressive_params(month)
    t1, t2 = p["thresholds"]
    r1, r2, r3 = p["rates"]
    b1, b2, b3 = p["basic"]
    basic = b1 if total_kwh <= t1 else (b2 if total_kwh <= t2 else b3)
    if total_kwh <= t1:
        energy = total_kwh * r1
    elif total_kwh <= t2:
        energy = t1*r1 + (total_kwh-t1)*r2
    else:
        energy = t1*r1 + (t2-t1)*r2 + (total_kwh-t2)*r3
    subtotal = basic + energy
    vat = subtotal * 0.10
    fund = subtotal * 0.027
    return {"기본요금":round(basic),"전력량요금":round(energy),"부가세":round(vat),"전력산업기반기금":round(fund),"합계":round(subtotal+vat+fund),"계절":p["season"]}

def get_tou_rate(hour):
    """
    제주 주택용 계시별 선택요금제 시간대 구분을 참고한 3단계 시간대별 요금제(TOU) 단가.
    - 경부하: 22~08시, 107.0원/kWh
    - 중간부하: 08~16시, 153.0원/kWh
    - 최대부하: 16~22시, 188.8원/kWh
    """
    h = int(hour) % 24
    if h >= 22 or h < 8:
        return 107.0
    if 8 <= h < 16:
        return 153.0
    return 188.8

def calculate_tou_bill_hourly(hourly_kwh_dict, month=None):
    p = get_progressive_params(month)
    t1, t2 = p["thresholds"]
    b1, b2, b3 = p["basic"]
    total_kwh = sum(hourly_kwh_dict.values())
    basic = b1 if total_kwh <= t1 else (b2 if total_kwh <= t2 else b3)
    energy = sum(kwh * get_tou_rate(h) for h, kwh in hourly_kwh_dict.items())
    subtotal = basic + energy
    vat = subtotal * 0.10
    fund = subtotal * 0.027
    return {"기본요금":round(basic),"전력량요금":round(energy),"부가세":round(vat),"전력산업기반기금":round(fund),"합계":round(subtotal+vat+fund)}

def calculate_dr_eligible_kwh(
    reduced_kwh,
    participation_rate=DEFAULT_DR_PARTICIPATION_RATE,
    max_eligible_kwh=None,
):
    """DR 보상 인정 감축량을 계산합니다.

    감축 가능량 전체를 보상 대상으로 보지 않고 참여율을 적용하며,
    월간 계산에서는 전체 월 사용량의 일정 비율로 상한을 둡니다.
    """
    eligible_kwh = max(float(reduced_kwh), 0.0) * float(participation_rate)
    if max_eligible_kwh is not None:
        eligible_kwh = min(eligible_kwh, max(float(max_eligible_kwh), 0.0))
    return max(eligible_kwh, 0.0)


def calculate_dr_incentive(
    reduced_kwh,
    incentive_rate=150,
    participation_rate=DEFAULT_DR_PARTICIPATION_RATE,
    max_eligible_kwh=None,
):
    """PTR 방식 DR 인센티브: 보상 인정 감축량 × 보상단가"""
    eligible_kwh = calculate_dr_eligible_kwh(reduced_kwh, participation_rate, max_eligible_kwh)
    return round(eligible_kwh * incentive_rate)


def _normalize_hours(hours):
    """시간 리스트를 0~23 범위의 중복 없는 정렬 리스트로 변환합니다."""
    return sorted({int(h) % 24 for h in hours})


def _appliance_segments(start_hour, hours, step=0.5):
    """
    가전 운전시간을 시간대별 조각으로 나눕니다.
    기존 코드의 hours % 1 방식은 1.5시간에서 0.5시간이 중복 계산될 수 있어 수정했습니다.
    """
    hours = float(hours)
    start_hour = int(start_hour) % 24
    if hours <= 0:
        return

    full_steps = int(hours // step)
    used = full_steps * step

    for i in range(full_steps):
        h = (start_hour + int((i * step) // 1)) % 24
        yield h, step

    remaining = round(hours - used, 10)
    if remaining > 1e-9:
        h = (start_hour + int(used // 1)) % 24
        yield h, remaining


def shift_dr_usage(hourly_kwh, dr_hours, shift_target_hours=None):
    """
    DR 시간대 사용량을 단순히 없애지 않고 저요금 시간대로 이동시킵니다.
    기본 이동 시간대: 22, 23, 0, 1, 2시
    """
    dr_hours = _normalize_hours(dr_hours)
    if shift_target_hours is None:
        shift_target_hours = [22, 23, 0, 1, 2]
    shift_target_hours = _normalize_hours(shift_target_hours)

    shifted = {h: float(hourly_kwh.get(h, 0.0)) for h in range(24)}
    move_kwh = sum(shifted.get(h, 0.0) for h in dr_hours)

    for h in dr_hours:
        shifted[h] = 0.0

    if move_kwh > 0 and shift_target_hours:
        add_each = move_kwh / len(shift_target_hours)
        for h in shift_target_hours:
            shifted[h] += add_each

    return shifted

def simulate_monthly_bills(monthly_kwh=300, dr_hours=None, incentive_rate=150, dr_participation_rate=DEFAULT_DR_PARTICIPATION_RATE, month=None, shift_target_hours=None):
    """
    월간 사용량 기준 누진제 / TOU / 시간대별 요금제(TOU)+DR 예상 요금을 비교합니다.

    개선점:
    - DR 시간대 사용량을 0으로 제거하지 않고 저요금 시간대로 이동
    - DR 인센티브는 PTR 방식, 즉 감축 kWh × 보상단가로 계산
    """
    if dr_hours is None:
        dr_hours = list(range(17, 21))
    dr_hours = _normalize_hours(dr_hours)

    if month is None:
        month = datetime.now().month

    hourly_ratio = {
        0:0.040,1:0.036,2:0.033,3:0.032,4:0.032,5:0.033,
        6:0.033,7:0.036,8:0.040,9:0.042,10:0.042,11:0.041,
        12:0.041,13:0.041,14:0.040,15:0.040,16:0.040,17:0.042,
        18:0.048,19:0.054,20:0.055,21:0.054,22:0.050,23:0.046,
    }
    ratio_sum = sum(hourly_ratio.values())
    if ratio_sum <= 0:
        raise ValueError("hourly_ratio의 합계가 0 이하입니다.")
    # 입력 비율 합계가 1과 약간 다를 수 있어 자동 정규화합니다.
    hourly_ratio = {h: r / ratio_sum for h, r in hourly_ratio.items()}

    hourly_kwh = {h: monthly_kwh * r for h, r in hourly_ratio.items()}

    progressive = calculate_progressive_bill(monthly_kwh, month)
    tou_result = calculate_tou_bill_hourly(hourly_kwh, month)

    base_dr_kwh = sum(hourly_kwh.get(h, 0) for h in dr_hours)
    hourly_kwh_dr = shift_dr_usage(hourly_kwh, dr_hours, shift_target_hours)
    after_dr_kwh = sum(hourly_kwh_dr.get(h, 0) for h in dr_hours)
    dr_reduced_kwh = max(base_dr_kwh - after_dr_kwh, 0)

    tou_dr_result = calculate_tou_bill_hourly(hourly_kwh_dr, month)
    max_dr_eligible_kwh = monthly_kwh * DEFAULT_DR_REWARD_CAP_RATIO
    dr_eligible_kwh = calculate_dr_eligible_kwh(dr_reduced_kwh, dr_participation_rate, max_dr_eligible_kwh)
    dr_incentive = calculate_dr_incentive(dr_reduced_kwh, incentive_rate, dr_participation_rate, max_dr_eligible_kwh)
    tou_dr_final = max(tou_dr_result["합계"] - dr_incentive, 0)

    return {
        "월간사용량": monthly_kwh,
        "계절": progressive["계절"],
        "누진제": progressive["합계"],
        "누진제_상세": progressive,
        "TOU": tou_result["합계"],
        "TOU_상세": tou_result,
        "TOU_DR요금": tou_dr_result["합계"],
        "TOU_DR_상세": tou_dr_result,
        "DR인센티브": dr_incentive,
        "DR감축량": round(dr_reduced_kwh, 3),
        "DR기준사용량": round(base_dr_kwh, 3),
        "DR이후사용량": round(after_dr_kwh, 3),
        "TOU_DR최종": tou_dr_final,
        "누진제대비TOU절약": progressive["합계"] - tou_result["합계"],
        "누진제대비DR절약": progressive["합계"] - tou_dr_final,
        "TOU대비DR절약": tou_result["합계"] - tou_dr_final,
        "인센티브단가": incentive_rate,
        "DR참여율": dr_participation_rate,
        "DR보상상한비율": DEFAULT_DR_REWARD_CAP_RATIO,
        "DR보상상한(kWh)": round(max_dr_eligible_kwh, 3),
        "DR실제보상대상감축량": round(dr_eligible_kwh, 3),
    }



# ─────────────────────────────────────────
# 6. 전처리된 REFIT/가정 전력 데이터 기반 요금 비교
# ─────────────────────────────────────────
def _detect_timestamp_column(df):
    candidates = ["timestamp", "datetime", "date_time", "time", "Time", "DateTime", "Timestamp"]
    for c in candidates:
        if c in df.columns:
            parsed = pd.to_datetime(df[c], errors="coerce")
            if parsed.notna().mean() > 0.7:
                return c
    for c in df.columns:
        parsed = pd.to_datetime(df[c], errors="coerce")
        if parsed.notna().mean() > 0.7:
            return c
    raise ValueError("timestamp/datetime 컬럼을 찾지 못했습니다.")


def _detect_power_column(df):
    candidates = [
        "power_W", "Power_W", "aggregate_W", "Aggregate_W", "total_power_W",
        "power", "Power", "aggregate", "Aggregate", "use", "mains", "Mains"
    ]
    for c in candidates:
        if c in df.columns and pd.api.types.is_numeric_dtype(df[c]):
            return c
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        raise ValueError("전력 사용량 숫자 컬럼을 찾지 못했습니다.")
    # timestamp에서 파생된 월/일/시간 컬럼보다 실제 전력 컬럼이 앞에 있는 경우가 많으므로 분산이 있는 컬럼 우선
    numeric_cols = sorted(numeric_cols, key=lambda c: df[c].std(skipna=True) if df[c].std(skipna=True) == df[c].std(skipna=True) else -1, reverse=True)
    return numeric_cols[0]


def prepare_timeseries_energy(df):
    """
    전처리된 REFIT/가정 전력 데이터프레임을 표준 형태로 변환합니다.
    반환 컬럼: timestamp, power_W, energy_kwh, hour, month
    - power_W 컬럼이 있으면 그대로 사용
    - 전력 컬럼이 kW 단위로 보이는 경우 자동으로 W로 변환
    - energy_kwh는 timestamp 간격의 중앙값을 이용해 계산
    """
    df = df.copy()
    ts_col = _detect_timestamp_column(df)
    p_col = _detect_power_column(df)

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(df[ts_col], errors="coerce"),
        "power_W": pd.to_numeric(df[p_col], errors="coerce"),
    }).dropna()

    out = out.sort_values("timestamp").reset_index(drop=True)
    if out.empty:
        raise ValueError("유효한 전력 데이터가 없습니다.")

    # 컬럼명이 kW이거나 값의 스케일이 kW로 보이면 W로 변환
    col_lower = str(p_col).lower()
    median_power = out["power_W"].median()
    if "kw" in col_lower and "kwh" not in col_lower:
        out["power_W"] *= 1000
    elif median_power < 30:  # 가정 총부하가 보통 kW 단위로 0~10 범위인 경우
        out["power_W"] *= 1000

    out = add_energy_kwh(out)
    out["hour"] = out["timestamp"].dt.hour
    out["month"] = out["timestamp"].dt.to_period("M").astype(str)
    return out


def _scale_hourly_profile(hourly_kwh, target_total_kwh):
    hourly_kwh = {int(h) % 24: float(v) for h, v in hourly_kwh.items()}
    total = sum(hourly_kwh.values())
    if total <= 0:
        return {h: 0.0 for h in range(24)}
    scale = float(target_total_kwh) / total
    return {h: hourly_kwh.get(h, 0.0) * scale for h in range(24)}


def simulate_from_hourly_profile(hourly_kwh, dr_hours=None, incentive_rate=150, dr_participation_rate=DEFAULT_DR_PARTICIPATION_RATE, month=None, shift_target_hours=None):
    """시간대별 kWh 분포를 그대로 사용해 누진제/시간대별 요금제(TOU)/DR 요금을 비교합니다."""
    if dr_hours is None:
        dr_hours = list(range(17, 21))
    dr_hours = _normalize_hours(dr_hours)
    if month is None:
        month = datetime.now().month

    hourly_kwh = {h: float(hourly_kwh.get(h, 0.0)) for h in range(24)}
    total_kwh = sum(hourly_kwh.values())
    progressive = calculate_progressive_bill(total_kwh, month)
    tou_result = calculate_tou_bill_hourly(hourly_kwh, month)

    base_dr_kwh = sum(hourly_kwh.get(h, 0.0) for h in dr_hours)
    hourly_kwh_dr = shift_dr_usage(hourly_kwh, dr_hours, shift_target_hours)
    after_dr_kwh = sum(hourly_kwh_dr.get(h, 0.0) for h in dr_hours)
    dr_reduced_kwh = max(base_dr_kwh - after_dr_kwh, 0)

    tou_dr_result = calculate_tou_bill_hourly(hourly_kwh_dr, month)
    max_dr_eligible_kwh = total_kwh * DEFAULT_DR_REWARD_CAP_RATIO
    dr_eligible_kwh = calculate_dr_eligible_kwh(dr_reduced_kwh, dr_participation_rate, max_dr_eligible_kwh)
    dr_incentive = calculate_dr_incentive(dr_reduced_kwh, incentive_rate, dr_participation_rate, max_dr_eligible_kwh)
    tou_dr_final = max(tou_dr_result["합계"] - dr_incentive, 0)

    return {
        "월간사용량": round(total_kwh, 1),
        "누진제": progressive["합계"],
        "누진제_상세": progressive,
        "TOU": tou_result["합계"],
        "TOU_상세": tou_result,
        "TOU_DR요금": tou_dr_result["합계"],
        "TOU_DR_상세": tou_dr_result,
        "DR인센티브": dr_incentive,
        "DR감축량": round(dr_reduced_kwh, 3),
        "DR기준사용량": round(base_dr_kwh, 3),
        "DR이후사용량": round(after_dr_kwh, 3),
        "TOU_DR최종": tou_dr_final,
        "누진제대비TOU절약": progressive["합계"] - tou_result["합계"],
        "누진제대비DR절약": progressive["합계"] - tou_dr_final,
        "TOU대비DR절약": tou_result["합계"] - tou_dr_final,
        "인센티브단가": incentive_rate,
        "DR참여율": dr_participation_rate,
        "DR보상상한비율": DEFAULT_DR_REWARD_CAP_RATIO,
        "DR보상상한(kWh)": round(max_dr_eligible_kwh, 3),
        "DR실제보상대상감축량": round(dr_eligible_kwh, 3),
    }


def simulate_recent_pattern_bills(df, recent_days=30, dr_hours=None, incentive_rate=150, dr_participation_rate=DEFAULT_DR_PARTICIPATION_RATE, month=None, shift_target_hours=None, household_count=5):
    """
    15분/5분 등 누적 전력 데이터에서 최근 사용 패턴을 추출하고,
    그 패턴이 30일간 유지된다고 가정한 월간 환산 요금을 계산합니다.
    """
    data = prepare_timeseries_energy(df)
    end_ts = data["timestamp"].max()
    start_ts = end_ts - pd.Timedelta(days=int(recent_days))
    recent = data[data["timestamp"] > start_ts].copy()
    if recent.empty:
        recent = data.copy()

    # REFIT_House_1_2_3_4_5_15min_AI_Dataset.csv는 5개 가구 통합 데이터로 사용하므로,
    # Billing 탭에서는 1가구 평균 사용 패턴으로 환산해 요금을 계산합니다.
    try:
        household_count = max(float(household_count), 1.0)
    except Exception:
        household_count = 5.0

    covered_days = max((recent["timestamp"].max() - recent["timestamp"].min()).total_seconds() / 86400, 1)
    observed_kwh_total = float(recent["energy_kwh"].sum())
    observed_kwh = observed_kwh_total / household_count
    monthly_kwh = observed_kwh / covered_days * 30

    hourly_recent_total = recent.groupby("hour")["energy_kwh"].sum().to_dict()
    hourly_recent = {h: float(v) / household_count for h, v in hourly_recent_total.items()}
    hourly_monthly = _scale_hourly_profile(hourly_recent, monthly_kwh)
    result = simulate_from_hourly_profile(
        hourly_monthly,
        dr_hours=dr_hours,
        incentive_rate=incentive_rate,
        dr_participation_rate=dr_participation_rate,
        month=month,
        shift_target_hours=shift_target_hours,
    )

    monthly_usage = (
        data.groupby("month")["energy_kwh"].sum().reset_index()
        .rename(columns={"month": "월", "energy_kwh": "사용량(kWh)"})
    )
    monthly_usage["사용량(kWh)"] = (monthly_usage["사용량(kWh)"] / household_count).round(1)

    result.update({
        "데이터시작": data["timestamp"].min(),
        "데이터끝": end_ts,
        "최근기간일수": round(covered_days, 1),
        "최근기간사용량": round(observed_kwh, 1),
        "최근기간전체사용량": round(observed_kwh_total, 1),
        "가구평균환산가구수": int(household_count) if float(household_count).is_integer() else household_count,
        "월간환산사용량": round(monthly_kwh, 1),
        "시간대별월간사용량": {h: round(v, 3) for h, v in hourly_monthly.items()},
        "월별사용량": monthly_usage,
    })
    return result

# ─────────────────────────────────────────
# 7. 가전 스케줄 기반 시간대별 요금 계산 (sel_dr.py 연동용)
# ─────────────────────────────────────────
def build_hourly_kwh(selected, start_hour):
    """
    사용자가 입력한 가전기기 목록과 시작시간을 받아 시간대별 사용량(kWh) 딕셔너리 생성

    selected: {name: {"watt": W, "hours": H}}
    start_hour: 시작 시간 (0~23)
    반환: {hour: kwh}
    """
    hourly_kwh = {h: 0.0 for h in range(24)}
    for name, info in selected.items():
        watt = float(info["watt"])
        hours = float(info["hours"])
        for h, duration in _appliance_segments(start_hour, hours):
            hourly_kwh[h] += (watt / 1000 * duration)
    return hourly_kwh


def calc_appliance_tou(selected, start_hour, month=None):
    """
    가전 스케줄 기반 시간대별 요금제(TOU) 요금 계산
    billing.py의 get_tou_rate 사용

    반환:
    - tou_cost: TOU 전력량요금 (원)
    - hourly_kwh: 시간대별 사용량
    - detail: 기기별 상세 요금
    """
    hourly_kwh = build_hourly_kwh(selected, start_hour)

    # 기기별 상세 계산
    detail = []
    for name, info in selected.items():
        watt = float(info["watt"])
        hours = float(info["hours"])
        c_tou = 0.0
        for h, duration in _appliance_segments(start_hour, hours):
            c_tou += (watt / 1000 * duration) * get_tou_rate(h)

        detail.append({
            "기기": name,
            "사용시간": f"{hours:g}시간",
            "사용량(kWh)": round(watt / 1000 * hours, 3),
            "시간대별 요금제(TOU) 요금": round(c_tou),
        })

    tou_cost = sum(d["시간대별 요금제(TOU) 요금"] for d in detail)
    return {
        "tou_cost": tou_cost,
        "hourly_kwh": hourly_kwh,
        "detail": detail,
    }


def calc_appliance_dr(selected, start_hour, dr_hours, incentive_rate=150, dr_participation_rate=DEFAULT_DR_PARTICIPATION_RATE, month=None, baseline_hour=None, shift_target_hours=None):
    """
    가전 스케줄 기반 시간대별 요금제(TOU)+DR 요금 및 인센티브 계산

    개선점:
    - 감축량 = 베이스라인 DR 사용량 - 최적 스케줄 DR 사용량
    - DR 시간대 사용량을 없애지 않고 저요금 시간대로 이동
    - 0.5시간 단위 중복 계산 방지
    """
    dr_hours = _normalize_hours(dr_hours)

    tou_result = calc_appliance_tou(selected, start_hour, month)
    tou_cost = tou_result["tou_cost"]
    hourly_kwh_opt = tou_result["hourly_kwh"]
    opt_dr_kwh = sum(hourly_kwh_opt.get(h, 0) for h in dr_hours)

    if baseline_hour is not None and baseline_hour != start_hour:
        baseline_result = calc_appliance_tou(selected, baseline_hour, month)
        hourly_kwh_base = baseline_result["hourly_kwh"]
    else:
        hourly_kwh_base = hourly_kwh_opt

    base_dr_kwh = sum(hourly_kwh_base.get(h, 0) for h in dr_hours)
    dr_reduced_kwh = max(base_dr_kwh - opt_dr_kwh, 0)

    hourly_kwh_dr = shift_dr_usage(hourly_kwh_opt, dr_hours, shift_target_hours)
    tou_dr_cost = round(sum(kwh * get_tou_rate(h) for h, kwh in hourly_kwh_dr.items()))

    # 가전별 DR 보상은 에어컨을 제외한 이동 가능 가전만 대상으로 보고,
    # 보상 대상 감축량은 전체 등록 가전 사용량의 10%를 상한으로 둡니다.
    reward_reduced_kwh = 0.0
    for reward_name, reward_info in selected.items():
        reward_factor = AIRCON_DR_REWARD_FACTOR if reward_name == "에어컨" else 1.0
        if reward_factor <= 0:
            continue
        opt_one = build_hourly_kwh({reward_name: reward_info}, start_hour)
        if baseline_hour is not None and baseline_hour != start_hour:
            base_one = build_hourly_kwh({reward_name: reward_info}, baseline_hour)
        else:
            base_one = opt_one
        one_base_dr = sum(base_one.get(h, 0) for h in dr_hours)
        one_opt_dr = sum(opt_one.get(h, 0) for h in dr_hours)
        reward_reduced_kwh += max(one_base_dr - one_opt_dr, 0) * reward_factor

    total_selected_kwh = sum(float(info["watt"]) / 1000 * float(info["hours"]) for info in selected.values())
    max_dr_eligible_kwh = total_selected_kwh * DEFAULT_DR_REWARD_CAP_RATIO
    dr_eligible_kwh = calculate_dr_eligible_kwh(reward_reduced_kwh, dr_participation_rate, max_dr_eligible_kwh)
    dr_incentive = calculate_dr_incentive(reward_reduced_kwh, incentive_rate, dr_participation_rate, max_dr_eligible_kwh)
    real_burden = max(tou_dr_cost - dr_incentive, 0)

    detail = []
    for name, info in selected.items():
        watt = float(info["watt"])
        hours = float(info["hours"])

        c_tou = 0.0
        hourly_one = {h: 0.0 for h in range(24)}
        for h, duration in _appliance_segments(start_hour, hours):
            kwh = watt / 1000 * duration
            hourly_one[h] += kwh
            c_tou += kwh * get_tou_rate(h)

        one_dr_base = hourly_one
        if baseline_hour is not None and baseline_hour != start_hour:
            one_dr_base = build_hourly_kwh({name: info}, baseline_hour)

        one_base_dr_kwh = sum(one_dr_base.get(h, 0) for h in dr_hours)
        one_opt_dr_kwh = sum(hourly_one.get(h, 0) for h in dr_hours)
        one_reduced = max(one_base_dr_kwh - one_opt_dr_kwh, 0)
        reward_factor = AIRCON_DR_REWARD_FACTOR if name == "에어컨" else 1.0
        one_reward_reduced = one_reduced * reward_factor
        one_incentive = calculate_dr_incentive(one_reward_reduced, incentive_rate, dr_participation_rate)

        hourly_one_shifted = shift_dr_usage(hourly_one, dr_hours, shift_target_hours)
        c_dr = round(sum(kwh * get_tou_rate(h) for h, kwh in hourly_one_shifted.items()))
        one_real = max(c_dr - one_incentive, 0)

        detail.append({
            "기기": name,
            "사용시간": f"{hours:g}시간",
            "사용량(kWh)": round(watt / 1000 * hours, 3),
            "시간대별 요금제(TOU) 요금": round(c_tou),
            "시간대별 요금제(TOU)+DR": one_real,
            "DR 감축량(kWh)": round(one_reduced, 3),
            "DR 인센티브": one_incentive,
            "DR 절약": max(round(c_tou) - one_real, 0),
        })

    return {
        "tou_cost": tou_cost,
        "tou_dr_cost": tou_dr_cost,
        "dr_reduced_kwh": round(dr_reduced_kwh, 3),
        "dr_incentive": dr_incentive,
        "real_burden": real_burden,
        "hourly_kwh": hourly_kwh_dr,
        "detail": detail,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("전력 요금 비교 테스트 (300kWh 기준)")
    print("=" * 60)
    result = simulate_monthly_bills(300, incentive_rate=150)
    print(f"\n계절: {result['계절']}")
    print(f"월간 사용량: {result['월간사용량']} kWh")
    print(f"\n① 누진제:         {result['누진제']:,}원")
    print(f"② TOU:            {result['TOU']:,}원")
    print(f"③ 시간대별 요금제(TOU)+DR 요금:    {result['TOU_DR요금']:,}원")
    print(f"   DR 감축량:      {result['DR감축량']} kWh")
    print(f"   DR 인센티브:    {result['DR인센티브']:,}원 ({result['인센티브단가']}원/kWh)")
    print(f"   시간대별 요금제(TOU)+DR 최종:   {result['TOU_DR최종']:,}원")
    print(f"\n누진제 대비 TOU 절약:   {result['누진제대비TOU절약']:,}원")
    print(f"누진제 대비 DR 절약:    {result['누진제대비DR절약']:,}원")
    print(f"TOU 대비 DR 절약:       {result['TOU대비DR절약']:,}원")
