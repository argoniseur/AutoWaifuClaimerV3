#    AutoWaifuClaimer
#    Copyright (C) 2020 RandomBananazz
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.

#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

from asyncio import TimeoutError
import discord
import sys
import re
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import datetime
from config import config
from classes.browsers import Browser
from classes.timers import Timer
import time

# noinspection PyArgumentList
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(config.LOG_FILE, 'a', 'utf-8'),
        logging.StreamHandler(sys.stdout)
    ])

# Initialize Selenium browser integration in separate module
browser = Browser()

# Declare global timer module
timer: Timer

# Main thread and Discord bot integration here
client = discord.Client()
main_user: discord.User
dm_channel: discord.DMChannel
roll_channel: discord.TextChannel
mudae: discord.Member
ready = False
rolls = []
roll_count = 0

# To be parsed by $tu and used for the auto roller
timing_info = {
    'claim_reset': None,
    'claim_available': None,
    'rolls_reset': None,
    'kakera_available': None,
    'kakera_reset': None,
    'daily_reset': None
}


def validate_parse(message):
    return message.content.split()[1:] if len(message.content.split()) == 3 else None


async def parse_user_message(message):
    if message.content.startswith("$quit"):
        success = await determine_operation(validate_parse(message))

    if message.content.startswith("$set"):
        success = await determine_operation(validate_parse(message))
        if success:
            browser.send_check()

    return


async def determine_operation(*params: str):
    operator, param = params[0][0], int(params[0][1])
    logging.info(f"{operator}, {param}")
    return {
        'roll_count': lambda: timer.set_roll_count(param),
        'auto_roll': lambda: browser.manual_roll(param),
        'rolling': lambda: logging.info("Quitting rolls")
    }.get(operator, lambda: browser.send_x())()


async def go_offline():
    await client.change_presence(status=discord.Status.offline)


async def close_bot():
    await client.close()
    client.loop.stop()
    client.loop.close()
    sys.exit()


