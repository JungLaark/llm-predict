from database import get_atm_info, get_cash_data, get_fault_data
from llm import ask_llm_with_fallback
from prompts import (
    build_cash_prompt,
    build_fault_prompt,
    ERR_GROUP_NAMES,
    ATM_STATUS_NAMES,
    CASH_STATUS_NAMES,
)


# =============================================
# 시재 예측
# =============================================
async def predict_cash(term_group_id: str, term_id: str, days: int = 7, base_date: str = None) -> dict:
    """
    시재 예측 메인 함수
    흐름: DB 조회 → Python 계산 → 프롬프트 조립 → LLM 해석
    """

    # 1단계: DB에서 데이터 가져오기
    atm_info = await get_atm_info(term_group_id, term_id)
    cash_data = await get_cash_data(term_group_id, term_id, days, base_date)

    if not atm_info:
        return {"error": f"ATM-{term_group_id}-{term_id}을(를) 찾을 수 없습니다."}

    # 2단계: Python으로 통계 계산
    analysis = calculate_cash_analysis(atm_info, cash_data, days)

    # 3단계: 프롬프트 생성 + LLM 호출
    prompt = build_cash_prompt(analysis)
    fallback = build_cash_fallback(analysis)
    llm_response = await ask_llm_with_fallback(
        prompt, fallback_message=fallback, think=False, max_tokens=200
    )

    # 4단계: 결과 조합하여 반환
    return {
        "term_group_id": term_group_id,
        "term_id": term_id,
        "location": analysis["location"],
        "analysis": analysis,
        "llm_summary": llm_response,
    }


def calculate_cash_analysis(atm_info: dict, cash_data: dict, days: int) -> dict:
    """DB 데이터를 바탕으로 시재 통계를 계산한다 (Python이 계산 담당)"""

    # 일별 거래건수 리스트
    daily_txs = cash_data.get("daily_transactions") or []
    tx_counts = [row["TRANSACTION_CNT"] or 0 for row in daily_txs]

    # 평균/최대/최소 거래건수
    if tx_counts:
        avg_tx = round(sum(tx_counts) / len(tx_counts), 1)
        max_tx = max(tx_counts)
        min_tx = min(tx_counts)
    else:
        avg_tx = max_tx = min_tx = 0

    # 현재 잔량 파악 (가장 최근 투입 기록)
    latest_stock = cash_data.get("latest_stock") or []
    stock_10000 = 0
    stock_50000 = 0
    last_addcash_date = "정보없음"

    for row in latest_stock:
        denom = str(row.get("DENOM_CD", ""))
        remain = row.get("REMAIN_CNT") or 0
        if "10000" in denom:
            stock_10000 = remain
            last_addcash_date = row.get("JNL_DATE", "정보없음")
        elif "50000" in denom:
            stock_50000 = remain

    # 소진 예상일 계산 (일평균 거래 기준, 거래 1건당 1장 가정)
    if avg_tx > 0:
        days_10000 = round(stock_10000 / avg_tx, 1)
        days_50000 = round(stock_50000 / (avg_tx * 0.3), 1)  # 오만원은 만원의 약 30% 사용
    else:
        days_10000 = 99
        days_50000 = 99

    return {
        "term_id": cash_data["term_id"],
        "location": atm_info.get("LOCATION_NAME", "알 수 없음"),
        "period_days": days,
        "avg_daily_tx": avg_tx,
        "max_daily_tx": max_tx,
        "min_daily_tx": min_tx,
        "stock_10000": stock_10000,
        "stock_50000": stock_50000,
        "days_until_empty_10000": days_10000,
        "days_until_empty_50000": days_50000,
        "last_addcash_date": last_addcash_date,
    }


def build_cash_fallback(analysis: dict) -> str:
    """LLM 실패 시 Python이 만드는 기본 메시지"""
    d10 = analysis["days_until_empty_10000"]
    if d10 <= 1:
        urgency = "긴급"
    elif d10 <= 3:
        urgency = "주의"
    else:
        urgency = "양호"

    return (
        f"[{urgency}] ATM {analysis['term_id']} - "
        f"만원권 잔량 {analysis['stock_10000']}장 "
        f"(약 {d10}일 후 소진 예상). "
        f"일평균 거래 {analysis['avg_daily_tx']}건."
    )


# =============================================
# 장애 예측
# =============================================
async def predict_fault(term_group_id: str, term_id: str, days: int = 30, base_date: str = None) -> dict:
    """
    장애 예측 메인 함수
    흐름: DB 조회 → Python 계산 → 프롬프트 조립 → LLM 해석
    """

    # 1단계: DB에서 데이터 가져오기
    atm_info = await get_atm_info(term_group_id, term_id)
    fault_data = await get_fault_data(term_group_id, term_id, days, base_date)

    if not atm_info:
        return {"error": f"ATM-{term_group_id}-{term_id}을(를) 찾을 수 없습니다."}

    # 2단계: Python으로 통계 계산
    analysis = calculate_fault_analysis(atm_info, fault_data, days)

    # 3단계: 프롬프트 생성 + LLM 호출
    prompt = build_fault_prompt(analysis)
    fallback = build_fault_fallback(analysis)
    llm_response = await ask_llm_with_fallback(
        prompt, fallback_message=fallback, think=False, max_tokens=200
    )

    # 4단계: 결과 조합하여 반환
    return {
        "term_group_id": term_group_id,
        "term_id": term_id,
        "location": analysis["location"],
        "analysis": analysis,
        "llm_summary": llm_response,
    }


