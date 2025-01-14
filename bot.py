import discord
from discord.ext import commands, tasks
import requests
import config
from pymongo import MongoClient

# Initialize MongoDB
mongo_client = MongoClient(config.MONGO_URI)
db = mongo_client.lc_tracker
users_collection = db.tracked_users
guilds_collection = db.guilds  # New collection for storing guild-specific data
guild_user_link_collection = db.guild_user_link  # New collection for linking guilds and tracked users

# Discord Bot Setup
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)
default_channels = []  # Dictionary to store default channels by guild ID
guild_id = []

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    track_solved_problems.start()  # Start auto-tracking
    await bot.tree.sync()

@bot.event
async def on_guild_join(guild: discord.Guild):
    # Notify the server that the bot has been added
    default_channel = guild.system_channel or guild.text_channels[0]  # Choose default system channel or first text channel
    if default_channel:
        await default_channel.send(f"Hello {guild.name}, I have been added to your server! Use `!track <username>` to track LeetCode stats.")
        # Save the guild data to the database for personalized experience
        guild_data = {
            "guild_id": guild.id,
            "default_channel_id": default_channel.id,
            "tracked_users": []  # This will store the list of tracked users for the server
        }
        guild_id.append(guild.id)
        guilds_collection.insert_one(guild_data)  # Insert guild data into the collection
        default_channels.append(default_channel)  # Store the default channel for later use
    else:
        print(f"No suitable default channel found for guild: {guild.name}")

# Function to fetch LeetCode stats using the new endpoint
def fetch_lc_stats(username):
    url = f"https://leetcode-api-faisalshohag.vercel.app/{username}"
    response = requests.get(url)

    try:
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
                    {"title": submission["title"], "titleSlug": submission["titleSlug"], "timestamp": submission["timestamp"], "statusDisplay": submission["statusDisplay"]}
                    for submission in data["recentSubmissions"]
                ]
            }
            return stats
    except Exception as e:
        print(f"Error fetching LeetCode stats: {e}")
    return None


# Command to track a new user
@bot.tree.command()
async def track(interaction: discord.Interaction, username: str):
    existing_user = users_collection.find_one({"username": username})
    if existing_user:
        await interaction.response.send_message(f"User `{username}` is already being tracked.")
        return
    
    stats = fetch_lc_stats(username)
    if not stats:
        await interaction.response.send_message(f"Could not find `{username}` on LeetCode.")
        return
    
    # Insert user into the database
    user_data = {
        "username": username,
        "ranking": stats["profile"]["ranking"],
        "submissions": stats["submitStats"]["acSubmissionNum"],
        "last_solved_timestamp": 0
    }

    # Update the guild's tracked users list
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild.id})
    if guild_data:
        tracked_users = guild_data["tracked_users"]
        if username not in [user["username"] for user in tracked_users]:
            guild_data["tracked_users"].append(user_data)
            guilds_collection.update_one(
                {"guild_id": interaction.guild.id},
                {"$set": {"tracked_users": guild_data["tracked_users"]}}
            )

            # Link the user to the guild in a separate collection
            guild_user_link_collection.insert_one({
                "guild_id": interaction.guild.id,
                "username": username
            })

            users_collection.insert_one(user_data)
            await interaction.response.send_message(f"Started tracking `{username}`.")
        else:
            await interaction.response.send_message(f"User `{username}` is already being tracked in this server.")
    else:
        await interaction.response.send_message("Guild not found in the database.")

# Command to display stats with user selection
@bot.tree.command()
async def stats(interaction: discord.Interaction):
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild.id})
    if not guild_data or not guild_data["tracked_users"]:
        await interaction.response.send_message("No users are being tracked.")
        return

    # Create a select menu with the list of users
    options = [
        discord.SelectOption(label=user['username'], value=user['username']) for user in guild_data["tracked_users"]
    ]
    select = discord.ui.Select(placeholder="Select a user", options=options)

    async def select_callback(interaction: discord.Interaction):
        selected_username = select.values[0]
        stats = fetch_lc_stats(selected_username)
        if not stats:
            await interaction.response.send_message(f"Could not find `{selected_username}` on LeetCode.")
            return

        message = f"\U0001F4CA **LeetCode Stats for {selected_username}**\n"
        message += f"\U0001F3C6 **Ranking:** {stats['profile']['ranking']}\n"
        for difficulty in stats['submitStats']['acSubmissionNum']:
            message += f"\u2705 {difficulty['difficulty']}: {difficulty['count']} problems solved\n"
        
        await interaction.response.send_message(message)

    select.callback = select_callback

    # Send the select menu to the user
    view = discord.ui.View()
    view.add_item(select)
    await interaction.response.send_message("Please select a user to view their stats:", view=view)

# Command to display leaderboard
@bot.tree.command()
async def leaderboard(interaction: discord.Interaction):
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild.id})
    if not guild_data or not guild_data["tracked_users"]:
        await interaction.response.send_message("No users are being tracked.")
        return
    
    # Sort users by ranking and create leaderboard message
    sorted_users = sorted(guild_data["tracked_users"], key=lambda x: x["ranking"])
    message = "\U0001F3C6 **LeetCode Leaderboard**\n"
    for idx, user in enumerate(sorted_users, start=1):
        message += f"{idx}. **{user['username']}** - Ranking: {user['ranking']}\n"
    
    await interaction.response.send_message(message)

# Background task: Check for new solved problems every 5 minutes
@tasks.loop(minutes=0.5)
async def track_solved_problems():
    print("Started here")
    for user in users_collection.find():
        username = user["username"]
        stats = fetch_lc_stats(username)

        if not stats or not stats["recentSubmissionList"]:
            continue
        
        last_solved_timestamp = user.get("last_solved_timestamp", 0)
        new_problems = [
            prob for prob in stats["recentSubmissionList"]
            if int(prob["timestamp"]) > last_solved_timestamp and prob.get("statusDisplay") == "Accepted"  # Check if status is "AC" (Accepted)
        ]
        print("new", new_problems)
        if new_problems:
            latest_timestamp = max(int(prob["timestamp"]) for prob in new_problems)
            users_collection.update_one(
                {"username": username},
                {"$set": {"last_solved_timestamp": latest_timestamp}}
            )

            # Send messages to default channel
            default_channel = default_channels[0]
            print(default_channel)
            for prob in new_problems:
                message = (
                    f"\U0001F680 **{username}** just solved a new problem!\n"
                    f"\U0001F538 **Problem:** [{prob['title']}](https://leetcode.com/problems/{prob['titleSlug']}/)\n"
                    f"\U0001F4C5 **Time:** <t:{prob['timestamp']}:F>\n"
                )
                await default_channel.send(message)

bot.run(config.DISCORD_TOKEN)
