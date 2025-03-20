import discord
import asyncio
import os
from discord.ext import commands
from discord.ui import View, Select, Modal, TextInput, Button
from datetime import datetime, timedelta
from dateutil import parser, tz
from dotenv import load_dotenv


# ------------------ Load Environment Variables ------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Please set the DISCORD_BOT_TOKEN environment variable.")

# ------------------ Global Data ------------------
guild_channel_map = {}  # Optional mapping from guild IDs to allowed channel IDs.
active_events = {}      # Stores events keyed by the event message ID.
EVENT_TIMEOUT_MINUTES = 60

# ------------------ Simulated Timezone Storage ------------------
creator_timezones = {
    # Example: 123456789012345678: "America/Los_Angeles"
}

# ------------------ Bot Setup ------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, reconnect=True)  # Ensures the bot reconnects

# ------------------ Heartbeat Task ------------------
async def keep_alive():
    """Sends a small API request to keep the bot's connection active."""
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await bot.application_info()  # Light API call to prevent timeout
            print("Heartbeat sent: Bot is still alive! 💓")
        except Exception as e:
            print(f"Heartbeat error: {e}")
        await asyncio.sleep(300)  # Sleep for 5 minutes

# ------------------ Background Cleanup Task ------------------
async def cleanup_expired_events():
    """Removes expired events every 5 minutes to prevent memory overflow."""
    while True:
        await asyncio.sleep(300)  
        now = datetime.now(tz.tzoffset("GMT+1", 3600))
        expired_events = [msg_id for msg_id, data in active_events.items() if now > data["expires_at"]]
        for msg_id in expired_events:
            active_events.pop(msg_id, None)
        print("Expired events cleaned up!")

# ------------------ Bot Ready Event ------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    bot.loop.create_task(keep_alive())  # Start heartbeat task

    try:
        print("🟡 Clearing all slash commands on bot startup...")
        bot.tree.clear_commands(guild=None)  # Clears old commands
        
        # ✅ Explicitly add the slash command before syncing
        bot.tree.add_command(dd)

        await bot.tree.sync()  # ✅ Re-syncs commands with Discord

        print(f"✅ Slash commands re-registered successfully!")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")


# ------------------ Slash Command: /dd ------------------
@bot.tree.command(name="dd", description="Creates a new dungeon group request.")
async def dd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await interaction.followup.send(content="Select your role:", view=CreatorRoleSelectionView(), ephemeral=True)

# ------------------ Global Lists ------------------
DUNGEONS = [
    "LFG - ANY", "Darkflame Cleft", "Cinderbrew Meadery", "Theater of Pain",
    "The Rookery", "Op Floodgate", "Motherlode", "Mechagone Workshop",
    "Priory of the Sacred Flame"
]
KEY_LEVELS = ["LFG"] + [str(i) for i in range(21)]
SCHEDULE_OPTIONS = ["Now", "Pick a Time"]

# ------------------ Helper Functions ------------------
def format_schedule(dt: datetime) -> str:
    """Format a datetime as 'Today HH:MM' if today, else as DD/MM/YYYY HH:MM."""
    wow_tz = tz.tzoffset("GMT+1", 3600)
    now = datetime.now(wow_tz)
    if dt.date() == now.date():
        return "Today " + dt.strftime("%H:%M")
    else:
        return dt.strftime("%d/%m/%Y %H:%M")

