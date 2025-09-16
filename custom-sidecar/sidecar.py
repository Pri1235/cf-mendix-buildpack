import sys, os, time
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))

from hdbcli import dbapi


# Establish a connection to main app

def establish_connection(address, port, user, password):
    try:
        conn = dbapi.connect(
            address=address,
            port=port,
            user=user,
            password=password
        )
        return conn
    except dbapi.Error as e:
        print(f"Error connecting to HANA database: {e}")
        return None


# way to get vcap services env variables to fecth the database creds
def fetch_Vcap_services():
    
    VCAP_SERVICES = os.getenv('VCAP_SERVICES')
    JSON_VCAP_OBJ = json.loads(VCAP_SERVICES)
    DB_ARRAY = JSON_VCAP_OBJ['hana']
    
    print("VCAP_SERVICES:", VCAP_SERVICES)  # Debug print to check the environment variable
    print("DB_ARRAY:", DB_ARRAY)  # Debug print to check the parsed database array  
    
    credentials = DB_ARRAY[0]['credentials']
    host = credentials['host']
    port = credentials['port']
    driver = credentials['driver']
    url = credentials['url']
    schema = credentials['schema']
    db_id = credentials['database_id']
    user = credentials['user']
    password = credentials['password']

    print(f"Connecting to HANA DB at {host}:{port} with user {user}")  # Debug print to verify connection details
    
    return {
    "address": host,
    "port": port,
    "user": user,
    "password": password
}


# fetch some data from System.User entity table
def get_data_from_db():
    conn = establish_connection(**fetch_Vcap_services())
    if not conn:
        print("No connection established.")
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT TABLE_NAME FROM TABLES WHERE SCHEMA_NAME = CURRENT_SCHEMA")
        print("Tables:", cursor.fetchall())
    
        cursor.execute("SELECT * FROM \"system$user\"")
        rows = cursor.fetchall()
        print("Users:", rows)
        return rows
    except dbapi.Error as e:
        print(f"Error fetching data from HANA database: {e}")
        return []
    finally:
        if conn:
            conn.close()
    
# add logs to verify the data being fetched
def log_data():
    data = get_data_from_db()
    if data:
        print("Fetched data from System.User:")
        for row in data:
            print(row)
    else:
        print("No data found.")
    
# close connection ?


def main():
    print("Sidecar module is running.")
    while True:
        try:
            log_data()
        except Exception as e:
            print(f"[ERROR] Sidecar failed: {e}", flush=True)
        time.sleep(300)

if __name__ == "__main__":
    main()
