import sqlite3
import json
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin
import re
from bs4 import BeautifulSoup
import logging
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class LearningSource:
    """Represents a trusted source for learning"""
    domain: str
    topic_categories: List[str]
    trust_level: int  # 1-10, 10 being highest trust
    last_crawled: Optional[datetime] = None
    crawl_frequency: int = 24  # hours between crawls

@dataclass
class KnowledgeNode:
    """Represents a piece of learned knowledge"""
    content_hash: str
    topic: str
    content: str
    source_url: str
    confidence_score: float
    learned_at: datetime
    validation_status: str  # 'pending', 'validated', 'flagged', 'rejected'

class MayMemoryDB:
    """May's persistent memory and learning system"""
    
    def __init__(self, db_path: str = "may_memory.db"):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Initialize the database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Knowledge storage
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT UNIQUE NOT NULL,
                topic TEXT NOT NULL,
                content TEXT NOT NULL,
                source_url TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                learned_at TEXT NOT NULL,
                validation_status TEXT DEFAULT 'pending',
                human_approved BOOLEAN DEFAULT 0
            )
        ''')
        
        # Trusted sources
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trusted_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT UNIQUE NOT NULL,
                topic_categories TEXT NOT NULL,
                trust_level INTEGER NOT NULL,
                last_crawled TEXT,
                crawl_frequency INTEGER DEFAULT 24,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Learning sessions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS learning_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                status TEXT DEFAULT 'active',
                nodes_discovered INTEGER DEFAULT 0,
                nodes_validated INTEGER DEFAULT 0
            )
        ''')
        
        # Content blacklist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filter_type TEXT NOT NULL,
                filter_value TEXT NOT NULL,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")