def build_event_embed(
    creator: discord.Member,
    dungeon: str,
    difficulty: str,
    scheduled: str,
    comment: str,
    assigned_roles: dict,
    scheduled_dt: datetime | None = None
) -> discord.Embed:
    """
    Builds an embed with:
      - Title: "{creator.display_name}'s Dungeon Group"
      - Author and thumbnail set to the creator’s display name and avatar.
      - Description includes Dungeon, Difficulty, and Scheduled time with extra newlines.
      - Scheduled time is appended with "(Server Time)"; if the creator’s timezone is known, local time is appended.
      - A separate field for Comment.
      - Role assignments (Tank, Healer, DPS) are listed vertically.
      - If the group is full (Tank and Healer assigned, and 3 DPS), a final field displays "🚫 **GROUP FULL** 🚫".
    """
    embed = discord.Embed(title=f"{creator.display_name}'s Dungeon Group", color=discord.Color.orange())
    embed.set_author(name=creator.display_name, icon_url=creator.display_avatar.url)
    embed.set_thumbnail(url=creator.display_avatar.url)
    
    desc = f"**Dungeon:** {dungeon}\n\n" \
           f"**Difficulty:** {difficulty}\n\n" \
           f"**Scheduled:** {scheduled} (Server Time)"
    if scheduled_dt and creator.id in creator_timezones:
        try:
            user_tz = tz.gettz(creator_timezones[creator.id])
            local_dt = scheduled_dt.astimezone(user_tz)
            desc += f" (Local: {local_dt.strftime('%H:%M')})"
        except Exception:
            pass
    desc += "\n\n"
    embed.description = desc

    if comment:
        embed.add_field(name="Comment", value=comment, inline=False)
    
    tank = assigned_roles["Tank"].mention if assigned_roles["Tank"] else "None"
    healer = assigned_roles["Healer"].mention if assigned_roles["Healer"] else "None"
    dps = ", ".join(m.mention for m in assigned_roles["DPS"]) if assigned_roles["DPS"] else "None"
    
    embed.add_field(name="🛡️ Tank", value=tank, inline=False)
    embed.add_field(name="💚 Healer", value=healer, inline=False)
    embed.add_field(name="⚔️ DPS", value=dps, inline=False)
    
    if assigned_roles["Tank"] is not None and assigned_roles["Healer"] is not None and len(assigned_roles["DPS"]) >= 3:
        embed.add_field(name="\u200b", value="🚫 **GROUP FULL** 🚫", inline=False)
    
    return embed

async def finalize_event(interaction: discord.Interaction, creator: discord.Member, dungeon: str, difficulty: str, sched_str: str, scheduled_dt: datetime | None, comment: str, assigned_roles: dict):
    """Finalizes the event creation by sending the embed, adding reactions, updating active_events, and pinging available roles."""
    wow_tz = tz.tzoffset("GMT+1", 3600)
    expires_at = datetime.now(wow_tz) + timedelta(minutes=EVENT_TIMEOUT_MINUTES)
    await interaction.response.edit_message(content="Event created!", view=None)
    embed = build_event_embed(creator, dungeon, difficulty, sched_str, comment, assigned_roles, scheduled_dt)
    msg = await interaction.followup.send(embed=embed, view=EventEditOptionsView(creator, msg_id=None))
    updated_view = EventEditOptionsView(creator, msg.id)
    await msg.edit(view=updated_view)
    active_events[msg.id] = {
        "creator": creator,
        "dungeon": dungeon,
        "difficulty": difficulty,
        "scheduled": sched_str,
        "comment": comment,
        "assigned_roles": assigned_roles,
        "expires_at": expires_at
    }
    await msg.add_reaction("🛡️")
    await msg.add_reaction("💚")
    await msg.add_reaction("⚔️")
    # Ping available roles.
    guild = interaction.guild
    open_pings = []
    if assigned_roles["Tank"] is None:
        role_obj = discord.utils.find(lambda r: r.name.lower() == "tank", guild.roles)
        if role_obj and role_obj.mentionable:
            open_pings.append(role_obj.mention)
    if assigned_roles["Healer"] is None:
        role_obj = discord.utils.find(lambda r: r.name.lower() == "healer", guild.roles)
        if role_obj and role_obj.mentionable:
            open_pings.append(role_obj.mention)
    if len(assigned_roles["DPS"]) < 3:
        role_obj = discord.utils.find(lambda r: r.name.lower() == "dps", guild.roles)
        if role_obj and role_obj.mentionable:
            open_pings.append(role_obj.mention)
    if open_pings:
        # Send a public follow-up message to ping the roles.
        await interaction.followup.send("Open spots: " + ", ".join(open_pings), ephemeral=False)

