import sqlite3
import discord                                                                                                                                   
from discord.ext import commands
from discord import app_commands
#import asyncio
#import random
import acconfig

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

CARL_BOT_ID = 235148962103951360

RESPONSE_MAP = {
    "good": ":smile:",
    "bad": "Fuck carl!",
    "carl": "Don't ever say that name around me. :rage:",
    "listen": "I always listen!",
    "cottage": "I'm coming to the cottage ||What even does this mean?||",
    "love": "Don't insult me! ||But I love you too bb!||"
}

# --- Database Setup ---
trigger_cache = []

def init_db():
    conn = sqlite3.connect('anti_carl.db')
    c = conn.cursor()
    # Create the table
    c.execute('''CREATE TABLE IF NOT EXISTS trigger_groups 
                 (response TEXT PRIMARY KEY, keywords TEXT)''')
    
    # Check if any data exists
    c.execute("SELECT COUNT(*) FROM trigger_groups")
    if c.fetchone()[0] == 0:
        print("First run detected. Pre-populating database with default triggers...")
        
        # 1. Flip your RESPONSE_MAP: Keyword -> Response TO Response -> Keywords
        # We use a temporary dict to group multiple keywords to the same response
        flipped_map = {}
        for keyword, response in RESPONSE_MAP.items():
            if response not in flipped_map:
                flipped_map[response] = []
            flipped_map[response].append(keyword)

        # 2. Insert into database
        for response, keywords_list in flipped_map.items():
            # Join ["good", "great"] into "good,great"
            keyword_string = ",".join(keywords_list)
            c.execute("INSERT INTO trigger_groups (response, keywords) VALUES (?, ?)", 
                      (response, keyword_string))
        
        conn.commit()
        print("Database pre-populated successfully!")

    conn.close()

def reload_cache():
    """Updates the global trigger_cache variable with the latest DB data."""
    global trigger_cache
    conn = sqlite3.connect('anti_carl.db')
    c = conn.cursor()
    c.execute("SELECT response, keywords FROM trigger_groups")
    # We store it as a list of tuples: [("🙂", ["good", "great"]), ...]
    raw_data = c.fetchall()
    conn.close()
    
    # Pre-process the strings into lists now so we don't have to do it every message
    trigger_cache = [(row[0], row[1].split(',')) for row in raw_data]
    print(f"Cache updated: {len(trigger_cache)} groups loaded.")

init_db()
reload_cache()

@bot.event
async def on_ready():
    # Set the status to "Watching Carl-bot"
    # Options: discord.ActivityType.watching, .listening, .playing, .competing
    activity = discord.Activity(type=discord.ActivityType.watching, name="Carl-bot")
    
    # You can also set the 'Status' (Online, Idle, DND, Invisible)
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Syncs slash commands with Discord
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')

@bot.listen("on_message")
async def anti_carl_reply(message):
    if message.author == bot.user:
        return

    # 1. Reply to Carl-bot
    if message.author.id == CARL_BOT_ID:
        await message.reply("ya mom's a hoe")
        return # Added return to stop processing if it's Carl

    # 2. Modular logic - Check conditions separately
    is_reply_to_me = False
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        if message.reference.resolved.author.id == bot.user.id:
            is_reply_to_me = True

    # This was previously indented too far!
    is_mentioned = bot.user.mentioned_in(message)

    # Now this runs if it's a reply OR a mention
    if is_reply_to_me or is_mentioned:
        content_lower = message.content.lower()
        
        # Check against the fast memory cache
        for response_text, keyword_list in trigger_cache:
            if any(k in content_lower for k in keyword_list):
                await message.reply(response_text)
                return
        
        # Fallback if no keywords matched
        await message.reply("You rang? :eyes:")

@bot.tree.command(name="set_response", description="Set multiple keywords for one response")
@app_commands.checks.has_permissions(moderate_members=True)
async def set_response(interaction: discord.Interaction, keywords: str, response: str):
    # 1. Clean up keywords (lowercase and remove spaces)
    clean_keywords = keywords.lower().replace(" ", "")
    
    # 2. Write to Database
    conn = sqlite3.connect('anti_carl.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO trigger_groups (response, keywords) VALUES (?, ?)", 
              (response, clean_keywords))
    conn.commit()
    conn.close()
    
    # 3. CRITICAL: Refresh the memory cache immediately
    reload_cache()
    
    await interaction.response.send_message(f"Updated cache! `{keywords}` -> `{response}`", ephemeral=True)

@bot.tree.command(name="list_triggers", description="Show all active keyword groups")
@app_commands.checks.has_permissions(moderate_members=True)
async def list_triggers(interaction: discord.Interaction):
    if not trigger_cache:
        await interaction.response.send_message("No triggers set yet! Use `/set_response`.", ephemeral=True)
        return

    embed = discord.Embed(title="🐢 Anti-Carl Trigger List", color=discord.Color.blue())
    
    for response, keywords in trigger_cache:
        # Join keywords back into a string for display
        keyword_str = ", ".join(keywords)
        embed.add_field(name=f"Response: {response}", value=f"Keywords: `{keyword_str}`", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Remove a Trigger Group ---
@bot.tree.command(name="remove_response", description="Delete a response and all its keywords")
@app_commands.describe(response="The exact response/emoji you want to remove")
@app_commands.checks.has_permissions(moderate_members=True)
async def remove_response(interaction: discord.Interaction, response: str):
    conn = sqlite3.connect('anti_carl.db')
    c = conn.cursor()
    
    # Check if it exists first
    c.execute("SELECT 1 FROM trigger_groups WHERE response = ?", (response,))
    if not c.fetchone():
        conn.close()
        await interaction.response.send_message(f"Could not find a trigger with the response: `{response}`", ephemeral=True)
        return

    c.execute("DELETE FROM trigger_groups WHERE response = ?", (response,))
    conn.commit()
    conn.close()
    
    reload_cache()
    await interaction.response.send_message(f"Successfully removed the `{response}` trigger group.", ephemeral=True)

# --- Edit Keywords for an Existing Response ---
@bot.tree.command(name="edit_keywords", description="Update the keywords for an existing response")
@app_commands.describe(response="The response to edit", new_keywords="The new comma-separated list of words")
@app_commands.checks.has_permissions(moderate_members=True)
async def edit_keywords(interaction: discord.Interaction, response: str, new_keywords: str):
    # Clean the input
    clean_keywords = ",".join([k.strip().lower() for k in new_keywords.split(',')])
    
    conn = sqlite3.connect('anti_carl.db')
    c = conn.cursor()
    
    # Verify the response exists before updating
    c.execute("SELECT 1 FROM trigger_groups WHERE response = ?", (response,))
    if not c.fetchone():
        conn.close()
        await interaction.response.send_message(f"The response `{response}` doesn't exist yet. Use `/set_response` to create it.", ephemeral=True)
        return

    c.execute("UPDATE trigger_groups SET keywords = ? WHERE response = ?", (clean_keywords, response))
    conn.commit()
    conn.close()
    
    reload_cache()
    await interaction.response.send_message(f"Keywords updated for `{response}`: `{clean_keywords}`", ephemeral=True)

# Implemented ping/pong to test if bot is alive during debugging
@bot.tree.command(name="ping", description="Checks if Anti-Carl is awake")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! I'm listening.", ephemeral=True)

bot.run(acconfig.API_KEY)