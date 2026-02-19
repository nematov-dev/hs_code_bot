# TIF TN HS Code Search Bot

A **Telegram bot** for searching TIF TN (HS) codes by product name, code, or AI-powered description. The bot supports Premium subscriptions, Admin management, and AI assistance for complex queries.

---

## Features

* 🔎 **Search by Product Name**
  Users can search for HS codes using the product name in Uzbek (Latin or Cyrillic).

* 🔢 **Search by HS Code**
  Search HS codes directly using code numbers.

* 🤖 **AI Search**
  Users can describe the product in natural language, and the bot uses AI to suggest relevant HS codes.

* 👤 **User Profile**
  Shows subscription status and expiration date.

* ⚙️ **Admin Panel**
  Admins can view statistics, give Premium subscriptions, and manage users.

* 📗 **Useful Sections**
  Additional helpful information for users (can be extended).

---

## Requirements

* Python 3.11+
* PostgreSQL database
* Telegram Bot Token
* Google Gemini API Key (for AI search)

### Python Packages

Install dependencies:

```bash
pip install aiogram pandas psycopg2-binary python-decouple google-genai
```

---

## Configuration

Create a `.env` file in the project root:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
GEMINI_API_KEY=YOUR_GOOGLE_GEMINI_API_KEY
ADMIN_ID=YOUR_TELEGRAM_ID

DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432
```

---

## Database

The bot uses PostgreSQL to store user data and subscription info.

* **Table:** `users_hs`

| Column       | Type      | Description                        |
| ------------ | --------- | ---------------------------------- |
| user_id      | BIGINT    | Telegram user ID (Primary Key)     |
| join_date    | TIMESTAMP | Date when user joined              |
| is_premium   | BOOLEAN   | Premium subscription status        |
| sub_end_date | TIMESTAMP | Subscription end date (if Premium) |

> The table is created automatically on bot startup.

---

## CSV File

The bot uses a CSV file for HS codes:

* **Path:** `documents/hs_codes_uz.csv`
* **Columns:**

  1. Code
  2. Description
  3. Unit

The bot reads and cleans the data on startup.

---

## Bot Commands and Buttons

### Main Menu

| Button            | Description                         |
| ----------------- | ----------------------------------- |
| 🔎 Nom bo'yicha   | Search by product name              |
| 🔢 Kod bo'yicha   | Search by code                      |
| 🤖 AI qidiruv     | AI-powered search                   |
| 👤 Hisobim        | Show user profile                   |
| 📗 Foydali bo'lim | Useful sections                     |
| ⚙️ Admin Panel    | Admin functions (only for admin ID) |

---

### Admin Panel

* View total users and Premium users
* Give Premium subscription to a user by Telegram ID
* Subscription duration selection (currently 30 days)

---

## AI Search

The bot uses **Google Gemini API** to analyze user-provided product descriptions and extract key terms to search the HS code database.

* The AI generates **Cyrillic keywords** for better matching.
* If a match is found, the results are displayed to the user.
* If no match is found, a friendly message is shown.

---

## Pagination

Search results support pagination:

* 5 items per page
* Inline buttons: `⬅️ Orqaga` (Back), `Oldinga ➡️` (Next)

---

## Logging

The bot logs errors and information via Python's `logging` module.

---

## How to Run

```bash
python main.py
```

Or using asyncio:

```bash
python -m bot
```

The bot will start polling Telegram and respond to user interactions.

---

## Notes

* Only **Premium users** can access AI Search.
* Admin ID is defined in `.env` to access Admin Panel.
* MarkdownV2 is used for Telegram formatting; special characters are automatically escaped.

---

## License

MIT License – free to use, modify, and distribute.
