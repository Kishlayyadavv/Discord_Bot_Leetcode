import discord
from discord.ext import commands, tasks
import requests
import os
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()

# Initialize MongoDB
mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client.lc_tracker
users_collection = db.tracked_users
guilds_collection = db.guilds
guild_user_link_collection = db.guild_user_link

# Discord Bot Setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    track_solved_problems.start()
    await bot.tree.sync()

@bot.event
async def on_guild_join(guild: discord.Guild):
    default_channel = guild.system_channel or next((ch for ch in guild.text_channels if ch.permissions_for(guild.me).send_messages), None)
    if default_channel:
        await default_channel.send(f"Hello {guild.name}, I have been added to your server! Use `/track <username>` to track LeetCode stats.")
        guild_data = {
            "guild_id": guild.id,
            "default_channel_id": default_channel.id,
            "tracked_users": []
        }
        guilds_collection.insert_one(guild_data)
    else:
        print(f"No suitable default channel found for guild: {guild.name}")

def fetch_lc_stats(username):
    url = f"https://leetcode-api-faisalshohag.vercel.app/{username}"
    try:
        response = requests.get(url)
        data = response.json()
        if 'ranking' in data:
            stats = {
                "profile": {
                    "ranking": data["ranking"]
                },
                "submitStats": {
                    "acSubmissionNum": [
                        {"difficulty": "Easy", "count": data["totalSubmissions"][1]["count"]},
                        {"difficulty": "Medium", "count": data["totalSubmissions"][2]["count"]},
                        {"difficulty": "Hard", "count": data["totalSubmissions"][3]["count"]},
                        {"difficulty": "All", "count": data["totalSubmissions"][0]["count"]},
                    ]
                },
                "recentSubmissionList": [
                    {"title": submission["title"], "titleSlug": submission["titleSlug"], 
                     "timestamp": submission["timestamp"], "statusDisplay": submission["statusDisplay"]}
                    for submission in data["recentSubmissions"]
                ]
            }
            return stats
    except Exception as e:
        print(f"Error fetching LeetCode stats: {e}")
    return None

@bot.tree.command()
async def track(interaction: discord.Interaction, username: str):
    # Defer the response immediately
    await interaction.response.defer(ephemeral=False)

    stats = fetch_lc_stats(username)
    if not stats:
        await interaction.followup.send(f"Could not find `{username}` on LeetCode.")
        return

    # Get current timestamp to track only new solutions
    current_time = int(stats["recentSubmissionList"][0]["timestamp"]) if stats["recentSubmissionList"] else 0

    user_data = {
        "username": username,
        "ranking": stats["profile"]["ranking"],
        "submissions": stats["submitStats"]["acSubmissionNum"],
        "last_solved_timestamp": current_time  # Set initial timestamp
    }

    # Update guild data
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild.id})
    if guild_data:
        # Check if user is already tracked in this guild
        if not any(user["username"] == username for user in guild_data["tracked_users"]):
            guild_data["tracked_users"].append(user_data)
            guilds_collection.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": {"tracked_users": guild_data["tracked_users"]}}
            )

            # Update or insert user in users collection
            users_collection.update_one(
                {"username": username},
                {"$set": user_data},
                upsert=True
            )

            # Link user to guild
            guild_user_link_collection.update_one(
                {"guild_id": interaction.guild.id, "username": username},
                {"$set": {"guild_id": interaction.guild.id, "username": username}},
                upsert=True
            )

            await interaction.followup.send(f"Started tracking `{username}`. Will notify about new solutions from now on.")
        else:
            await interaction.followup.send(f"User `{username}` is already being tracked in this server.")
    else:
        await interaction.followup.send("Guild not found in the database.")