# ------------------ Channel Selection on Guild Join ------------------
class ChannelSelect(Select):
    def __init__(self, channels: list):
        options = [discord.SelectOption(label=ch.name, value=str(ch.id)) for ch in channels]
        super().__init__(placeholder="Select channel for bot usage", options=options, min_values=1, max_values=1)
    async def callback(self, interaction: discord.Interaction):
        selected_id = int(self.values[0])
        guild_channel_map[interaction.guild.id] = selected_id
        await interaction.response.send_message(f"Channel set to <#{selected_id}>.", ephemeral=True)

class ChannelSelectionView(View):
    def __init__(self, channels: list):
        super().__init__(timeout=60)
        self.add_item(ChannelSelect(channels))

@bot.event
async def on_guild_join(guild: discord.Guild):
    channels = [ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages]
    if not channels:
        return
    view = ChannelSelectionView(channels)
    if guild.system_channel:
        try:
            await guild.system_channel.send("Please select the channel for bot usage:", view=view)
        except discord.Forbidden:
            pass
    else:
        try:
            await guild.owner.send(f"Please select the channel for bot usage in **{guild.name}**:", view=view)
        except Exception:
            pass

# ------------------ Interactive Event Creation ------------------
# Step 1: Creator Role Selection.
class CreatorRoleSelectMenu(Select):
    def __init__(self):
        options = [discord.SelectOption(label=role, value=role) for role in ["Tank", "Healer", "DPS"]]
        super().__init__(placeholder="Select your role", options=options)
    async def callback(self, interaction: discord.Interaction):
        if interaction.guild.id in guild_channel_map and interaction.channel.id != guild_channel_map[interaction.guild.id]:
            await interaction.response.send_message("This command is restricted to the designated channel.", ephemeral=True)
            return
        creator_role = self.values[0]
        await interaction.response.edit_message(content="Select a dungeon:", view=DungeonSelectionView(interaction.user, creator_role))

class CreatorRoleSelectionView(View):
    def __init__(self):
        super().__init__()
        self.add_item(CreatorRoleSelectMenu())

# Step 2: Dungeon Selection.
class DungeonSelectMenu(Select):
    def __init__(self, creator: discord.Member, creator_role: str):
        self.creator = creator
        self.creator_role = creator_role
        options = [discord.SelectOption(label=d, value=d) for d in DUNGEONS]
        super().__init__(placeholder="Select a Dungeon", options=options)
    async def callback(self, interaction: discord.Interaction):
        dungeon = self.values[0]
        await interaction.response.edit_message(content="Select key level:", view=KeyLevelSelectionView(self.creator, self.creator_role, dungeon))

class DungeonSelectionView(View):
    def __init__(self, creator: discord.Member, creator_role: str):
        super().__init__()
        self.add_item(DungeonSelectMenu(creator, creator_role))

# Step 3: Key Level Selection.
class KeyLevelSelectMenu(Select):
    def __init__(self):
        options = [discord.SelectOption(label=level, value=level) for level in KEY_LEVELS]
        super().__init__(placeholder="Select Key Level", options=options)
    async def callback(self, interaction: discord.Interaction):
        parent: KeyLevelSelectionView = self.view  # type: ignore
        parent.difficulty = self.values[0]
        await interaction.response.edit_message(content="Select a start time:", view=ScheduleSelectionView(parent.creator, parent.creator_role, parent.dungeon, parent.difficulty))
        
class KeyLevelSelectionView(View):
    def __init__(self, creator: discord.Member, creator_role: str, dungeon: str):
        super().__init__()
        self.creator = creator
        self.creator_role = creator_role
        self.dungeon = dungeon
        self.difficulty = None
        self.add_item(KeyLevelSelectMenu())

