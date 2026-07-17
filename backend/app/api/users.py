from fastapi import APIRouter

router = APIRouter()


@router.get("/users/me")
async def get_current_user():
    """获取当前用户信息（简化版，后续集成 JWT 认证）。"""
    return {
        "id": "anonymous",
        "nickname": "Guest",
    }
