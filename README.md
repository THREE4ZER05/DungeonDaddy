
![Banner](https://github.com/user-attachments/assets/ec214a4d-9354-4ad1-b4f8-8214634dfad0)

# DungeonDaddy Bot

DungeonDaddy is a Discord bot designed to help organise dungeon groups for **World of Warcraft (WoW)** M+. Players can create and join dungeon runs, select roles, and schedule events—all within Discord!

---

## 🚀 Features

✅ **Create Dungeon Groups** – Easily create and manage dungeon runs.  
✅ **Role Selection** – Players can assign themselves as Tank, Healer, or DPS.  
✅ **Scheduled Runs** – Set up runs for specific times and notify players.  
✅ **Automatic Cleanup** – Expired events are removed to keep things tidy.  
✅ **Reactions for Roles** – Players can react to sign up for dungeons.  
✅ **Heartbeat System** – Ensures the bot stays active and doesn’t disconnect.  

---

## 📌 Installation & Setup

### 1️⃣ Prerequisites

Before installing, make sure you have:

- [Python 3.8+](https://www.python.org/downloads/)
- `pip` (Comes with Python)
- A [Discord Bot Token](https://discord.com/developers/docs/intro)
- A `.env` file for storing environment variables

---

### 2️⃣ Clone the Repository

Open a terminal or command prompt and run:

```bash
git clone https://github.com/yourusername/DungeonDaddy.git
cd DungeonDaddy
```

---

### 3️⃣ Install Dependencies

Run the following command to install the required dependencies:

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Set Up `.env` File

Create a `.env` file in the project directory and add the following:

```ini
DISCORD_BOT_TOKEN=your-bot-token-here
```

Replace `your-bot-token-here` with your actual **Discord Bot Token**.

---

### 5️⃣ Run the Bot

To start the bot, simply run:

```bash
python daddy.py
```

---

## 🛠 Commands

| Command  | Description                        |
|----------|------------------------------------|
| `/dd`    | Start creating a dungeon group    |
| 🛡️       | Select "Tank" role                |
| 💚       | Select "Healer" role              |
| ⚔️       | Select "DPS" role                 |
| 🏹       | Players react to join dungeon runs |

---

## 🛠 Troubleshooting

### 🔹 Bot Isn’t Responding to Commands

- Make sure the bot has **applications.commands** permission.
- Try removing old slash commands:

  ```bash
  python reset_commands.py
  ```

- Restart the bot:

  ```bash
  python daddy.py
  ```

---

### 🔹 Bot Keeps Going Offline

- Check that the **heartbeat system** is running properly.
- Ensure your **hosting service** doesn’t shut down inactive processes.

---

### 🔹 "Command Already Registered" Error

- Run the following command to clear duplicate commands:

  ```bash
  python reset_commands.py
  ```

- Restart the bot and **only register commands in `on_ready()`**.

---

## 💡 Future Features

✅ **Automated Role Notifications**  
✅ **Dungeon Leaderboard System**  
✅ **Advanced Scheduling with Reminders**  
✅ **Cross-Server Dungeon Management**  

---

## ❤️ About This Project

This bot is a **passion project** while I’m learning Python! 🐍  
I’m new to coding and built **DungeonDaddy** as a fun way to practise, experiment, and improve my skills.

I’ll do my best to keep it updated, but please be patient if things break—this is all part of my **learning journey**. 🚀

If you have suggestions or find bugs, feel free to **open an issue** or reach out!

---

## 📜 Licence

This project is licensed under the **MIT Licence**.  
Feel free to **modify and use it** for your own purposes!
