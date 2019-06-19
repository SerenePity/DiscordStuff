from discord.ext import commands
import discord
import re
import transliteration.greek
import traceback
import random
import time
import robotic_roman
import shlex
from TextToOwO import owo


MAX_TRIES = 5
BOT_OWNER = '285179803819311106'

class PlayerSession():

    def __init__(self, player, answer, language, channel):
        self.player = player
        self.answer = answer
        self.tries = 0
        self.game_on = True
        self.language = language
        self.channel = channel

    def end_game(self):
        self.language = None
        self.answer = None
        self.tries = 0
        self.game_on = False
        self.channel = None


class Game():

    def __init__(self, game_owner, answer, language, channel):
        self.game_owner = game_owner
        self.game_on = True
        self.players_dict = dict()
        self.language = language
        self.channel = channel
        self.answer = answer
        self.exited_players = set()
        self.players_dict[game_owner] = PlayerSession(game_owner, answer, language, channel)

    def get_game_owner_sess(self):
        return self.players_dict[self.game_owner]

    def add_player(self, player):
        self.players_dict[player] = PlayerSession(player, self.answer, self.language, self.channel)

    def get_player_sess(self, player):
        return self.players_dict[player]

    def end_player_sess(self, player):
        self.exited_players.add(player)
        if player in self.players_dict:
            self.players_dict[player].end_game()
        del self.players_dict[player]

    def no_players_left(self):
        return all(not self.players_dict[player].game_on for player in self.players_dict)

    def end_game(self):
        self.language = None
        self.answer = None
        self.game_on = False
        self.channel = None
        self.exited_players = set()
        self.players_dict = dict()


