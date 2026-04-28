import os 
import aiomysql
from datetime import datetime, timedelta

# 커넥션 풀(전역)
pool = None

async def init_pool():
    """앱 시작 시 호출 - DB 커넥션 풀 생성"""
    global pool
    pool = await aiomysql.create_pool(
        host=os.getenv("DB_HOST", "192.168.28.22"),
        port=int(os.getenv("DB_PORT", "1432")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        db=os.getenv("DB_NAME", "datm"),
        minsize=1,
        maxsize=5,
        autocommit=True,
    )

async def close_pool():
    """앱 종료 시 호출 - 풀 닫기"""
    global pool
    if pool: 
        pool.close()
        await pool.wait_closed()


async def get_atm_info(term_group_id: str, term_id: str) -> dict:
    """ATM 기본 정보 조회 (기기마스터)"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("""
                    SELECT a.TERM_GROUP_ID,
                        a.TERM_ID, 
                        a.ATM_CO_CD, 
                        a.MODEL_CD,
                        c.CORNER_NAME AS LOCATION_NAME,
                        a.ATM_STATUS, 
                        a.SERVICE_START_TIME, 
                        a.SERVICE_END_TIME
                    FROM t_atm a
                    LEFT JOIN t_corner c 
                        ON a.TERM_GROUP_ID = c.TERM_GROUP_ID 
                    AND a.CORNER_CD = c.CORNER_CD
                    WHERE a.TERM_GROUP_ID = %s
                    AND a.TERM_ID = %s
            """, (term_group_id, term_id,))
            return await cur.fetchone()


async def get_cash_data(term_group_id: str, term_id: str, days: int = 7, base_date: str = None) -> dict:
    """시재 예측용 데이터 조회"""
    if base_date:
        ref_date = datetime.strptime(base_date, "%Y%m%d")
    else:
        ref_date = datetime.now()


    start_date = (ref_date - timedelta(days=days)).strftime("%Y%m%d")
    end_date = base_date if base_date else datetime.now().strftime("%Y%m%d")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # 1) 최근 N일간 일별 거래건수 (t_atmrunhistory)
            await cur.execute("""
                SELECT BASE_DATE, 
                       TRANSACTION_CNT
                  FROM t_atmrunhistory
                 WHERE TERM_GROUP_ID = %s
                   AND TERM_ID = %s
                   AND BASE_DATE >= %s
                 ORDER BY BASE_DATE
            """, (term_group_id, term_id, start_date))
            daily_transactions = await cur.fetchall()

            # 2) 최근 시재투입 내역 (t_addcash)
            await cur.execute("""
                SELECT JNL_DATE, 
                       CASSETTE_NO, 
                       DENOM_CD,
                       ADD_CNT, 
                       REMAIN_CNT
                 FROM  t_addcash
                WHERE  TERM_GROUP_ID = %s
                  AND  TERM_ID = %s
                  AND  JNL_DATE >= %s
                ORDER BY JNL_DATE DESC, JNL_TIME DESC
            """, (term_group_id, term_id, start_date))
            addcash_history = await cur.fetchall()


            # 3) 가장 최근 잔량 (권종별)
            await cur.execute("""
                SELECT DENOM_CD, 
                       REMAIN_CNT, 
                       JNL_DATE
                 FROM  t_addcash
                WHERE  TERM_GROUP_ID  = %s
                  AND  TERM_ID = %s
                  AND  JNL_DATE <= %s
                ORDER BY JNL_DATE DESC, JNL_TIME DESC
                LIMIT 4
            """, (term_group_id, term_id, end_date))
            latest_stock = await cur.fetchall()

        return{
            "term_group_id": term_group_id,
            "term_id": term_id,
            "daily_transactions": daily_transactions,
            "addcash_history": addcash_history,
            "latest_stock": latest_stock
        }

async def get_fault_data(term_group_id: str, term_id: str, days: int = 30, base_date: str = None) -> dict:
    """장애 예측용 데이터 조회"""
    if base_date:
        ref_date = datetime.strptime(base_date, "%Y%m%d")
    else:
        ref_date = datetime.now()


    start_date = (ref_date - timedelta(days=days)).strftime("%Y%m%d")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:

            # 1) 장애그룹이력 (t_atmerrgrouphistory)
            await cur.execute("""
                SELECT BASE_DATE, 
                       ERR_GROUP_CD, 
                       FAULT_CNT, 
                       FAULT_TIME
                  FROM t_atmerrgrouphistory
                 WHERE TERM_GROUP_ID = %s
                   AND TERM_ID = %s
                   AND BASE_DATE >= %s
                ORDER BY BASE_DATE
            """, (term_group_id, term_id, start_date))
            fault_history = await cur.fetchall()

            # 2) 가동률 정보 (t_atmrunhistory)
            await cur.execute("""
                SELECT BASE_DATE,
                       CDM_BILL_FAULT_CNT, 
                       CDM_BILL_FAULT_TIME,
                       MACHINE_FAULT_CNT, 
                       MACHINE_FAULT_TIME,
                       CUS_FAULT_CNT, 
                       CUS_FAULT_TIME,
                       OPERATION_FAULT_CNT,
                       OPERATION_FAULT_TIME,
                       TOTAL_RUN_TIME, 
                       TOTAL_TARGET_TIME,
                       TRANSACTION_CNT
                FROM   t_atmrunhistory
                WHERE  TERM_GROUP_ID = %s
                AND    TERM_ID = %s
                AND    BASE_DATE >= %s
                """, (term_group_id, term_id, start_date))
            run_history = await cur.fetchall()

            # 3) 현재 ATM 상태 (t_atmmonitor 최신 1건)
            await cur.execute("""
                SELECT ATM_STATUS,
                       MAN_STATUS,
                       OMAN_STATUS,
                       ERR_CD,
                       JNL_DATE, 
                       JNL_TIME
                FROM   t_atmmonitor
                WHERE  TERM_GROUP_ID = %s
                  AND  TERM_ID = %s
                ORDER BY JNL_DATE DESC, JNL_TIME DESC
                LIMIT 1
                """, (term_group_id, term_id,))
            current_status = await cur.fetchone()
        return {
            "term_group_id": term_group_id,
            "term_id": term_id,
            "fault_history": fault_history,
            "run_history": run_history,
            "current_status": current_status
        }


