import re
import os
import json
import openai
import discord
import logging
import requests
from collections import deque
from discord.ext import commands

script_dir = os.path.dirname(os.path.realpath(__file__))
openai.api_base = "Your provider API base(optional if you use OpenAI api)"

config_path = os.path.join(script_dir, 'config.json')
with open(config_path) as config_file:
    config = json.load(config_file)

logger = logging.getLogger('discord')

openai.api_key = config["openai_api_key"]

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix=".", intents=intents)

history = deque()
history_length = 0

context = config["context"]

global_personality = config["global_personality"]


def get_user(user):
    for entry in context:
        if entry["discord_name"].lower() == user.lower():
            return entry
    return None


def get_messages(sender, recipient, message):
    sender = sender.lower()
    sender_role = "assistant" if sender == "assistant" else "user"
    role = recipient.lower() if sender == "assistant" else sender

    user = get_user(role)
    personality = user['personality'] if user else config["global_personality"]

    bot_context = config["system_context"]

    system_role = {"role": "system", "content": f"{bot_context}."}

    prefix = '' if sender_role == 'assistant' else f"{personality}"
    add_message({"role": sender_role, "content": f"{prefix} {message}"})

    return [
        system_role,
        *[{"role": obj['role'], "content": obj['content']} for obj in history]
    ]


async def generate_response(message):
    try:
        if message.author == bot.user:
            return

        def call_openai_api():
            logger.info('Звоню на Апишник')
            return openai.ChatCompletion.create(
                model=config["model"],
                messages=get_messages(message.author.name, 'assistant', message.content),

                temperature=0.7
                
            )

        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="Говорит с " + message.author.name))
        async with message.channel.typing():
            logger.info(message.author.name + ": " + message.content)
            response = await bot.loop.run_in_executor(None, call_openai_api)
            content = response['choices'][0]['message']['content']
            await message.reply(content)
            get_messages('assistant', message.author.name, content)
            logger.info("Assistant: " + content)
            logger.info("Токены: " + str(response["usage"]["total_tokens"]))

    except Exception as e:
        message.reply(config["error_message"])
        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=config["presence"]))
        logging.error(f"Ошибка генерации: {e}", exc_info=True)


def add_message(message):
    global history_length
    message_length = len(str(message))
    logger.info(f'Добавляю {message_length} символов в историю')

    while history_length > config["memory_characters"]:
        oldest_message = history.popleft()
        history_length -= len(str(oldest_message))
        logger.info(f'Удаляю собщение из истории, количество символов:{history_length}')

    history.append(message)
    history_length += message_length
    logger.info(f'Добавил сообщение в историю, количество символов: {history_length}')


@bot.listen()
async def on_ready():
    logger.info(f'Залогинился как {bot.user} (Айди: {bot.user.id})')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=config["presence"]))


@bot.listen()
async def on_message(message):
   # if '@here' in message.content:
      #  return
   # if '@everyone' in message.content:
      #  return
    if message.content.startswith(f'<@{bot.user.id}>') or bot.user.mentioned_in(message):
        message.content = message.content.replace(f'<@{bot.user.id}>', '').strip()

        message.content = f'{message.author.name}: {message.content}'
        await generate_response(message)

def write_char(data):
    with open("config.json", "w", encoding="utf-8") as f: 
       json.dump(data, f, indent=4, ensure_ascii=False)



@bot.listen()
async def on_message(message):
    if message.content.startswith(".промпт"):
        try:
            with open("config.json") as personality:
                data = json.load(personality)
                temp = data["context"]
                for entry in temp:
                    if "discord_name" in entry and entry["discord_name"] == message.author.name:
                        entry["personality"] = message.content[len(".промпт"):].strip()
                        break
                else:
                    y = {"discord_name": message.author.name, "personality": message.content[len(".промпт"):].strip()}
                    temp.append(y)
                write_char(data)
                await message.channel.send("Сработало")
        except Exception as e:
            await message.channel.send(f"Произошла ошибка: {e}")

@bot.listen()
async def on_command_error(ctx, error):
  print(f'Ошибка {type(error).__name__}: {error}')

bot.run(config["discord_token"])