@client.event
async def on_ready():
    await go_offline()
    # Ensure the browser is ready before proceeding (blocking call)
    try:
        browser_login.result()
    except TimeoutError or ValueError:
        await close_bot()

    def parse_tu(message):
        logging.info("$tu received")
        global timing_info
        if message.channel != roll_channel or message.author != mudae:
            logging.info("Not from Mudae, or wrong channel")
            return

        # Take the username between the stars and check if we have a can't or can, maybe surrounded by two _
        match_username = re.search(r"""^\*\*(.*)\*\*,\ you\ (?:\_\_)?(can't|can)(?:\_\_)?\ claim""", message.content, re.DOTALL | re.VERBOSE)
        if match_username:
            logging.info("Username: " + match_username.group(1) + " Claim: " + match_username.group(2))

        # Either next claim reset is etc OR can't claim for another etc
        match_claim_reset = re.search(r"""(?:The\ next\ claim\ reset\ is\ in\ |another\ )\*\*(\d+(?:h\ \d+)?)(?=\*\*\ min)""", message.content, re.DOTALL | re.VERBOSE)
        if match_claim_reset:
            logging.info("Claim reset: " + match_claim_reset.group(1))

        # You have X rolls
        match_roll_number = re.search(r"""have\ \*\*([0-9]*)\*\*\ rolls""", message.content, re.DOTALL | re.VERBOSE)
        if match_roll_number:
            logging.info("Number of rolls" + match_roll_number.group(1))

        # Next rolls reset in etc
        match_rolls_reset = re.search(r"""Next\ rolls\ reset\ in\ \*\*(\d+(?:h\ \d+)?)(?=\*\*\ min)""", message.content, re.DOTALL | re.VERBOSE)
        if match_rolls_reset:
            logging.info("Rolls reset: " + match_rolls_reset.group(1))

        # Shamelessly stolen from previous version
        match_daily_reset = re.search(r"""(?<=\$daily).*?(available|\d+h\ \d+)""", message.content, re.DOTALL | re.VERBOSE)
        if match_daily_reset:
            logging.info("Daily reset: " + match_daily_reset.group(1))

        # You can or can't react, with maybe 2 _ before
        match_kakera_available = re.search(r"""You\ (?:\_\_)?(can't|can).*?(?=react)""", message.content, re.DOTALL | re.VERBOSE)
        if match_kakera_available:
            logging.info("Kak available: " + match_kakera_available.group(1))

        # Either now or a timing
        match_kakera_reset = re.search(r"""((now)|(for\ \*\*(\d+(?:h\ \d+)?)(?=\*\*\ min)))""",
                                           message.content, re.DOTALL | re.VERBOSE)
        if match_kakera_available.group(1) == 'can':
            logging.info("Kak reset is " + str(match_kakera_reset.group(1)) + " because you can kak react")
        else:
            logging.info("Kak reset: " + match_kakera_reset.group(1))

        # Shamelessly stolen from previous version
        match_dk_reset = re.search(r"""\$dk.*?(ready|\d+h\ \d+)""", message.content, re.DOTALL | re.VERBOSE)
        if match_dk_reset:
            logging.info("Dk reset: " + match_dk_reset.group(1))

        if match_username.group(1) != main_user.name:
            logging.info("User name doesn't match")
            return
        # Convert __h __ to minutes
        times = []
        for x in [match_claim_reset.group(1), match_rolls_reset.group(1), match_daily_reset.group(1), match_kakera_reset.group(1)]:
            # Specifically, group 7 may be None if kakera is ready
            logging.info(str(x))
            if x is None:
                x = 0
            elif 'h' in x:
                x = x.split('h')
                x = int(x[0]) * 60 + int(x[1])
            elif x == 'ready' or x == 'now' or x == 'available':
                x = 0
            else:
                x = int(x)
            times.append(x)
        kakera_available = match_kakera_available.group(1) == 'can'
        claim_available = match_username.group(2) == 'can'

        timing_info = {
            'claim_reset': datetime.datetime.now() + datetime.timedelta(minutes=times[0]),
            'claim_available': claim_available,
            'rolls_reset': datetime.datetime.now() + datetime.timedelta(minutes=times[1]),
            'kakera_available': kakera_available,
            'kakera_reset': datetime.datetime.now() + datetime.timedelta(minutes=times[3]),
            'daily_reset': datetime.datetime.now() + datetime.timedelta(minutes=times[2]),
            'rolls_at_launch': match_roll_number.group(1)
        }

        return True

    global main_user, mudae, dm_channel, roll_channel, timer, timing_info, ready
    logging.info(f'Bot connected as {client.user.name} with ID {client.user.id}')
    main_user = await client.fetch_user(config.USER_ID)
    dm_channel = await main_user.create_dm()
    roll_channel = await client.fetch_channel(config.CHANNEL_ID)
    mudae = await client.fetch_user(config.MUDAE_ID)

    # Parse timers by sending $tu command
    # Only do so once by checking ready property
    if not ready:
        logging.info('Attempting to parse $tu command... Send $tu command within 60 seconds.')
        try:
            # browser.send_text("tu") # AUTO TU PARSING debug utility
            await client.wait_for('message', check=parse_tu, timeout=60)
        except TimeoutError:
            logging.critical('Could not parse $tu command, quitting (try again)')
            browser.close()
            await close_bot()
        else:
            logging.info('$tu command parsed')
            logging.info('Creating new Timer based on parsed information')
            timer = Timer(browser, timing_info["claim_reset"], timing_info["rolls_reset"], timing_info["daily_reset"],
                          timing_info['claim_available'], timing_info["kakera_reset"], timing_info["kakera_available"], int(timing_info["rolls_at_launch"]))
            browser.send_text("Init")
            time.sleep(2)
            if config.DAILY_DURATION > 0:
                threading.Thread(name='daily', target=timer.wait_for_daily).start()
            if config.ROLL_DURATION > 0:
                threading.Thread(name='roll', target=timer.wait_for_roll).start()
            threading.Thread(name='claim', target=timer.wait_for_claim).start()
            threading.Thread(name='kakera', target=timer.wait_for_kakera).start()

            # For some reason, browser Discord crashes sometime at this point
            # Refresh the page to fix
            browser.refresh()  # Blocking call
            logging.info("Listener is ready")
            ready = True


