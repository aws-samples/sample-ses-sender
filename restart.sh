#!/bin/bash
cd "$(dirname "$0")"

echo "=== SES Sender 重启 ==="

case "${1:-all}" in
  all)
    echo "► 重建并重启所有服务..."
    docker-compose up -d --build
    ;;
  backend|be)
    echo "► 重建并重启 backend..."
    docker-compose up -d --build backend
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
    echo "  all        重建并重启所有服务（默认）"
    echo "  backend    仅重建后端"
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
