import asyncio
import httpx

BASE_URL = "http://localhost:8000"

async def verify_v2_4():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        # 1. Trigger an action that should be logged (CREATE TEAM)
        print("Triggering action (Create Team)...")
        headers = {"X-User-ID": "audit-tester"}
        try:
            await client.post("/teams", json={"id": "audit-team", "name": "Audit Team"}, headers=headers)
        except Exception:
            pass # Ignore if exists

        # 2. Check Audit Logs
        print("Checking Audit Logs...")
        r = await client.get("/audit-logs")
        logs = r.json()
        print(f"Audit Logs Found: {len(logs)}")
        if len(logs) > 0:
            print(f"Latest Log: {logs[0]}")
            assert logs[0]['user_id'] == 'audit-tester'
            assert 'POST /teams' in logs[0]['action']
        else:
            print("❌ No audit logs found!")

if __name__ == "__main__":
    asyncio.run(verify_v2_4())
