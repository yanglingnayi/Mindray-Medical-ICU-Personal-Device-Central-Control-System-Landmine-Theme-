import asyncio

from app.hl7.mllp_server import MLLPServer

async def main():
    server = MLLPServer()
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())