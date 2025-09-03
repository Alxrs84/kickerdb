import sqlite3
import os

# Define the path to your database file
DB_PATH = "kicker_main.db"

def cleanup_invalid_players():
    """
    Connects to the database and deletes all player_seasonal_details records
    where the market_value is 999000000.
    """
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file '{DB_PATH}' not found.")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # SQL statement to delete records with the invalid market value
        delete_query = "DELETE FROM player_seasonal_details WHERE market_value = 999000000"

        # Execute the delete statement
        cursor.execute(delete_query)
        deleted_count = cursor.rowcount
        conn.commit()

        print(f"Cleanup successful. Deleted {deleted_count} records with a market value of 999000000.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()  # Rollback any changes on error

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("Starting cleanup of non-real player data...")
    cleanup_invalid_players()
    print("Cleanup script finished.")