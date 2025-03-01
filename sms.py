import requests
import time
import os
from dotenv import load_dotenv
import logging
import schedule

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sms_scheduler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sms_scheduler")

# Load environment variables
load_dotenv()

# Configuration
API_BASE_URL = "http://localhost:8000"  # Your FastAPI application URL
CHECK_INTERVAL_MINUTES = 2  # How often to check for new messages

def check_inbound_sms():
    """Check for new inbound SMS messages and process them."""
    try:
        logger.info("Checking for new inbound SMS messages...")
        response = requests.post(f"{API_BASE_URL}/check/inbound-sms")
        
        if response.status_code == 200:
            result = response.json()
            processed_count = result.get("processed_messages", 0)
            logger.info(f"Successfully processed {processed_count} messages")
        else:
            logger.error(f"Failed to check inbound SMS: {response.status_code} - {response.text}")
    
    except Exception as e:
        logger.error(f"Error checking inbound SMS: {str(e)}")

def main():
    logger.info("Starting SMS scheduler")
    
    # Schedule the job to run every X minutes
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_inbound_sms)
    
    # Run once immediately at startup
    check_inbound_sms()
    
    # Keep the script running
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()