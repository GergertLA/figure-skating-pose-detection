import psycopg2

def get_db_connection():
    conn = psycopg2.connect(
        database="***",
        user="***",
        password="***",
        host="***",
        port="***"
    )

    return conn