# Step 4: Schedule Selection.
class ScheduleSelectMenu(Select):
    def __init__(self, creator: discord.Member, creator_role: str, dungeon: str, difficulty: str):
        self.creator = creator
        self.creator_role = creator_role
        self.dungeon = dungeon
        self.difficulty = difficulty
        options = [discord.SelectOption(label=opt, value=opt) for opt in SCHEDULE_OPTIONS]
        super().__init__(placeholder="Select a start time", options=options)
    async def callback(self, interaction: discord.Interaction):
        option = self.values[0]
        assigned_roles = {"Tank": None, "Healer": None, "DPS": []}
        if self.creator_role == "Tank":
            assigned_roles["Tank"] = self.creator
        elif self.creator_role == "Healer":
            assigned_roles["Healer"] = self.creator
        elif self.creator_role == "DPS":
            assigned_roles["DPS"] = [self.creator]
        if option == "Now":
            sched_str = "Now"
            scheduled_dt = None
        else:  # "Pick a Time"
            return await interaction.response.send_modal(CustomTimeModal(self.creator, self.creator_role, self.dungeon, self.difficulty))
        await interaction.response.edit_message(content="Would you like to add a comment?", view=CommentPromptView(self.creator, self.creator_role, self.dungeon, self.difficulty, sched_str, scheduled_dt, assigned_roles))
        
class ScheduleSelectionView(View):
    def __init__(self, creator: discord.Member, creator_role: str, dungeon: str, difficulty: str):
        super().__init__()
        self.add_item(ScheduleSelectMenu(creator, creator_role, dungeon, difficulty))

# ------------------ Custom Time Modal (for "Pick a Time") ------------------
class CustomTimeModal(Modal):
    def __init__(self, creator: discord.Member, creator_role: str, dungeon: str, difficulty: str):
        super().__init__(title="Pick a Custom Time")
        self.creator = creator
        self.creator_role = creator_role
        self.dungeon = dungeon
        self.difficulty = difficulty
        self.custom_time = TextInput(
            label="Enter start time (DD/MM/YYYY HH:MM)",
            style=discord.TextStyle.short,
            placeholder="20/03/2025 15:00",
            required=True
        )
        self.add_item(self.custom_time)
    async def on_submit(self, interaction: discord.Interaction):
        wow_tz = tz.tzoffset("GMT+1", 3600)
        try:
            dt = parser.parse(self.custom_time.value, dayfirst=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=wow_tz)
            sched_str = format_schedule(dt)
            scheduled_dt = dt
        except Exception:
            sched_str = self.custom_time.value
            scheduled_dt = None
        assigned_roles = {"Tank": None, "Healer": None, "DPS": []}
        if self.creator_role == "Tank":
            assigned_roles["Tank"] = self.creator
        elif self.creator_role == "Healer":
            assigned_roles["Healer"] = self.creator
        elif self.creator_role == "DPS":
            assigned_roles["DPS"] = [self.creator]
        await interaction.response.send_message("Event time set!", ephemeral=True)
        await interaction.followup.send(view=CommentPromptView(self.creator, self.creator_role, self.dungeon, self.difficulty, sched_str, scheduled_dt, assigned_roles))
        
# ------------------ Comment Prompt View ------------------
class CommentPromptView(View):
    def __init__(self, creator: discord.Member, creator_role: str, dungeon: str, difficulty: str, sched_str: str, scheduled_dt: datetime | None, assigned_roles: dict):
        super().__init__(timeout=180)
        self.creator = creator
        self.creator_role = creator_role
        self.dungeon = dungeon
        self.difficulty = difficulty
        self.sched_str = sched_str
        self.scheduled_dt = scheduled_dt
        self.assigned_roles = assigned_roles
        self.comment = ""
        self.add_item(SkipCommentButton())
        self.add_item(AddCommentButtonPrompt())
        
