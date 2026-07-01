"""
생활패턴 기반 가전 스케줄 최적화 모듈

역할
- UI에서 입력받은 생활패턴, 가전 목록, DR 이벤트 정보를 바탕으로
  현실 제약을 만족하는 추천 시작 시간을 계산합니다.
- 기존 sel_dr.py에 들어 있던 제약조건 로직을 UI 코드와 분리한 파일입니다.

핵심 제약
- 소음 가전: 야간/늦은 저녁 추천 제한
- 활동 가전: 사용자가 깨어 있고 집에 있는 시간에만 추천
- 냉난방 가전: 냉방·난방 의미가 있는 시간대로 제한
- 전기차: 다음날 기상 전 충전 완료 조건 반영
- 분산 제약: 여러 가전이 같은 시간대에 몰리지 않도록 페널티 부여
- 절감 임계값: 절감액이 너무 작으면 굳이 이동하지 않음
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional


# ─────────────────────────────────────────
# 1. 가전별 현실 제약
# ─────────────────────────────────────────
NOISY_APPLIANCES = {"세탁기", "건조기", "청소기", "식기세척기"}
ACTIVE_ONLY_APPLIANCES = {"청소기"}
CLIMATE_APPLIANCES = {"에어컨", "히터", "난방기"}
EV_APPLIANCES = {"전기차 충전", "전기차", "EV 충전"}

# 냉난방 가전은 새벽 시간 추천을 피하고, 낮~밤 위주로 추천
# 단, 에어컨은 현재 기온/습도/시간별 예보를 추가로 반영해 쾌적성 페널티를 계산합니다.
CLIMATE_HOUR_RANGE = (10, 23)

# 에어컨 온도 연동 최적화 기준
AC_HOT_TEMP = 30.0          # 매우 더움: 쾌적성 우선, 과도한 지연 방지
AC_WARM_TEMP = 27.0         # 더움: 냉방 필요, DR/피크 회피 우선
AC_MILD_TEMP = 24.0         # 약간 더움: 절감 효과가 클 때만 추천
AC_MAX_COMFORT_DELAY = 3    # 30도 이상일 때 현재 시각 기준 최대 권장 지연 시간
AC_HUMIDITY_HIGH = 75.0       # 습도가 높아 체감 더위가 커지는 기준
AC_HUMIDITY_VERY_HIGH = 85.0  # 고습 환경: 냉방/제습 필요성이 매우 큰 기준

# 소음 가전 제한 시간
NOISY_BLOCK_START = 20
NOISY_BLOCK_END = 7

# 절감액이 이 금액보다 작으면 굳이 이동하지 않음
DEFAULT_MIN_SAVING_WON = 100

# 같은 시작 시간에 가전이 몰릴 때 부여하는 분산 페널티 계수
DEFAULT_SPREAD_PENALTY_PER_KW = 30

# DR 시간대 사용 회피 페널티: DR은 시간대 사용을 줄여야 보상받으므로 할인 대신 페널티로 처리
DEFAULT_DR_AVOID_PENALTY_PER_KWH = 380
EV_DR_AVOID_PENALTY_PER_KWH = 550
DIRECT_DR_AVOID_PENALTY_PER_KWH = 260
AC_DR_AVOID_PENALTY_HOT = 90
AC_DR_AVOID_PENALTY_WARM = 220
AC_DR_AVOID_PENALTY_MILD = 380


def _default_rate_func(hour: int, dr: bool = False, dr_hours: Optional[Iterable[int]] = None, dr_reward: float = 150) -> float:
    """
    billing.py가 있으면 billing.get_tou_rate를 사용하고,
    없으면 자체 fallback 단가를 사용합니다.
    """
    try:
        from billing import get_tou_rate  # type: ignore
        rate = float(get_tou_rate(int(hour) % 24))
    except Exception:
        h = int(hour) % 24
        rate = 307.3 if 17 <= h < 21 else 120.0

    # DR은 "사용하면 할인"이 아니라 "줄이면 보상" 구조이므로,
    # 스케줄 비용 계산 단계에서는 단가를 낮추지 않습니다.
    # DR 회피 효과는 optimize_appliance_schedule()의 페널티로 반영합니다.
    return rate


def to_24h(hour_12: int, ampm: str) -> int:
    """오전/오후 12시간 입력을 24시간제로 변환합니다."""
    h = int(hour_12)
    if ampm == "오전":
        return 0 if h == 12 else h
    return h if h == 12 else h + 12


def format_hour(hour: int) -> str:
    """24시간 정수를 UI 표시용 오전/오후 문구로 변환합니다."""
    h = int(hour) % 24
    ap = "오전" if h < 12 else "오후"
    hh = h if 1 <= h <= 12 else (12 if h % 12 == 0 else h % 12)
    return f"{ap} {hh}시"


def normalize_hours(hours: Iterable[int]) -> List[int]:
    """시간 리스트를 0~23 범위의 중복 없는 정렬 리스트로 변환합니다."""
    return sorted({int(h) % 24 for h in hours})


def hour_range(start: int, end: int) -> List[int]:
    """
    시작~종료 시간 리스트를 생성합니다.
    end가 start보다 작거나 같으면 자정 넘어가는 구간으로 처리합니다.
    예: 22~2 → [22, 23, 0, 1]
    """
    start = int(start) % 24
    end = int(end) % 24
    if start == end:
        return []
    if end > start:
        return list(range(start, end))
    return list(range(start, 24)) + list(range(0, end))


def appliance_segments(start_hour: int, hours: float, step: float = 0.5):
    """
    가전 운전시간을 시간대별 조각으로 나눕니다.
    기존 sel_dr.py의 hours % 1 방식은 1.5시간에서 0.5시간이 중복될 수 있어 수정했습니다.
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


