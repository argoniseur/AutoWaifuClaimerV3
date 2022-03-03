import datetime
import logging
import time
from config import config
# import random

launch = True


class Timer:
    """
    Class to facilitate auto rolling on a timer.
    browser: browsers.Browser
        Browser to control.
    next_claim: datetime.datetime
        Time of next claim.
    next_roll: datetime.datetime
        Time of next roll.
    next_daily: datetime.datetime
        Time of next daily, or current time if it is ready.
    roll_count: int
        Number of times to roll.
    claim_available: bool
        Whether a claim is currently available or not.
    next_kakera: datetime.datetime
        Time of next kakera, or current time if it is ready.
    kakera_available: bool
        Whether a kakera loot is currently available or not.
    """

    def __init__(self, browser, next_claim, next_roll, next_daily, claim_available, next_kakera, kakera_available, rolls_at_launch):
        self.browser = browser
        self.claim_timer = next_claim
        self.roll_timer = next_roll
        self.daily_timer = next_daily
        self.claim_available = claim_available
        self.kakera_available = kakera_available
        self.kakera_timer = next_kakera
        self.roll_count = config.MAX_ROLLS
        self.daily_duration = config.DAILY_DURATION
        self.claim_duration = config.CLAIM_DURATION
        self.time_to_roll = config.TIME_TO_ROLL  # if not config.RANDOM_TIME else random.choice(list(range(5,25)))
        self.roll_duration = config.ROLL_DURATION
        self.kakera_duration = config.KAKERA_DURATION
        self.logger = logging.getLogger(__name__)
        self.logger.info('Timer created')
        self.logger.info(f'Claim is {"available" if claim_available else "unavailable"}')
        self.logger.info(f'Kakera loot is {"available" if kakera_available else "unavailable"}')
        self.roll_count = rolls_at_launch

    def get_claim_availability(self):
        return self.claim_available

    def set_roll_count(self, count: int):
        self.roll_count = count

    def get_roll_count(self):
        return self.roll_count

    def set_roll_timer(self, timer: int):
        self.roll_timer = timer

    def get_roll_timer(self):
        return self.roll_timer

    def set_claim_availability(self, available: bool):
        self.claim_available = available

    def get_kakera_availability(self):
        return self.kakera_available

    def set_kakera_availability(self, available: bool):
        self.kakera_available = available

    def wait_for_roll(self):
        global launch
        while True:
            hour = 3600  # Testing
            minute = 60
            end_of_interval = hour - (minute * self.time_to_roll)
            time_to_sleep = (end_of_interval + (self.roll_timer - datetime.datetime.now()).total_seconds())
            self.logger.info(f'Roll timer sleeping for {self.time_convert(time_to_sleep)}')

            # If we just launched the bot, we roll without waiting for the next interval
            if not launch:
                time.sleep(time_to_sleep)
            else:
                time.sleep(5)
                launch = False

            self.roll_timer += datetime.timedelta(minutes=self.roll_duration)
            self.logger.info('Rolls have been reset')
            if self.claim_available:
                self.logger.info(f'Initiating {self.roll_count} rolls')
                self.browser.roll(self.roll_count)
                if config.ALWAYS_ROLL:
                    self.logger.info(f'Initiating {self.roll_count} rolls')
                    self.browser.roll(self.roll_count)
                else:
                    self.logger.info(f'No claim available, not rolling')

    def wait_for_claim(self):
        while True:
            x = (self.claim_timer - datetime.datetime.now()).total_seconds()
            self.logger.info(f'Claim timer sleeping for {self.time_convert(x)}')
            time.sleep(x)
            self.claim_timer += datetime.timedelta(minutes=self.claim_duration)
            self.logger.info(f'Claims have been reset')
            self.claim_available = True

    def wait_for_daily(self):
        while True:
            x = (self.daily_timer - datetime.datetime.now()).total_seconds()
            if x > 0:  # In case daily is already ready
                self.logger.info(f'Daily timer sleeping for {self.time_convert(x)}')
                time.sleep(x)
                self.logger.info(f'Daily has been reset, initiating daily commands')
            else:
                self.logger.info('Daily is ready, initiating daily commands')
            self.daily_timer += datetime.timedelta(minutes=self.daily_duration)
            self.browser.send_text(f'{config.COMMAND_PREFIX}daily')
            time.sleep(3)  # Wait 3 seconds for processing
            self.browser.send_text(f'{config.COMMAND_PREFIX}dk')

    def wait_for_kakera(self):
        while True:
            x = (self.kakera_timer - datetime.datetime.now()).total_seconds()
            if x > 0:  # In case kakera is already ready
                self.logger.info(f'Kakera loot timer sleeping for {self.time_convert(x)}')
                time.sleep(x)
            self.kakera_timer += datetime.timedelta(minutes=self.kakera_duration)
            self.logger.info(f'Kakera loot has been reset')
            self.kakera_available = True

    @staticmethod
    def time_convert(seconds):
        seconds = seconds % (24 * 3600)
        hour = seconds // 3600
        seconds %= 3600
        minutes = seconds // 60
        seconds %= 60

        return "%d:%02d:%02d" % (hour, minutes, seconds)
