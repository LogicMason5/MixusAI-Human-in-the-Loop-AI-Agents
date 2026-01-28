from typing import List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from services.strategy_analyzer import (
    get_recommended_stocks,
    get_recommended_cryptos
)

router = APIRouter(
    prefix="/recommend",
    tags=["Recommendation"]
)


# =========================
# Response Models
# =========================

class RecommendationResponse(BaseModel):
    recommendations: List[dict]


# =========================
# Helpers
# =========================

def limit_results(items: List[dict], count: int) -> List[dict]:
    return items if count == 0 else items[:count]


# =========================
# Endpoints
# =========================

@router.get(
    "/stocks",
    response_model=RecommendationResponse,
    summary="Get stock recommendations"
)
async def get_stock_recommendations(
    count: int = Query(
        10,
        ge=0,
        le=100,
        description="Number of recommendations to return (0 = all)"
    )
):
    try:
        recommendations = get_recommended_stocks()
        return {
            "recommendations": limit_results(recommendations, count)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch stock recommendations: {str(e)}"
        )


@router.get(
    "/cryptos",
    response_model=RecommendationResponse,
    summary="Get crypto recommendations"
)
async def get_crypto_recommendations(
    count: int = Query(
        10,
        ge=0,
        le=100,
        description="Number of recommendations to return (0 = all)"
    )
):
    try:
        recommendations = get_recommended_cryptos()
        return {
            "recommendations": limit_results(recommendations, count)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch crypto recommendations: {str(e)}"
        )
