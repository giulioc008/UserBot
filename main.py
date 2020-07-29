from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncio
import logging as logger
import os
import pymysql
from pyrogram import Client, Filters, Message
from pyrogram.api import functions
from pyrogram.errors import FloodWait
import random
import re
import res
from res import Configurations
import requests
import subprocess
from telegraph import Telegraph

configurations_map = {
	"commands": "commands",
	"database": "database",
	"logger": "logger"
}

loop = asyncio.get_event_loop()

config = Configurations("config/config.json", configurations_map)
loop.run_until_complete(config.parse())
config.set("app_hash", os.environ.pop("app_hash", None))
config.set("app_id", int(os.environ.pop("app_id", None)))
config.set("phone_number", os.environ.pop("phoneNumber", None))
config.set("userbot_username", os.environ.pop("userbot_username", None))

connection = pymysql.connect(
	host=config.get("database")["host"],
	user=os.environ.pop("database_username", config.get("database")["username"]),
	password=os.environ.pop("database_password", config.get("database")["password"]),
	database=config.get("userbot_username"),
	port=config.get("database")["port"],
	charset="utf8",
	cursorclass=pymysql.cursors.DictCursor,
	autocommit=False)

logger.basicConfig(
	filename=config.get("logger")["path"],
	datefmt="%d/%m/%Y %H:%M:%S",
	format=config.get("logger")["format"],
	level=config.get("logger").pop("level", logger.INFO))

minute = 60
scheduler = AsyncIOScheduler()

with connection.cursor() as cursor:
	logger.info("Initializing the Admins ...")
	cursor.execute("SELECT `id` FROM `Admins` WHERE `username`=%(user)s;", {
		"user": "username"
	})
	config.set("creator", cursor.fetchone()["id"])

	logger.info("Admins initializated\nSetting the admins list ...")
	cursor.execute("SELECT `id` FROM `Admins`;")
	admins_list = list(map(lambda n: n["id"], cursor.fetchall()))

	logger.info("Admins setted\nSetting the chats list ...")
	cursor.execute("SELECT `id` FROM `Chats` WHERE `type`!=bot;")
	chats_list = list(map(lambda n: n["id"], cursor.fetchall()))
chats_list.append("me")

logger.info("Chats initializated\nInitializing the Client ...")
app = Client(session_name=config.get("userbot_username"), api_id=config.get("app_id"), api_hash=config.get("app_hash"), phone_number=config.get("phone_number"), lang_code="it", workdir=".", parse_mode="html")