class SkipCommentButton(Button):
    def __init__(self):
        super().__init__(label="Skip Comment", style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction):
        parent: CommentPromptView = self.view  # type: ignore
        await finalize_event(interaction, parent.creator, parent.dungeon, parent.difficulty, parent.sched_str, parent.scheduled_dt, parent.comment, parent.assigned_roles)
        
class AddCommentButtonPrompt(Button):
    def __init__(self):
        super().__init__(label="Add Comment", style=discord.ButtonStyle.secondary)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CommentModalForPrompt(self.view))
        
class CommentModalForPrompt(Modal):
    def __init__(self, parent_view: CommentPromptView):
        super().__init__(title="Enter Comment")
        self.parent_view = parent_view
        self.comment_input = TextInput(
            label="Comment (max 100 characters)",
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.comment_input)
    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.comment = self.comment_input.value
        await finalize_event(interaction, self.parent_view.creator, self.parent_view.dungeon, self.parent_view.difficulty, self.parent_view.sched_str, self.parent_view.scheduled_dt, self.parent_view.comment, self.parent_view.assigned_roles)

# ------------------ Event Edit Options (Editing) ------------------
class EventEditOptionsView(View):
    def __init__(self, creator: discord.Member, msg_id: int | None):
        super().__init__(timeout=None)
        self.creator_id = creator.id
        if msg_id is not None:
            self.add_item(EditDungeonButton(msg_id))
            self.add_item(EditKeyLevelButton(msg_id))
            self.add_item(EditScheduleButton(msg_id))
            self.add_item(EditCommentButton(msg_id))
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("Only the event creator can use these buttons.", ephemeral=True)
            return False
        return True

class EditDungeonButton(Button):
    def __init__(self, event_id: int):
        super().__init__(label="Edit Dungeon", style=discord.ButtonStyle.primary)
        self.event_id = event_id
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        if interaction.user != event_data["creator"]:
            await interaction.response.send_message("Only the event creator can edit this event.", ephemeral=True)
            return
        await interaction.response.send_message("Select new dungeon:", view=EditDungeonView(self.event_id), ephemeral=True)

class EditDungeonSelect(Select):
    def __init__(self, event_id: int):
        self.event_id = event_id
        options = [discord.SelectOption(label=d, value=d) for d in DUNGEONS]
        super().__init__(placeholder="Select new dungeon", options=options)
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        event_data["dungeon"] = self.values[0]
        embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                                  event_data["scheduled"], event_data["comment"], event_data["assigned_roles"])
        guild = interaction.guild
        channel = guild.get_channel(interaction.channel.id)
        msg = await channel.fetch_message(self.event_id)
        await msg.edit(embed=embed)
        await interaction.response.send_message("Dungeon updated.", ephemeral=True)

class EditDungeonView(View):
    def __init__(self, event_id: int):
        super().__init__(timeout=60)
        self.add_item(EditDungeonSelect(event_id))

class EditKeyLevelButton(Button):
    def __init__(self, event_id: int):
        super().__init__(label="Edit Key Level", style=discord.ButtonStyle.primary)
        self.event_id = event_id
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        if interaction.user != event_data["creator"]:
            await interaction.response.send_message("Only the event creator can edit this event.", ephemeral=True)
            return
        await interaction.response.send_message("Select new key level:", view=EditKeyLevelView(self.event_id), ephemeral=True)

class EditKeyLevelSelect(Select):
    def __init__(self, event_id: int):
        self.event_id = event_id
        options = [discord.SelectOption(label=level, value=level) for level in KEY_LEVELS]
        super().__init__(placeholder="Select new key level", options=options)
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        event_data["difficulty"] = self.values[0]
        embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                                  event_data["scheduled"], event_data["comment"], event_data["assigned_roles"])
        guild = interaction.guild
        channel = guild.get_channel(interaction.channel.id)
        msg = await channel.fetch_message(self.event_id)
        await msg.edit(embed=embed)
        await interaction.response.send_message("Key level updated.", ephemeral=True)

