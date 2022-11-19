import discord # It's dangerous to go alone! Take this. /ref
from discord import app_commands # v2.0, use slash commands
from discord.ext import commands # required for client bot making

import pymongo # for online database
from pymongo import MongoClient

import sys # kill switch for messagerater (search for :kill)

from datetime import datetime, timedelta
from time import mktime # for unix time code, tracking how often guilds were updated
from utils import *

mongoURI = open("mongo.txt","r").read()
cluster = MongoClient(mongoURI)
RaterDB = cluster["RaterDB"]

version = "1.0.0"

intents = discord.Intents.default()
intents.message_content = True
intents.emojis_and_stickers = True
intents.guilds = True


class Bot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    logChannel: discord.TextChannel

client = Bot(
        intents = intents,
        command_prefix = "/!\"@:\\#", #unnecessary, but needs to be set so.. uh.. yeah. Unnecessary terminal warnings avoided.
        case_insensitive=True,
        # activity = discord.Game(name="with slash (/) commands!"),
        allowed_mentions = discord.AllowedMentions(everyone = False)
    )


@client.event
async def on_ready():
    print(f"[#] Logged in as {client.user}, in version {version}")#,color="green")
    # await client.logChannel.send(f":white_check_mark: **Started ChannelTracker** in version {version}")

@client.event
async def setup_hook():
    client.RaterDB = RaterDB

@client.tree.command(name="update",description="Update slash-commands")
async def updateCmds(itx: discord.Interaction):
    if not isAdmin(itx):
        await itx.response.send_message("You don't have the right role to be update the slash commands! (to prevent ratelimiting)",ephemeral=True) #todo
        return
    await client.tree.sync()
    # commandList = await client.tree.fetch_commands()
    # client.commandList = commandList
    await itx.response.send_message("Updated commands")

messageIdMarkedForDeletion = []


async def updateStat(star_message, starboard_emoji):
    # find original message
    text = star_message.embeds[0].fields[0].value ## "[Jump!]({msgLink})"
    link = text.split("(")[1][:-1]
    #    https: 0 / 1 / discord.com 2 / channels 3 / 985931648094834798 4 / 1006682505149169694 5 / 1014887159485968455 6
    guild_id, channel_id, message_id = [int(i) for i in link.split("/")[4:]]
    try:
        ch = client.get_channel(channel_id)
        original_message = await ch.fetch_message(message_id)
    except discord.NotFound:
        # if original message removed, remove starboard message
        await logMsg(star_message.guild, f"{starboard_emoji} :x: Starboard message {star_message.id} was removed (from {message_id}) (original message could not be found)")
        messageIdMarkedForDeletion.append(star_message.id)
        await star_message.delete()
        return

    # star_stat_message = 0
    # reactionTotal = 0
    # # get message stars excluding Rina's
    # for reaction in original_message.reactions:
    #     try:
    #         if str(reaction.emoji) == starboard_emoji:
    #             star_stat_message += reaction.count
    #             if reaction.me:
    #                 star_stat_message -= 1
    #     except AttributeError: #is not a custom emoji
    #         pass
    #
    # star_stat_starboard = 0
    # # get starboard stars excluding Rina's
    # for reaction in star_message.reactions:
    #     try:
    #         if str(reaction.emoji) == starboard_emoji:
    #             star_stat_starboard += reaction.count
    #             if reaction.me:
    #                 star_stat_starboard -= 1
    #     except AttributeError: #is not a custom emoji
    #         pass
    #
    # if star_stat_starboard > star_stat_message:
    #     star_stat = star_stat_starboard
    # else:
    #     star_stat = star_stat_message
    #
    # for reaction in star_message.reactions:
    #     if reaction.emoji == '❌':
    #         reactionTotal = star_stat + reaction.count - 1 # stars (exc. rina) + x'es - rina's x
    #         star_stat -= reaction.count
    #         if reaction.me:
    #             star_stat += 1
    #
    # #if more x'es than stars, and more than 15 reactions, remove message
    # if star_stat < 0 and reactionTotal > 10:
    #     await logMsg(star_message.guild, f"{starboard_emoji} :x: Starboard message {star_message.id} was removed (from {message_id}) (too many downvotes! Score: {star_stat}, Votes: {reactionTotal})")
    #     await star_message.delete()
    #     return
    #
    # # update message to new star value
    # parts = star_message.content.split("**")
    # parts[1] = str(star_stat)
    # new_content = '**'.join(parts)
    # await star_message.edit(content=new_content)