def appliance_active_hours(start_hour: int, hours: float) -> List[int]:
    """가전이 실제로 걸치는 시간대 목록을 반환합니다."""
    return normalize_hours(h for h, _duration in appliance_segments(start_hour, hours))


def _is_away_hour(hour: int, work_start: int, work_end: int, commute: str = "일반 가정") -> bool:
    """외출/부재 시간대 여부를 계산합니다.

    UI에서는 출퇴근 유형을 제거하고 일반 가정의 외출 시간대로만 입력받습니다.
    기존 파일과의 호환을 위해 과거 commute 값도 함께 처리합니다.
    """
    h = int(hour) % 24
    if commute in {"일반 가정", "출근함 (집 비움)"}:
        return work_start <= h < work_end
    if commute == "파트타임 (오전)":
        return work_start <= h < 13
    if commute == "파트타임 (오후)":
        return 13 <= h < work_end
    # 재택근무 또는 알 수 없는 값은 외출 없음으로 처리
    return False


def build_base_available_hours(
    wake_hour: int = 7,
    sleep_hour: int = 23,
    work_start: int = 9,
    work_end: int = 18,
    commute: str = "출근함 (집 비움)",
    allow_sleep: bool = True,
    allow_away: bool = True,
) -> List[int]:
    """
    사용자의 생활패턴으로 전체 기본 가용시간을 계산합니다.
    이 함수는 '가구 전체'의 기본 사용 가능 시간만 판단하고,
    소음/청소기/에어컨/전기차 같은 가전별 제약은 is_allowed_hour에서 따로 봅니다.
    """
    available = []
    for h in range(24):
        sleeping = h >= sleep_hour or h < wake_hour

        away = _is_away_hour(h, work_start, work_end, commute)

        ok = True
        if sleeping and not allow_sleep:
            ok = False
        if away and not allow_away:
            ok = False
        if ok:
            available.append(h)
    return available


def is_allowed_hour(
    appliance: str,
    hour: int,
    base_available: Iterable[int],
    wake_hour: int = 7,
    sleep_hour: int = 23,
    work_start: int = 9,
    work_end: int = 18,
    commute: str = "일반 가정",
    allow_sleep: bool = True,
    allow_away: bool = True,
) -> bool:
    """
    가전별로 특정 시간에 추천 가능한지 판단합니다.

    제약 우선순위
    1. 사용자의 기본 가용시간
    2. 소음 가전 야간/늦은 저녁 제한
    3. 활동 가전의 취침·외출 시간 제한
    4. 냉난방 가전의 의미 없는 새벽 가동 제한
    """
    h = int(hour) % 24
    base_available_set = {int(x) % 24 for x in base_available}

    if h not in base_available_set:
        return False

    sleeping = h >= sleep_hour or h < wake_hour
    away = _is_away_hour(h, work_start, work_end, commute)

    # 가전별 예약 허용 여부: 사용자가 가전 추가 단계에서 직접 선택
    if sleeping and not allow_sleep:
        return False
    if away and not allow_away:
        return False

    # 소음 제약: 저녁 8시 이후~오전 7시 제외
    if appliance in NOISY_APPLIANCES:
        if h >= NOISY_BLOCK_START or h < NOISY_BLOCK_END:
            return False

    # 활동시간 제약: 청소기 등은 사용자가 깨어 있고 집에 있는 시간에만 허용
    if appliance in ACTIVE_ONLY_APPLIANCES:
        sleeping = h >= sleep_hour or h < wake_hour
        if sleeping:
            return False

        away = _is_away_hour(h, work_start, work_end, commute)
        if away:
            return False

        # 너무 이른 아침/늦은 저녁 회피
        if h < 8 or h >= 21:
            return False

    # 냉난방 제약: 새벽 가동은 비현실적이므로 낮~밤 위주로 허용
    if appliance in CLIMATE_APPLIANCES:
        lo, hi = CLIMATE_HOUR_RANGE
        in_range = (lo <= h < hi) if hi <= 24 else (h >= lo or h < (hi - 24))
        if not in_range:
            return False

    return True


def is_allowed_schedule(
    appliance: str,
    start_hour: int,
    hours: float,
    base_available: Iterable[int],
    wake_hour: int = 7,
    sleep_hour: int = 23,
    work_start: int = 9,
    work_end: int = 18,
    commute: str = "일반 가정",
    allow_sleep: bool = True,
    allow_away: bool = True,
) -> bool:
    """가전의 전체 가동 구간이 제약을 만족하는지 판단합니다."""
    active_hours = appliance_active_hours(start_hour, hours)
    if not active_hours:
        return False

    return all(
        is_allowed_hour(
            appliance, h, base_available,
            wake_hour=wake_hour,
            sleep_hour=sleep_hour,
            work_start=work_start,
            work_end=work_end,
            commute=commute,
            allow_sleep=allow_sleep,
            allow_away=allow_away,
        )
        for h in active_hours
    )


