import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
import json
import asyncio

# Import the sprint wrappers from main
from main import _sprint1, _sprint2, _sprint3, _sprint4

app = FastAPI(title="Debate API")

# Allow CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QueryRequest(BaseModel):
    query: str

@app.post("/api/debate")
async def debate_endpoint(request: QueryRequest):
    query = request.query

    async def event_generator():
        try:
            # Yield initial status
            yield {
                "event": "status",
                "data": json.dumps({"status": "starting", "message": "Pipeline initialized."})
            }
            
            # Sprint 1
            # Run in a separate thread so we don't block the async event loop
            s1 = await asyncio.to_thread(_sprint1, query)
            yield {
                "event": "sprint1",
                "data": json.dumps(s1.model_dump())
            }

            # Sprint 2
            s2 = await asyncio.to_thread(_sprint2, s1)
            yield {
                "event": "sprint2",
                "data": json.dumps(s2.model_dump())
            }

            # Sprint 3
            s3 = await asyncio.to_thread(_sprint3, s1, s2)
            yield {
                "event": "sprint3",
                "data": json.dumps(s3.model_dump())
            }

            # Sprint 4
            s4 = await asyncio.to_thread(_sprint4, s1, s2, s3)
            yield {
                "event": "sprint4",
                "data": json.dumps(s4.model_dump())
            }

            yield {
                "event": "done",
                "data": json.dumps({"status": "complete"})
            }
            
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }

    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
