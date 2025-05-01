import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agent import MeetingPlanner

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DateRequest(BaseModel):
    date: str


@app.post("/api/analyze-meetings")
async def analyze_meetings(request: DateRequest):
    try:
        # Create and initialize the meeting planner
        planner = MeetingPlanner()

        # Build the graph
        graph = planner.build_graph()

        async def event_generator():
            # Run the graph with the given date and stream events
            async for event in graph.astream_events({"date": request.date}):
                kind = event["event"]
                tags = event.get("tags", [])

                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if "streaming" in tags:
                        yield json.dumps(
                            {"type": "streaming", "content": content}
                        ) + "\n"
                        print(content)

                elif kind == "on_custom_event":
                    event_name = event["name"]
                    if event_name in [
                        "calendar_status",
                        "calendar_parser_status",
                        "react_status",
                        "markdown_formatter_status",
                        "company_event",
                    ]:
                        yield json.dumps(
                            {"type": event_name, "content": event["data"]}
                        ) + "\n"
                        # if event_name == "company_event":
                        #     print(f"Company Event Data: {event['data']}")

        return StreamingResponse(event_generator(), media_type="application/json")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
