import pymysql # type: ignore
# We need current_app context to access app.config when running within Flask
from flask import current_app
import logging

# This function establishes the connection using configuration defined in config.py
def get_db_connection():
    """Establishes and returns a PyMySQL connection with DictCursor."""
    # We retrieve configuration from the Flask app context
    try:
        return pymysql.connect(
            host=current_app.config["DB_HOST"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
            connect_timeout=5
        )
    except Exception as e:
        # Log the error if connection fails
        logging.error(f"Database connection error: {e}")
        # Re-raise the exception to be handled by the caller (route)
        raise

# This is a simple wrapper for testing and decorators
# where we might not have the full Flask app context yet.
def connect_db_simple(config):
    """Establishes connection using a specific config object (for testing/init)."""
    return pymysql.connect(
        host=config.DB_HOST,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=5
    )