from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import asyncio
import json
from datetime import datetime
from may_learning_engine import MayLearningEngine
import uvicorn

app = FastAPI(title="May's Learning Interface", description="Monitor and control May's autonomous learning")
templates = Jinja2Templates(directory="templates")

# Initialize May
may_engine = MayLearningEngine()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard for monitoring May's learning"""
    # Get recent learning activity
    recent_knowledge = may_engine.get_knowledge_on_topic("", limit=10)  # Get all recent
    
    # Get learning sessions
    conn = sqlite3.connect(may_engine.memory.db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT topic, start_time, status, nodes_discovered, nodes_validated 
        FROM learning_sessions 
        ORDER BY start_time DESC LIMIT 5
    ''')
    sessions = cursor.fetchall()
    conn.close()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "recent_knowledge": recent_knowledge,
        "sessions": sessions,
        "learning_active": may_engine.learning_active
    })

@app.post("/start_learning")
async def start_learning(topic: str = Form(...)):
    """Start May learning about a specific topic"""
    if may_engine.learning_active:
        raise HTTPException(status_code=400, detail="Learning session already active")
    
    # Start learning in background
    asyncio.create_task(may_engine.learn_from_web(topic))
    
    return JSONResponse({"status": "success", "message": f"May started learning about '{topic}'"})

@app.post("/approve_knowledge")
async def approve_knowledge(content_hash: str = Form(...)):
    """Approve a piece of knowledge May learned"""
    may_engine.approve_knowledge(content_hash)
    return JSONResponse({"status": "success", "message": "Knowledge approved"})

@app.get("/knowledge/{topic}")
async def get_knowledge(topic: str, limit: int = 20):
    """Get May's knowledge on a specific topic"""
    knowledge = may_engine.get_knowledge_on_topic(topic, limit)
    return JSONResponse(knowledge)

@app.post("/add_trusted_source")
async def add_trusted_source(
    domain: str = Form(...),
    categories: str = Form(...),
    trust_level: int = Form(...)
):
    """Add a new trusted source for May to learn from"""
    import sqlite3
    
    conn = sqlite3.connect(may_engine.memory.db_path)
    cursor = conn.cursor()
    
    try:
        categories_list = [cat.strip() for cat in categories.split(",")]
        cursor.execute('''
            INSERT INTO trusted_sources (domain, topic_categories, trust_level)
            VALUES (?, ?, ?)
        ''', (domain, json.dumps(categories_list), trust_level))
        
        conn.commit()
        return JSONResponse({"status": "success", "message": f"Added trusted source: {domain}"})
    
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    
    finally:
        conn.close()

@app.get("/learning_status")
async def learning_status():
    """Get current learning status"""
    return JSONResponse({
        "learning_active": may_engine.learning_active,
        "timestamp": datetime.now().isoformat()
    })

@app.post("/stop_learning")
async def stop_learning():
    """Emergency stop for learning"""
    may_engine.learning_active = False
    return JSONResponse({"status": "success", "message": "Learning stopped"})

# HTML Template for the dashboard
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>May's Learning Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .status { padding: 10px; border-radius: 4px; }
        .active { background: #d4edda; color: #155724; }
        .inactive { background: #f8d7da; color: #721c24; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .knowledge-item { border-left: 4px solid #007bff; padding-left: 15px; margin: 10px 0; }
        .form-group { margin: 10px 0; }
        label { display: block; margin-bottom: 5px; }
        input, select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; width: 200px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 May's Learning Dashboard</h1>
        
        <div class="card">
            <h2>Learning Status</h2>
            <div class="status {{ 'active' if learning_active else 'inactive' }}">
                {% if learning_active %}
                    🟢 May is actively learning
                    <button onclick="stopLearning()" style="float: right;">Stop Learning</button>
                {% else %}
                    🔴 May is not currently learning
                {% endif %}
            </div>
        </div>
        
        <div class="card">
            <h2>Start New Learning Session</h2>
            <form onsubmit="startLearning(event)">
                <div class="form-group">
                    <label>Topic for May to learn about:</label>
                    <input type="text" id="topic" placeholder="e.g., machine learning, quantum physics" required>
                </div>
                <button type="submit">Start Learning</button>
            </form>
        </div>
        
        <div class="card">
            <h2>Recent Knowledge Acquired</h2>
            {% for item in recent_knowledge %}
            <div class="knowledge-item">
                <strong>{{ item.topic }}</strong> (Confidence: {{ "%.2f"|format(item.confidence) }})<br>
                <small>From: {{ item.source }} | Learned: {{ item.learned_at }}</small><br>
                <p>{{ item.content[:200] }}...</p>
                <button onclick="approveKnowledge('{{ item.content_hash }}')">Approve</button>
            </div>
            {% endfor %}
        </div>
        
        <div class="card">
            <h2>Add Trusted Source</h2>
            <form onsubmit="addSource(event)">
                <div class="form-group">
                    <label>Domain:</label>
                    <input type="text" id="domain" placeholder="example.com" required>
                </div>
                <div class="form-group">
                    <label>Categories (comma-separated):</label>
                    <input type="text" id="categories" placeholder="science, technology" required>
                </div>
                <div class="form-group">
                    <label>Trust Level (1-10):</label>
                    <input type="number" id="trust_level" min="1" max="10" value="5" required>
                </div>
                <button type="submit">Add Source</button>
            </form>
        </div>
    </div>

    <script>
        async function startLearning(event) {
            event.preventDefault();
            const topic = document.getElementById('topic').value;
            
            const response = await fetch('/start_learning', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `topic=${encodeURIComponent(topic)}`
            });
            
            const result = await response.json();
            alert(result.message);
            if (result.status === 'success') {
                location.reload();
            }
        }
        
        async function stopLearning() {
            const response = await fetch('/stop_learning', { method: 'POST' });
            const result = await response.json();
            alert(result.message);
            location.reload();
        }
        
        async function approveKnowledge(contentHash) {
            const response = await fetch('/approve_knowledge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `content_hash=${contentHash}`
            });
            
            const result = await response.json();
            alert(result.message);
        }
        
        async function addSource(event) {
            event.preventDefault();
            const domain = document.getElementById('domain').value;
            const categories = document.getElementById('categories').value;
            const trustLevel = document.getElementById('trust_level').value;
            
            const response = await fetch('/add_trusted_source', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `domain=${domain}&categories=${categories}&trust_level=${trustLevel}`
            });
            
            const result = await response.json();
            alert(result.message);
            if (result.status === 'success') {
                event.target.reset();
            }
        }
        
        // Auto-refresh status every 30 seconds
        setInterval(async () => {
            const response = await fetch('/learning_status');
            const status = await response.json();
            // Update UI based on status if needed
        }, 30000);
    </script>
</body>
</html>
'''

# Create templates directory if it doesn't exist
import os
os.makedirs("templates", exist_ok=True)
with open("templates/dashboard.html", "w") as f:
    f.write(DASHBOARD_HTML)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)