@client.event
async def on_raw_reaction_add(payload):
    if payload.member.id == client.user.id:
        return

    #get the message id from payload.message_id through the channel (with payload.channel_id) (oof lengthy process)
    ch = client.get_channel(payload.channel_id)
    message = await ch.fetch_message(payload.message_id)

    collection = RaterDB["guild_info"]
    query = {"guild_id": message.guild.id}
    guild = collection.find_one(query)
    if guild is None:
        # can't send logging message, because we have no clue what channel that's supposed to be Xd
        debug("Not enough data is configured to work with the starboard. Please fix this with `/config`!",color="red")
        return
    try:
        _star_channel = guild["starboard_channel"]
        _rated_channel = guild["rated_channel"]
        star_minimum = guild["starboard_min_upvotes"]
        starboard_emoji = guild["starboard_emoji"]
        starboard_embed_color = guild["starboard_embed_color"]
        starboard_caption = guild["starboard_caption"]
        starboard_image_only = guild["starboard_image_only"]
        starboard_upvote_emoji = guild["starboard_upvote_emoji"]
        starboard_downvote_emoji = guild["starboard_downvote_emoji"]
        allow_downvotes = guild["starboard_allow_downvotes"]
    except KeyError:
        raise KeyError("Not enough data is configured to do add an item to the starboard! Please fix this with `/config`!")
    star_channel = client.get_channel(_star_channel)
    rated_channel = client.get_channel(_rated_channel)

    if message.channel.id == star_channel.id:
        await updateStat(message, starboard_emoji)
        return
    if message.channel.id != rated_channel.id:
        return

    for reaction in message.reactions:
        try:
            reaction.emoji
        except AttributeError:
            return
        if str(reaction.emoji) == starboard_emoji:
            if reaction.me:
                # check if this message is already in the starboard. If so, update it
                async for star_message in star_channel.history(limit=200):
                    for embed in star_message.embeds:
                        if embed.footer.text == str(message.id):
                            await updateStat(star_message, starboard_emoji)
                            return
                return
            elif reaction.count == star_minimum:
                if message.author == client.user:
                    #can't starboard Rina's message
                    return
                for attachment in message.attachments:
                    if attachment.height:
                        # is image or video
                        break #skips the for-loop's "else" statement, thus continuing the function
                else:
                    if starboard_image_only:
                        return

                msgLink = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"
                embed = discord.Embed(
                        color=discord.Colour.from_rgb(r=starboard_embed_color[0], g=starboard_embed_color[1], b=starboard_embed_color[2]),
                        title='',
                        description=f"{message.content}",
                        timestamp=datetime.now()
                    )
                embed.add_field(name="Source", value=f"[Jump!]({msgLink})")
                embed.set_footer(text=f"{message.id}")
                for attachment in message.attachments:
                    if attachment.height: #is image or video
                        embed.set_image(url=attachment.url)
                        break
                        # can only set one image per embed.. :/
                try:
                    name = message.author.nick
                except AttributeError:
                    name = message.author.name
                embed.set_author(
                        name=f"{name}",
                        url="https://amitrans.org/", #todo
                        icon_url=message.author.display_avatar.url
                )

                msg = await star_channel.send(
                        starboard_caption,
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                await logMsg(star_channel.guild, f"{starboard_emoji} Starboard message {msg.jump_url} was created from {message.jump_url}. Content: \"\"\"{message.content}\"\"\" and attachments: {[x.url for x in message.attachments]}")
                # add initial star reaction to starboarded message, and new starboard msg
                # add star reaction to original message to prevent message from being re-added to the starboard
                await message.add_reaction(starboard_emoji)
                await msg.add_reaction(starboard_upvote_emoji)
                if allow_downvotes:
                    await msg.add_reaction(starboard_downvote_emoji)

@client.event
async def on_raw_reaction_remove(payload):
    #get the message id from payload.message_id through the channel (with payload.channel_id) (oof lengthy process)
    ch = client.get_channel(payload.channel_id)
    message = await ch.fetch_message(payload.message_id)

    collection = RaterDB["guild_info"]
    query = {"guild_id": message.guild.id}
    guild = collection.find_one(query)
    if guild is None:
        # can't send logging message, because we have no clue what channel that's supposed to be Xd
        debug("Not enough data is configured to work with the starboard! Please fix this with `/config`!",color="red")
        return
    try:
        _star_channel = guild["starboard_channel"]
        _rated_channel = guild["rated_channel"]
        starboard_emoji = guild["starboard_emoji"]
    except KeyError:
        raise KeyError("Not enough data is configured to .. remove a star from an item on the starboard because idk what channel i need to look in! Please fix this with `/config`!")
    star_channel = client.get_channel(_star_channel)
    rated_channel = client.get_channel(_rated_channel)

    if message.channel.id == star_channel.id:
        await updateStat(message, starboard_emoji)
        return
    if message.channel.id != rated_channel.id:
        return

    for reaction in message.reactions:
        if str(reaction.emoji) == starboard_emoji:
            if reaction.me:
                # check if this message is already in the starboard. If so, update it
                async for star_message in star_channel.history(limit=500):
                    for embed in star_message.embeds:
                        if embed.footer.text == str(message.id):
                            await updateStat(star_message, starboard_emoji)
                            return

@client.event
async def on_raw_message_delete(message_payload):
    collection = RaterDB["guild_info"]
    query = {"guild_id": message_payload.guild_id}
    guild = collection.find_one(query)
    if guild is None:
        debug("Not enough data is configured to work with the starboard! Please fix this with `/config`!",color="red")
        return
    try:
        _star_channel = guild["starboard_channel"]
        starboard_emoji = guild["starboard_emoji"]
    except KeyError:
        raise KeyError("Not enough data is configured to .. check starboard for a message matching the deleted message's ID, because idk what channel i need to look in! Please fix this with `/config`!")
    star_channel = client.get_channel(_star_channel)

    if message_payload.message_id in messageIdMarkedForDeletion: #global variable
        messageIdMarkedForDeletion.remove(message_payload.message_id)
        return
    if message_payload.channel_id == star_channel.id:
        # check if the deleted message is a starboard message; if so, log it at starboard message deletion
        await logMsg(star_channel.guild, f"{starboard_emoji} :x: Starboard message was removed (from {message_payload.message_id}) (Starboard message was deleted manually).")
        return
    elif message_payload.channel_id != star_channel.id:
        # check if this message's is in the starboard. If so, delete it
        async for star_message in star_channel.history(limit=400):
            for embed in star_message.embeds:
                if embed.footer.text == str(message_payload.message_id):
                    try:
                        image = star_message.embeds[0].image.url
                    except AttributeError:
                        image = ""
                    try:
                        msg_link = str(message_payload.message_id)+"  |  "+(await client.get_channel(message_payload.channel_id).fetch_message(message_payload.message_id)).jump_url
                    except discord.NotFound:
                        msg_link = str(message_payload.message_id)+" (couldn't get jump link)"
                    await logMsg(star_channel.guild, f"{starboard_emoji} :x: Starboard message {star_message.id} was removed (from {msg_link}) (original message was removed (this starboard message's linked id matched the removed message's)). Content: \"\"\"{star_message.embeds[0].description}\"\"\" and attachment: {image}")
                    await star_message.delete()
                    return

@client.tree.command(name="config",description="Edit message rater settings (staff only)")
@app_commands.choices(mode=[
    discord.app_commands.Choice(name='Rated channel (which channel do I look in?)', value=1),
    discord.app_commands.Choice(name="Log (which channel logs the starboarded messages?)", value=2),
    discord.app_commands.Choice(name='Starboard channel (Where are starboard messages sent?)', value=3),
    discord.app_commands.Choice(name='Star minimum (How many stars should a message get before starboarded', value=4),
    discord.app_commands.Choice(name='Starboard emoji (What emoji do you need to react with to starboard it)', value=5),
    discord.app_commands.Choice(name='Upvote emoji (What emoji do you need to react with to upvote a starboarded message)', value=6),
    discord.app_commands.Choice(name='Downvote emoji (What emoji do you need to react with to downvote a starboarded message)', value=7),
    discord.app_commands.Choice(name='AllowDownvotes (Do you want downvotes to be added/have a function in messages?', value=8),
    discord.app_commands.Choice(name='ImageOnly (Do you want non-images/non-attachment to be starboarded?)', value=9),
    discord.app_commands.Choice(name='Message caption (What do you want to say at the top of the starboard message embed?)', value=10),
    discord.app_commands.Choice(name='Embed color (What color do you want the embed to be?)', value=11),
])
@app_commands.describe(mode="What mode do you want to use?",
                       value="Fill in the value/channel-id of the thing/channel you want to edit")
async def config(itx: discord.Interaction, mode: int, value: str):
    if not isAdmin(itx):
        await itx.response.send_message("You don't have the right role to be able to execute this command! (sorrryyy)",ephemeral=True) #todo
        return

    query = {"guild_id": itx.guild_id}
    collection = RaterDB["guild_info"]

    modes = [
        "", #0
        "rated channel", #1
        "log", #2
        "starboard channel", #3
        "star minimum", #4
        "starboard emoji", #5
        "upvote emoji", #6
        "downvote emoji", #7
        "allow downvotes", #8
        "image only", #9
        "message caption", #10
        "embed color", #11
    ]
    mode = modes[mode]
    warning = ""

    async def format(value, type, error_msg=None):
        if type is int:
            try:
                return int(value)
            except ValueError:
                pass
        elif type is float:
            try:
                return float(value)
            except ValueError:
                pass
        elif type is bool:
            true = ["true","1","yes","y","apply","allow","stroue","correct"]
            if value.lower() in true:
                return True
            return False

        if error_msg is not None:
            await itx.response.send_message(error_msg, ephemeral=True)
            return None

    if mode   == "rated channel":
        if value is not None:
            value = await format(value, int, error_msg="You have to give a numerical ID for the channel you want to use!")
            if value is None:
                return
            ch = client.get_channel(value)
            if type(ch) is not discord.TextChannel:
                await itx.response.send_message(f"The ID you gave wasn't for the type of channel I was looking for! (Need <class 'discord.TextChannel'>, got {type(ch)})", ephemeral=True)
                return
            collection.update_one(query, {"$set": {"rated_channel": ch.id}}, upsert=True)
            value = ch.id
    elif mode == "log":
        if value is not None:
            value = await format(value, int, error_msg="You have to give a numerical ID for the channel you want to use!")
            if value is None:
                return
            ch = client.get_channel(value)
            if type(ch) is not discord.TextChannel:
                await itx.response.send_message(f"The ID you gave wasn't for the type of channel I was looking for! (Need <class 'discord.TextChannel'>, got {type(ch)})", ephemeral=True)
                return
            collection.update_one(query, {"$set": {"log_channel": ch.id}}, upsert=True)
            value = ch.id
    elif mode == "starboard channel":
        if value is not None:
            value = await format(value, int, error_msg="You have to give a numerical ID for the channel you want to use!")
            if value is None:
                return
            ch = client.get_channel(value)
            if type(ch) is not discord.TextChannel:
                await itx.response.send_message(f"The ID you gave wasn't for the type of channel I was looking for! (Need <class 'discord.TextChannel'>, got {type(ch)})", ephemeral=True)
                return
            collection.update_one(query, {"$set": {"starboard_channel": ch.id}}, upsert=True)
            value = ch.id
    elif mode == "star minimum":
        if value is not None:
            value = await format(value, int, error_msg="You need to give an integer value for your new minimum amount!")
            if value is None:
                return
            collection.update_one(query, {"$set": {"starboard_min_upvotes": value}}, upsert=True)
    elif mode == "starboard emoji":
        if value is not None:
            if ":" in value:
                try:
                    value = value.split(":")[2][:-1] #get ID of emoji
                except IndexError:
                    await itx.response.send_message("You have to give the emoji or numerical ID of the emoji you want to use!",ephemeral=True)
                    return

            try:
                value = int(value)
            except ValueError:
                pass
            emoji = client.get_emoji(value)
            if emoji is None:
                warning += "This emoji might not exist! Are you sure you filled in a correct ID? Ignore this warning if you used a unicode emoji.\n"
            else:
                value = emoji
            collection.update_one(query, {"$set": {"starboard_emoji": str(value)}}, upsert=True)
    elif mode == "upvote emoji":
        if value is not None:
            if ":" in value:
                try:
                    value = value.split(":")[2][:-1] #get ID of emoji
                except IndexError:
                    await itx.response.send_message("You have to give the emoji or numerical ID of the emoji you want to use!",ephemeral=True)
                    return

            try:
                value = int(value)
            except ValueError:
                pass
            emoji = client.get_emoji(value)
            if emoji is None:
                warning += "This emoji might not exist! Are you sure you filled in a correct ID or emoji? Ignore this warning if you used a unicode emoji.\n"
            else:
                value = emoji
            collection.update_one(query, {"$set": {"starboard_upvote_emoji": str(value)}}, upsert=True)
    elif mode == "downvote emoji":
        if value is not None:
            if ":" in value:
                try:
                    value = value.split(":")[2][:-1]  # get ID of emoji ["<a","name","123456789>"]
                except IndexError:
                    await itx.response.send_message("You have to give the emoji or numerical ID of the emoji you want to use!", ephemeral=True)
                    return


            try:
                value = int(value)
            except ValueError:
                pass
            emoji = client.get_emoji(value)
            if emoji is None:
                warning += "This emoji might not exist! Are you sure you filled in a correct ID? Ignore this warning if you used a unicode emoji.\n"
            else:
                value = emoji
            collection.update_one(query, {"$set": {"starboard_downvote_emoji": str(value)}}, upsert=True)
    elif mode == "allow downvotes":
        if value is not None:
            value = await format(value, bool)
            collection.update_one(query, {"$set": {"starboard_allow_downvotes": value}}, upsert=True)
    elif mode == "image only":
        if value is not None:
            value = await format(value, bool)
            collection.update_one(query, {"$set": {"starboard_image_only": value}}, upsert=True)
    elif mode == "message caption":
        if value is not None:
            collection.update_one(query, {"$set": {"starboard_caption": value}}, upsert=True)
    elif mode == "embed color":
        if value is not None:
            _colors = value.split(",")
            if len(_colors) != 3:
                await itx.response.send_message("You must use the following layout: \"rrr, ggg, bbb\" like \"127, 0, 255\"! (where rrr is red a number value from 0-255)")
            colors = []
            for _color in _colors:
                color = await format(_color.strip(), int, error_msg="You must use the following layout: \"rrr, ggg, bbb\" like \"127, 0, 255\"! (where rrr is red a number value from 0-255)\n" +
                                                                    f'"{_color}" is not an integer!')
                if color is None:
                    return None
                colors.append(color)
            collection.update_one(query, {"$set": {"starboard_embed_color": colors}}, upsert=True)
            value = colors

    await itx.response.send_message(warning+f"Edited value of '{mode}' to '{value}' successfully.",ephemeral=True)

async def on_message(message):
    # kill switch, see cmd_addons for other on_message events.
    if message.author.id == 262913789375021056:
        if message.content == ":kill all the starboards.":
            sys.exit(0)

try:
    client.run(open('token.txt',"r").read())
except SystemExit:
    print("Exited the program forcefully using the kill switch")
