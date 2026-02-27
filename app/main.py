from fastapi import FastAPI

from app.api.router import api_router

app = FastAPI(
    title="IG DM Engine",
    description="AI-powered Instagram DM lead generation and personalization platform",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
