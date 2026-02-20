import sqlite3
import discord                                                                                                                                   
from discord.ext import commands
from discord import app_commands
#import asyncio
#import random
import requests
import json
import asyncio
import acconfig

class AntiCarlBot(commands.Bot):
    def __init__(self):
        # 1. Setup the intents object first
        my_intents = discord.Intents.default()
        my_intents.message_content = True
        my_intents.members = True
        my_intents.presences = True

        # 2. Pass that object into the parent class
        super().__init__(
            command_prefix="!",
            intents=my_intents
        )

    async def setup_hook(self):
        await self.tree.sync()
        print("Slash commands synced!")

bot = AntiCarlBot()

CARL_BOT_ID = 235148962103951360

RESPONSE_MAP = {
    "good": ":smile:",
    "bad": "Fuck carl!",
    "carl": "Don't ever say that name around me. :rage:",
    "listen": "I always listen! :innocent:",
    "cottage": "I'm coming to the cottage ||What even does this mean?||",
    "love": "Don't insult me! ||But I love you too bb!||"
}

# --- Database Setup ---
trigger_cache = []  # list of (id, response, [keywords])

def init_db():
    conn = sqlite3.connect('anti-carl.db')
    c = conn.cursor()
    
    # Updated schema with proper primary key
    c.execute('''CREATE TABLE IF NOT EXISTS trigger_groups 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  response TEXT NOT NULL,
                  keywords TEXT NOT NULL UNIQUE)''')
    
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

        for response, keywords_list in flipped_map.items():
            keyword_string = ",".join(keywords_list)
            try:
                c.execute("INSERT INTO trigger_groups (response, keywords) VALUES (?, ?)", 
                          (response, keyword_string))
            except sqlite3.IntegrityError:
                print(f"Skipped duplicate keywords during init: {keyword_string}")
        
        conn.commit()
        print("Database pre-populated successfully!")

    conn.close()

def reload_cache():
    """Updates the global trigger_cache variable with the latest DB data."""
    global trigger_cache
    conn = sqlite3.connect('anti-carl.db')
    c = conn.cursor()
    c.execute("SELECT id, response, keywords FROM trigger_groups ORDER BY id")
    raw_data = c.fetchall()
    conn.close()
    
    # Now includes id: [(id, "🙂", ["good", "great"]), ...]
    trigger_cache = [(row[0], row[1], row[2].split(',')) for row in raw_data]
    print(f"Cache updated: {len(trigger_cache)} groups loaded.")

