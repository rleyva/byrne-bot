import argparse
import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import discord
import yt_dlp
from discord.ext import commands
from prettytable import PrettyTable


'''
   ____   __   __   ____     _   _   U _____ u   ____     U  ___ u _____   
U | __")u \ \ / /U |  _"\ u | \ |"|  \| ___"|/U | __")u    \/"_ \/|_ " _|  
 \|  _ \/  \ V /  \| |_) |/<|  \| |>  |  _|"   \|  _ \/    | | | |  | |    
  | |_) | U_|"|_u  |  _ <  U| |\  |u  | |___    | |_) |.-,_| |_| | /| |\   
  |____/    |_|    |_| \_\  |_| \_|   |_____|   |____/  \_)-\___/ u |_|U   
 _|| \\_.-,//|(_   //   \\_ ||   \\,-.<<   >>  _|| \\_       \\   _// \\_  
(__) (__)\_) (__) (__)  (__)(_")  (_/(__) (__)(__) (__)     (__) (__) (__) 


ByrneBot is a music playback bot for Discord.

Currently supported features:
- Playback and queuing of Youtube URLs.
- Basic playback interactions (pause, resume, stop).

TODO:
- Support for YouTube playlists.
- Stream from YouTube instead of downloading each video.
- All of the commands marked as TODO (purge, search, loop, skip, shuffle).
- Collecting some user stats would be nice...
- Better formatting of playlist when running `!show`.
- Break things out into seperate files.
'''

@dataclass
class MediaInfo:
    title: str
    identifier: str
    uploader: str
    duration: float
    tags: List[str]
    filepath: Path


@dataclass
class Request:
    context: discord.ext.commands.Context
    media: MediaInfo


class MediaHandler:
    #
    # Handles interactions with media sources, namely Youtube for now.
    #
    def __init__(self, working_dir):
        self.options = {
            'format': 'm4a/bestaudio/best',
            'outtmpl': f'{working_dir}/%(title)s-%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
            }],
        }

    async def get(self, url, loop=None):
        # TODO: Add a try catch or validation incase the URL is malformed. 
        # TODO: This function requires a bit of rework... 
        loop = loop or asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(self.options) as ydl:
            logging.info(f"Attempting to download {url}")
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
            return MediaInfo(info['title'],
                             info['id'],
                             info['uploader'],
                             info['duration'],
                             info['tags'],
                             info['requested_downloads'][0]['filepath'])


