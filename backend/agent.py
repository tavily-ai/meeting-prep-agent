import json
import logging
import os
from typing import Dict, List
from typing import Optional as OptionalType

from dotenv import load_dotenv
from langchain import hub
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.callbacks.manager import dispatch_custom_event
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.graph import END, START, StateGraph
from mcp_use import MCPAgent, MCPClient
from pydantic import BaseModel, Field
from tavily import TavilyClient
from typing_extensions import TypedDict

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic models for structured output
class Attendee(BaseModel):
    email: str
    name: OptionalType[str] = None
    status: OptionalType[str] = None
    info: OptionalType[str] = None


class Meeting(BaseModel):
    title: str
    company: str  # This will be the client company name
    attendees: List[Attendee] = Field(default_factory=list)
    meeting_time: str


class CalendarData(BaseModel):
    meetings: List[Meeting] = Field(default_factory=list)


class State(TypedDict):
    date: str
    calendar_data: str
    calendar_events: List[Dict]
    react_results: List[str]
    markdown_results: str


class MeetingPlanner:
    def __init__(
        self,
    ):
        # Initialize
        self.stream_insights_llm = ChatOpenAI(model="gpt-4.1").with_config(
            {"tags": ["streaming"]}
        )
        self.react_llm = ChatOpenAI(model="o3-mini-2025-01-31")
        self.fast_llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"), model="llama-3.3-70b-versatile"
        )
        self.react_prompt = hub.pull("hwchase17/react")
        self.tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        self.react_tools = [
            TavilySearch(
                max_results=3, include_raw_content=True, search_depth="advanced"
            )
        ]
        self.react_agent = create_react_agent(
            self.react_llm, self.react_tools, self.react_prompt
        )
        self.react_agent_executor = AgentExecutor(
            agent=self.react_agent, tools=self.react_tools, handle_parsing_errors=True
        )

    async def calendar_node(self, state: State):
        """Fetch calendar events for a specified date"""
        dispatch_custom_event("calendar_status", "Connecting to Google Calendar MCP...")
        google_calendar_config = {
            "mcpServers": {
                "google-calendar": {
                    "command": "node",
                    "args": [os.getenv("GOOGLE_CALENDAR_CONFIG")],
                }
            }
        }

        # Create MCPClient from configuration dictionary
        client = MCPClient.from_dict(google_calendar_config)

        # Create agent with the client
        agent = MCPAgent(llm=self.fast_llm, client=client, max_steps=30)

        date = state["date"]
        # Run the query
        calendar_data = await agent.run(
            f"What is on my calendar for {date}. Include the meeting title, time, and the attendees - names and emails."
        )

        return {
            "calendar_data": calendar_data,
        }

    def calendar_parser_node(self, state: State):
        """Parse the calendar data into a structured format using structured output from LLM"""
        dispatch_custom_event("calendar_parser_status", "Analyzing Your Calendar...")

        calendar_data = state["calendar_data"]

        # Create a structured parser using ChatOpenAI with structured output
        parser_llm = ChatOpenAI(
            temperature=0, model="gpt-4.1-nano"
        ).with_structured_output(CalendarData)
        # Define the prompt for extraction
        extraction_prompt = """
        Extract meeting information from the following calendar data:
        
        {calendar_data}
        
        Important context:
        - You work for Tavily, so "Tavily" is your company, not the client company
        - For each meeting, identify the client company name (the company Tavily is meeting with)
        - Only include attendees from the client company (exclude anyone with @tavily.com email)
        
        For each meeting, extract:
        1. The meeting title
        2. The client company name (the external company Tavily is meeting with)
        3. All client attendees with their emails and names (exclude Tavily employees)
        4. The meeting time in the format [Hour:Minute AM/PM]
        5. Any additional information about the meeting attendees
        Return the information in a structured json format.
        """

        # Parse the calendar data
        structured_data = parser_llm.invoke(
            extraction_prompt.format(calendar_data=calendar_data)
        )

        # Process into the format needed by the rest of the application
        calendar_events = []

        for meeting in structured_data.meetings:
            # Extract company name from meeting title if needed
            company = meeting.company
            # Create event data
            event_data = {
                "company": company,
                "title": meeting.title,
                "attendees": {},
                "meeting_time": meeting.meeting_time,
            }

            # Process attendees (only client attendees)
            for attendee in meeting.attendees:
                email = attendee.email
                name = (
                    attendee.name if attendee.name else email.split("@")[0]
                )  # Use part of email as name if not available

                # Skip Tavily employees
                if "tavily.com" in email.lower():
                    continue

                # Add to event attendees
                event_data["attendees"][email] = name
            dispatch_custom_event(
                "company_event", f"{company} @ {meeting.meeting_time}"
            )
            calendar_events.append(event_data)
        return {"calendar_events": calendar_events}

    def react_node(self, state: State):
        """Use react architecture to search for information about the attendees"""

        calendar_events = state["calendar_events"]
        dispatch_custom_event(
            "react_status", "Searching Tavily for Meeting Insights..."
        )
        # Create a function to process a single event
        formatted_prompt = f"""
        Your goal is to help me prepare for an upcoming meeting. 
        You will be provided with the name of a company we are meeting with and a list of attendees.

        meeting information:
        {calendar_events}

        Please find the profile information (e.g. linkedin profile) of the attendees using tavily search.

        1. Search for the attendees name using all available information such as their email, initials/last name, etc.
        - provide details on the attendees experience, education, and skills, and location
        - If there are multiple attendees with the same name, only focus on the one that works at the relevant company
        - it is important you find the profile of all the attendees!
        2. Research the company in the context of AI initiatives using tavily search.
        3. Provide your findings summarized concisely with the relevant links. Do not include anything else in the output.
        """

        result = self.react_agent_executor.invoke({"input": formatted_prompt})

        return {"react_results": result["output"]}

    def markdown_formatter_node(self, state: State):
        """Format the react results into a markdown string"""
        dispatch_custom_event(
            "markdown_formatter_status", "Formatting Meeting Insights..."
        )
        research_results = state["react_results"]
        calendar_events = state["calendar_events"]

        # Create a formatting prompt for the LLM
        formatting_prompt = """
        You are a meeting preparation assistant. You are given a list of calendar events and research results.
        Your job is to prepare your colleagues for a day of meetings.
        You must optimize for clarity and conciseness. Do not include any information that is not relevant to the meeting preparation.

        Create a well-structured markdown document from the following meeting research results.

        For each company, create a section with:
        1. ## Company name @ Time of meeting
        2. ### Meeting context (only if available)
        - relevant background information about the company (only if available)
        - relevant background information about the meeting (only if available)
        3. ### Attendee subsections with their roles, background, and relevant information 
        4. Use proper markdown formatting including bold, italics, and bullet points where appropriate
        5. Please include inline citations as Markdown hyperlinks directly in the response text.

        Calendar Events: {calendar_events}
        Research Results: {research_results}

        Format the output as clean, well-structured markdown with clear sections and subsections.
        """
        print("research results: ", research_results)

        # Use the LLM to format the results
        formatted_results = self.stream_insights_llm.invoke(
            formatting_prompt.format(
                calendar_events=json.dumps(calendar_events, indent=2),
                research_results=research_results,
            )
        )
        return {"markdown_results": formatted_results.content}

    def build_graph(self):
        """Build and compile the graph"""
        graph_builder = StateGraph(State)

        graph_builder.add_node("Google Calendar MCP", self.calendar_node)
        graph_builder.add_node("Calendar Data Parser", self.calendar_parser_node)
        graph_builder.add_node("ReAct", self.react_node)
        graph_builder.add_node("Markdown Formatter", self.markdown_formatter_node)

        graph_builder.add_edge(START, "Google Calendar MCP")
        graph_builder.add_edge("Google Calendar MCP", "Calendar Data Parser")
        graph_builder.add_edge("Calendar Data Parser", "ReAct")
        graph_builder.add_edge("ReAct", "Markdown Formatter")
        graph_builder.add_edge("Markdown Formatter", END)

        compiled_graph = graph_builder.compile()

        return compiled_graph
