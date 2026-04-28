def build_cash_prompt(analysis: dict) -> str:
    """
    시재예측용 프롬프트 생성

    Args:
        analysis: Python이 계산한 분석 결과 딕셔너리
            - term_id: 기번
            - location: 설치장소명
            - period_days: 분석 기간(일)
            - avg_daily_tx: 일평균 거래건수
            - max_daily_tx: 최대 일 거래건수
            - min_daily_tx: 최소 일 거래건수
            - stock_10000: 만원권 현재 잔량
            - stock_50000: 오만원권 현재 잔량
            - days_until_empty_10000: 만원권 소진 예상일
            - days_until_empty_50000: 오만원권 소진 예상일
            - last_addcash_date: 마지막 투입일
    """

    return f"""당신은 ATM 시재 관리 전문가입니다. 
    아래 분석 데이터를 바탕으로 운영자에게 보충 시점과 조치사항을 안내해주세요.

    [ATM 정보]
    - 기번: {analysis['term_id']}
    - 설치장소: {analysis['location']}

    [거래 분석 ({analysis['period_days']}일간)]
    - 일평균 거래: {analysis['avg_daily_tx']}건
    - 최대 일 거래: {analysis['max_daily_tx']}건
    - 최소 일 거래: {analysis['min_daily_tx']}건

    [현재 잔량]
    - 만원권: {analysis['stock_10000']}장 (약 {analysis['days_until_empty_10000']}일 후 소진)
    - 오만원권: {analysis['stock_50000']}장 (약 {analysis['days_until_empty_50000']}일 후 소진)
    - 마지막 투입일: {analysis['last_addcash_date']}
    
    3문장 이내로 핵심만 답변해주세요:
    1) 보충이 시급한가? (긴급/주의/양호)
    2) 언제까지 보충해야 하는가?
    3) 권종별 권장 보충량
    """

def build_fault_prompt(analysis: dict) -> str:
    """
    장애예측용 프롬프트 생성

    Args:
        analysis: Python이 계산한 분석 결과 딕셔너리
            - term_id: 기번
            - location: 설치장소명
            - period_days: 분석 기간(일)
            - total_faults: 총 장애 건수
            - fault_summary: 장애유형별 요약 문자열
            - avg_run_rate: 평균 가동률(%)
            - recent_status: 현재 상태
            - top_fault_type: 최다 장애유형
            - fault_trend: 장애 추세 (증가/감소/유지)
    """

    return f"""당신은 ATM 장애 분석 전문가입니다.
    아래 분석 데이터를 바탕으로 장애 위험도와 예방 조치를 안내해주세요.

    [ATM 정보]
    - 기번: {analysis['term_id']}
    - 설치장소: {analysis['location']}

    [장애 분석 ({analysis['period_days']}일간)]
    - 총 장애 건수: {analysis['total_faults']}건
    - 장애유형별: {analysis['fault_summary']}
    - 최다 장애: {analysis['top_fault_type']}
    - 장애 추세: {analysis['fault_trend']}

    [가동 현황]
    - 평균 가동률: {analysis['avg_run_rate']}%
    - 현재 상태: {analysis['recent_status']}

    3문장 이내로 핵심만 답변해주세요:
    1) 장애 위험도는? (높음/보통/낮음)
    2) 가장 주의해야 할 장애유형과 이유
    3) 권장 예방 조치
    """

# 장애그룹코드 → 한글 변환 매핑
ERR_GROUP_NAMES = {
    "01": "CDM 장애",
    "02": "명세표부 장애",
    "04": "고객미숙",
    "16": "명세표 회수함",
    "25": "기타",
    "33": "통신 장애",
    "62": "카드부 장애",
    "71": "현금걸림",
    "73": "현금부족",
    "78": "현금미수취",
    "81": "만원권 부족",
    "82": "오만원권 부족",
}

# ATM 상태코드 → 한글 변환 매핑
ATM_STATUS_NAMES = {
    "1": "정상(온라인)",
    "3": "장애시작",
    "4": "장애중",
    "5": "복구",
    "6": "오프라인",
}

# 만원권/오만원권 상태 (MAN_STATUS, OMAN_STATUS)
CASH_STATUS_NAMES = {
    "0": "정상",
    "1": "니어엔드(부족임박)",
    "2": "엠프티(소진)",
}