class MayLearningEngine:
    """May's autonomous learning engine with safety constraints"""
    
    def __init__(self, db_path: str = "may_memory.db"):
        self.memory = MayMemoryDB(db_path)
        self.session = None
        self.learning_active = False
        
        # Safety constraints
        self.max_pages_per_session = 50
        self.learning_cooldown = 3600  # 1 hour between learning sessions
        self.content_validation_threshold = 0.7
        
        # Initialize with some safe, high-quality sources
        self.initialize_trusted_sources()
        self.initialize_content_filters()
    
    def initialize_trusted_sources(self):
        """Set up initial trusted sources for learning"""
        default_sources = [
            LearningSource("en.wikipedia.org", ["general", "science", "technology"], 9),
            LearningSource("stackoverflow.com", ["programming", "technology"], 8),
            LearningSource("arxiv.org", ["science", "mathematics", "ai"], 10),
            LearningSource("github.com", ["programming", "open-source"], 7),
            LearningSource("nature.com", ["science", "research"], 10),
            LearningSource("sciencedirect.com", ["science", "research"], 9),
        ]
        
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        for source in default_sources:
            cursor.execute('''
                INSERT OR IGNORE INTO trusted_sources 
                (domain, topic_categories, trust_level, crawl_frequency)
                VALUES (?, ?, ?, ?)
            ''', (source.domain, json.dumps(source.topic_categories), 
                  source.trust_level, source.crawl_frequency))
        
        conn.commit()
        conn.close()
        logger.info("Initialized trusted sources")
    
    def initialize_content_filters(self):
        """Set up content filtering to prevent learning harmful content"""
        harmful_keywords = [
            "violence", "harmful", "dangerous", "illegal", "malware",
            "exploit", "hack", "phishing", "scam", "fraud"
        ]
        
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        for keyword in harmful_keywords:
            cursor.execute('''
                INSERT OR IGNORE INTO content_filters 
                (filter_type, filter_value) VALUES (?, ?)
            ''', ("keyword", keyword))
        
        conn.commit()
        conn.close()
        logger.info("Initialized content filters")
    
    async def start_learning_session(self, topic: str) -> int:
        """Start a new learning session on a specific topic"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO learning_sessions (topic, start_time, status)
            VALUES (?, ?, 'active')
        ''', (topic, datetime.now().isoformat()))
        
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        self.learning_active = True
        logger.info(f"Started learning session {session_id} for topic: {topic}")
        return session_id
    
    async def learn_from_web(self, topic: str, max_depth: int = 3):
        """Main learning function - May explores the web autonomously"""
        if self.learning_active:
            logger.warning("Learning session already active")
            return
        
        session_id = await self.start_learning_session(topic)
        
        try:
            # Get relevant trusted sources for this topic
            relevant_sources = self.get_relevant_sources(topic)
            
            async with aiohttp.ClientSession() as session:
                self.session = session
                
                for source in relevant_sources:
                    if not self.learning_active:
                        break
                    
                    logger.info(f"Learning from {source.domain} about {topic}")
                    await self.crawl_source(source, topic, max_depth)
                    
                    # Respect rate limits
                    await asyncio.sleep(2)
        
        except Exception as e:
            logger.error(f"Learning session failed: {e}")
        
        finally:
            await self.end_learning_session(session_id)
    
    def get_relevant_sources(self, topic: str) -> List[LearningSource]:
        """Get trusted sources relevant to the learning topic"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM trusted_sources WHERE active = 1')
        sources = []
        
        for row in cursor.fetchall():
            categories = json.loads(row[2])  # topic_categories
            if topic.lower() in [cat.lower() for cat in categories] or 'general' in categories:
                sources.append(LearningSource(
                    domain=row[1],
                    topic_categories=categories,
                    trust_level=row[3],
                    last_crawled=row[4],
                    crawl_frequency=row[5]
                ))
        
        conn.close()
        return sorted(sources, key=lambda x: x.trust_level, reverse=True)
    
    async def crawl_source(self, source: LearningSource, topic: str, max_depth: int):
        """Crawl a specific source for learning content"""
        try:
            # Start with the main domain
            base_url = f"https://{source.domain}"
            
            # For Wikipedia, construct a topic-specific URL
            if "wikipedia" in source.domain:
                base_url = f"https://en.wikipedia.org/wiki/{topic.replace(' ', '_')}"
            
            await self.extract_and_store_knowledge(base_url, topic, source)
            
        except Exception as e:
            logger.error(f"Failed to crawl {source.domain}: {e}")
    
    async def extract_and_store_knowledge(self, url: str, topic: str, source: LearningSource):
        """Extract knowledge from a webpage and store it"""
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    return
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract meaningful content
                content = self.extract_meaningful_content(soup)
                
                if content and self.validate_content(content):
                    knowledge_node = KnowledgeNode(
                        content_hash=hashlib.sha256(content.encode()).hexdigest(),
                        topic=topic,
                        content=content,
                        source_url=url,
                        confidence_score=source.trust_level / 10.0,
                        learned_at=datetime.now(),
                        validation_status='pending'
                    )
                    
                    self.store_knowledge(knowledge_node)
                    logger.info(f"Learned new knowledge from {url}")
        
        except Exception as e:
            logger.error(f"Failed to extract knowledge from {url}: {e}")
    
    def extract_meaningful_content(self, soup: BeautifulSoup) -> str:
        """Extract meaningful text content from HTML"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()
        
        # Get text content
        text = soup.get_text()
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Return first 1000 characters for now (can be adjusted)
        return text[:1000] if len(text) > 50 else ""
    
    def validate_content(self, content: str) -> bool:
        """Validate content against safety filters"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT filter_value FROM content_filters WHERE active = 1')
        harmful_keywords = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # Check for harmful content
        content_lower = content.lower()
        for keyword in harmful_keywords:
            if keyword in content_lower:
                logger.warning(f"Content blocked due to keyword: {keyword}")
                return False
        
        return True
    
    def store_knowledge(self, knowledge: KnowledgeNode):
        """Store validated knowledge in memory"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO knowledge 
                (content_hash, topic, content, source_url, confidence_score, 
                 learned_at, validation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (knowledge.content_hash, knowledge.topic, knowledge.content,
                  knowledge.source_url, knowledge.confidence_score,
                  knowledge.learned_at.isoformat(), knowledge.validation_status))
            
            conn.commit()
            logger.info(f"Stored knowledge about {knowledge.topic}")
        
        except Exception as e:
            logger.error(f"Failed to store knowledge: {e}")
        
        finally:
            conn.close()
    
    async def end_learning_session(self, session_id: int):
        """End the current learning session"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE learning_sessions 
            SET end_time = ?, status = 'completed'
            WHERE id = ?
        ''', (datetime.now().isoformat(), session_id))
        
        conn.commit()
        conn.close()
        
        self.learning_active = False
        logger.info(f"Ended learning session {session_id}")
    
    def get_knowledge_on_topic(self, topic: str, limit: int = 10) -> List[Dict]:
        """Retrieve May's learned knowledge on a specific topic"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        if topic:
            cursor.execute('''
                SELECT content_hash, topic, content, source_url, confidence_score, learned_at 
                FROM knowledge 
                WHERE topic LIKE ? AND validation_status != 'rejected'
                ORDER BY confidence_score DESC, learned_at DESC
                LIMIT ?
            ''', (f"%{topic}%", limit))
        else:
            cursor.execute('''
                SELECT content_hash, topic, content, source_url, confidence_score, learned_at 
                FROM knowledge 
                WHERE validation_status != 'rejected'
                ORDER BY learned_at DESC
                LIMIT ?
            ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'content_hash': row[0],
                'topic': row[1],
                'content': row[2],
                'source': row[3],
                'confidence': row[4],
                'learned_at': row[5]
            })
        
        conn.close()
        return results
    
    def approve_knowledge(self, content_hash: str):
        """Human approval of learned knowledge"""
        conn = sqlite3.connect(self.memory.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE knowledge 
            SET validation_status = 'validated', human_approved = 1
            WHERE content_hash = ?
        ''', (content_hash,))
        
        conn.commit()
        conn.close()
        logger.info(f"Knowledge approved: {content_hash[:16]}...")

# FastAPI Web Interface
app = FastAPI(title="May's Learning Interface", description="Monitor and control May's autonomous learning")

# Create templates directory and file
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Initialize May
may_engine = MayLearningEngine()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard for monitoring May's learning"""
    # Get recent learning activity
    recent_knowledge = may_engine.get_knowledge_on_topic("", limit=10)
    
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

# Create the HTML template
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
                <p>{{ item.content[:200] }}{% if item.content|length > 200 %}...{% endif %}</p>
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
        }, 30000);
    </script>
</body>
</html>
'''

# Write the template file
with open("templates/dashboard.html", "w") as f:
    f.write(DASHBOARD_HTML)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)