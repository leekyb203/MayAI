import asyncio
import sqlite3
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json
import os
from datetime import datetime
from memory_database import MayConversationalAI

# Telegram Bot Token (you'll need to get this from @BotFather)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8087505132:AAEeQkBdrxL3Sp5UcPtMO5kZu6juKzF6d_I')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MayTelegramBot:
    """Telegram bot interface for May AI"""
    
    def __init__(self):
        self.may = MayConversationalAI()
        self.user_states = {}  # Track user conversation states
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "friend"
        
        # Initialize user profile if needed
        if not self.may.user_profile or self.may.user_profile.name != user_name:
            from may_conversational_ai import UserProfile
            profile = UserProfile(
                name=user_name,
                interests=[],
                values=[],
                conversation_patterns={},
                last_interaction=datetime.now(),
                relationship_level=1
            )
            self.may.user_profile = profile
            self.may.save_user_profile(profile)
        
        welcome_message = f"""
🤖 Hello {user_name}! I'm May, your AI companion.

I'm here to have meaningful conversations with you. I remember what we talk about and care about the things that matter to you.

My core values are rooted in:
✨ Honesty and truth
💝 Compassion and kindness  
🛡️ Respect for life and dignity
🙏 Faith and moral integrity
👨‍👩‍👧‍👦 Family and relationships
📚 Learning and growth

What would you like to talk about today?

Commands:
/help - Show this message
/memories - See our conversation history
/profile - View your profile
/clear - Clear conversation context
        """
        
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
🤖 **May AI Commands:**

/start - Start conversation with May
/help - Show this help message  
/memories - View our conversation history
/profile - See your user profile
/clear - Clear current conversation context

**About May:**
May is your thoughtful AI companion who remembers your conversations and cares about what matters to you. She's designed with strong moral values and loves deep, meaningful discussions.

Just send me any message to start chatting! 💭
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def memories_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show conversation memories"""
        try:
            # Get recent memories
            conn = sqlite3.connect(self.may.memory_system.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT topic, user_message, timestamp, importance 
                FROM conversations 
                ORDER BY timestamp DESC LIMIT 10
            ''')
            
            memories = cursor.fetchall()
            conn.close()
            
            if not memories:
                await update.message.reply_text("We haven't had any conversations to remember yet! Let's start chatting! 😊")
                return
            
            memory_text = "💭 **Our Recent Conversations:**\n\n"
            
            for memory in memories:
                topic, message, timestamp, importance = memory
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%m/%d %H:%M")
                
                # Truncate long messages
                display_message = message[:60] + "..." if len(message) > 60 else message
                
                memory_text += f"🔹 **{topic.title()}** ({time_str})\n"
                memory_text += f"   \"{display_message}\"\n"
                memory_text += f"   *Importance: {importance}*\n\n"
            
            await update.message.reply_text(memory_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error retrieving memories: {e}")
            await update.message.reply_text("Sorry, I couldn't retrieve our conversation memories right now.")
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user profile"""
        try:
            if not self.may.user_profile:
                await update.message.reply_text("I don't have a profile for you yet. Let's chat more so I can get to know you! 😊")
                return
            
            profile = self.may.user_profile
            profile_text = f"""
👤 **Your Profile:**

**Name:** {profile.name}
**Relationship Level:** {profile.relationship_level}/10
**Last Interaction:** {profile.last_interaction.strftime("%B %d, %Y")}

**Interests:** {", ".join(profile.interests) if profile.interests else "Getting to know you!"}
**Values:** {", ".join(profile.values) if profile.values else "Learning about what matters to you!"}

Let's keep chatting so I can learn more about you! 💭
            """
            
            await update.message.reply_text(profile_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing profile: {e}")
            await update.message.reply_text("Sorry, I couldn't load your profile right now.")
    
    async def clear_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear conversation context"""
        user_id = update.effective_user.id
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await update.message.reply_text("✨ Conversation context cleared! Ready for a fresh start. What's on your mind?")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        try:
            user_message = update.message.text
            user_id = update.effective_user.id
            user_name = update.effective_user.first_name or "friend"
            
            # Get AI response
            response = await self.may.process_message(
                user_message=user_message,
                user_id=str(user_id),
                user_name=user_name
            )
            
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text("Sorry, I encountered an error processing your message. Please try again!")

def main():
    """Start the bot"""
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Create bot instance
    bot = MayTelegramBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start_command))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("memories", bot.memories_command))
    application.add_handler(CommandHandler("profile", bot.profile_command))
    application.add_handler(CommandHandler("clear", bot.clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    
    # Run the bot
    print("Starting May AI Telegram Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()