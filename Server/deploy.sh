#!/bin/bash                                             
set -e                                                                              # 어떤 명령이든 에러 발생 시 즉시 스크립트 중단

echo "========================================="
echo "  ATMS 예측 모듈 서버 구축"
echo "========================================="
echo ""

# ─── 1. 사전 확인 ───────────────────────────
echo "[1/6] 사전 확인..."

if ! command -v docker &> /dev/null; then                                           # docker 명령어가 존재하는지 확인
    echo "ERROR: Docker가 설치되어 있지 않습니다."
    exit 1
fi
echo "  Docker: $(docker --version)"

# Docker Compose v2 확인/설치
if docker compose version &> /dev/null 2>&1; then
    COMPOSE="docker compose"
    echo "  Compose: $(docker compose version)"
elif command -v docker-compose &> /dev/null; then
    COMPOSE="docker-compose"
    echo "  Compose: $(docker-compose --version)"
else
    echo "  Docker Compose가 없습니다. 설치합니다..."
    DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
    mkdir -p "$DOCKER_CONFIG/cli-plugins"
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
        -o "$DOCKER_CONFIG/cli-plugins/docker-compose"
    chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"
    COMPOSE="docker compose"
    echo "  Compose 설치 완료: $(docker compose version)"
fi

echo ""

# ─── 2. 환경 설정 ───────────────────────────
echo "[2/6] 환경 설정..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "  .env 파일 생성됨 (.env.example 복사)"
        echo "  ⚠ .env 파일의 DB_PASSWORD를 반드시 수정하세요!"
        echo ""
        read -p "  .env 수정 후 Enter를 누르세요 (또는 Ctrl+C로 중단)... "
    fi
fi

echo ""

# ─── 3. 리소스 확인 ─────────────────────────
echo "[3/6] 서버 리소스 확인..."

TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
AVAIL_MEM=$(free -g | awk '/^Mem:/{print $7}')
CPU_COUNT=$(nproc)

echo "  CPU: ${CPU_COUNT}코어"
echo "  메모리: 전체 ${TOTAL_MEM}GB / 가용 ${AVAIL_MEM}GB"
echo "  필요: Ollama 10GB + Python 2GB = 12GB"

if [ "$AVAIL_MEM" -lt 12 ]; then
    echo "  ⚠ 가용 메모리가 12GB 미만입니다. 계속하시겠습니까?"
    read -p "  계속하려면 Enter (중단: Ctrl+C)... "
fi

echo ""

# ─── 4. 컨테이너 빌드 및 시작 ───────────────
echo "[4/6] 컨테이너 빌드 및 시작..."
$COMPOSE up -d --build

echo "  컨테이너 시작 완료"
echo ""

# ─── 5. Ollama 모델 다운로드 ─────────────────
echo "[5/6] Ollama 준비 대기 및 모델 다운로드..."

# Ollama 준비 대기 (최대 60초)
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "  Ollama 준비 완료"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ERROR: Ollama가 시작되지 않았습니다."
        echo "  로그 확인: docker logs atms-ollama"
        exit 1
    fi
    echo "  대기 중... ($i/30)"
    sleep 2
done

# 모델이 없으면 다운로드
if ! docker exec atms-ollama ollama list 2>/dev/null | grep -q "qwen3:8b"; then
    echo "  Qwen3 8B 모델 다운로드 시작 (약 5.2GB)..."
    echo "  ※ 네트워크 속도에 따라 시간이 걸릴 수 있습니다."
    docker exec atms-ollama ollama pull qwen3:8b                                    # 모델 다운로드
    echo "  모델 다운로드 완료"
else
    echo "  Qwen3 8B 모델 이미 존재"
fi

echo ""

# ─── 6. 상태 확인 ────────────────────────────
echo "[6/6] 최종 상태 확인..."
echo ""
echo "--- Ollama 모델 목록 ---"
docker exec atms-ollama ollama list
echo ""
echo "--- 컨테이너 상태 ---"
docker ps --filter "name=atms-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "--- API 헬스 체크 ---"
sleep 3
curl -s http://localhost:8500/health 2>/dev/null && echo "" || echo "  API가 아직 시작 중입니다. 잠시 후 재시도하세요."
echo ""

echo "========================================="
echo "  구축 완료!"
echo "========================================="
echo ""
echo "  Ollama:    http://localhost:11434"
echo "  예측 API:  http://localhost:8500"
echo "  API 문서:  http://localhost:8500/docs"
echo ""
echo "  리소스 제한:"
echo "    Ollama  → CPU 12코어, RAM 10GB (5분 유휴 시 모델 언로드)"
echo "    Python  → CPU 4코어,  RAM 2GB"
echo ""
echo "  유용한 명령어:"
echo "    로그 확인:    docker logs -f atms-ollama"
echo "    모델 테스트:  docker exec atms-ollama ollama run qwen3:8b '안녕하세요'"
echo "    중지:         $COMPOSE down"
echo "    재시작:       $COMPOSE restart"
echo ""
