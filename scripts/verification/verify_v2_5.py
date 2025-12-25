import asyncio
import httpx

BASE_URL = "http://localhost:8000"

async def verify_v2_5():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # Check Diagnostics
        print("Checking Diagnostics...")
        r = await client.get("/diagnostics")
        assert r.status_code == 200
        data = r.json()
        print(f"Diagnostics: {data}")
        assert data['status'] == 'ok'
        assert data['checks']['database'] == 'ok'
        assert data['checks']['dependencies']['fastapi'] == 'installed'

if __name__ == "__main__":
    asyncio.run(verify_v2_5())