async def get_ai_response(user_message: str) -> str | None:
    """Returns AI reply or None if Ollama is unreachable (silent fail)."""
    try:
        payload = {
            "model": acconfig.OLLAMA_MODEL,          # "gpt-oss:20b"
            "messages": [
                {"role": "system", "content": acconfig.SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            "stream": False,                         # we want full response at once
            "options": {                             # optional tuning — feel free to tweak or remove
                "temperature": acconfig.OLLAMA_TEMPERATURE, #0.9,
                "top_p": 0.95
            }
        }

        # Run the blocking requests call in a thread so it doesn't freeze the bot
        response = await asyncio.to_thread(
            requests.post,
            f"{acconfig.OLLAMA_HOST}/api/chat",
            json=payload,
            timeout=120                              # generous timeout — 20B model can be a bit slow on laptop
        )

        response.raise_for_status()                  # raise if 4xx/5xx

        # Ollama /api/chat returns JSON with "message" → "content"
        result = response.json()
        ai_text = result.get("message", {}).get("content", "").strip()

        return ai_text if ai_text else None

    except requests.exceptions.RequestException as e:
        print(f"[Ollama fallback] connection failed: {type(e).__name__} - {e}")
        return None
    except Exception as e:
        print(f"[Ollama fallback] unexpected error: {type(e).__name__} - {e}")
        return None

@bot.event
async def on_ready():
    # Set the status to "Watching Carl-bot"
    # Options: discord.ActivityType.watching, .listening, .playing, .competing
    activity = discord.Activity(type=discord.ActivityType.watching, name="Carl-bot")
    
    await bot.change_presence(status=discord.Status.online, activity=activity)

    print(f'Logged in as {bot.user}')

@bot.listen("on_message")
async def anti_carl_reply(message):
    if message.author == bot.user:
        return

    # 1. Reply to Carl-bot
    if message.author.id == CARL_BOT_ID:
        await message.reply("ya mom's a hoe")
        return

    # 2. Modular logic - Check conditions separately
    is_reply_to_me = False
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        if message.reference.resolved.author.id == bot.user.id:
            is_reply_to_me = True

    is_mentioned = bot.user.mentioned_in(message)

    if is_reply_to_me or is_mentioned:
        # If we're tagged in @everyone, ignore that
        if message.mention_everyone:
            return

        clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if not clean_content:
            clean_content = message.content

        ai_reply = await get_ai_response(clean_content)
        if ai_reply:
            await message.reply(ai_reply)
            return

        content_lower = message.content.lower()
        
        for _, response_text, keyword_list in trigger_cache:
            if any(k.strip() in content_lower for k in keyword_list):
                await message.reply(response_text)
                return
        
        # Fallback
        #await message.reply("¯\_(ツ)_/¯")
        # AI fallback — only triggered on mention/reply-to-me with no keyword match
        # If Ollama is unreachable → silently do nothing (exactly as you requested)
        #ai_reply = await get_ai_response(message.content)
        #if ai_reply:
        #    await message.reply(ai_reply)
        # else: nothing — completely silent

# ────────────────────────────────────────────────
#   Autocomplete helper for selecting a trigger group
# ────────────────────────────────────────────────
async def trigger_response_autocomplete(interaction: discord.Interaction, current: str):
    # Return list of current responses for selection
    choices = [
        app_commands.Choice(name=f"{resp} ({', '.join(kws[:3])}{'...' if len(kws)>3 else ''})", value=str(tid))
        for tid, resp, kws in trigger_cache
        if current.lower() in resp.lower() or any(current.lower() in k.lower() for k in kws)
    ][:25]  # Discord limit
    return choices

# ────────────────────────────────────────────────
#   Improved: /set_response now prevents keyword overlap
# ────────────────────────────────────────────────
@bot.tree.command(name="set_response", description="Add or update a response with keywords (keywords must be unique)")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.describe(
    keywords="Comma-separated keywords (no spaces)",
    response="The reply/emote the bot should send"
)
async def set_response(interaction: discord.Interaction, keywords: str, response: str):
    clean_keywords = ",".join(k.strip().lower() for k in keywords.split(',') if k.strip())
    if not clean_keywords:
        await interaction.response.send_message("No valid keywords provided.", ephemeral=True)
        return

    conn = sqlite3.connect('anti-carl.db')
    c = conn.cursor()

    # Check if any of these keywords already exist
    placeholders = ",".join("?" for _ in clean_keywords.split(","))
    c.execute(f"SELECT keywords FROM trigger_groups WHERE keywords IN ({placeholders})", 
              clean_keywords.split(","))
    conflicts = c.fetchall()

    if conflicts:
        conflict_list = ", ".join(row[0] for row in conflicts)
        await interaction.response.send_message(
            f"Cannot add: these keywords already exist in another group:\n`{conflict_list}`\n"
            "Remove or edit the existing group first.", ephemeral=True)
        conn.close()
        return

    # Insert or replace (but since keywords are unique, REPLACE would fail → we use INSERT)
    try:
        c.execute("INSERT INTO trigger_groups (response, keywords) VALUES (?, ?)", 
                  (response, clean_keywords))
        conn.commit()
        await interaction.response.send_message(f"Added: `{clean_keywords}` → `{response}`", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message("Error: keywords already exist (race condition?). Try again.", ephemeral=True)
    
    conn.close()
    reload_cache()

@bot.tree.command(name="list_triggers", description="Show all active keyword groups")
@app_commands.checks.has_permissions(moderate_members=True)
async def list_triggers(interaction: discord.Interaction):
    if not trigger_cache:
        await interaction.response.send_message("No triggers set yet! Use `/set_response`.", ephemeral=True)
        return

    embed = discord.Embed(title="🐢 Anti-Carl Trigger List", color=discord.Color.blue())
    
    for tid, response, keywords in trigger_cache:
        keyword_str = ", ".join(keywords)
        embed.add_field(
            name=f"ID {tid} | Response: {response}",
            value=f"Keywords: `{keyword_str}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove_response", description="Delete a trigger group by selecting it")
@app_commands.describe(trigger="The trigger group to remove")
@app_commands.autocomplete(trigger=trigger_response_autocomplete)
@app_commands.checks.has_permissions(moderate_members=True)
async def remove_response(interaction: discord.Interaction, trigger: str):
    try:
        trigger_id = int(trigger)
    except ValueError:
        await interaction.response.send_message("Invalid selection.", ephemeral=True)
        return

    conn = sqlite3.connect('anti-carl.db')
    c = conn.cursor()
    c.execute("DELETE FROM trigger_groups WHERE id = ?", (trigger_id,))
    if c.rowcount == 0:
        await interaction.response.send_message(f"No trigger with ID {trigger_id} found.", ephemeral=True)
    else:
        conn.commit()
        await interaction.response.send_message(f"Removed trigger ID {trigger_id}.", ephemeral=True)
    
    conn.close()
    reload_cache()

@bot.tree.command(name="edit_trigger", description="Edit response and/or keywords of an existing trigger")
@app_commands.describe(
    trigger="Select the trigger group to edit",
    new_response="New response text (leave empty to keep current)",
    new_keywords="New comma-separated keywords (leave empty to keep current)"
)
@app_commands.autocomplete(trigger=trigger_response_autocomplete)
@app_commands.checks.has_permissions(moderate_members=True)
async def edit_trigger(
    interaction: discord.Interaction,
    trigger: str,
    new_response: str = None,
    new_keywords: str = None
):
    try:
        trigger_id = int(trigger)
    except ValueError:
        await interaction.response.send_message("Invalid trigger selection.", ephemeral=True)
        return

    # Get current values
    conn = sqlite3.connect('anti-carl.db')
    c = conn.cursor()
    c.execute("SELECT response, keywords FROM trigger_groups WHERE id = ?", (trigger_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        await interaction.response.send_message(f"Trigger ID {trigger_id} not found.", ephemeral=True)
        return

    current_response, current_keywords_str = row
    current_keywords = current_keywords_str.split(',')

    # Prepare updates
    updates = []
    params = []

    if new_response is not None and new_response.strip():
        updates.append("response = ?")
        params.append(new_response.strip())

    if new_keywords is not None and new_keywords.strip():
        clean_new = ",".join(k.strip().lower() for k in new_keywords.split(',') if k.strip())
        if not clean_new:
            conn.close()
            await interaction.response.send_message("No valid keywords provided.", ephemeral=True)
            return

        # Check for conflicts with **other** groups
        c.execute("SELECT id FROM trigger_groups WHERE keywords = ? AND id != ?", (clean_new, trigger_id))
        if c.fetchone():
            conn.close()
            await interaction.response.send_message(
                f"Cannot update: these keywords are already used by another group.", ephemeral=True)
            return

        updates.append("keywords = ?")
        params.append(clean_new)

    if not updates:
        conn.close()
        await interaction.response.send_message("No changes provided.", ephemeral=True)
        return

    # Apply update
    query = f"UPDATE trigger_groups SET {', '.join(updates)} WHERE id = ?"
    params.append(trigger_id)
    c.execute(query, params)
    conn.commit()
    conn.close()

    reload_cache()

    changes = []
    if new_response and new_response.strip():
        changes.append(f"response → `{new_response}`")
    if new_keywords and new_keywords.strip():
        changes.append(f"keywords → `{clean_new}`")

    await interaction.response.send_message(
        f"Updated trigger ID {trigger_id}:\n" + "\n".join(changes),
        ephemeral=True
    )

# Implemented ping/pong to test if bot is alive during debugging
@bot.tree.command(name="ping", description="Checks if Anti-Carl is awake")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! I'm listening.", ephemeral=True)

init_db()
reload_cache()

bot.run(acconfig.API_KEY)