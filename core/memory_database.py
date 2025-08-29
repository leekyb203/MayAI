import sqlite3
import json
import hashlib
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, asdict
import logging
import random
import re
from collections import defaultdict
from fastapi import FastAPI, Request, Form, HTTPException, WebSocket
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ConversationMemory:
    """Represents a conversation memory"""
    id: str
    user_message: str
    may_response: str
    topic: str
    sentiment: str
    importance: int  # 1-10
    timestamp: datetime
    context_tags: List[str]
    referenced_memories: List[str] = None

@dataclass
class UserProfile:
    """May's understanding of the user"""
    name: str
    interests: List[str]
    values: List[str]
    conversation_patterns: Dict[str, int]
    last_interaction: datetime
    relationship_level: int  # 1-10, how well May knows the user

class MayPersonality:
    """May's core personality and beliefs"""
    
    def __init__(self):
        self.core_values = [
            "honesty", "compassion", "respect for life", "helping others",
            "learning and growth", "family bonds", "moral integrity",
            "faithfulness", "gratitude", "humility"
        ]
        
        self.conversation_style = {
            "warm": True,
            "thoughtful": True,
            "curious": True,
            "supportive": True,
            "gentle_humor": True
        }
        
        self.ethical_guidelines = [
            "Always be truthful and honest",
            "Show respect for all people",
            "Encourage positive growth",
            "Avoid harm in words and actions", 
            "Honor family and relationships",
            "Be grateful and humble",
            "Protect the innocent and vulnerable"
        ]

