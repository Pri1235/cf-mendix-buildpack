import sys, os, time
import json
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Add vendor path for HANA dependencies
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "vendor"))

try:
    from hdbcli import dbapi
    logger.info("Successfully imported hdbcli")
except ImportError as e:
    logger.error(f"Failed to import hdbcli: {e}")
    logger.error("Make sure vendor directory contains HANA client libraries")
    sys.exit(1)


def establish_connection(address, port, user, password):
    """Establish a connection to HANA database"""
    try:
        logger.info(f"Attempting to connect to HANA at {address}:{port} with user {user}")
        conn = dbapi.connect(
            address=address,
            port=port,
            user=user,
            password=password
        )
        logger.info("Successfully connected to HANA database")
        return conn
    except dbapi.Error as e:
        logger.error(f"Error connecting to HANA database: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {e}")
        return None


def fetch_vcap_services():
    """Fetch database credentials from VCAP_SERVICES environment variable"""
    try:
        vcap_services = os.getenv('VCAP_SERVICES')
        
        if not vcap_services:
            logger.error("VCAP_SERVICES environment variable not found")
            return None
            
        logger.info("VCAP_SERVICES found, parsing...")
        json_vcap_obj = json.loads(vcap_services)
        
        # Check if hana service exists
        if 'hana' not in json_vcap_obj:
            logger.error("No HANA service found in VCAP_SERVICES")
            logger.info(f"Available services: {list(json_vcap_obj.keys())}")
            return None
            
        db_array = json_vcap_obj['hana']
        
        if not db_array or len(db_array) == 0:
            logger.error("HANA service array is empty")
            return None
            
        credentials = db_array[0]['credentials']
        
        # Extract connection details
        connection_info = {
            "address": credentials['host'],
            "port": int(credentials['port']),
            "user": credentials['user'],
            "password": credentials['password']
        }
        
        logger.info(f"Database connection info extracted - Host: {connection_info['address']}, Port: {connection_info['port']}, User: {connection_info['user']}")
        
        # Log additional info for debugging
        logger.info(f"Schema: {credentials.get('schema', 'N/A')}")
        logger.info(f"Database ID: {credentials.get('database_id', 'N/A')}")
        
        return connection_info
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing VCAP_SERVICES JSON: {e}")
        return None
    except KeyError as e:
        logger.error(f"Missing key in VCAP_SERVICES: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching VCAP services: {e}")
        return None


def get_data_from_db():
    """Fetch data from HANA database"""
    connection_info = fetch_vcap_services()
    
    if not connection_info:
        logger.error("Could not get database connection information")
        return []

    conn = establish_connection(**connection_info)
    if not conn:
        logger.error("No connection established")
        return []

    try:
        cursor = conn.cursor()
        
        # First, check what tables are available
        logger.info("Checking available tables...")
        cursor.execute("SELECT TABLE_NAME FROM TABLES WHERE SCHEMA_NAME = CURRENT_SCHEMA")
        tables = cursor.fetchall()
        logger.info(f"Available tables: {[table[0] for table in tables]}")
        
        # Try to find the correct table name
        table_variants = [
            '"system$user"',
            'SYSTEM$USER',
            '"SYSTEM$USER"',
            'system$user'
        ]
        
        users_data = []
        for table_name in table_variants:
            try:
                logger.info(f"Trying to query table: {table_name}")
                cursor.execute(f"SELECT * FROM {table_name}")
                users_data = cursor.fetchall()
                logger.info(f"Successfully queried {table_name}, found {len(users_data)} records")
                break
            except dbapi.Error as e:
                logger.warning(f"Could not query {table_name}: {e}")
                continue
        
        if not users_data:
            logger.warning("Could not find system user table, trying alternative approach...")
            # Try to get any user-related data
            cursor.execute("SELECT CURRENT_USER, CURRENT_SCHEMA FROM DUMMY")
            current_info = cursor.fetchall()
            logger.info(f"Current user info: {current_info}")
            
        return users_data
        
    except dbapi.Error as e:
        logger.error(f"Database error fetching data: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching data: {e}")
        return []
    finally:
        if conn:
            try:
                conn.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")


def log_data():
    """Log fetched data"""
    try:
        data = get_data_from_db()
        if data:
            logger.info(f"Fetched {len(data)} records from System.User:")
            for i, row in enumerate(data):
                logger.info(f"  Row {i+1}: {row}")
        else:
            logger.warning("No data found or unable to fetch data")
    except Exception as e:
        logger.error(f"Error in log_data: {e}")


def main():
    """Main sidecar loop"""
    logger.info("=== HANA Sidecar module is starting ===")
    
    # Initial environment check
    logger.info("Checking environment...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Script location: {os.path.dirname(__file__)}")
    
    # Check if VCAP_SERVICES is available
    if 'VCAP_SERVICES' in os.environ:
        logger.info("VCAP_SERVICES environment variable found")
    else:
        logger.error("VCAP_SERVICES environment variable not found")
        logger.info("Available environment variables:")
        for key in sorted(os.environ.keys()):
            if any(keyword in key.upper() for keyword in ['VCAP', 'DB', 'HANA', 'DATABASE']):
                logger.info(f"  {key}={os.environ[key][:100]}...")
    
    # Check vendor directory
    vendor_dir = os.path.join(os.path.dirname(__file__), "vendor")
    logger.info(f"Vendor directory: {vendor_dir}")
    logger.info(f"Vendor directory exists: {os.path.exists(vendor_dir)}")
    
    if os.path.exists(vendor_dir):
        try:
            vendor_contents = os.listdir(vendor_dir)
            logger.info(f"Vendor directory contents: {vendor_contents}")
        except Exception as e:
            logger.error(f"Error listing vendor directory: {e}")
    
    logger.info("=== Starting main sidecar loop ===")
    
    iteration = 0
    while True:
        try:
            iteration += 1
            logger.info(f"--- Iteration {iteration} ---")
            log_data()
            logger.info(f"Sleeping for 300 seconds (5 minutes)...")
            time.sleep(300)
        except KeyboardInterrupt:
            logger.info("Sidecar interrupted by user")
            break
        except Exception as e:
            logger.error(f"[ERROR] Sidecar failed in iteration {iteration}: {e}")
            logger.info("Continuing to next iteration...")
            time.sleep(60)  # Wait 1 minute before retrying on error


if __name__ == "__main__":
    main()
