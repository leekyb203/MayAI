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
        
        # Learning sessions (for tracking what May is actively learning)
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
        
        # Content blacklist (for filtering harmful content)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS content_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filter_type TEXT NOT NULL,  -- 'keyword', 'domain', 'pattern'
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
        
        cursor.execute('''
            SELECT topic, content, source_url, confidence_score, learned_at 
            FROM knowledge 
            WHERE topic LIKE ? AND validation_status != 'rejected'
            ORDER BY confidence_score DESC, learned_at DESC
            LIMIT ?
        ''', (f"%{topic}%", limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'topic': row[0],
                'content': row[1],
                'source': row[2],
                'confidence': row[3],
                'learned_at': row[4]
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


# Usage Example
async def main():
    """Example usage of May's learning system"""
    may = MayLearningEngine()
    
    # Start learning about a specific topic
    print("May is starting to learn about 'artificial intelligence'...")
    await may.learn_from_web("artificial intelligence")
    
    # Retrieve what May learned
    knowledge = may.get_knowledge_on_topic("artificial intelligence")
    
    print(f"\nMay learned {len(knowledge)} things about AI:")
    for item in knowledge[:3]:  # Show first 3
        print(f"\nFrom: {item['source']}")
        print(f"Confidence: {item['confidence']:.2f}")
        print(f"Content: {item['content'][:200]}...")

if __name__ == "__main__":
    asyncio.run(main())