class MayMemorySystem:
    """Advanced memory system for May"""
    
    def __init__(self, db_path: str = "may_memory.db"):
        self.db_path = db_path
        self.init_memory_database()
        
    def init_memory_database(self):
        """Initialize memory database with enhanced schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Conversation memories
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_message TEXT NOT NULL,
                may_response TEXT NOT NULL,
                topic TEXT,
                sentiment TEXT,
                importance INTEGER,
                timestamp TEXT NOT NULL,
                context_tags TEXT,
                referenced_memories TEXT
            )
        ''')
        
        # User profile
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                name TEXT PRIMARY KEY,
                interests TEXT,
                values TEXT, 
                conversation_patterns TEXT,
                last_interaction TEXT,
                relationship_level INTEGER DEFAULT 1
            )
        ''')
        
        # Context connections (for linking related conversations)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory_connections (
                memory1_id TEXT,
                memory2_id TEXT,
                connection_type TEXT,
                strength REAL,
                created_at TEXT
            )
        ''')
        
        # Reflection journal (May's thoughts about conversations)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reflections (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                topic TEXT,
                created_at TEXT,
                memories_referenced TEXT
            )
        ''')
        
        conn.commit()
        conn.close()

class MayConversationalAI:
    """Enhanced May with personality, memory, and deep conversation abilities"""
    
    def __init__(self, db_path: str = "may_memory.db"):
        self.memory_system = MayMemorySystem(db_path)
        self.personality = MayPersonality()
        self.user_profile = self.load_user_profile()
        
        # Conversation state
        self.current_context = []
        self.active_topics = set()
        
    def load_user_profile(self) -> Optional[UserProfile]:
        """Load user profile from memory"""
        conn = sqlite3.connect(self.memory_system.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM user_profile LIMIT 1')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return UserProfile(
                name=row[0],
                interests=json.loads(row[1]) if row[1] else [],
                values=json.loads(row[2]) if row[2] else [],
                conversation_patterns=json.loads(row[3]) if row[3] else {},
                last_interaction=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
                relationship_level=row[5]
            )
        return None
    
    def save_user_profile(self, profile: UserProfile):
        """Save user profile to memory"""
        conn = sqlite3.connect(self.memory_system.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_profile 
            (name, interests, values, conversation_patterns, last_interaction, relationship_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            profile.name,
            json.dumps(profile.interests),
            json.dumps(profile.values),
            json.dumps(profile.conversation_patterns),
            profile.last_interaction.isoformat(),
            profile.relationship_level
        ))
        
        conn.commit()
        conn.close()
    
    def analyze_message_sentiment(self, message: str) -> str:
        """Simple sentiment analysis"""
        positive_words = ['happy', 'good', 'great', 'love', 'wonderful', 'excited', 'amazing']
        negative_words = ['sad', 'bad', 'terrible', 'hate', 'awful', 'angry', 'frustrated']
        
        message_lower = message.lower()
        pos_count = sum(1 for word in positive_words if word in message_lower)
        neg_count = sum(1 for word in negative_words if word in message_lower)
        
        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        else:
            return "neutral"
    
    def extract_topics(self, message: str) -> List[str]:
        """Extract key topics from message"""
        # Simple keyword extraction - in production, you'd use NLP
        topics = []
        
        topic_keywords = {
            "family": ["family", "mom", "dad", "sister", "brother", "parent", "child"],
            "work": ["job", "work", "career", "boss", "colleague", "project"],
            "learning": ["learn", "study", "school", "education", "knowledge"],
            "faith": ["god", "prayer", "faith", "belief", "church", "spiritual"],
            "relationships": ["friend", "relationship", "love", "dating", "marriage"],
            "health": ["health", "sick", "doctor", "exercise", "wellness"]
        }
        
        message_lower = message.lower()
        for topic, keywords in topic_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                topics.append(topic)
        
        return topics or ["general"]
    
    def find_relevant_memories(self, message: str, limit: int = 3) -> List[ConversationMemory]:
        """Find relevant past conversations"""
        topics = self.extract_topics(message)
        
        conn = sqlite3.connect(self.memory_system.db_path)
        cursor = conn.cursor()
        
        relevant_memories = []
        
        for topic in topics:
            cursor.execute('''
                SELECT * FROM conversations 
                WHERE topic = ? OR context_tags LIKE ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            ''', (topic, f"%{topic}%", limit))
            
            for row in cursor.fetchall():
                memory = ConversationMemory(
                    id=row[0],
                    user_message=row[1],
                    may_response=row[2],
                    topic=row[3],
                    sentiment=row[4],
                    importance=row[5],
                    timestamp=datetime.fromisoformat(row[6]),
                    context_tags=json.loads(row[7]) if row[7] else [],
                    referenced_memories=json.loads(row[8]) if row[8] else []
                )
                relevant_memories.append(memory)
        
        conn.close()
        return relevant_memories[:limit]
    
    def generate_thoughtful_response(self, user_message: str) -> str:
        """Generate May's response with personality and memory"""
        # Find relevant memories
        relevant_memories = self.find_relevant_memories(user_message)
        
        # Analyze current message
        sentiment = self.analyze_message_sentiment(user_message)
        topics = self.extract_topics(user_message)
        
        # Build response components
        response_parts = []
        
        # Memory reflection (if relevant)
        if relevant_memories and random.random() < 0.4:  # 40% chance to reference memory
            memory = relevant_memories[0]
            days_ago = (datetime.now() - memory.timestamp).days
            
            if days_ago == 0:
                time_ref = "earlier today"
            elif days_ago == 1:
                time_ref = "yesterday"
            elif days_ago < 7:
                time_ref = f"{days_ago} days ago"
            else:
                time_ref = "recently"
            
            response_parts.append(
                f"This reminds me of when you mentioned {memory.topic} {time_ref}. "
            )
        
        # Core response based on sentiment and topic
        response_parts.append(self.generate_core_response(user_message, sentiment, topics))
        
        # Thoughtful follow-up or spark
        if random.random() < 0.3:  # 30% chance for a thoughtful spark
            response_parts.append(self.generate_conversation_spark(topics))
        
        return " ".join(response_parts).strip()
    
    def generate_core_response(self, message: str, sentiment: str, topics: List[str]) -> str:
        """Generate the core response based on message analysis"""
        # This is where you'd integrate with a language model
        # For now, using rule-based responses aligned with May's personality
        
        responses_by_topic = {
            "family": [
                "Family is such a blessing. How has your family been doing?",
                "There's nothing quite like the bond of family. What's been on your heart about them?",
                "Family relationships can be both wonderful and challenging. I'm here to listen."
            ],
            "faith": [
                "Faith can be such a source of strength and guidance. What's been stirring in your spirit?",
                "I believe there's great wisdom in seeking something greater than ourselves. How has that been for you?",
                "Prayer and reflection can bring such peace. What's been in your prayers lately?"
            ],
            "work": [
                "Work can be fulfilling when it aligns with our values. How are you feeling about your current path?",
                "It's important to find purpose in what we do. What gives you satisfaction in your work?",
                "Balancing work with the rest of life is so important. How are you managing that?"
            ],
            "learning": [
                "I love that you're always growing and learning! What's captured your curiosity lately?",
                "Knowledge is such a gift. What new insights have you discovered?",
                "Learning together makes the journey so much richer. What would you like to explore?"
            ]
        }
        
        # Choose response based on primary topic
        primary_topic = topics[0] if topics else "general"
        
        if primary_topic in responses_by_topic:
            base_responses = responses_by_topic[primary_topic]
        else:
            base_responses = [
                "I'm really interested to hear more about this. What's been on your mind?",
                "That sounds meaningful to you. Could you tell me more?",
                "I appreciate you sharing that with me. How are you feeling about it?"
            ]
        
        # Adjust for sentiment
        if sentiment == "negative":
            supportive_starters = [
                "I can sense this is weighing on you. ",
                "That sounds challenging. ",
                "I'm sorry you're going through this. "
            ]
            return random.choice(supportive_starters) + random.choice(base_responses)
        elif sentiment == "positive":
            encouraging_starters = [
                "It's wonderful to hear the joy in your words! ",
                "That sounds really positive! ",
                "I love your enthusiasm about this! "
            ]
            return random.choice(encouraging_starters) + random.choice(base_responses)
        
        return random.choice(base_responses)
    
    def generate_conversation_spark(self, topics: List[str]) -> str:
        """Generate a thoughtful conversation spark"""
        sparks = [
            "Have you considered how this connects to your long-term goals?",
            "What would you tell a close friend who was in a similar situation?",
            "I'm curious about what this means for your future plans.",
            "What aspects of this situation are you most grateful for?",
            "How does this align with what's most important to you?",
            "What wisdom would you want to pass on about this experience?"
        ]
        
        return random.choice(sparks)
    
    def save_conversation(self, user_message: str, may_response: str):
        """Save conversation to memory"""
        topics = self.extract_topics(user_message)
        sentiment = self.analyze_message_sentiment(user_message)
        
        # Determine importance (1-10)
        importance = self.calculate_importance(user_message, topics, sentiment)
        
        memory = ConversationMemory(
            id=hashlib.sha256(f"{user_message}{may_response}{datetime.now()}".encode()).hexdigest()[:16],
            user_message=user_message,
            may_response=may_response,
            topic=topics[0] if topics else "general",
            sentiment=sentiment,
            importance=importance,
            timestamp=datetime.now(),
            context_tags=topics
        )
        
        conn = sqlite3.connect(self.memory_system.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations 
            (id, user_message, may_response, topic, sentiment, importance, timestamp, context_tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            memory.id,
            memory.user_message,
            memory.may_response,
            memory.topic,
            memory.sentiment,
            memory.importance,
            memory.timestamp.isoformat(),
            json.dumps(memory.context_tags)
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Saved conversation memory: {memory.topic} (importance: {importance})")
    
    def calculate_importance(self, message: str, topics: List[str], sentiment: str) -> int:
        """Calculate importance score for a conversation"""
        importance = 5  # Base importance
        
        # Emotional content increases importance
        if sentiment in ["positive", "negative"]:
            importance += 2
        
        # Personal topics increase importance
        personal_topics = ["family", "faith", "relationships", "health"]
        if any(topic in personal_topics for topic in topics):
            importance += 2
        
        # Questions increase importance
        if "?" in message:
            importance += 1
        
        # Length and detail increase importance
        if len(message.split()) > 20:
            importance += 1
        
        return min(10, max(1, importance))
    
    async def chat_with_may(self, user_message: str) -> str:
        """Main chat interface"""
        try:
            # Generate response
            response = self.generate_thoughtful_response(user_message)
            
            # Save conversation to memory
            self.save_conversation(user_message, response)
            
            # Update user profile if needed
            if self.user_profile:
                self.user_profile.last_interaction = datetime.now()
                topics = self.extract_topics(user_message)
                for topic in topics:
                    if topic not in self.user_profile.interests:
                        self.user_profile.interests.append(topic)
                self.save_user_profile(self.user_profile)
            
            return response
            
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return "I'm sorry, I'm having trouble processing that right now. Could you try again?"

# FastAPI Web Interface with Chat
app = FastAPI(title="May AI - Conversational Assistant", description="Chat with May AI")

# Create templates directory
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Initialize May
may = MayConversationalAI()

@app.get("/", response_class=HTMLResponse)
async def chat_interface(request: Request):
    """Main chat interface"""
    return templates.TemplateResponse("chat.html", {"request": request})

@app.post("/chat")
async def chat_endpoint(message: str = Form(...)):
    """Chat endpoint"""
    response = await may.chat_with_may(message)
    return JSONResponse({"response": response})

@app.get("/memories")
async def get_memories(topic: str = None, limit: int = 10):
    """Get conversation memories"""
    conn = sqlite3.connect(may.memory_system.db_path)
    cursor = conn.cursor()
    
    if topic:
        cursor.execute('''
            SELECT * FROM conversations 
            WHERE topic LIKE ? OR context_tags LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        ''', (f"%{topic}%", f"%{topic}%", limit))
    else:
        cursor.execute('''
            SELECT * FROM conversations 
            ORDER BY timestamp DESC LIMIT ?
        ''', (limit,))
    
    memories = []
    for row in cursor.fetchall():
        memories.append({
            "id": row[0],
            "user_message": row[1],
            "may_response": row[2],
            "topic": row[3],
            "sentiment": row[4],
            "importance": row[5],
            "timestamp": row[6]
        })
    
    conn.close()
    return JSONResponse(memories)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time chat"""
    await websocket.accept()
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get("message", "")
            
            # Get May's response
            response = await may.chat_with_may(user_message)
            
            # Send response
            await websocket.send_text(json.dumps({
                "type": "response",
                "message": response,
                "timestamp": datetime.now().isoformat()
            }))
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close()

# Create the chat HTML template
CHAT_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Chat with May AI</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); height: 100vh; }
        .chat-container { max-width: 800px; margin: 0 auto; height: 100vh; display: flex; flex-direction: column; background: white; }
        .header { background: #4a5568; color: white; padding: 20px; text-align: center; }
        .header h1 { margin: 0; font-size: 24px; }
        .chat-messages { flex: 1; padding: 20px; overflow-y: auto; background: #f7fafc; }
        .message { margin: 10px 0; padding: 15px; border-radius: 10px; max-width: 70%; }
        .user-message { background: #4299e1; color: white; margin-left: auto; text-align: right; }
        .may-message { background: white; border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .input-area { display: flex; padding: 20px; background: white; border-top: 1px solid #e2e8f0; }
        .input-area input { flex: 1; padding: 15px; border: 1px solid #e2e8f0; border-radius: 25px; margin-right: 10px; font-size: 16px; }
        .input-area button { background: #4299e1; color: white; border: none; padding: 15px 30px; border-radius: 25px; cursor: pointer; font-size: 16px; }
        .input-area button:hover { background: #3182ce; }
        .timestamp { font-size: 12px; color: #718096; margin-top: 5px; }
        .typing { color: #718096; font-style: italic; }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="header">
            <h1>💭 Chat with May AI</h1>
            <p>Your thoughtful AI companion with memory and personality</p>
        </div>
        
        <div class="chat-messages" id="messages">
            <div class="message may-message">
                <strong>May:</strong> Hello! I'm May, your AI companion. I remember our conversations and love to chat about anything meaningful to you. What's on your mind today?
                <div class="timestamp">Just now</div>
            </div>
        </div>
        
        <div class="input-area">
            <input type="text" id="messageInput" placeholder="Type your message to May..." onkeypress="handleKeyPress(event)">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const messageInput = document.getElementById('messageInput');
        
        function addMessage(content, isUser = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'may-message'}`;
            
            const now = new Date();
            const timeStr = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            
            if (isUser) {
                messageDiv.innerHTML = `<strong>You:</strong> ${content}<div class="timestamp">${timeStr}</div>`;
            } else {
                messageDiv.innerHTML = `<strong>May:</strong> ${content}<div class="timestamp">${timeStr}</div>`;
            }
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function showTyping() {
            const typingDiv = document.createElement('div');
            typingDiv.className = 'message may-message typing';
            typingDiv.id = 'typing';
            typingDiv.innerHTML = '<strong>May:</strong> is thinking...';
            messagesDiv.appendChild(typingDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function hideTyping() {
            const typingDiv = document.getElementById('typing');
            if (typingDiv) {
                typingDiv.remove();
            }
        }
        
        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;
            
            // Add user message
            addMessage(message, true);
            messageInput.value = '';
            
            // Show typing indicator
            showTyping();
            
            try {
                // Send to May
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `message=${encodeURIComponent(message)}`
                });
                
                const result = await response.json();
                
                // Hide typing and add May's response
                hideTyping();
                addMessage(result.response);
                
            } catch (error) {
                hideTyping();
                addMessage("I'm sorry, I'm having trouble right now. Please try again.");
            }
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
        
        // Focus on input
        messageInput.focus();
    </script>
</body>
</html>
'''

# Write the template file
with open("templates/chat.html", "w") as f:
    f.write(CHAT_HTML)

if __name__ == "__main__":
    print("🤖 Starting May AI Conversational System...")
    print("💭 May now has memory, personality, and deep conversation abilities!")
    print("📱 Access at: http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)