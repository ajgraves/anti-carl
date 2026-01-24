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
    "cottage": "I'm coming to the cottage",
    "love": "Don't insult me! ||But I love you too bb!||"
}

@bot.event
async def on_ready():
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

        for trigger, response in RESPONSE_MAP.items():
            if trigger in content_lower:
                await message.reply(response)
                return

        await message.reply("You rang? (x_x)")

# Implemented ping/pong to test if bot is alive during debugging
@bot.tree.command(name="ping", description="Checks if Anti-Carl is awake")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong! I'm listening.", ephemeral=True)

bot.run(API_KEY)