@bot.tree.command()
async def stats(interaction: discord.Interaction):
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild.id})
    if not guild_data or not guild_data["tracked_users"]:
        await interaction.response.send_message("No users are being tracked in this server.")
        return

    # Refresh stats for all users
    updated_users = []
    for user in guild_data["tracked_users"]:
        current_stats = fetch_lc_stats(user["username"])
        if current_stats:
            updated_users.append({
                "username": user["username"],
                "ranking": current_stats["profile"]["ranking"],
                "submissions": current_stats["submitStats"]["acSubmissionNum"]
            })

    if not updated_users:
        await interaction.response.send_message("Could not fetch updated stats for any users.")
        return

    options = [discord.SelectOption(label=user["username"], value=user["username"]) 
               for user in updated_users]

    select = discord.ui.Select(placeholder="Select a user", options=options)

    async def select_callback(interaction: discord.Interaction):
        selected_username = select.values[0]
        user_stats = next((user for user in updated_users if user["username"] == selected_username), None)

        if user_stats:
            message = f"\U0001F4CA **LeetCode Stats for {selected_username}**\n"
            message += f"\U0001F3C6 **Ranking:** {user_stats['ranking']}\n"
            for difficulty in user_stats['submissions']:
                message += f"\u2705 **{difficulty['difficulty']}:** {difficulty['count']} problems solved\n"

            await interaction.response.send_message(message)
        else:
            await interaction.response.send_message(f"Could not find stats for `{selected_username}`.")

    select.callback = select_callback
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("Select a user to view their stats:", view=view)

@bot.tree.command()
async def leaderboard(interaction: discord.Interaction):
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild.id})
    if not guild_data or not guild_data["tracked_users"]:
        await interaction.response.send_message("No users are being tracked in this server.")
        return

    # Refresh rankings for all users
    updated_users = []
    for user in guild_data["tracked_users"]:
        current_stats = fetch_lc_stats(user["username"])
        if current_stats:
            updated_users.append({
                "username": user["username"],
                "ranking": current_stats["profile"]["ranking"]
            })

    if not updated_users:
        await interaction.response.send_message("Could not fetch updated rankings.")
        return

    # Sort users by ranking
    sorted_users = sorted(updated_users, key=lambda x: x["ranking"])
    message = "\U0001F3C6 **LeetCode Leaderboard**\n\n"

    for idx, user in enumerate(sorted_users, start=1):
        medal = "\U0001F947" if idx == 1 else "\U0001F948" if idx == 2 else "\U0001F949" if idx == 3 else "\U0001F3C6"
        message += f"{medal} **{idx}.** {user['username']} - Ranking: {user['ranking']}\n"

    await interaction.response.send_message(message)

@tasks.loop(minutes=1)
async def track_solved_problems():
    for guild in guilds_collection.find():
        guild_channel = await bot.fetch_channel(guild["default_channel_id"])
        if not guild_channel:
            continue

        for user in guild["tracked_users"]:
            username = user["username"]
            stats = fetch_lc_stats(username)

            if not stats or not stats["recentSubmissionList"]:
                continue

            last_solved_timestamp = user.get("last_solved_timestamp", 0)
            new_problems = [
                prob for prob in stats["recentSubmissionList"]
                if int(prob["timestamp"]) > last_solved_timestamp and prob["statusDisplay"] == "Accepted"
            ]

            if new_problems:
                latest_timestamp = max(int(prob["timestamp"]) for prob in new_problems)

                # Update timestamp in both collections
                users_collection.update_one(
                    {"username": username},
                    {"$set": {"last_solved_timestamp": latest_timestamp}}
                )

                guilds_collection.update_one(
                    {"guild_id": guild["guild_id"], "tracked_users.username": username},
                    {"$set": {"tracked_users.$.last_solved_timestamp": latest_timestamp}}
                )

                for prob in new_problems:
                    message = (
                        f"\U0001F680 **{username}** just solved a new problem!\n"
                        f"\U0001F538 **Problem:** [{prob['title']}](https://leetcode.com/problems/{prob['titleSlug']}/)\n"
                        f"\U0001F4C5 **Time:** <t:{prob['timestamp']}:F>\n"
                    )
                    await guild_channel.send(message)

bot.run(os.getenv("DISCORD_TOKEN"))