def ev_deadline_ok(appliance: str, start_hour: int, hours: float, wake_hour: int = 7) -> bool:
    """
    전기차 충전 제약:
    - 저녁 이후 또는 새벽 시간에 시작
    - 다음날 기상 시간 전까지 충전 완료
    """
    if appliance not in EV_APPLIANCES:
        return True

    start = int(start_hour) % 24
    hours = float(hours)

    # 낮 시작은 비권장
    if not (start >= 18 or start < wake_hour):
        return False

    # 자정 넘어가는 충전 완료 시각 계산
    end_abs = start + hours
    if start < wake_hour:
        # 이미 새벽 시작이면 같은 날 기상 시간 전에 끝나야 함
        return end_abs <= wake_hour

    # 저녁 시작이면 다음날 기상 시간 전까지 끝나야 함
    return end_abs <= 24 + wake_hour



def _hours_until(current_hour: int, start_hour: int) -> int:
    """현재 시각에서 추천 시작 시각까지의 대기 시간을 0~23시간으로 계산합니다."""
    return (int(start_hour) % 24 - int(current_hour) % 24) % 24


def _schedule_overlaps_hours(start_hour: int, hours: float, target_hours: Iterable[int]) -> int:
    """가전 운전 구간이 특정 시간대와 겹치는 시간 슬롯 수를 반환합니다."""
    target = {int(h) % 24 for h in target_hours}
    return sum(1 for h in appliance_active_hours(start_hour, hours) if h in target)


def _schedule_overlap_kwh(start_hour: int, hours: float, watt: float, target_hours: Iterable[int]) -> float:
    """가전 운전 구간 중 특정 시간대와 겹치는 전력량(kWh)을 계산합니다."""
    target = {int(h) % 24 for h in target_hours}
    total = 0.0
    for h, duration in appliance_segments(start_hour, hours):
        if int(h) % 24 in target:
            total += float(watt) / 1000.0 * float(duration)
    return total


def dr_avoidance_penalty(
    appliance: str,
    start_hour: int,
    hours: float,
    watt: float,
    dr_mode: bool = False,
    dr_hours: Optional[Iterable[int]] = None,
    current_temp: Optional[float] = None,
    hourly_temps: Optional[Mapping[int, float]] = None,
    current_humidity: Optional[float] = None,
    hourly_humidity: Optional[Mapping[int, float]] = None,
) -> float:
    """
    DR 시간대 사용 회피 페널티입니다.
    - 일반 가전/전기차: DR 시간대 사용을 불리하게 만들어 회피 유도
    - 에어컨: 쾌적성 가전이므로 DR 시간대 사용을 금지하거나 강제 회피하지 않음
      대신 결과 설명에서 설정온도 상향/제습 중심의 완화 운전으로 안내
    """
    if not dr_mode or not dr_hours:
        return 0.0

    overlap_kwh = _schedule_overlap_kwh(start_hour, hours, watt, dr_hours)
    if overlap_kwh <= 0:
        return 0.0

    # 에어컨은 온도·습도에 따른 쾌적성 유지가 우선이므로 DR 회피 페널티를 적용하지 않습니다.
    # 요금 차이는 기본 시간대별 요금제(TOU) 비용에만 반영됩니다.
    if appliance == "에어컨":
        return 0.0

    if appliance in EV_APPLIANCES:
        rate = EV_DR_AVOID_PENALTY_PER_KWH
    elif appliance in ACTIVE_ONLY_APPLIANCES:
        rate = DIRECT_DR_AVOID_PENALTY_PER_KWH
    else:
        rate = DEFAULT_DR_AVOID_PENALTY_PER_KWH
    return overlap_kwh * rate


def _forecast_temp_at(hour: int, current_temp: Optional[float], hourly_temps: Optional[Mapping[int, float]]) -> Optional[float]:
    """시간별 예보가 있으면 해당 시간 기온을, 없으면 현재 기온을 사용합니다."""
    if hourly_temps:
        try:
            value = hourly_temps.get(int(hour) % 24)
            if value is not None:
                return float(value)
        except Exception:
            pass
    if current_temp is None:
        return None
    try:
        return float(current_temp)
    except Exception:
        return None


def _forecast_humidity_at(hour: int, current_humidity: Optional[float], hourly_humidity: Optional[Mapping[int, float]]) -> Optional[float]:
    """시간별 습도 예보가 있으면 해당 시간 습도를, 없으면 현재 습도를 사용합니다."""
    if hourly_humidity:
        try:
            value = hourly_humidity.get(int(hour) % 24)
            if value is not None:
                return float(value)
        except Exception:
            pass
    if current_humidity is None:
        return None
    try:
        return float(current_humidity)
    except Exception:
        return None


