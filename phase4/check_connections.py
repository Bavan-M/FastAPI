import asyncio
import asyncpg
import motor.motor_asyncio
import redis.asyncio as redis

async def check_postgres():
    try:
        conn=await asyncpg.connect(
            "postgresql://postgres:master@localhost:5432/fastapi_phase4"
        )
        version=await conn.fetchval("SELECT version()")
        print(f"PostgreSQL connected:{version[:30]}")
        await conn.close()
    except Exception as e:
        print(f"PostgreSQL failed {e}")

async def check_mongoDB():
    try:
        client=motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017")
        await client.admin.command("ping")
        print("MongoDB Connected")
        client.close()
    except Exception as e:
        print(f"MongoDB failed: {e}")

async def check_redis():
    try:
        r=redis.from_url("redis://localhost:6379")
        await r.ping()
        print("Redis connected")
        await r.aclose()
    except Exception as e:
        print(f"Redis failed {e}")

async def main():
    print("Checking all database conections")
    await check_postgres()
    await check_mongoDB()
    await check_redis()
    print("Done")

asyncio.run(main())