@client.event
async def on_reaction_add(reaction, user):
    # We check if it's a mudae reaction
    if user == mudae:
        if reaction.message.embeds:
            embed = reaction.message.embeds[0]
            # We check if it's claimed
            if embed.footer.text:
                match = re.search(r'(?<=Belongs to )\w+', embed.footer.text, re.DOTALL)
                if match:
                    # if match, it's a kak reaction.
                    # Necessary to do like this to prevent any trolling with fake reactions
                    if reaction.emoji.name in config.EMOJI_LIST and timer.get_kakera_availability():
                        logging.info(f'Attempting to loot kakera')
                        try:
                            await pool.submit(browser.react_emoji, reaction.emoji.name, reaction.message.id)
                        except TimeoutError:
                            logging.critical('First Kakera loot failed, could not detect bot reaction')
                            try:
                                await pool.submit(browser.react_emoji, reaction.emoji.name, reaction.message.id)
                            except TimeoutError:
                                logging.critical('Second attempt failed. exiting.')
                                return
                            else:
                                await dm_channel.send(content=f"Kakera loot attempted for {reaction.emoji.name}")
                    else:
                        logging.info("Kak was not in list or timer not up, no attempts made")


@client.event
async def on_message(message):
    def parse_embed():
        # Regex based parsing adapted from the EzMudae module by Znunu
        # https://github.com/Znunu/EzMudae
        desc = embed.description
        name = embed.author.name
        series = None
        owner = None
        key = False
        kak = 0

        # Get series and key value if present
        match = re.search(r'^(.*?[^<]*)(?:<:(\w+key))?', desc, re.DOTALL)
        if match:
            series = match.group(1).replace('\n', ' ').strip()
            if len(match.groups()) == 3:
                key = match.group(2)

        # Check if it was a roll
        # Look for stars in embed (Example: **47**)
        match = re.search(r'(?<=\*)(\d+)', desc, re.DOTALL)
        if match:
            kak = match.group(0)

        # Look for picture wheel (Example: 1/31)
        # match = re.search(r'(?<=\d)(\/)', desc, re.DOTALL) doesn't find

        match = re.search(r'(:female:|:male:)', desc, re.DOTALL)
        if match:
            return

        # Check if valid parse
        if not series:
            return

        # Get owner if present
        if not embed.footer.text:
            is_claimed = False
        else:
            match = re.search(r'(?<=Belongs to )\w+', embed.footer.text, re.DOTALL)
            if match:
                is_claimed = True
                owner = match.group(0)
            else:
                is_claimed = False

        # Log in roll list and console/logfile
        with open('waifu_list/rolled.txt', 'a') as f:
            f.write(f'{datetime.datetime.now()}    {name} - {series}\n')

        logging.info(f'Parsed roll: {name} - {series} - Claimed: {is_claimed}')

        return {'name': name,
                'series': series,
                'is_claimed': is_claimed,
                'owner': owner,
                'key': key,
                'kak': kak}

    def reaction_check(payload):
        # Return if reaction message or author incorrect
        if payload.message_id != message.id:
            return
        if payload.user_id != mudae.id:
            return

        # Open thread to click emoji
        emoji = payload.emoji
        pool.submit(browser.react_emoji, emoji.name, message.id)
        return True

    # BEGIN ON_MESSAGE BELOW #
    global main_user, mudae, dm_channel, roll_channel, ready, rolls, roll_count
    if not ready:
        return

    if message.channel == roll_channel and message.author == main_user:
        # User Control
        await parse_user_message(message)

    # Only parse messages from the bot in the right channel that contain a valid embed
    if message.channel != roll_channel or message.author != mudae or not len(message.embeds) == 1 or \
            message.embeds[0].image.url == message.embeds[0].Empty:
        return
    # Check for user input

    embed = message.embeds[0]
    if not (waifu_result := parse_embed()):
        return  # Return if parsing failed
    browser.set_character(waifu_result['name'])

    if not waifu_result['is_claimed']:
        await message.add_reaction("😀")

    # If unclaimed waifu was on likelist
    was_in_array = 0
    if not waifu_result['is_claimed'] and timer.get_claim_availability() and waifu_result['name'] in love_array:
        was_in_array = 1
        if config.CLAIM_METHOD_CLICK:
            await client.wait_for('raw_reaction_add', check=reaction_check, timeout=10)
        else:
            pool.submit(browser.attempt_claim)

        logging.info(f'Character {waifu_result["name"]} in lovelist, attempting marry')
        await dm_channel.send(content=f"{waifu_result['name']} is in the lovelist"
                                      f"Attempted to marry", embed=embed)

    if waifu_result['name'] in like_array and not waifu_result['is_claimed']:
        was_in_array = 1
        await dm_channel.send(content=f"{waifu_result['name']} is in the likelist:"
                                      f"\nhttps://discord.com/channels/{config.SERVER_ID}/{config.CHANNEL_ID}/{message.id}\n")

    if int(waifu_result['kak']) >= config.CLAIM_KAK and was_in_array == 0:
        pool.submit(browser.attempt_claim)
        await dm_channel.send(content=f"{waifu_result['name']} is {waifu_result['kak']} kaks. "
                                      f"Attempted to marry", embed=embed)

    if (waifu_result['name'] not in like_array or love_array) and int(waifu_result['kak']) < config.CLAIM_KAK:
        browser.set_im_state(True)
        if config.TEST_REACT:
            pool.submit(browser.attempt_claim)

    if int(timer.get_tiers()) == 0 and timer.get_claim_availability() and not waifu_result['is_claimed']:
        # It's the last rolls before reset
        logging.info("Added to rolls list")
        rolls.append({
            'message': message,
            'parsed': waifu_result,
            'kak': waifu_result['kak']
        })

    roll_count = roll_count + 1
    if roll_count == config.MAX_ROLLS and rolls: #config.MAX_ROLLS:
        logging.info("Attempt to claim max roll from rolls")
        max_roll = max(rolls, key=lambda x: x['kak'])

        pool.submit(browser.react_emoji, "😀", max_roll['message'].id)
        await dm_channel.send(content=f"{max_roll['name']} is {waifu_result['kak']} kaks"
                                      f"Attempted to marry", embed=max_roll['message'].embeds[0])
        rolls = []
        roll_count = 0

    # Security in case you only roll claimed characters
    if roll_count == config.MAX_ROLLS and not rolls:
        roll_count = 0

    # If key was rolled
    if waifu_result['owner'] == main_user.name and waifu_result['key']:
        await dm_channel.send(content=f"{waifu_result['key']} rolled for {waifu_result['name']}", embed=embed)