class EditKeyLevelView(View):
    def __init__(self, event_id: int):
        super().__init__(timeout=60)
        self.add_item(EditKeyLevelSelect(event_id))

class EditScheduleButton(Button):
    def __init__(self, event_id: int):
        super().__init__(label="Edit Schedule", style=discord.ButtonStyle.primary)
        self.event_id = event_id
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        if interaction.user != event_data["creator"]:
            await interaction.response.send_message("Only the event creator can edit this event.", ephemeral=True)
            return
        await interaction.response.send_message("Select new schedule:", view=EditScheduleView(self.event_id), ephemeral=True)

class EditScheduleSelect(Select):
    def __init__(self, event_id: int):
        self.event_id = event_id
        options = [discord.SelectOption(label=opt, value=opt) for opt in SCHEDULE_OPTIONS]
        super().__init__(placeholder="Select new schedule", options=options)
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        if self.values[0] == "Now":
            new_sched_str = "Now"
            new_scheduled_dt = None
        else:
            return await interaction.response.send_modal(EditScheduleModal(self.event_id))
        event_data["scheduled"] = new_sched_str
        wow_tz = tz.tzoffset("GMT+1", 3600)
        event_data["expires_at"] = datetime.now(wow_tz) + timedelta(minutes=EVENT_TIMEOUT_MINUTES)
        embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                                  new_sched_str, event_data["comment"], event_data["assigned_roles"])
        guild = interaction.guild
        channel = guild.get_channel(interaction.channel.id)
        msg = await channel.fetch_message(self.event_id)
        await msg.edit(embed=embed)
        await interaction.response.send_message("Schedule updated.", ephemeral=True)

class EditScheduleView(View):
    def __init__(self, event_id: int):
        super().__init__(timeout=60)
        self.add_item(EditScheduleSelect(event_id))

class EditScheduleModal(Modal):
    def __init__(self, event_id: int):
        super().__init__(title="Edit Schedule - Custom Time")
        self.event_id = event_id
        self.new_time = TextInput(
            label="Enter new start time (DD/MM/YYYY HH:MM)",
            style=discord.TextStyle.short,
            placeholder="20/03/2025 15:00",
            required=True
        )
        self.add_item(self.new_time)
    async def on_submit(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        wow_tz = tz.tzoffset("GMT+1", 3600)
        try:
            dt = parser.parse(self.new_time.value, dayfirst=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=wow_tz)
            new_sched_str = format_schedule(dt)
            new_scheduled_dt = dt
        except Exception:
            new_sched_str = self.new_time.value
            new_scheduled_dt = None
        event_data["scheduled"] = new_sched_str
        event_data["expires_at"] = datetime.now(wow_tz) + timedelta(minutes=EVENT_TIMEOUT_MINUTES)
        embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                                  new_sched_str, event_data["comment"], event_data["assigned_roles"], scheduled_dt=new_scheduled_dt)
        guild = interaction.guild
        channel = guild.get_channel(interaction.channel.id)
        msg = await channel.fetch_message(self.event_id)
        await msg.edit(embed=embed)
        await interaction.response.send_message("Schedule updated.", ephemeral=True)

class EditCommentModal(Modal):
    def __init__(self, event_id: int):
        super().__init__(title="Edit Comment")
        self.event_id = event_id
        self.new_comment = TextInput(
            label="Enter new comment (max 100 characters)",
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.new_comment)
    async def on_submit(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        event_data["comment"] = self.new_comment.value.strip()
        embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                                  event_data["scheduled"], event_data["comment"], event_data["assigned_roles"])
        guild = interaction.guild
        channel = guild.get_channel(interaction.channel.id)
        msg = await channel.fetch_message(self.event_id)
        await msg.edit(embed=embed)
        await interaction.response.send_message("Comment updated.", ephemeral=True)

