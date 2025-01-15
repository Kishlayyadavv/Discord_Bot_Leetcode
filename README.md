
# **LeetCode Discord Tracker Bot**

This is a **Discord bot** designed to track and display **LeetCode stats** of users in a server. It fetches the stats using the **LeetCode API**, tracks the user's recent problem submissions, and sends notifications when a user solves new problems.

---

## **Features**

- **Track User Stats**: Use the `!track <username>` command to start tracking a user's LeetCode stats.
- **Leaderboard**: Display a leaderboard of tracked users based on their LeetCode ranking.
- **Recent Submissions**: The bot sends notifications to a Discord channel when a tracked user solves a new problem.
- **Guild-Specific**: The bot tracks users on a per-guild basis and notifies the guild channels accordingly.

---

## **Setup**

### **Prerequisites**

- Python 3.7 or higher
- **MongoDB** instance (cloud or local)
- **Discord Developer Application** with Bot Token

### **Installation**

1. Clone the repository:
    ```bash
    git clone https://github.com/Kishlayyadavv/Discord_Bot_Leetcode
    cd Discord_Bot_Leetcode
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Create a `.env` file in the root directory and add the following variables:
    ```env
    DISCORD_TOKEN=<your_discord_bot_token>
    MONGO_URI=<your_mongo_connection_string>
    ```

4. Run the bot:
    ```bash
    python bot.py
    ```

---

## **Commands**

### `!track <username>`
Start tracking a user's LeetCode stats. Example:
```
!track john_doe
```

### `!stats`
Displays the stats of tracked users in the server. A dropdown will appear to select a user.

### `!leaderboard`
Shows the LeetCode leaderboard for the tracked users based on their ranking.

---

## **Database**

This bot uses **MongoDB** to store:

- **Users**: Contains user stats such as ranking and submissions.
- **Guilds**: Stores server (guild) data, including the tracked users for each guild.
- **Guild-User Link**: Links users to specific guilds for proper tracking.

---

## **Contributions**

Feel free to fork the repository and create pull requests for improvements or bug fixes. 

## **License**

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