def _apparent_cooling_temp(temp: Optional[float], humidity: Optional[float]) -> Optional[float]:
    """
    에어컨 최적화용 체감 냉방 온도입니다.
    실제 기온에 습도 보정을 더해 고습 환경에서 냉방·제습 필요성이 커지도록 반영합니다.

    - 습도 60% 이하는 보정하지 않음
    - 습도 60% 초과분은 10%p당 약 0.7℃ 수준으로 보정
    - 과도한 튐을 막기 위해 최대 +2.5℃까지만 반영
    """
    if temp is None:
        return None
    if humidity is None:
        return float(temp)
    try:
        temp = float(temp)
        humidity = float(humidity)
    except Exception:
        return float(temp)
    humidity_bonus = max(0.0, humidity - 60.0) * 0.07
    humidity_bonus = min(humidity_bonus, 2.5)
    return temp + humidity_bonus


def aircon_comfort_penalty(
    start_hour: int,
    hours: float,
    current_hour: int,
    current_temp: Optional[float] = None,
    hourly_temps: Optional[Mapping[int, float]] = None,
    current_humidity: Optional[float] = None,
    hourly_humidity: Optional[Mapping[int, float]] = None,
    dr_mode: bool = False,
    dr_hours: Optional[Iterable[int]] = None,
) -> float:
    """
    에어컨 전용 쾌적성 페널티입니다.

    설계 의도
    - 30℃ 이상 또는 고습 체감 30℃ 이상: 쾌적성을 우선해 너무 늦은 시작을 강하게 억제
    - 27~29℃ 또는 고습 체감 27~29℃: 냉방/제습은 필요하지만 DR/피크 시간대 회피를 우선
    - 24~26℃: 냉방 필요성이 낮으므로 절감 효과가 클 때만 이동
    - 24℃ 미만: 에어컨 사용 우선순위를 낮춤
    """
    raw_temp = _forecast_temp_at(start_hour, current_temp, hourly_temps)
    humidity = _forecast_humidity_at(start_hour, current_humidity, hourly_humidity)
    temp = _apparent_cooling_temp(raw_temp, humidity)
    if temp is None:
        return 0.0

    wait = _hours_until(current_hour, start_hour)
    # 에어컨은 DR 시간대 사용 금지 대상이 아니라 쾌적성 가전으로 처리합니다.
    # 따라서 DR/피크 중첩 자체에 별도 페널티를 크게 주지 않고, 온습도와 지연 시간 중심으로 판단합니다.
    penalty = 0.0

    # 고습 환경은 같은 기온이라도 제습 필요성과 불쾌감이 커지므로 지연을 덜 선호합니다.
    if humidity is not None:
        if humidity >= AC_HUMIDITY_VERY_HIGH:
            penalty += 180
            if wait > 4:
                penalty += (wait - 4) * 55
        elif humidity >= AC_HUMIDITY_HIGH:
            penalty += 90
            if wait > 6:
                penalty += (wait - 6) * 35

    if temp >= AC_HOT_TEMP:
        # 폭염에 가까우면 장시간 지연이 비현실적이므로 현재~3시간 이내를 선호
        if wait > AC_MAX_COMFORT_DELAY:
            penalty += (wait - AC_MAX_COMFORT_DELAY) * 260
    elif temp >= AC_WARM_TEMP:
        # 더운 날은 냉방·제습 필요성이 있으므로 과도한 지연만 억제
        if wait > 6:
            penalty += (wait - 6) * 70
    elif temp >= AC_MILD_TEMP:
        # 애매한 날씨에서는 냉방 필요성을 낮게 보되, DR 시간대 사용 자체를 금지하지 않음
        penalty += 220
    else:
        # 충분히 시원하면 냉방 추천 우선순위를 크게 낮춤
        penalty += 900

    # 취침 직전 새로 켜는 추천은 불편할 수 있으므로 약한 페널티
    if 22 <= int(start_hour) % 24 <= 23:
        penalty += 120

    return penalty


def climate_constraint_note(
    appliance: str,
    moved: bool = True,
    current_temp: Optional[float] = None,
    current_humidity: Optional[float] = None,
) -> str:
    """냉난방 가전 결과표에 표시할 온도 기반 제약 문구입니다."""
    if appliance != "에어컨":
        return "🌡️ 냉난방 시간대 (새벽 제외)"
    if not moved:
        return "✅ 현재 사용 유지 (온도·절감액 고려)"
    if current_temp is None:
        return "🌡️ 냉방 시간대 + 쾌적성 고려"
    try:
        temp = float(current_temp)
    except Exception:
        return "🌡️ 냉방 시간대 + 쾌적성 고려"
    humidity = None
    try:
        humidity = float(current_humidity) if current_humidity is not None else None
    except Exception:
        humidity = None
    apparent_temp = _apparent_cooling_temp(temp, humidity) or temp
    if humidity is not None and humidity >= AC_HUMIDITY_VERY_HIGH:
        return "💧 고습 제습 + 쾌적성 우선"
    if apparent_temp >= AC_HOT_TEMP:
        return "🌡️ 폭염/고습 대응 (쾌적성 우선)"
    if apparent_temp >= AC_WARM_TEMP:
        return "🌡️ 더위·습도 대응 + 완화 운전"
    if apparent_temp >= AC_MILD_TEMP:
        return "🌡️ 냉방 필요 낮음 + 비용 고려"
    return "🌿 냉방 필요 낮음"