if __name__ == '__main__':
    logging.info("Graceful Killer Initialized")
    with open('waifu_list/lovelist.txt', 'r') as f:
        logging.info('Parsing lovelist')
        love_array = tuple(
            {x.strip() for x in [x for x in f.readlines() if not x.startswith('\n')] if not x.startswith('#')})
        logging.info(f'Current lovelist: {love_array}')

    with open('waifu_list/likelist.txt', 'r') as f:
        logging.info('Parsing likelist')
        like_array = tuple(
            {x.strip() for x in [x for x in f.readlines() if not x.startswith('\n')] if not x.startswith('#')})
        logging.info(f'Current likelist: {like_array}')

    pool = ThreadPoolExecutor()
    try:
        logging.info('Starting browser thread')
        browser_login = pool.submit(Browser.browser_login, browser)
        client.loop.run_until_complete(client.start(config.BOT_TOKEN))
    except KeyboardInterrupt or RuntimeError:
        logging.critical("Keyboard interrupt, quitting")
        client.loop.run_until_complete(client.logout())
    except discord.LoginFailure or aiohttp.ClientConnectorError or RuntimeError:
        logging.critical(f"Improper token has been passed or connection to Discord failed, quitting")
    finally:
        browser.close()
        client.loop.stop()
        client.loop.close()
