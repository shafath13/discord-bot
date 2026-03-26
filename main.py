import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, random, asyncio, json, aiohttp
from groq import AsyncGroq
from dotenv import load_dotenv

# --- 1. SETUP ---
load_dotenv()
TOKEN = os.getenv("TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

MODEL_NAME = "llama-3.1-8b-instant" 
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 2. DATA PERSISTENCE ---
DATA_FILE = "bot_memory.json"

def save_game():
    data = {"user_data": user_data, "chat_channels": list(chat_channels), 
            "spawn_channels": list(spawn_channels), "counting_data": counting_data}
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_game():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                d = json.load(f)
                return (d.get("user_data", {}), set(d.get("chat_channels", [])), 
                        set(d.get("spawn_channels", [])), d.get("counting_data", {"channel_id": None, "last_number": 0, "last_user": None}))
        except: pass
    return {}, set(), set(), {"channel_id": None, "last_number": 0, "last_user": None}

user_data, chat_channels, spawn_channels, counting_data = load_game()
active_spawns = {} 

CAT_TYPES = {"Common": {"emoji": "🐱", "color": 0x95a5a6}, "Rare": {"emoji": "🥈", "color": 0x3498db}, 
             "Epic": {"emoji": "💎", "color": 0x9b59b6}, "Legendary": {"emoji": "👑", "color": 0xf1c40f}}

RIDDLES = [
    {"q": "I speak without a mouth and hear without ears. What am I?", "a": ["echo"]},
    {"q": "The more of this there is, the less you see. What is it?", "a": ["darkness", "dark"]},
    {"q": "I have keys but no locks. What am I?", "a": ["keyboard"]},
    {"q": "What has to be broken before you can use it?", "a": ["egg"]},
    {"q": "I’m tall when I’m young, and I’m short when I’m old. What am I?", "a": ["candle", "pencil"]}
]

# --- 3. RIDDLE UI ---

class RiddleView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=60)
        self.user = user

    @discord.ui.button(label="Next Riddle", style=discord.ButtonStyle.green, emoji="🧠")
    async def next_riddle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user: return await interaction.response.send_message("Not your game!", ephemeral=True)
        await interaction.message.edit(view=None)
        await play_riddle(interaction.channel, self.user)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="🛑")
    async def stop_riddle(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user: return await interaction.response.send_message("Not your game!", ephemeral=True)
        await interaction.message.edit(view=None)
        await interaction.response.send_message("Game ended. Catch ya later.")

async def play_riddle(channel, user):
    riddle = random.choice(RIDDLES)
    await channel.send(f"🧠 **Riddle for {user.mention}:**\n> {riddle['q']}")
    try:
        msg = await bot.wait_for('message', check=lambda m: m.author == user and m.channel == channel, timeout=30.0)
        if any(ans in msg.content.lower() for ans in riddle['a']):
            await msg.reply("🎉 **Correct!**", view=RiddleView(user))
        else:
            await msg.reply(f"❌ **Wrong!** Answer: **{riddle['a'][0]}**.")
    except: await channel.send(f"⏰ Timeout! Answer: **{riddle['a'][0]}**.")

# --- 4. ALL COMMANDS ---

@bot.command()
async def sync(ctx):
    if ctx.author.guild_permissions.administrator:
        await bot.tree.sync()
        await ctx.send("✅ All Commands Synced!")

@bot.tree.command(name="setup_counting")
async def setup_counting(interaction: discord.Interaction):
    counting_data.update({"channel_id": interaction.channel.id, "last_number": 0, "last_user": None})
    save_game()
    await interaction.response.send_message("🔢 Counting setup! Start with **1**.")

@bot.tree.command(name="chat_enable")
async def chat_enable(interaction: discord.Interaction):
    chat_channels.add(interaction.channel.id)
    save_game()
    await interaction.response.send_message("💬 AI Chat active!")

@bot.tree.command(name="setup_cats")
async def setup_cats(interaction: discord.Interaction):
    spawn_channels.add(interaction.channel.id)
    save_game()
    await interaction.response.send_message("🐾 Cat spawns active!")

@bot.tree.command(name="profile")
async def profile(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    stats = user_data.get(uid, {"cats": {"Common": 0, "Rare": 0, "Epic": 0, "Legendary": 0}})
    embed = discord.Embed(title=f"🎒 {interaction.user.name}'s Bag", color=0x3498db)
    for r, count in stats["cats"].items():
        embed.add_field(name=f"{CAT_TYPES[r]['emoji']} {r}", value=count, inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="riddle")
async def riddle_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🎲 Riddle game starting...")
    await play_riddle(interaction.channel, interaction.user)

@bot.tree.command(name="prank")
@app_commands.checks.has_permissions(administrator=True)
async def prank(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"⚠️ **INITIATING BAN** for {member.mention}... reason: *skill issue.*")
    await asyncio.sleep(4)
    await interaction.channel.send("Pranked. You're safe. 🤡")

@bot.tree.command(name="ghost_ping")
async def ghost_ping(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message("🤫", ephemeral=True)
    msg = await interaction.channel.send(member.mention)
    await msg.delete()

# --- 5. THE BRAIN (FIXED MULTI-MESSAGE & TYPING) ---

@bot.event
async def on_message(message):
    # 1. Ignore other bots
    if message.author.bot and message.author.id != bot.user.id: return
    
    # 2. Handle Counting
    if counting_data.get("channel_id") == message.channel.id and message.content.isdigit():
        num = int(message.content)
        expected = counting_data["last_number"] + 1
        
        if message.author.id == bot.user.id:
            counting_data.update({"last_number": num, "last_user": str(bot.user.id)})
            save_game()
            return # Stop processing this message

        if num == expected and str(message.author.id) != counting_data["last_user"]:
            counting_data.update({"last_number": num, "last_user": str(message.author.id)})
            save_game()
            await message.add_reaction("✅")
            await asyncio.sleep(1)
            await message.channel.send(str(num + 1))
            return # Stop processing this message
        else:
            counting_data.update({"last_number": 0, "last_user": None})
            save_game()
            try: await message.delete()
            except: pass
            roasts = [f"Actual skill issue {message.author.mention}. Back to 1.", 
                      f"Imagine failing at math. {message.author.mention} ruined it. Restart from 1."]
            await message.channel.send(random.choice(roasts))
            return # Stop processing this message

    # 3. Handle Cat Catching
    if message.channel.id in active_spawns and message.content.lower() == "cat":
        rarity = active_spawns.pop(message.channel.id)
        uid = str(message.author.id)
        if uid not in user_data: user_data[uid] = {"cats": {"Common": 0, "Rare": 0, "Epic": 0, "Legendary": 0}}
        user_data[uid]["cats"][rarity] += 1
        save_game()
        await message.reply(f"🎯 **CATCH!** You got a **{rarity}** cat!")
        return # Stop processing this message

    # 4. Handle AI Chat (3 Second Typing Delay)
    if message.channel.id in chat_channels and not message.content.startswith(('!', '/')):
        if message.author.bot: return
        
        async with message.channel.typing():
            # MANDATORY 3 SECOND DELAY
            await asyncio.sleep(3)
            try:
                prompt = "You are Flame, a witty, chill Gen-Z bot. 1 short sentence max. Use slang."
                completion = await groq_client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "system", "content": prompt},
                              {"role": "user", "content": message.clean_content}],
                    max_tokens=60
                )
                response = completion.choices[0].message.content
                if response:
                    await message.reply(response, mention_author=False)
            except: pass
        return # Stop processing this message

    await bot.process_commands(message)

# --- 6. AUTO SPAWNS ---
@tasks.loop(minutes=2)
async def auto_spawn_cat():
    for cid in spawn_channels:
        if cid not in active_spawns and random.random() < 0.40:
            channel = bot.get_channel(cid)
            if channel:
                rarity = random.choices(list(CAT_TYPES.keys()), weights=[60, 25, 10, 5])[0]
                active_spawns[cid] = rarity
                async with aiohttp.ClientSession() as s:
                    async with s.get('https://api.thecatapi.com/v1/images/search') as r:
                        url = (await r.json())[0]['url']
                embed = discord.Embed(title="🐾 A cat appeared!", description="Type `cat`!", color=CAT_TYPES[rarity]['color'])
                embed.set_image(url=url)
                await channel.send(embed=embed)

@bot.event
async def on_ready():
    if not auto_spawn_cat.is_running(): auto_spawn_cat.start()
    await bot.tree.sync()
    print("🔥 Flame AI Live.")

bot.run(TOKEN)