def constraint_note(appliance: str, moved: bool = True) -> str:
    """UI 테이블에 표시할 제약 사유 문구를 반환합니다."""
    if not moved:
        return "✅ 지금이 적절 (옮길 실익 적음)"
    if appliance in EV_APPLIANCES:
        return "🌙 기상 전 충전 완료"
    if appliance in ACTIVE_ONLY_APPLIANCES:
        return "🏠 직접 사용 시간 (취침·외출 제외)"
    if appliance in CLIMATE_APPLIANCES:
        return "🌡️ 냉난방 시간대 (새벽 제외)"
    if appliance in NOISY_APPLIANCES:
        return "🔇 소음 배려 (야간 제외)"
    return "⏰ 자유 배치"


def cost_at(
    appliance: str,
    start_hour: int,
    info: Mapping[str, Any],
    dr_mode: bool = False,
    dr_hours: Optional[Iterable[int]] = None,
    dr_reward: float = 150,
    rate_func: Optional[Callable[..., float]] = None,
) -> float:
    """
    특정 가전을 특정 시작시간에 운전할 때의 전력량요금을 계산합니다.
    """
    if rate_func is None:
        rate_func = _default_rate_func

    watt = float(info.get("watt", 0))
    hours = float(info.get("hours", 0))
    if watt <= 0 or hours <= 0:
        return 0.0

    total = 0.0
    for h, duration in appliance_segments(start_hour, hours):
        kwh = watt / 1000 * duration
        total += kwh * rate_func(h, dr_mode, dr_hours, dr_reward)
    return total


def build_hourly_costs(
    selected: Mapping[str, Mapping[str, Any]],
    dr_mode: bool = False,
    dr_hours: Optional[Iterable[int]] = None,
    dr_reward: float = 150,
    rate_func: Optional[Callable[..., float]] = None,
) -> List[Dict[str, Any]]:
    """
    전체 등록 가전에 대해 시작시간 0~23시의 비용을 계산합니다.
    UI의 시간대별 막대그래프나 TOP3 추천에 사용할 수 있습니다.
    """
    if rate_func is None:
        rate_func = _default_rate_func

    hourly_costs = []
    for start in range(24):
        total_tou = 0.0
        total_dr = 0.0
        detail = []

        for name, info in selected.items():
            c_tou = cost_at(name, start, info, False, dr_hours, dr_reward, rate_func)
            c_dr = cost_at(name, start, info, True, dr_hours, dr_reward, rate_func)

            total_tou += c_tou
            total_dr += c_dr

            detail.append({
                "기기": name,
                "사용시간": f"{float(info.get('hours', 0)):g}시간",
                "TOU 요금": round(c_tou),
                "TOU+DR": round(c_dr),
                "DR 절약": max(round(c_tou - c_dr), 0),
            })

        hourly_costs.append({
            "시작시간": start,
            "TOU요금": round(total_tou),
            "TOU_DR요금": round(total_dr),
            "총요금": round(total_dr if dr_mode else total_tou),
            "detail": detail,
        })

    return hourly_costs



def _is_after_process_start(prev_start: int, prev_hours: float, candidate_start: int) -> bool:
    """세탁기→건조기처럼 선행 가전이 끝난 뒤 후행 가전이 시작되는지 확인합니다."""
    wait = _hours_until(int(prev_start) % 24, int(candidate_start) % 24)
    return wait >= float(prev_hours)


