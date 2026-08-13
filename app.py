import os
import re
from typing import Optional, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import session_db
from rl_agent import rl_agent
from tools import WebSearchTool, LinkFetcherTool, YouTubeTranscriptTool, rag_engine
from llm_service import llm_service

app = FastAPI(title="ChatGPT with RL & Tools API", version="1.1")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Database
session_db.init_db()

# Pydantic Schemas
class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"

class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    manual_action: Optional[str] = None # Direct, Web Search, RAG Document Search, Hybrid, or None for RL Auto

class FeedbackRequest(BaseModel):
    message_id: str
    feedback: int # 1 for 👍, -1 for 👎

# API Endpoints
@app.get("/api/sessions")
def list_sessions():
    sessions = session_db.get_all_sessions()
    if not sessions:
        new_sess = session_db.create_session("Welcome Chat")
        sessions = [new_sess]
    return sessions

@app.post("/api/sessions")
def create_session(req: CreateSessionRequest):
    return session_db.create_session(req.title or "New Chat")

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    session_db.delete_session(session_id)
    return {"status": "success", "session_id": session_id}

@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str):
    return session_db.get_session_messages(session_id)

@app.post("/api/chat")
def chat(req: ChatRequest):
    session_id = req.session_id
    if not session_id or not session_db.get_session(session_id):
        new_sess = session_db.create_session("New Chat")
        session_id = new_sess["id"]
        
    user_query = req.message.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Message content cannot be empty")
        
    # Save User Message to DB
    session_db.add_message(session_id=session_id, role="user", content=user_query)
    
    # Check session history to auto-title if first exchange
    history = session_db.get_session_messages(session_id)
    if len(history) <= 2:
        auto_title = user_query[:30] + ("..." if len(user_query) > 30 else "")
        session_db.update_session_title(session_id, auto_title)

    tools_used = []
    tool_contexts = []

    # 1. URL & Link Ingestion (YouTube or General Web Links)
    urls = re.findall(r'https?://[^\s]+', user_query)
    for url in urls:
        if "youtube.com" in url or "youtu.be" in url:
            yt_res = YouTubeTranscriptTool.fetch_transcript(url)
            tools_used.append("YouTube Transcript Fetcher")
            tool_contexts.append(f"📹 **YouTube Video Transcript & Breakdown**:\n{yt_res['transcript']}")
            # Index into RAG vector store
            raw_text = yt_res.get("full_text") or yt_res["transcript"]
            rag_engine.add_raw_text(f"YouTube_{yt_res['video_id']}.txt", raw_text)
            session_db.save_document_meta(f"YouTube_{yt_res['video_id']}.txt", "youtube/transcript", 3)
        else:
            link_res = LinkFetcherTool.fetch_url_content(url)
            tools_used.append("Link Content Fetcher")
            tool_contexts.append(f"🔗 **Extracted Web Page Content ({link_res.get('title', url)})**:\n{link_res['content']}")
            # Index into RAG vector store
            slug = re.sub(r'[^a-zA-Z0-9]', '_', url)[-25:]
            rag_engine.add_raw_text(f"Link_{slug}.txt", link_res['content'])
            session_db.save_document_meta(f"Link_{slug}.txt", "web/article", 4)

    # 2. RL State & Action Selection
    has_docs = bool(rag_engine.chunks)
    rl_state = rl_agent.extract_state(user_query, has_docs=has_docs)
    action_selected, q_val, is_exploration = rl_agent.select_action(rl_state, manual_override=req.manual_action)

    # 3. Dynamic Tool Execution based on RL Action Decision
    if action_selected in ["Web Search", "Hybrid"] and not urls:
        web_results = WebSearchTool.search(user_query, max_results=3)
        tools_used.append("Web Search")
        web_text = "\n".join([f"- [{item['title']}]({item['url']}): {item['snippet']}" for item in web_results])
        tool_contexts.append(f"🌐 **Web Search Results**:\n{web_text}")

    if action_selected in ["RAG Document Search", "Hybrid"] and has_docs:
        rag_results = rag_engine.search(user_query, top_k=3)
        if rag_results:
            tools_used.append("RAG Document Search")
            rag_text = "\n".join([f"- **Document [{item['filename']}]** (Score: {item['score']}):\n\"{item['text']}\"" for item in rag_results])
            tool_contexts.append(f"📄 **Retrieved Knowledge Passages (RAG)**:\n{rag_text}")

    combined_context = "\n\n".join(tool_contexts) if tool_contexts else None

    # LLM Generation
    bot_response_text = llm_service.generate_chat_response(
        messages=history,
        system_instruction=(
            "You are a helpful, accurate ChatGPT-like AI assistant with background tools. "
            "When presented with web link transcripts or YouTube video transcripts, provide a clear, "
            "detailed breakdown of what happens in the course/video, explaining key technical steps, "
            "concepts, and timestamped sections when available."
        ),
        tool_context=combined_context
    )

    # Save Bot Message to DB
    bot_msg = session_db.add_message(
        session_id=session_id,
        role="assistant",
        content=bot_response_text,
        tools_used=tools_used,
        action_selected=action_selected
    )

    policy_dist = rl_agent.get_policy_distribution(rl_state)

    return {
        "session_id": session_id,
        "message": bot_msg,
        "action_selected": action_selected,
        "tools_used": tools_used,
        "rl_state": rl_state,
        "q_value": q_val,
        "is_exploration": is_exploration,
        "policy_distribution": policy_dist
    }

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    msg_data = session_db.update_message_feedback(req.message_id, req.feedback)
    if not msg_data:
        raise HTTPException(status_code=404, detail="Message not found")
        
    action = msg_data.get("action_selected", "Direct")
    content = msg_data.get("content", "")
    reward = 1.0 if req.feedback > 0 else -1.0
    
    state = rl_agent.extract_state(content, has_docs=bool(rag_engine.chunks))
    rl_agent.update_reward(state, action, reward)
    
    return {
        "status": "success",
        "message_id": req.message_id,
        "reward": reward,
        "action": action,
        "updated_rl_stats": rl_agent.get_statistics()
    }

@app.post("/api/rag/upload")
async def upload_document(file: UploadFile = File(...)):
    contents = await file.read()
    res = rag_engine.add_document(file.filename, contents)
    meta = session_db.save_document_meta(file.filename, file.content_type or "unknown", res["chunk_count"])
    return {
        "status": "success",
        "document": meta,
        "details": res
    }

@app.get("/api/rag/documents")
def list_documents():
    return session_db.get_all_documents()

@app.get("/api/rl/stats")
def get_rl_stats():
    return rl_agent.get_statistics()

# Mount Static Files
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