def calculate_fault_analysis(atm_info: dict, fault_data: dict, days: int) -> dict:
    """DB 데이터를 바탕으로 장애 통계를 계산한다"""

    # 장애그룹별 집계
    fault_history = fault_data.get("fault_history") or []
    fault_by_type = {}
    total_faults = 0

    for row in fault_history:
        code = row.get("ERR_GROUP_CD", "99")
        cnt = row.get("FAULT_CNT") or 0
        name = ERR_GROUP_NAMES.get(code, f"기타({code})")
        fault_by_type[name] = fault_by_type.get(name, 0) + cnt
        total_faults += cnt

    # 장애유형별 요약 문자열
    if fault_by_type:
        fault_summary = ", ".join(
            f"{name} {cnt}건" for name, cnt in
            sorted(fault_by_type.items(), key=lambda x: x[1], reverse=True)
        )
        top_fault_type = max(fault_by_type, key=fault_by_type.get)
    else:
        fault_summary = "장애 이력 없음"
        top_fault_type = "없음"

    # 가동률 계산
    run_history = fault_data.get("run_history") or []
    run_rates = []
    for row in run_history:
        target = row.get("TOTAL_TARGET_TIME") or 0
        actual = row.get("TOTAL_RUN_TIME") or 0
        if target > 0:
            run_rates.append(round(actual / target * 100, 1))

    avg_run_rate = round(sum(run_rates) / len(run_rates), 1) if run_rates else 0

    # 장애 추세 판단 (전반기 vs 후반기)
    fault_trend = calculate_trend(fault_history)

    # 현재 상태
    current = fault_data.get("current_status")
    if current:
        atm_st = ATM_STATUS_NAMES.get(str(current.get("ATM_STATUS", "")), "알 수 없음")
        man_st = CASH_STATUS_NAMES.get(str(current.get("MAN_STATUS", "")), "알 수 없음")
        recent_status = f"ATM: {atm_st}, 만원권: {man_st}"
    else:
        recent_status = "상태 정보 없음"

    return {
        "term_id": fault_data["term_id"],
        "location": atm_info.get("LOCATION_NAME", "알 수 없음"),
        "period_days": days,
        "total_faults": total_faults,
        "fault_summary": fault_summary,
        "top_fault_type": top_fault_type,
        "fault_trend": fault_trend,
        "avg_run_rate": avg_run_rate,
        "recent_status": recent_status,
    }


def calculate_trend(fault_history: list) -> str:
    """장애 이력을 전반/후반으로 나눠 추세를 판단한다"""
    if len(fault_history) < 2:
        return "데이터 부족"

    mid = len(fault_history) // 2
    first_half = sum(row.get("FAULT_CNT", 0) or 0 for row in fault_history[:mid])
    second_half = sum(row.get("FAULT_CNT", 0) or 0 for row in fault_history[mid:])

    if second_half > first_half * 1.3:
        return "증가"
    elif second_half < first_half * 0.7:
        return "감소"
    else:
        return "유지"


def build_fault_fallback(analysis: dict) -> str:
    """LLM 실패 시 Python이 만드는 기본 메시지"""
    total = analysis["total_faults"]
    if total >= 10:
        risk = "높음"
    elif total >= 3:
        risk = "보통"
    else:
        risk = "낮음"

    return (
        f"[위험도: {risk}] ATM {analysis['term_id']} - "
        f"{analysis['period_days']}일간 장애 {total}건 발생. "
        f"최다 장애: {analysis['top_fault_type']}. "
        f"추세: {analysis['fault_trend']}."
    )


# =============================================
# 데이터 조회 (LLM 없이 즉시 응답)
# =============================================
async def data_cash(term_group_id: str, term_id: str, days: int = 7, base_date: str = None) -> dict:
    atm_info = await get_atm_info(term_group_id, term_id)
    cash_data = await get_cash_data(term_group_id, term_id, days, base_date)
    if not atm_info:
        return {"error": f"ATM-{term_group_id}-{term_id}을(를) 찾을 수 없습니다."}
    analysis = calculate_cash_analysis(atm_info, cash_data, days)
    return {
        "term_group_id": term_group_id,
        "term_id": term_id,
        "location": analysis["location"],
        "analysis": analysis,
        "daily_transactions": cash_data.get("daily_transactions", []),
        "addcash_history": cash_data.get("addcash_history", []),
        "latest_stock": cash_data.get("latest_stock", []),
    }

async def data_fault(term_group_id: str, term_id: str, days: int = 30, base_date: str = None) -> dict:
    atm_info = await get_atm_info(term_group_id, term_id)
    fault_data = await get_fault_data(term_group_id, term_id, days, base_date)
    if not atm_info:
        return {"error": f"ATM-{term_group_id}-{term_id}을(를) 찾을 수 없습니다."}
    analysis = calculate_fault_analysis(atm_info, fault_data, days)
    return {
        "term_group_id": term_group_id,
        "term_id": term_id,
        "location": analysis["location"],
        "analysis": analysis,
        "fault_history": fault_data.get("fault_history", []),
        "run_history": fault_data.get("run_history", []),
        "current_status": fault_data.get("current_status"),
    }