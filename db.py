import psycopg2

def get_db_connection():
    conn = psycopg2.connect(
        database="NeuroScate",
        user="postgres",
        password="13Gergert08",
        host="localhost",
        port="5432"
    )
    return conn