@app.on_message(Filters.command("add", prefixes="/") & (Filters.user(admins_list) | Filters.channel))
async def add_to_the_database(client: Client, message: Message):
	# /add
	global admins_list, chats_list, config, connection

	message.command.pop(0)

	# Checking if the data are of a chat or of a user
	if message.reply_to_message is not None:
		# Checking if the user is in the admins list
		if message.reply_to_message.from_user.id in admins_list:
			await res.split_reply_text(config, message, "The user @{} is already an admin.".format(message.reply_to_message.from_user.username), quote=False)
			logger.info("{} have sent an incorrect /add request.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))
			return

		# Retrieving the data of the new admin
		chat = {
			"id": message.reply_to_message.from_user.id
		}

		# Adding the new admin to the list
		admins_list.append(chat["id"])
	else:
		# Checking if the chat is in the list
		if message.chat.id in chats_list:
			await res.split_reply_text(config, message, "The chat {} is already present in the list of allowed chat.".format(message.chat.title), quote=False)
			logger.info("{} have sent an incorrect /add request.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))
			return

		# Retrieving the data of the chat
		chat = message.chat
		chat = chat.__dict__

		# Deleting the message
		await message.delete(revoke=True)

		# Adding the chat to the list
		chats_list.append(chat["id"])

	# Removing inutil informations
	chat.pop("_client", None)
	chat.pop("_", None)
	chat.pop("photo", None)
	chat.pop("description", None)
	chat.pop("pinned_message", None)
	chat.pop("sticker_set_name", None)
	chat.pop("can_set_sticker_set", None)
	chat.pop("members_count", None)
	chat.pop("restrictions", None)
	chat.pop("permissions", None)
	chat.pop("distance", None)
	chat.pop("status", None)
	chat.pop("last_online_date", None)
	chat.pop("next_offline_date", None)
	chat.pop("dc_id", None)
	chat.pop("is_self", None)
	chat.pop("is_contact", None)
	chat.pop("is_mutual_contact", None)
	chat.pop("is_deleted", None)
	chat.pop("is_bot", None)
	chat.pop("is_verified", None)
	chat.pop("is_restricted", None)
	chat.pop("is_scam", None)
	chat.pop("is_support", None)
	chat.pop("language_code", None)

	with connection.cursor() as cursor:
		if chat.get("type", None) is None:
			# Adding the users to the database
			cursor.execute("INSERT INTO `Admins` (`id`, `first_name`, `last_name`, `username`, `phone_number`) VALUES (%(id)s, %(first_name)s, %(last_name)s, %(username)s, %(phone_number)s);", chat)

			text = "Admin added to the database."
		else:
			# Adding the chats to the database
			cursor.execute("INSERT INTO `Chats` (`id`, `type`, `title`, `username`, `first_name`, `last_name`, `invite_link`) VALUES (%(id)s, %(type)s, %(title)s, %(username)s, %(first_name)s, %(last_name)s, %(invite_link)s);", chat)

			text = "Chat added to the database."
	connection.commit()

	await res.split_reply_text(config, message, text, quote=False)
	logger.info("I\'ve answered to /add because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_callback_query(Filters.user(players_allowed_list))
async def answer_inline_button(client: Client, callback_query: CallbackQuery):
	global config, connection

	# Retrieving the data of the CallbackQuery
	data = callback_query.data.split("!")

	"""
		data[0] is the type of the request
		data[1] is the number of the page
	"""

	# Retrieving the keyboard of the CallbackQuery
	keyboard = callback_query.message.reply_markup.inline_keyboard

	# Retrieving the text of the CallbackQuery
	text = callback_query.message.text

	# Checking if the CallbackQuery have the correct syntax
	if data[0] == "groups":
		data[1] = res.str_to_int(data[1])

		# Retrieving the groups chats
		with connection.cursor() as cursor:
			cursor.execute("SELECT `id`, `title`, `username`, `invite_link` FROM `Chats`;")
			chat = cursor.fetchall().copy()

		chat = sorted(chat, key=lambda n: n["title"])

		chat = chat[data[1] * 6 : (data[1] + 1) * 6]

		# Restructuring the InlineKeyboard
		for i in chat:
			button = await chat_button(client, i, connection)

			keyboard.append([
				button
			])

		keyboard.append([
			InlineKeyboardButton(text="Previous", callback_data="groups!{}".format(data[1] - 1))
			InlineKeyboardButton(text="Next", callback_data="groups!{}".format(data[1] + 1))
		])
	keyboard = InlineKeyboardMarkup(keyboard)

	await output.edit_reply_markup(keyboard)

	logger.info("I have answered to an Inline button.")


@app.on_message(Filters.service)
async def automatic_management_service(_, message: Message):
	global config, connection

	# Checking if the message is a new_chat_members message
	if message.new_chat_members is not None:
		# Retrieving the list of the spammer by Telegram
		to_delete = message.new_chat_members.copy()
		to_delete = list(map(lambda n: n.id, to_delete))

		message.new_chat_members = list(filter(lambda n: n.is_scam is not None and n.is_scam is False, message.new_chat_members))

		for i in message.new_chat_members:
			to_delete.remove(i.id)

		# Retrieving the list of the spammer by Combot Anti Spam
		tmp = message.new_chat_members.copy()

		for i in range(len(tmp)):
			# Downloading the user's informations
			response = requests.get(url="https://api.cas.chat/check?user_id={}".format(tmp[i].id))

			# Retrieving the user's informations
			result = response.json()

			# Checking if it's a spammer
			if result["ok"] is False:
				continue

			to_delete.append(message.new_chat_members.pop(i).id)

		if to_delete is True:
			for i in to_delete:
				await message.chat.kick_member(i.id)

	await message.delete(revoke=True)


@app.on_message(Filters.command("check", prefixes="/") & Filters.user(config.get("creator")))
async def check_database(_, message: Message):
	global admins_list, connection, chats_list

	with connection.cursor() as cursor:
		cursor.execute("SELECT * FROM `Admins`;")
		print("{}\n".format(cursor.fetchall()))
	print("{}\n".format(list(map(lambda n: "\t{} - {}\n".format(n, type(n)), admins_list))))

	with connection.cursor() as cursor:
		cursor.execute("SELECT * FROM `Chats`;")
		print("{}\n".format(cursor.fetchall()))
	print("{}\n".format(list(map(lambda n: "\t{} - {}\n".format(n, type(n)), chats_list))))

	print("\n\n")
	logger.info("I\'ve answered to /check because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("ip", prefixes="/") & Filters.user(config.get("creator")))
async def check_IP(_, message: Message):
	# Retrieve the HTML page that contains the public IP's informations
	response = requests.get(url="http://ip4.me")
	response.raise_for_status()

	# Extracting the IP from the HTML page
	result = re.findall("(.*[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*.*)", response.text)
	result = result.pop(0)
	result = re.findall("(.*[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*)", result)
	result = result.pop(0)
	i = result.rfind(">")
	i += 1
	result = result[i:]

	await res.split_reply_text(config, message, "The IP address of my host service is {}.".format(result), quote=False)

	logger.info("I\'ve answered to /ip because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("eval", prefixes=["/", "!", "."]))
async def evaluation(client: Client, message: Message):
	# /eval
	global config

	message.command.pop(0)

	command = " ".join(message.command)

	result = eval(command)
	text = "<b>Espression:</b>\n\t<code>{}</code>\n\n<b>Result:</b>\n\t<code>{}</code>".format(command, result)

	await res.split_edit_text(config, message, text, quote=False)

	logger.info("I\'ve answered to /eval because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("exec", prefixes=["/", "!", "."]))
async def execution(client: Client, message: Message):
	# /exec
	global config

	message.command.pop(0)

	command = " ".join(message.command)

	if command == "clear":
		os.system(command)

	result = subprocess.check_output(command, shell=True)
	result = result.decode("utf-8")
	result = result.replace("\n", "</code>\n\t<code>")
	text = "<b>Command:</b>\n\t<code>{}</code>\n\n<b>Result:</b>\n\t<code>{}</code>".format(command, result)

	await res.split_edit_text(config, message, text, quote=False)

	logger.info("I\'ve answered to /exec because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("groups", prefixes="/") & Filters.user(players_allowed_list) & Filters.private)
async def groups(_, message: Message):
	# /groups
	global config, connection

	# Retrieving the groups chats
	with connection.cursor() as cursor:
		cursor.execute("SELECT `id`, `title`, `username`, `invite_link` FROM `Chats`;")
		chat = cursor.fetchall().copy()

	chat = sorted(chat, key=lambda n: n["title"])

	chat = chat[: 6]

	# Restructuring the InlineKeyboard
	for i in chat:
		button = await chat_button(client, i, connection)

		keyboard.append([
			button
		])

	keyboard.append([
		InlineKeyboardButton(text="", callback_data=""),
		InlineKeyboardButton(text="Next", callback_data="groups!1")
	])
	keyboard = InlineKeyboardMarkup(keyboard)

	await res.split_reply_text(config, message, "Your groups are:", quote=False, reply_markup=keyboard)
	logger.info("I\'ve answered to /groups because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("help", prefixes="/") & Filters.user(players_allowed_list) & Filters.private)
async def help(_, message: Message):
	# /help
	global admins_list, config

	commands = config.get("commands")

	# Filter the commands list in base at their domain
	if message.from_user.id != config.get("creator"):
		commands = list(filter(lambda n: n["domain"] != "creator", commands))
	if message.from_user.id not in admins_list:
		commands = list(filter(lambda n: n["domain"] != "exarch", commands))

	await res.split_reply_text(config, message, "In this section you will find the list of the command of the UserBot.\n\t{}".format("\n\t".join(list(map(lambda n: "<code>/{}{}</code> - {}".format(n["name"], " {}".format(n["parameters"]) if n["parameters"] != "" else n["parameters"], n["description"])), commands))), quote=False)

	logger.info("I\'ve answered to /help because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("init", prefixes="/") & Filters.user(admins_list) & Filters.private)
async def initializing(client: Client, _):
	# /init
	global config, scheduler

	# Scheduling the functions
	scheduler.add_job(update, IntervalTrigger(days=1, timezone="Europe/Rome"), kwargs={
		"client": client,
		"message": None
	})

	# Setting the maximum message length
	max_length = await client.send(functions.help.GetConfig())
	config.set("message_max_length", max_length.message_length_max)

	# Retrieving the UserBot id
	userbot = await client.get_users(config.get("userbot_username"))
	config.set("userbot_id", userbot.id)

	logger.info("I\'ve answered to /init because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(Filters.command("remove", prefixes="/") & (Filters.user(admins_list) | Filters.channel))
async def remove_from_the_database(client: Client, message: Message):
	# /remove
	global admins_list, chats_list, config

	# Checking if the data are of a chat or of a user
	if message.reply_to_message is not None:
		# Checking if the user is authorized
		if message.reply_to_message.from_user.id not in admins_list:
			await res.split_reply_text(config, message, "You can\'t remove an admin that doesn't exists.", quote=False)
			logger.info("{} have sent an incorrect /remove request.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))
			return

		# Retrieving the data of the admin
		chat = message.reply_to_message.from_user

		# Removing the admin from the list
		admins_list.remove(chat.id)
	else:
		# Checking if the chat is in the list
		if message.chat.id not in chats_list:
			await res.split_reply_text(config, message, "The chat {} isn\'t present in the list of allowed chat.".format(message.chat.title), quote=False)
			logger.info("{} have sent an incorrect /remove request.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))
			return

		# Retrieving the data of the chat
		chat = message.chat

		# Deleting the message
		await message.delete(revoke=True)

		# Removing the chat from the list
		chats_list.remove(chat.id)

	# Removing the chat/user from the database
	with connection.cursor() as cursor:
		text = "Chat removed from the database."

		if cursor.execute("DELETE FROM `Chats` WHERE `id`=%(id)s;", {
			"id": chat.id
		}) == 0:
			cursor.execute("DELETE FROM `Admins` WHERE `id`=%(id)s;", {
				"id": chat.id
			})

			text = "Admin removed from the database."
	connection.commit()

	await res.split_reply_text(config, message, text, quote=False)
	logger.info("I\'ve answered to /remove because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


@app.on_message(res.unknown_filter(config) & Filters.private)
async def unknown(_, message: Message):
	global config

	await res.split_reply_text(config, message, "This command isn\'t supported.", quote=False)
	logger.info("I managed an unsupported command.")


@app.on_message(Filters.command("update", prefixes="/") & Filters.user(config.get("creator")) & Filters.private)
async def update(client: Client, message: Message = None):
	# /update
	global admins_list, chats_list, connection

	chats = await client.get_users(admins_list)

	# Retrieving the list of deleted accounts
	to_delete = chats.copy()
	to_delete = list(map(lambda n: n.id, to_delete))

	chats = list(filter(lambda n: n.is_deleted is not None and n.is_deleted is False, chats))
	chats = list(filter(lambda n: n.is_scam is not None and n.is_scam is False, chats))

	for i in chats:
		to_delete.remove(i.id)

	# Retrieving the list of the spammer by Combot Anti Spam
	tmp = chats.copy()

	for i in range(len(tmp)):
		# Downloading the user's informations
		response = requests.get(url="https://api.cas.chat/check?user_id={}".format(tmp[i].id))

		# Retrieving the user's informations
		result = response.json()

		# Checking if it's a spammer
		if result["ok"] is False:
			continue

		to_delete.append(chats.pop(i).id)

	chats = list(map(lambda n: n.__dict__, chats))

	with connection.cursor() as cursor:
		# Removing inutil informations
		for i in to_delete:
			cursor.execute("DELETE FROM `Admins` WHERE `id`=%(id)s;", {
				"id": i
			})

		for i in chats:
			# Removing inutil informations
			i.pop("_client", None)
			i.pop("_", None)
			i.pop("photo", None)
			i.pop("restrictions", None)
			i.pop("status", None)
			i.pop("last_online_date", None)
			i.pop("next_offline_date", None)
			i.pop("dc_id", None)
			i.pop("is_self", None)
			i.pop("is_contact", None)
			i.pop("is_mutual_contact", None)
			i.pop("is_deleted", None)
			i.pop("is_bot", None)
			i.pop("is_verified", None)
			i.pop("is_restricted", None)
			i.pop("is_scam", None)
			i.pop("is_support", None)
			i.pop("language_code", None)

			# Updating the database
			cursor.execute("UPDATE `Admins` SET `first_name`=%(first_name)s, `last_name`=%(last_name)s, `username`=%(username)s, `phone_number`=%(phone_number)s WHERE `id`=%(id)s;", i)
	connection.commit()

	chats = list()
	for i in chats_list:
		try:
			chats.append(await client.get_chat(i))
		except FloodWait as e:
			await asyncio.sleep(e.x)

	chats = list(map(lambda n: n.__dict__, chats))

	with connection.cursor() as cursor:
		for i in chats:
			# Removing inutil informations
			i.pop("_client", None)
			i.pop("_", None)
			i.pop("photo", None)
			i.pop("description", None)
			i.pop("pinned_message", None)
			i.pop("sticker_set_name", None)
			i.pop("can_set_sticker_set", None)
			i.pop("members_count", None)
			i.pop("restrictions", None)
			i.pop("permissions", None)
			i.pop("distance", None)
			i.pop("is_verified", None)
			i.pop("is_restricted", None)
			i.pop("is_scam", None)
			i.pop("is_support", None)

			# Updating the database
			cursor.execute("UPDATE `Chats` SET `type`=%(type)s, `title`=%(title)s, `username`=%(username)s, `first_name`=%(first_name)s, `last_name`=%(last_name)s, `invite_link`=%(invite_link)s WHERE `id`=%(id)s;", i)
	connection.commit()

	for i in chats_list:
		# Retrieving the list of chat members
		members = await client.iter_chat_members(i)
		members = list(members)

		# Retrieving the users from the list
		members = list(map(lambda n: n.user, members))

		members = list(filter(lambda n: n.is_bot is not None and n.is_bot is False, members))

		# Retrieving the list of deleted accounts
		to_delete = members.copy()
		to_delete = list(map(lambda n: n.id, to_delete))

		members = list(filter(lambda n: n.is_deleted is not None and n.is_deleted is False, members))
		members = list(filter(lambda n: n.is_scam is not None and n.is_scam is False, members))
		members = list(map(lambda n: n.id, members))

		for j in members:
			to_delete.remove(j)

		# Retrieving the list of the spammer by Combot Anti Spam
		tmp = members.copy()

		for i in range(len(tmp)):
			# Downloading the user's informations
			response = requests.get(url="https://api.cas.chat/check?user_id={}".format(tmp[i].id))

			# Retrieving the user's informations
			result = response.json()

			# Checking if it's a spammer
			if result["ok"] is False:
				continue

			to_delete.append(members.pop(i).id)

		# Removing inutil informations
		if to_delete is True:
			for j in to_delete:
				await message.chat.kick_member(j)

	logger.info("I\'ve answered to /update because of {}.".format("@{}".format(message.from_user.username) if message.from_user.username is not None else message.from_user.id))


logger.info("Client initializated\nStarted serving ...")
scheduler.start()
app.run()
connection.close()