def optimize_appliance_schedule(
    selected: Mapping[str, Mapping[str, Any]],
    current_hour: int,
    available_hours: Iterable[int],
    wake_hour: int = 7,
    sleep_hour: int = 23,
    work_start: int = 9,
    work_end: int = 18,
    commute: str = "출근함 (집 비움)",
    dr_mode: bool = False,
    dr_hours: Optional[Iterable[int]] = None,
    dr_reward: float = 150,
    min_saving_won: float = DEFAULT_MIN_SAVING_WON,
    spread_penalty_per_kw: float = DEFAULT_SPREAD_PENALTY_PER_KW,
    appliance_icons: Optional[Mapping[str, str]] = None,
    rate_func: Optional[Callable[..., float]] = None,
    current_temp: Optional[float] = None,
    hourly_temps: Optional[Mapping[int, float]] = None,
    current_humidity: Optional[float] = None,
    hourly_humidity: Optional[Mapping[int, float]] = None,
) -> Dict[str, Any]:
    """
    가전별 현실 제약과 분산 제약을 반영해 최적 시작시간을 계산합니다.

    반환값 주요 필드
    - hourly_costs: 전체 등록 가전을 같은 시작시간에 운전한다고 가정한 24시간 비용
    - optimal: 전체 등록 가전 기준 최저 비용 시작시간
    - per_appliance_plan: 가전별 맞춤 추천 시간
    - plan_rows: UI dataframe에 바로 넣기 좋은 형태
    - current_temp/hourly_temps/current_humidity/hourly_humidity: 에어컨 추천 시 기온·습도와 시간별 예보를 반영
    """
    if rate_func is None:
        rate_func = _default_rate_func
    if dr_hours is None:
        dr_hours = []
    if appliance_icons is None:
        appliance_icons = {}

    selected = {
        name: {
            "watt": float(info.get("watt", 0)),
            "hours": float(info.get("hours", 0)),
            "allow_sleep": bool(info.get("allow_sleep", True)),
            "allow_away": bool(info.get("allow_away", True)),
        }
        for name, info in selected.items()
        if float(info.get("watt", 0)) > 0 and float(info.get("hours", 0)) > 0
    }

    available_hours = normalize_hours(available_hours)
    if not available_hours:
        available_hours = list(range(24))

    hourly_costs = build_hourly_costs(
        selected,
        dr_mode=dr_mode,
        dr_hours=dr_hours,
        dr_reward=dr_reward,
        rate_func=rate_func,
    )

    now_cost = hourly_costs[int(current_hour) % 24]["총요금"]
    avail_costs = [c for c in hourly_costs if c["시작시간"] in available_hours] or hourly_costs
    optimal = min(avail_costs, key=lambda x: x["총요금"])
    opt_h = optimal["시작시간"]
    opt_cost = optimal["총요금"]
    saving = now_cost - opt_cost
    saving_pct = round(saving / now_cost * 100) if now_cost > 0 else 0

    used_slots: Dict[int, int] = {}
    per_appliance_plan: List[Dict[str, Any]] = []
    plan_by_name: Dict[str, Dict[str, Any]] = {}

    # 세탁기와 건조기를 함께 등록하면 두 가전을 하나의 세탁-건조 세트로 봅니다.
    # 세탁기 사용 직후 또는 1시간 이내에 건조기가 이어지도록 후보를 같이 평가합니다.
    priority = {"세탁기": 0, "건조기": 1}
    ordered_names = sorted(selected.keys(), key=lambda n: (priority.get(n, 2), list(selected.keys()).index(n)))
    processed_names = set()

    if "세탁기" in selected and "건조기" in selected:
        washer_info = selected["세탁기"]
        dryer_info = selected["건조기"]
        washer_hours = float(washer_info["hours"])
        dryer_hours = float(dryer_info["hours"])
        pair_candidates = []

        for washer_start in range(24):
            washer_allow_sleep = bool(washer_info.get("allow_sleep", True))
            washer_allow_away = bool(washer_info.get("allow_away", True))
            if not is_allowed_schedule(
                "세탁기", washer_start, washer_hours, available_hours,
                wake_hour=wake_hour, sleep_hour=sleep_hour,
                work_start=work_start, work_end=work_end, commute=commute,
                allow_sleep=washer_allow_sleep, allow_away=washer_allow_away,
            ):
                continue

            washer_end = (float(washer_start) + float(washer_hours)) % 24
            # 현실성을 위해 건조기는 세탁 종료 직후를 최우선으로 보고, 불가하면 1시간 이내 후보만 허용합니다.
            for dryer_gap in [0, 1]:
                dryer_start = (washer_end + dryer_gap) % 24
                dryer_allow_sleep = bool(dryer_info.get("allow_sleep", True))
                dryer_allow_away = bool(dryer_info.get("allow_away", True))
                if not is_allowed_schedule(
                    "건조기", dryer_start, dryer_hours, available_hours,
                    wake_hour=wake_hour, sleep_hour=sleep_hour,
                    work_start=work_start, work_end=work_end, commute=commute,
                    allow_sleep=dryer_allow_sleep, allow_away=dryer_allow_away,
                ):
                    continue

                washer_cost = cost_at("세탁기", washer_start, washer_info, False, dr_hours, dr_reward, rate_func)
                dryer_cost = cost_at("건조기", dryer_start, dryer_info, False, dr_hours, dr_reward, rate_func)
                washer_dr_penalty = dr_avoidance_penalty(
                    appliance="세탁기", start_hour=washer_start, hours=washer_hours,
                    watt=float(washer_info["watt"]), dr_mode=dr_mode, dr_hours=dr_hours,
                    current_temp=current_temp, hourly_temps=hourly_temps,
                    current_humidity=current_humidity, hourly_humidity=hourly_humidity,
                )
                dryer_dr_penalty = dr_avoidance_penalty(
                    appliance="건조기", start_hour=dryer_start, hours=dryer_hours,
                    watt=float(dryer_info["watt"]), dr_mode=dr_mode, dr_hours=dr_hours,
                    current_temp=current_temp, hourly_temps=hourly_temps,
                    current_humidity=current_humidity, hourly_humidity=hourly_humidity,
                )
                # 건조기가 세탁 직후일수록 선호하고, 1시간 지연은 작은 페널티만 줍니다.
                chain_penalty = dryer_gap * 80
                spread_penalty = (
                    used_slots.get(washer_start, 0) * (float(washer_info["watt"]) / 1000) * spread_penalty_per_kw
                    + used_slots.get(dryer_start, 0) * (float(dryer_info["watt"]) / 1000) * spread_penalty_per_kw
                )
                score = washer_cost + dryer_cost + washer_dr_penalty + dryer_dr_penalty + chain_penalty + spread_penalty
                pair_candidates.append({
                    "washer_start": washer_start,
                    "dryer_start": dryer_start,
                    "dryer_gap": dryer_gap,
                    "washer_cost": round(washer_cost),
                    "dryer_cost": round(dryer_cost),
                    "score": score,
                })

        # 제약이 너무 엄격해 후보가 없는 경우에도 건조기가 세탁보다 먼저 가는 결과는 막습니다.
        # 이때는 세탁기 사용 가능 후보 중 가장 낮은 비용 시간을 잡고, 건조기를 세탁 직후로 강제 배치합니다.
        if not pair_candidates:
            relaxed_washer_candidates = []
            for washer_start in range(24):
                if is_allowed_schedule(
                    "세탁기", washer_start, washer_hours, available_hours,
                    wake_hour=wake_hour, sleep_hour=sleep_hour,
                    work_start=work_start, work_end=work_end, commute=commute,
                    allow_sleep=bool(washer_info.get("allow_sleep", True)),
                    allow_away=bool(washer_info.get("allow_away", True)),
                ):
                    dryer_start = (float(washer_start) + float(washer_hours)) % 24
                    washer_cost = cost_at("세탁기", washer_start, washer_info, False, dr_hours, dr_reward, rate_func)
                    dryer_cost = cost_at("건조기", dryer_start, dryer_info, False, dr_hours, dr_reward, rate_func)
                    score = washer_cost + dryer_cost + dr_avoidance_penalty(
                        appliance="세탁기", start_hour=washer_start, hours=washer_hours,
                        watt=float(washer_info["watt"]), dr_mode=dr_mode, dr_hours=dr_hours,
                        current_temp=current_temp, hourly_temps=hourly_temps,
                        current_humidity=current_humidity, hourly_humidity=hourly_humidity,
                    ) + dr_avoidance_penalty(
                        appliance="건조기", start_hour=dryer_start, hours=dryer_hours,
                        watt=float(dryer_info["watt"]), dr_mode=dr_mode, dr_hours=dr_hours,
                        current_temp=current_temp, hourly_temps=hourly_temps,
                        current_humidity=current_humidity, hourly_humidity=hourly_humidity,
                    )
                    relaxed_washer_candidates.append({
                        "washer_start": washer_start,
                        "dryer_start": dryer_start,
                        "dryer_gap": 0,
                        "washer_cost": round(washer_cost),
                        "dryer_cost": round(dryer_cost),
                        "score": score + 300,
                    })
            pair_candidates = relaxed_washer_candidates

        if pair_candidates:
            pair_best = min(pair_candidates, key=lambda x: x["score"])
            for pair_name, pair_start_key, pair_cost_key, pair_note in [
                ("세탁기", "washer_start", "washer_cost", "🧺 세탁-건조 세트 시작"),
                ("건조기", "dryer_start", "dryer_cost", "🌬️ 세탁 종료 직후 건조"),
            ]:
                info = selected[pair_name]
                pair_start = int(pair_best[pair_start_key]) % 24
                pair_hours = float(info["hours"])
                plan = {
                    "name": pair_name,
                    "icon": appliance_icons.get(pair_name, "⚡"),
                    "start": pair_start,
                    "end": (float(pair_start) + float(pair_hours)) % 24,
                    "hours": pair_hours,
                    "cost": int(pair_best[pair_cost_key]),
                    "moved": True,
                    "constrained": True,
                    "constraint_note": pair_note,
                }
                per_appliance_plan.append(plan)
                plan_by_name[pair_name] = plan
                used_slots[pair_start] = used_slots.get(pair_start, 0) + 1
                processed_names.add(pair_name)

    for name in ordered_names:
        if name in processed_names:
            continue
        info = selected[name]
        watt = float(info["watt"])
        hours = float(info["hours"])
        allow_sleep = bool(info.get("allow_sleep", True))
        allow_away = bool(info.get("allow_away", True))

        candidates = []
        for start in range(24):
            if not is_allowed_schedule(
                name,
                start,
                hours,
                available_hours,
                wake_hour=wake_hour,
                sleep_hour=sleep_hour,
                work_start=work_start,
                work_end=work_end,
                commute=commute,
                allow_sleep=allow_sleep,
                allow_away=allow_away,
            ):
                continue

            if not ev_deadline_ok(name, start, hours, wake_hour=wake_hour):
                continue

            # 세탁기와 건조기를 함께 등록한 경우, 건조기는 세탁기 종료 이후만 후보로 허용합니다.
            if name == "건조기" and "세탁기" in plan_by_name:
                washer_plan = plan_by_name["세탁기"]
                if not _is_after_process_start(washer_plan["start"], washer_plan["hours"], start):
                    continue

            # DR 시간대는 할인하지 않고 기본 TOU 요금으로 계산합니다.
            # DR 회피는 아래 dr_penalty로 별도 반영합니다.
            base_cost = cost_at(name, start, info, False, dr_hours, dr_reward, rate_func)
            crowd = used_slots.get(start, 0)
            spread_penalty = crowd * (watt / 1000) * spread_penalty_per_kw
            climate_penalty = 0.0
            if name == "에어컨":
                climate_penalty = aircon_comfort_penalty(
                    start_hour=start,
                    hours=hours,
                    current_hour=current_hour,
                    current_temp=current_temp,
                    hourly_temps=hourly_temps,
                    current_humidity=current_humidity,
                    hourly_humidity=hourly_humidity,
                    dr_mode=dr_mode,
                    dr_hours=dr_hours,
                )
            dr_penalty = dr_avoidance_penalty(
                appliance=name,
                start_hour=start,
                hours=hours,
                watt=watt,
                dr_mode=dr_mode,
                dr_hours=dr_hours,
                current_temp=current_temp,
                hourly_temps=hourly_temps,
                current_humidity=current_humidity,
                hourly_humidity=hourly_humidity,
            )
            score = base_cost + spread_penalty + climate_penalty + dr_penalty

            candidates.append({
                "start": start,
                "cost": round(base_cost),
                "score": score,
                "spread_penalty": round(spread_penalty, 2),
                "climate_penalty": round(climate_penalty, 2),
                "dr_penalty": round(dr_penalty, 2),
            })

        if candidates:
            best = min(candidates, key=lambda x: x["score"])
            best_start = best["start"]
            best_cost = best["cost"]
            moved = True

            now_allowed = is_allowed_schedule(
                name,
                current_hour,
                hours,
                available_hours,
                wake_hour=wake_hour,
                sleep_hour=sleep_hour,
                work_start=work_start,
                work_end=work_end,
                commute=commute,
                allow_sleep=allow_sleep,
                allow_away=allow_away,
            ) and ev_deadline_ok(name, current_hour, hours, wake_hour=wake_hour)
            if name == "건조기" and "세탁기" in plan_by_name:
                washer_plan = plan_by_name["세탁기"]
                now_allowed = now_allowed and _is_after_process_start(washer_plan["start"], washer_plan["hours"], current_hour)

            now_cost_one = round(cost_at(name, current_hour, info, False, dr_hours, dr_reward, rate_func))

            # 현재 사용이 제약을 만족하고 절감액이 작으면 이동하지 않음
            if now_allowed and (now_cost_one - best_cost) < min_saving_won:
                best_start = int(current_hour) % 24
                best_cost = now_cost_one
                moved = False
            else:
                used_slots[best_start] = used_slots.get(best_start, 0) + 1
        else:
            # 제약을 만족하는 시간이 없으면 전체 가용시간 중 최저가로 폴백
            best_start = opt_h
            best_cost = None
            moved = True

        end_hour = (best_start + int(round(hours))) % 24
        icon = appliance_icons.get(name, "⚡")

        note = climate_constraint_note(name, moved, current_temp, current_humidity) if name in CLIMATE_APPLIANCES else constraint_note(name, moved)
        if name == "건조기" and "세탁기" in plan_by_name:
            note = "🧺 세탁 종료 후 건조"

        plan = {
            "name": name,
            "icon": icon,
            "start": best_start,
            "end": end_hour,
            "hours": hours,
            "cost": best_cost,
            "moved": moved,
            "constrained": (
                name in NOISY_APPLIANCES
                or name in ACTIVE_ONLY_APPLIANCES
                or name in CLIMATE_APPLIANCES
                or name in EV_APPLIANCES
            ),
            "constraint_note": note,
        }
        per_appliance_plan.append(plan)
        plan_by_name[name] = plan

    plan_rows = []
    for plan in per_appliance_plan:
        plan_rows.append({
            "기기": f"{plan['icon']} {plan['name']}",
            "추천 시작": format_hour(plan["start"]),
            "종료": format_hour(plan["end"]),
            "예상 요금": f"{plan['cost']:,}원" if plan["cost"] is not None else "—",
            "제약": plan["constraint_note"],
        })

    top3 = sorted(avail_costs, key=lambda x: x["총요금"])[:3]

    return {
        "hourly_costs": hourly_costs,
        "available_hours": available_hours,
        "now_cost": now_cost,
        "optimal": optimal,
        "optimal_hour": opt_h,
        "optimal_cost": opt_cost,
        "saving": saving,
        "saving_pct": saving_pct,
        "top3": top3,
        "per_appliance_plan": per_appliance_plan,
        "plan_rows": plan_rows,
    }


if __name__ == "__main__":
    sample_selected = {
        "세탁기": {"watt": 500, "hours": 1.5},
        "건조기": {"watt": 3000, "hours": 1.0},
        "전기차 충전": {"watt": 7000, "hours": 2.0},
        "청소기": {"watt": 1000, "hours": 0.5},
    }

    available = build_base_available_hours(
        wake_hour=7,
        sleep_hour=23,
        work_start=9,
        work_end=18,
        commute="출근함 (집 비움)",
        allow_sleep=True,
        allow_away=True,
    )

    result = optimize_appliance_schedule(
        sample_selected,
        current_hour=18,
        available_hours=available,
        wake_hour=7,
        sleep_hour=23,
        work_start=9,
        work_end=18,
        commute="출근함 (집 비움)",
        dr_mode=True,
        dr_hours=range(17, 21),
        dr_reward=150,
        appliance_icons={
            "세탁기": "🫧",
            "건조기": "🌬️",
            "전기차 충전": "🚗",
            "청소기": "🌀",
        },
        current_temp=29.0,
    )

    print("최적 시작 시간:", result["optimal_hour"])
    print("현재 대비 절감액:", result["saving"])
    print("가전별 계획:")
    for row in result["plan_rows"]:
        print(row)