class EditCommentButton(Button):
    def __init__(self, event_id: int):
        super().__init__(label="Edit Comment", style=discord.ButtonStyle.primary)
        self.event_id = event_id
    async def callback(self, interaction: discord.Interaction):
        event_data = active_events.get(self.event_id)
        if not event_data:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return
        if interaction.user != event_data["creator"]:
            await interaction.response.send_message("Only the event creator can edit this event.", ephemeral=True)
            return
        await interaction.response.send_modal(EditCommentModal(self.event_id))

class EventEditOptionsView(View):
    def __init__(self, creator: discord.Member, msg_id: int | None):
        super().__init__(timeout=None)
        self.creator_id = creator.id
        if msg_id is not None:
            self.add_item(EditDungeonButton(msg_id))
            self.add_item(EditKeyLevelButton(msg_id))
            self.add_item(EditScheduleButton(msg_id))
            self.add_item(EditCommentButton(msg_id))
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message("Only the event creator can use these buttons.", ephemeral=True)
            return False
        return True

# ------------------ Reaction Role Handlers ------------------
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    allowed_emojis = {"🛡️", "💚", "⚔️"}
    
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return
    message = await channel.fetch_message(payload.message_id)
    user = guild.get_member(payload.user_id)
    if not user:
        return
    
    if payload.emoji.name not in allowed_emojis:
        try:
            await message.remove_reaction(payload.emoji, user)
        except Exception:
            pass
        return
    
    if payload.user_id == bot.user.id:
        return
    if payload.message_id not in active_events:
        return
    event_data = active_events[payload.message_id]
    wow_tz = tz.tzoffset("GMT+1", 3600)
    if datetime.now(wow_tz) > event_data["expires_at"]:
        return  # Event timed out.
    
    emoji_to_role = {"🛡️": "Tank", "💚": "Healer", "⚔️": "DPS"}
    if payload.emoji.name not in emoji_to_role:
        return
    role_name = emoji_to_role[payload.emoji.name]
    assigned = event_data["assigned_roles"]
    if (assigned["Tank"] and assigned["Tank"].id == user.id) or \
   (assigned["Healer"] and assigned["Healer"].id == user.id) or \
   any(member.id == user.id for member in assigned["DPS"]):
        try:
            await message.remove_reaction(payload.emoji, user)
        except Exception:
            pass
        return
    if role_name in ["Tank", "Healer"]:
        if assigned[role_name]:
            try:
                await message.remove_reaction(payload.emoji, user)
            except Exception:
                pass
            return
        else:
            assigned[role_name] = user
    elif role_name == "DPS":
        if len(assigned["DPS"]) >= 3:
            try:
                await message.remove_reaction(payload.emoji, user)
            except Exception:
                pass
            return
        else:
            assigned["DPS"].append(user)
    embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                              event_data["scheduled"], event_data["comment"], assigned)
    await message.edit(embed=embed)

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    if payload.message_id not in active_events:
        return
    event_data = active_events[payload.message_id]
    wow_tz = tz.tzoffset("GMT+1", 3600)
    if datetime.now(wow_tz) > event_data["expires_at"]:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    channel = guild.get_channel(payload.channel_id)
    if not channel:
        return
    message = await channel.fetch_message(payload.message_id)
    user = guild.get_member(payload.user_id)
    if not user:
        return
    emoji_to_role = {"🛡️": "Tank", "💚": "Healer", "⚔️": "DPS"}
    if payload.emoji.name not in emoji_to_role:
        return
    role_name = emoji_to_role[payload.emoji.name]
    assigned = event_data["assigned_roles"]
    if role_name in ["Tank", "Healer"]:
        if assigned[role_name] == user:
            assigned[role_name] = None
    elif role_name == "DPS":
        if user in assigned["DPS"]:
            assigned["DPS"].remove(user)
    embed = build_event_embed(event_data["creator"], event_data["dungeon"], event_data["difficulty"],
                              event_data["scheduled"], event_data["comment"], assigned)
    await message.edit(embed=embed)


bot.run(TOKEN)