class PlaybackCog(commands.Cog): 
    #
    # Class containing all of the commands for fetching songs from a URL.
    #
    def __init__(self, bot, media_handler):
        self.bot = bot
        self.media_handler = media_handler
        self.queue = deque() 

    # TODO: Move initialization related functions outside of this Cog.
    
    ####################################################################
    # --- Start of functions that should be moved out of this Cog ---- #
    ####################################################################

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"{self.bot.user} successfully logged in.")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        else:
            # TODO: Remove this once things are working.
            logging.info(f"{message.author} sent: {message.content}")

    @commands.command(name="join", help="Join voice channel.")
    async def join(self, ctx):
        if ctx.message.author.voice:
            logging.info(f"Joining {str(ctx.message.author.voice.channel)}.")
            channel = ctx.message.author.voice.channel
        else:
            message = f"{ctx.message.author.name} is not connected to a voice channel."
            logging.info(message)
            await ctx.send(message)
            return
        await channel.connect()


    @commands.command(name="leave", help="Leave voice channel.")
    async def leave(self, ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_connected():
            # TODO: Note which voice channel the bot is leaving from.
            logging.info(f"{self.bot.user} is leaving the voice channel.")
            await voice_client.disconnect()
        else:
            message = f"{self.bot.user} is not connected to a voice channel."
            logging.info(message)
            await ctx.send(message)


    #################################################################
    # --- End of functions that should be moved out of this Cog --- #
    #################################################################

    @commands.command(name="play", help="Plays/queues song.")
    async def play(self, ctx, url): 
        def ready_for_playback(queue):
            return queue and not queue[0].context.message.guild.voice_client.is_playing()

        # Helper function for playing songs from the queue.
        async def _play_from_queue(self): 
            if ready_for_playback(self.queue):
                request = self.queue.popleft()
                await request.context.send(f"Playing {request.media.title}.")
                request.context.message.guild.voice_client.play(
                        discord.FFmpegPCMAudio(executable="ffmpeg",
                        source=request.media.filepath),
                        after=lambda e: asyncio.run_coroutine_threadsafe(_play_from_queue(self), self.bot.loop))

        # Fetch the song from the URL, place it in the queue, and dispatch the playback function.
        media = await self.media_handler.get(url, self.bot.loop) 
        self.queue.append(Request(ctx, media))
        logging.info(f"Added {media.title} ({media.filepath}) to the queue.") 
        await ctx.send(f"Added {media.title} to the queue.")
        await _play_from_queue(self)


    @commands.command(name="pause", help="Pauses currently playing audio.")
    async def pause(self, ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_playing():
            voice_client.pause()
        else:
            await ctx.send("No playback to pause.")                   
 
    
    @commands.command(name="resume", help="Resumes paused audio.")
    async def resume(self, ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_paused():
            voice_client.resume()
            await ctx.send("Resuming playback.")
        else:
            await ctx.send("No playback to resume.")


    @commands.command(name="stop", help="Stops audio playback.")
    async def stop(self, ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client.is_playing():
            voice_client.stop()
            await ctx.send("Stopping playback.")


    @commands.command(name="show", help="Show queue.")
    async def show(self, ctx):
        table = PrettyTable()
        table.field_names = ["#", "Title", "Uploader", "Duration (s)"]
        for i, request in enumerate(self.queue):
            row = request.media
            table.add_row([i, f"{row.title:^20}", f"{row.uploader:^20}", row.duration])
        await ctx.send(f"```{table.get_string()}```")
    

    @commands.command(name="purge", help="Purges the playback queue.")
    async def purge(self, ctx):
        await ctx.send("Purge feature is currently not implemented.")


    @commands.command(name="search", help="Searches YouTube for requested item.")
    async def search(self, ctx):
        await ctx.send("Seach feature is currently not implemented.")


    @commands.command(name="loop", help="Loops currently playing item until `loop` command is issued again.")
    async def loop(self, ctx):
        await ctx.send("Loop feature is currently not implemented.")


    @commands.command(name="skip", help="Skips currently playing item.")
    async def skip(self, ctx):
        await ctx.send("Skip feature is currently not implemented.")


    @commands.command(name="shuffle", help="Shuffle the contents of the queue.")
    async def shuffle(self, ctx):
        await ctx.send("Shuffle is currently not implemented.")


class ByrneBot:
    @dataclass
    class Config:
        directory: Path
        token: str


    def __init__(self, config: MusicBobConfig):
        self.config = config
        logging.info(f"Initialized MusicBob instance! Working Directory: {self.config.directory}  Token: {self.config.token}")

        # Initialize the PlaybackCog
        self.bot = commands.Bot(command_prefix="!")
        self.bot.add_cog(PlaybackCog(self.bot, MediaHandler(config.directory)))
        logging.info("MusicBob instance has been initialized. Waiting to run...")


    def run(self):
        logging.info("MusicBob instance is running!")
        self.bot.run(self.config.token)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

    parser = argparse.ArgumentParser()
    parser.add_argument('--token', type=str, help="Discord API token.")
    parser.add_argument('--directory', type=Path, help="Working directory where songs will be downloaded to.")
    args = parser.parse_args()

    assert args.directory is not None and args.directory.is_dir(), "Invalid directory was provided!"
    assert args.token is not None, "No API token was provided!"

    config = Config(args.directory, args.token)
    bot = ByrneBot(config)
    bot.run()
