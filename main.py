import discord
from discord.ext import commands
import random
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(intents=intents)

count = 0
COUNT_CHANNEL_ID = 123456789  # change later

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.sync_commands()

@bot.event
async def on_message(message):
    global count

    if message.author.bot:
        return

    await message.channel.send("👀 I saw that")

    if message.channel.id == COUNT_CHANNEL_ID:
        if message.content.isdigit():
            num = int(message.content)
            if num == count + 1:
                count += 1
            else:
                await message.channel.send("❌ Wrong number! Restart from 1")
                count = 0

    await bot.process_commands(message)

@bot.slash_command(name="avatar")
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.respond(member.display_avatar.url)

@bot.slash_command(name="riddle")
async def riddle(ctx):
    riddles = [
        ("What has keys but can't open locks?", "A piano"),
        ("What gets wetter the more it dries?", "A towel"),
    ]
    q, a = random.choice(riddles)
    await ctx.respond(f"{q}\nAnswer: {a}")

bot.run(os.getenv("TOKEN"))
