import discord
import asyncio
import os
from discord.ext import commands
from discord.ui import View, Modal, Button, TextInput, Select
from collections import defaultdict
import re
from datetime import datetime, timedelta
from dateutil import parser

# Hardcoded Token (Replace with your actual bot token)
TOKEN = "MTM1MDk1MjU4MTUzMDEyODQ0NA.G5evMG.wAkR3amG4t6JtbpDm_Wx8UHGXSL3irXFTEy9Bs"

leaderboard_data = {"creators": defaultdict(int), "participants": defaultdict(int)}
guild_channel_map = {}

DUNGEONS = [
   "LFG - ANY", "Darkflame Cleft", "Cinderbrew Meadery", "Theater of Pain", "The Rookery",
    "Op Floodgate", "Motherlode", "Mechagone Workshop", "Priory of the Sacred Flame"
]

VALID_ROLES = ["Tank", "Healer", "DPS"]
role_emoji_map = {"Tank": "🛡️", "Healer": "💚", "DPS": "⚔️"}

# Stores active dungeon events
active_dungeon_events = {}

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

async def delete_event(channel_id, delay):
    await asyncio.sleep(delay)
    if channel_id in active_dungeon_events:
        message_id = active_dungeon_events[channel_id]["message_id"]
        channel = bot.get_channel(channel_id)
        if channel:
            try:
                message = await channel.fetch_message(message_id)
                await message.delete()
            except discord.NotFound:
                pass
        del active_dungeon_events[channel_id]

async def schedule_event_reminder(channel_id, scheduled_time):
    now = datetime.utcnow()
    delay = max((scheduled_time - timedelta(minutes=15) - now).total_seconds(), 0)
    await asyncio.sleep(delay)
    channel = bot.get_channel(channel_id)
    if channel:
        await channel.send("⚠️ Reminder: Your Mythic+ Dungeon starts in 15 minutes! ⚠️")

class DungeonSelectionView(View):
    def __init__(self, interaction):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.add_item(Select(
            placeholder="Select a Dungeon",
            options=[discord.SelectOption(label=d, value=d) for d in DUNGEONS],
            custom_id="dungeon_select",
            callback=self.select_dungeon
        ))

    async def select_dungeon(self, interaction: discord.Interaction):
        values = interaction.data.get("values")
        if not values:
            await interaction.response.send_message("No dungeon selected. Please try again.", ephemeral=True)
            return
        dungeon = values[0]
        await interaction.response.send_modal(DungeonSetupModal(interaction, dungeon))

class DungeonSetupModal(Modal, title="Dungeon Group Setup"):
    def __init__(self, interaction, dungeon):
        super().__init__(title="Dungeon Group Setup")
        self.interaction = interaction
        self.dungeon = dungeon

        self.key_level = TextInput(label="Enter Key Level", placeholder="Enter a number or 'any' if LFG", required=True)
        self.schedule = TextInput(label="Start Time", placeholder="Now or e.g., Today at 17:00 Server Time", required=True)

        self.add_item(self.key_level)
        self.add_item(self.schedule)

    async def on_submit(self, interaction: discord.Interaction):
        key_level_value = self.key_level.value.strip()
        schedule_value = self.schedule.value.strip().lower()

        if not (key_level_value.isdigit() or key_level_value == "any"):
            await interaction.response.send_message("Invalid key level. Please enter a number or 'any'.", ephemeral=True)
            return

        scheduled_time = None
        if schedule_value != "now":
            try:
                scheduled_time = parser.parse(schedule_value)
            except ValueError:
                await interaction.response.send_message("Invalid date format. Use YYYY-MM-DD HH:MM.", ephemeral=True)
                return

        await interaction.response.defer()

        followup_message = await interaction.channel.send(
            "Please select your role:",
            view=RoleSelectionView(interaction, self.dungeon, key_level_value, scheduled_time)
        )

        active_dungeon_events[interaction.channel.id] = {
            "message_id": followup_message.id,
            "dungeon": self.dungeon,
            "scheduled_time": scheduled_time,
            "players": {},
            "backups": {"Tank": [], "Healer": [], "DPS": []}
        }

        if scheduled_time:
            asyncio.create_task(schedule_event_reminder(interaction.channel.id, scheduled_time))

class RoleSelectionView(View):
    def __init__(self, interaction, dungeon, key_level, scheduled_time):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.dungeon = dungeon
        self.key_level = key_level
        self.scheduled_time = scheduled_time

        self.add_item(RoleButton("Tank"))
        self.add_item(RoleButton("Healer"))
        self.add_item(RoleButton("DPS"))

class RoleButton(Button):
    def __init__(self, role):
        super().__init__(label=role, style=discord.ButtonStyle.primary, custom_id=role)
        self.role = role

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        event = active_dungeon_events.get(interaction.channel.id)
        if not event:
            await interaction.response.send_message("Event not found. Please start a new dungeon request.", ephemeral=True)
            return

        if user_id in event["players"]:
            await interaction.response.send_message("You have already selected a role.", ephemeral=True)
            return

        event["players"][user_id] = self.role
        await interaction.response.send_message(f"You have selected {self.role}.", ephemeral=True)
        await update_event_message(interaction, event)

async def update_event_message(interaction, event):
    message = await interaction.channel.fetch_message(event["message_id"])
    updated_text = f"**Dungeon Group: {event['dungeon']}**\n\n"
    for user_id, role in event["players"].items():
        user = interaction.guild.get_member(user_id)
        updated_text += f"{user.display_name} - {role}\n"
    await message.edit(content=updated_text)

@bot.tree.command(name="leaderboard", description="View the top dungeon hosts and participants.")
async def leaderboard(interaction: discord.Interaction):
    creators = sorted(leaderboard_data["creators"].items(), key=lambda x: x[1], reverse=True)[:5]
    participants = sorted(leaderboard_data["participants"].items(), key=lambda x: x[1], reverse=True)[:5]
    embed = discord.Embed(title="🏆 Dungeon Leaderboards 🏆", color=discord.Color.gold())
    embed.add_field(name="🔹 **Top Hosts**", value="\n".join([f"{i+1}. {name} ({count} runs)" for i, (name, count) in enumerate(creators)]), inline=False)
    embed.add_field(name="🔹 **Top Participants**", value="\n".join([f"{i+1}. {name} ({count} runs)" for i, (name, count) in enumerate(participants)]), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dd", description="Creates a new dungeon group request.")
async def dd(interaction: discord.Interaction):
    await interaction.response.send_message("Select a dungeon:", view=DungeonSelectionView(interaction), ephemeral=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

bot.run(TOKEN)
 