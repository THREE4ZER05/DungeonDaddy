import discord
import os
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    print("❌ ERROR: DISCORD_BOT_TOKEN is missing! Check your .env file.")
    exit()

# Create bot instance
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    try:
        print("🟡 Clearing all slash commands...")
        bot.tree.clear_commands(guild=None)  # ✅ FIXED: Removed 'await'
        await bot.tree.sync()
        print("✅ All slash commands have been removed.")
    except Exception as e:
        print(f"❌ Failed to clear commands: {e}")

    await bot.close()  # Closes the bot after clearing commands

# Run the bot
print("🟡 Starting bot...")
bot.run(TOKEN)
