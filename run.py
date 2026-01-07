from app import create_app, test_db_connection

# Create the application instance using the factory
app = create_app()

if __name__ == "__main__":
    # Run the database test before starting the server
    test_db_connection()

    # Start the Flask application
    app.run(host="127.0.0.1", port=8000, debug=True)