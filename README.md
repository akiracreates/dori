# Dori Bot -- Telegram English Vocabulary Assistant

## 1. Project name and purpose

Dori Bot is a Telegram bot that helps students systematically learn
English vocabulary and helps teachers manage a shared word base for
their groups. The bot focuses on practice, repetition and simple
tracking of progress instead of static word lists.

## 2. Project description

Dori Bot provides: - Student interface for personal dictionaries,
flashcard-based practice, and viewing words by module and level. -
Teacher interface for adding, editing, and batch-uploading words into a
central SQLite database.

Key features: - Student/Teacher roles (teacher role protected by
password) - Personal dictionary editing - Flashcard training - SQLite
storage - Modular and level-based vocabulary structure

## 3. Installation and run

### 3.1. Prerequisites

-   Python 3.10+
-   Telegram bot token from @BotFather
-   Git

### 3.2. Clone repository

    git clone https://github.com/akiracreates/dori.git
    cd dori

### 3.3. Virtual environment (optional)

    python -m venv .venv
    source .venv/bin/activate

### 3.4. Install dependencies

    pip install -r requirements.txt

### 3.5. Environment configuration

Create `.env`:

    BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
    TEACHER_PASS=YOUR_TEACHER_PASSWORD

### 3.6. Run bot

    python -m bot.main

## 4. Usage

### Student role

-   Add/edit/delete words in personal dictionary
-   Flashcard practice
-   View words by module
-   Change level

### Teacher role

-   Add single word
-   Add batch of words
-   Edit words
-   View complete word list

## 5. Repository structure

    bot/
      main.py
      menus.py
      sharedState.py
      handlers/
      database/
      services/
    requirements.txt
    flashcard.png
    README.md

## 6. Technical requirements

-   Python 3.10+
-   aiogram 3.x
-   SQLite3
-   Pillow
-   python-dotenv

## 7. Authors

-   Amira Haggag --- Team lead & developer
-   Georgy Dodi --- Analyst & tester
-   Ivan Tkachenko --- Analyst & tester
-   Mylene Jordan --- Manager & developer
-   Natalia Zlenko --- Manager
-   Irina Slavova --- Tester
-   Maksim Yelanskyi --- Fullstack developer

## 8. Contact

GitHub issues: https://github.com/akiracreates/dori
