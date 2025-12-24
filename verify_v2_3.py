import asyncio
import httpx
import json

BASE_URL = "http://localhost:8000"

async def test_v2_3_features():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        print("Checking health...")
        r = await client.get("/health")
        print(f"Health: {r.json()}")

        # 1. Create Team
        print("\nCreating Team...")
        try:
            r = await client.post("/teams", json={"id": "team-alpha", "name": "Alpha Squad"})
            print(f"Create Team: {r.status_code} - {r.json()}")
        except Exception as e:
            print(f"Team creation failed (might already exist): {e}")

        # 2. Create User
        print("\nCreating User...")
        try:
            r = await client.post("/users", json={"id": "user-1", "username": "jdoe", "team_id": "team-alpha", "role": "admin"})
            print(f"Create User: {r.status_code} - {r.json()}")
        except Exception as e:
            print(f"User creation failed: {e}")

        # 3. Add Comment (Need a result first, but we can try with a dummy result ID if FK enforcement is loose or we have data)
        # Note: SQLite Foreign Keys are off by default in some drivers unless enabled. 
        # But we added `foreign_keys=True`? No we didn't explicitly enable PRAGMA foreign_keys in `database.py`.
        # Let's try adding a comment.
        print("\nAdding Comment...")
        try:
            r = await client.post("/comments", json={"result_id": 1, "user_id": "user-1", "content": "This logic looks flawed."})
            print(f"Add Comment: {r.status_code} - {r.json()}")
        except Exception as e:
            print(f"Add Comment failed: {e}")

        # 4. Export Data
        print("\nExporting Data...")
        r = await client.get("/admin/export")
        print(f"Export Status: {r.status_code}")
        data = r.json()
        print(f"Export keys: {list(data.keys())}")
        if "teams" in data:
            print(f"Teams count: {len(data['teams'])}")
        if "comments" in data:  # We didn't add comments to export in the previous step? Let's check server.py content again.
            print(f"Comments count: {len(data.get('comments', []))}")

        # Check if comments were actually exported. I think I missed adding them to the export dict keys?
        # server.py: data["evaluations"]... I strictly added Teams, Users, Projects, Evals. I missed Comments in the keys assignment in export_data?
        # Let's check the code I wrote.
        
if __name__ == "__main__":
    asyncio.run(test_v2_3_features())