class Scholasticus(commands.Bot):

    def __init__(self, prefix):
        super().__init__(command_prefix=prefix)
        self.robot = robotic_roman.RoboticRoman()
        self.quotes_commands = dict()
        self.markov_commands = dict()
        self.authors = set()
        self.games = dict()
        self.players_to_game_owners = dict()

    def sleep_for_n_seconds(self, n):
        time.sleep(n - ((time.time() - self.start_time) % n))

    async def on_ready(self):
        print('Logged on as', self.user)
        self.robot.load_all_models()
        self.authors_set = set(list(self.robot.quotes_dict.keys()) + list(self.robot.greek_quotes_dict.keys()) + list(self.robot.off_topic_quotes_dict))
        self.authors_set.add('reddit')
        self.authors = [self.robot.format_name(person) for person in self.authors_set]
        for author in self.authors:
            self.markov_commands[f"as {author.lower()} allegedly said:"] = author
            self.quotes_commands[f"as {author.lower()} said:"] = author
        print('Done initializing')

    async def process_guess(self, channel, player, content):
        try:
            guess = content.lower().strip()
        except:
            await self.send_message(channel, "You forgot to guess an answer.")
            return
        if guess.strip() == "":
            await self.send_message(channel, "You forgot to guess an answer.")
            return
        print("Guess: " + guess)
        game_owner = self.players_to_game_owners[player]
        game_answer = self.games[game_owner].answer.strip()
        if guess == game_answer:
            await self.send_message(channel,
                                    f"{player.mention}, correct! The answer is {self.robot.format_name(game_answer)}.")
            self.games[game_owner].end_game()
            return

        if self.games[game_owner].language == 'greek' and guess not in self.robot.greek_authors:
            await self.send_message(channel, "You're playing a Greek game, but picked a Latin author! Try again.")
            return
        if self.games[game_owner].language == 'latin' and guess not in self.robot.authors:
            await self.send_message(channel, "You're playing a Latin game, but picked a Greek author! Try again.")
            return

        self.games[game_owner].get_player_sess(player).tries += 1

        if self.games[game_owner].players_dict[player].tries < MAX_TRIES:
            guesses_remaining = MAX_TRIES - self.games[game_owner].players_dict[player].tries
            if guesses_remaining == 1:
                await self.send_message(channel,
                                        f"Wrong answer, {player.mention}, you have 1 guess left.")
            else:
                await self.send_message(channel, f"Wrong answer, {player.mention}, you have {guesses_remaining} guesses left.")
        else:
            self.games[game_owner].players_dict[player].end_game()
            if self.games[game_owner].no_players_left():
                if len(self.games[game_owner].players_dict) == 1:
                    await self.send_message(channel,
                                    f"Sorry, {player.mention}, you've run out of guesses. The answer was {self.robot.format_name(game_answer)}. Better luck next time!")
                else:
                    await self.send_message(channel,
                                      f"Everybody has run out of guesses. The answer was {self.robot.format_name(game_answer)}. Better luck next time!")
                self.end_game(game_owner)
                #self.games[game_owner].end_game()
            else:
                await self.send_message(channel,
                                        f"Sorry, {player.mention}, you've run out of guesses! Better luck next time!")
                self.games[game_owner].get_player_sess(player).end_game()
                self.games[game_owner].exited_players.add(player)
                del self.players_to_game_owners[player]


    async def start_game(self, channel, game_owner, text_set):
        repeat_text = ""
        if game_owner in self.games and self.games[game_owner].game_on:
            repeat_text = "Okay, restarting game. "
        if text_set == "greek":
            answer = random.choice(self.robot.greek_authors)
        else:
            answer = random.choice(self.robot.authors)
        passage = self.robot.random_quote(answer)
        self.games[game_owner] = Game(game_owner, answer, text_set, channel)
        self.players_to_game_owners[game_owner] = game_owner
        print("Answer: " + answer)
        await self.send_message(channel,
                                f"{repeat_text}{game_owner.mention}, name the author or source of the following passage:\n\n_{passage}_")


    def end_game(self, game_owner):
        game = self.games[game_owner]
        for player in game.players_dict:
            if player in self.players_to_game_owners:
                del self.players_to_game_owners[player]
        del self.games[game_owner]

    async def on_message(self, message):
        # potential for infinite loop if bot responds to itself
        if message.author == self.user:
            return

        author = message.author
        channel = message.channel
        content = message.content

        if content.lower().startswith(self.command_prefix + 'tr'):
            try:
                tr_args = shlex.split(content)
            except:
                await self.send_message(channel, "Error, no closing quotation. Please try to enclose the input within quotes.")
                return
            try:
                input = ' '.join(tr_args[1:])
                transliterated = transliteration.greek.transliterate(input)
                await self.send_message(channel, transliterated)
                return
            except Exception as e:
                traceback.print_exc()
                await self.send_message(channel, f"Error transliterating input.")
                return

        if content.lower().startswith(self.command_prefix + 'ulfilas'):
            qt_args = shlex.split(content)
            print(qt_args)
            try:
                if len(qt_args) > 1:
                    version = qt_args[1]
                else:
                    version = 'kjv'
                translation = self.robot.ulfilas_translations(version)
                await self.send_message(channel ,translation)

            except Exception as e:
                traceback.print_exc()
                await self.send_message(channel, "Error retrieving verse.")


        if content.lower().startswith(self.command_prefix + 'biblecompare'):
            qt_args = shlex.split(content)
            print(qt_args)
            try:

                if re.match(r"[0-9]+:[0-9]+", qt_args[2]):
                    verse = qt_args[1] + ' ' + qt_args[2]
                    print("Verse: " + verse)
                    versions = qt_args[3:]
                    translation = self.robot.bible_compare(verse, versions)
                elif len(qt_args) > 1:
                    versions = qt_args[1:]
                    translation = self.robot.bible_compare_random_verses(versions)
                else:
                    await self.send_message(channel, "Invalid arguments.")
                    return
                await self.send_message(channel ,translation)
                return
            except Exception as e:
                traceback.print_exc()
                await self.send_message(channel, "Verse not found. Please check that you have a valid Bible version by checking here https://www.biblegateway.com/versions, and here https://getbible.net/api.")
                return

        if content.lower().startswith(self.command_prefix + 'qt'):
            qt_args = shlex.split(content)
            print(qt_args)
            try:
                if (qt_args[1].strip() == '-t'):
                    author = ' '.join(qt_args[2:]).lower().strip()
                    if author == "reddit":
                        await self.send_message(channel, "Sorry, www.reddit.com has been deleted. Please switch to Quora instead. Thank you.")
                        return

                    transliterated = transliteration.greek.transliterate(self.robot.random_quote(author.lower()))
                    await self.send_message(channel, transliterated)
                    return
                else:
                    author = ' '.join(qt_args[1:]).lower().strip()
                    if author == "reddit":
                        await self.send_message(channel, "Sorry, www.reddit.com has been deleted. Please switch to Quora instead. Thank you.")
                        return
                    await self.send_message(channel, self.robot.random_quote(author.lower()))
            except Exception as e:
                traceback.print_exc()
                if not author:
                    await self.send_message(channel, "No person provided")
                else:
                    await self.send_message(channel, f"I do not have quotes for {self.robot.format_name(author)}.")

        if content.lower().startswith(self.command_prefix + 'owo'):
            qt_args = shlex.split(content)
            print(qt_args)
            try:
                author = ' '.join(qt_args[1:]).lower().strip()
                await self.send_message(channel, owo.text_to_owo(self.robot.random_quote(author.lower())))
            except Exception as e:
                traceback.print_exc()
                if not author:
                    await self.send_message(channel, "No person provided")
                else:
                    await self.send_message(channel, f"I do not have quotes for {self.robot.format_name(author)}.")
                    
        if content.strip().lower().startswith(self.command_prefix + "markov"):
            markov_args = shlex.split(content)
            print(markov_args)
            try:
                if (markov_args[1].strip() == '-t'):
                    author = ' '.join(markov_args[2:]).lower().strip()
                    transliterated = transliteration.greek.transliterate(self.robot.make_sentence(author.lower()))
                    await self.send_message(channel, transliterated)
                    return
                else:
                    author = markov_args[1].strip().lower()
                    await self.send_message(channel, self.robot.make_sentence(author.lower()))
                    return
            except Exception as e:
                traceback.print_exc()
                if not author:
                    await self.send_message(channel, "No person provided")
                else:
                    await self.send_message(channel, f"I do not have a Markov model for {self.robot.format_name(author)}.")

        if content.strip().lower() in self.markov_commands:
            author = self.markov_commands[content.strip().lower()]
            try:
                await self.send_message(channel, self.robot.make_sentence(author.lower()))
            except Exception as e:
                traceback.print_exc()
                if not author:
                    await self.send_message(channel, "No person provided")
                else:
                    await self.send_message(channel, f"I do not have a Markov model for {self.robot.format_name(author)}.")

        if content.strip().lower() in self.quotes_commands:
            person = self.quotes_commands[content.strip().lower()]
            if person.strip().lower() == 'reddit' and message.author.id != BOT_OWNER:
                await self.send_message(channel, "No.")
                return
            try:
                await self.send_message(channel, self.robot.random_quote(person.lower()))
            except Exception as e:
                traceback.print_exc()
                if not person:
                    await self.send_message(channel, "No person provided.")
                else:
                    await self.send_message(channel, f"I do not have quotes for {self.robot.format_name(person)}.")

        if content.lower().startswith(self.command_prefix + 'latinquote'):
            await self.send_message(channel, self.robot.pick_random_quote())

        if content.lower().startswith(self.command_prefix + 'greekquote'):
            args = shlex.split(content.lower())
            transliterate = len(args) > 1 and args[1] == '-t'
            quote = self.robot.pick_greek_quote()
            if transliterate:
                quote = transliteration.greek.transliterate(quote)
            await self.send_message(channel, quote)

        if content.lower().startswith(self.command_prefix + 'helpme'):
            await self.send_message(channel, self.robot.help_command())

        if content.lower().startswith(self.command_prefix + 'latinauthors'):
            await self.send_message(channel, '```yaml\n' + ', '.join([self.robot.format_name(a) for a in sorted(self.robot.quotes_dict.keys())]) + '```')

        if content.lower().startswith(self.command_prefix + 'greekauthors'):
            await self.send_message(channel, '```yaml\n' + ', '.join([self.robot.format_name(a) for a in sorted(self.robot.greek_quotes_dict.keys())]) + '```')

        if content.lower().startswith(self.command_prefix + 'greekgame'):
            await self.start_game(channel, author, "greek")
            return

        if content.lower().startswith(self.command_prefix + 'latingame'):
            await self.start_game(channel, author, "latin")
            return

        if content.lower().startswith(self.command_prefix + 'greekgame'):
            await self.start_game(channel, author, "greek")
            return

        if content.lower().startswith(self.command_prefix + 'giveup'):
            if author in self.players_to_game_owners:
                game_owner = self.players_to_game_owners[author]
                game = self.games[game_owner]
                game.end_player_sess(author)
                del self.players_to_game_owners[author]
                if game.no_players_left():
                    await self.send_message(channel, f"{author.mention} has left the game. There are no players left. The answer was {self.robot.format_name(game.answer)}.")
                    self.end_game(game_owner)
                else:
                    await self.send_message(channel, f"{author.mention} has left the game.")
            return

        if author in self.players_to_game_owners :
            game_owner = self.players_to_game_owners[author]
            game = self.games[game_owner]
            if game.game_on and content.lower().strip() in self.authors_set and channel == game.channel:
                if game.players_dict[author].game_on and game.players_dict[author].tries < MAX_TRIES:
                    await self.process_guess(channel, author, content)
                return

        if content.lower().startswith(self.command_prefix + 'join'):
            if len(message.mentions) > 0 :
                game_owner = message.mentions[0]
                if game_owner == author:
                    await self.send_message(channel, "You cannot join your own game!")
                    return
                if game_owner not in self.games:
                    await self.send_message(channel, f"{author.mention}, that person does not have a running game.")
                    return
                if self.games[game_owner].game_on:
                    if author in self.games[game_owner].exited_players:
                        await self.send_message(channel, "You cannot rejoin a game that you've exited")
                        return
                    self.players_to_game_owners[author] = game_owner
                    self.games[game_owner].add_player(author)
                    await self.send_message(channel, f"{author.mention} has joined the game started by {game_owner.mention}.")
                else:
                    self.send_message(channel, f"{author.mention}, you attempted to join a game that doesn't exist.")
            else:
                await self.send_message(channel,
                                        f"{author.mention}, please specify the name of the player whose game you want to join.")
