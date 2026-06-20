#!/bin/bash
cd "$(dirname "$0")"

echo "=== SES Sender 重启 ==="

# 在 backend 容器内跑后端单元测试（依赖已装）。失败则返回非 0。
run_backend_tests() {
  echo "► 运行后端单元测试..."
  if ! docker ps --format '{{.Names}}' | grep -q '^ses-sender-backend$'; then
    echo "  (backend 容器未运行，先临时构建镜像跑测试)"
    docker-compose build backend >/dev/null 2>&1
    docker-compose run --rm --no-deps backend python -m pytest tests/ -q
    return $?
  fi
  docker exec ses-sender-backend python -m pytest tests/ -q
  return $?
}

# 重建后端前先跑测试，测试不过则中止部署。
guard_tests() {
  if ! run_backend_tests; then
    echo ""
    echo "✗ 测试未通过，已中止部署。请修复后重试，或用 'force' 跳过测试。"
    exit 1
  fi
  echo "✓ 测试通过"
  echo ""
}

case "${1:-all}" in
  all)
    guard_tests
    echo "► 重建并重启所有服务..."
    docker-compose up -d --build
    ;;
  backend|be)
    guard_tests
    echo "► 重建并重启 backend..."
    docker-compose up -d --build backend
    ;;
  force)
    echo "► 跳过测试，强制重建所有服务..."
    docker-compose up -d --build
    ;;
  test|t)
    run_backend_tests
    exit $?
    ;;
  frontend|fe)
    echo "► 重建并重启 frontend..."
    cd frontend && npm run build && cd ..
    docker-compose up -d --build frontend
    ;;
  mcp)
    echo "► 重建并重启 mcp..."
    docker-compose up -d --build mcp
    ;;
  quick|q)
    echo "► 快速重启（不重建镜像）..."
    docker-compose restart backend frontend
    ;;
  stop)
    echo "► 停止所有服务..."
    docker-compose down
    echo "✓ 已停止"
    exit 0
    ;;
  logs)
    docker-compose logs -f --tail=50 ${2:-backend}
    exit 0
    ;;
  status|ps)
    docker-compose ps
    exit 0
    ;;
  *)
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  all        跑测试 → 重建并重启所有服务（默认）"
    echo "  backend    跑测试 → 仅重建后端"
    echo "  force      跳过测试，强制重建所有服务"
    echo "  test       仅运行后端单元测试"
    echo "  frontend   构建前端并重启"
    echo "  mcp        仅重建 MCP 服务"
    echo "  quick      快速重启（不重建镜像）"
    echo "  stop       停止所有服务"
    echo "  logs [svc] 查看日志（默认 backend）"
    echo "  status     查看服务状态"
    exit 1
    ;;
esac

echo ""
echo "=== 服务状态 ==="
docker-compose ps
echo ""
echo "✓ 完成"
