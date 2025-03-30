from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os.path
import pickle
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import base64
import email
import time


# Database setup
Base = declarative_base()

class Email(Base):
    __tablename__ = 'emails'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(String(100), unique=True)
    sender = Column(String(255))
    subject = Column(String(500))
    body = Column(Text)
    received_date = Column(DateTime)
    labels = Column(String(500))

# Create database engine and tables
engine = create_engine('sqlite:///emails.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()
print("Database Session created")


def get_email_details(msg):
    """Extract relevant email details from the message"""
    payload = msg['payload']
    headers = payload.get('headers', [])
    
    subject = next((header['value'] for header in headers if header['name'].lower() == 'subject'), '')
    sender = next((header['value'] for header in headers if header['name'].lower() == 'from'), '')
    date_str = next((header['value'] for header in headers if header['name'].lower() == 'date'), '')
    
    # Get email body
    body = ''
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    # Decode base64 body
                    body = base64.urlsafe_b64decode(part['body']['data'].encode('UTF-8')).decode('UTF-8')
    elif 'body' in payload:
        if 'data' in payload['body']:
            # Decode base64 body
            body = base64.urlsafe_b64decode(payload['body']['data'].encode('UTF-8')).decode('UTF-8')
    
    try:
        received_date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
    except:
        received_date = datetime.now()
    
    return {
        'message_id': msg['id'],
        'sender': sender,
        'subject': subject,
        'body': body,
        'received_date': received_date,
        'labels': ','.join(msg.get('labelIds', []))
    }

def process_rules(email_data):
    print("processing rules")
    # print(email_data)
    """Process email rules from rules.json"""
    if not os.path.exists('email_rules.json'):
        return
    
    with open('email_rules.json', 'r') as f:
        rules_data = json.load(f)
    
    for rule in rules_data['rules']:
        conditions_met = False
        match_type = rule.get('match_type', 'all').lower()
        
        if match_type == 'all':
            conditions_met = all(
                check_condition(email_data, condition)
                for condition in rule['conditions']
            )
        elif match_type == 'any':
            conditions_met = any(
                check_condition(email_data, condition)
                for condition in rule['conditions']
            )
        
        if conditions_met:
            # print(email_data)
            execute_actions(email_data, rule['actions'])

def check_condition(email_data, condition):
    """Check if an email meets a specific condition"""
    field = condition['field'].lower()
    operator = condition['operator'].lower()
    value = condition['value']
    
    # Get attribute value using getattr
    try:
        field_value = getattr(email_data, field)
    except AttributeError:
        return False
    
    # String operations
    if operator == 'contains':
        return value.lower() in str(field_value).lower()
    elif operator == 'does_not_contain':
        return value.lower() not in str(field_value).lower()
    elif operator == 'equals':
        return str(field_value).lower() == value.lower()
    elif operator == 'does_not_equal':
        return str(field_value).lower() != value.lower()
    
    # Date operations
    if field == 'received_date':
        email_date = field_value
        current_date = datetime.now()
        
        if operator == 'greater_than_days':
            delta = current_date - email_date
            return delta.days > int(value)
        elif operator == 'less_than_days':
            delta = current_date - email_date
            return delta.days < int(value)
        elif operator == 'greater_than_months':
            delta = current_date - email_date
            return delta.days > (int(value) * 30) 
        elif operator == 'less_than_months':
            delta = current_date - email_date
            return delta.days < (int(value) * 30)  
    
    return False

def execute_actions(email_data, actions):
    """Execute actions for matching rules"""
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)
    # print("executing actions")
    for action in actions:
        action_type = action['type'].lower()
        
        if action_type == 'mark_as_read':
            service.users().messages().modify(
                userId='me',
                id=email_data.message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        elif action_type == 'mark_as_unread':
            print("marking as unread")
            service.users().messages().modify(
                userId='me',
                id=email_data.message_id,
                body={'addLabelIds': ['UNREAD']}
            ).execute()
        elif action_type == 'move_message':
            print("moving message " + email_data.message_id + " to " + action['folder_id'])
            # Get all labels
            labels = service.users().labels().list(userId='me').execute().get('labels', [])
            # print(labels)
            target_label_name = action['folder_id']
            
            # Find or create the target label
            target_label = next((label for label in labels if label['name'].lower() == target_label_name.lower()), None)
            if not target_label:
                # Create new label if it doesn't exist
                new_label = {
                    'name': target_label_name,
                    'labelListVisibility': 'labelShow',
                    'messageListVisibility': 'show'
                }
                target_label = service.users().labels().create(userId='me', body=new_label).execute()
            
            # Move message by adding new label and removing INBOX label
            service.users().messages().modify(
                userId='me',
                id=email_data.message_id,
                body={
                    'addLabelIds': [target_label['id']],
                    'removeLabelIds': ['INBOX']
                }
            ).execute()

def authenticate_gmail():
    """Authenticate with Gmail API and return credentials"""
    SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
    creds = None

    # Load existing credentials from token.pickle
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # Refresh credentials if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    # Create new credentials if none exist
    elif not creds:
        flow = InstalledAppFlow.from_client_secrets_file(
            'cred.json', SCOPES)
        creds = flow.run_local_server(port=0)
        # Save credentials for future use
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def get_latest_email_date():
    """Last email date in the database"""
    latest_email = session.query(Email.received_date).order_by(Email.received_date.desc()).first()
    if latest_email:
        # print(latest_email)
        return latest_email[0]
    return datetime(2025, 1, 1)  # Default to Jan 1st 2025 if no emails

def get_inbox_messages():
    """Fetch new messages from Gmail after the last timestamp in the database"""
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)
    
    # Get latest email timestamp
    latest_date = get_latest_email_date()
    timestamp = int(latest_date.timestamp())
    
    # Get messages after the latest timestamp
    results = service.users().messages().list(
        userId='me',
        labelIds=['INBOX'],
        maxResults=500,
        q=f'after:{timestamp}'
    ).execute()
    
    messages = results.get('messages', [])
    print(f"Fetching new emails after {latest_date}, Found {len(messages) if messages else 0} new emails")
    
    if not messages:
        return []

    #Process messages in batches
    email_details_list = []
    BATCH_SIZE = 50
    print("processing emails & Storing them in the Database, please wait")
    for i in range(0, len(messages), BATCH_SIZE):
        batch_messages = messages[i:i + BATCH_SIZE]
        
       
        bulks_messages= []
        for message in batch_messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            email_details = get_email_details(msg)
            email_details_list.append(email_details)
            bulks_messages.append(Email(**email_details))
        
        time.sleep(0.5)  # rate limiting

    try:
        session.bulk_save_objects(bulks_messages)
        session.commit()
        print(f"Attempted to insert {len(email_details_list)} emails")
        return email_details_list

    except Exception as e:
        print(f"Error during bulk insert: {e}")
        session.rollback()
        return []

def fetch_emails_from_db():
    print("Fetching emails from database")
    emails = session.query(Email).all()
    session.close()
    return emails

def perform_rules():
    print("Starting to perform rules")
    emails = fetch_emails_from_db()
    for email in emails:
        print("Processing email: " + email.message_id)
        process_rules(email)
    print("Finished performing rules on " + str(len(emails)) + " emails")

def get_rule_conditions():
    """Get all conditions from rules.json"""
    if not os.path.exists('email_rules.json'):
        return []
    
    with open('email_rules.json', 'r') as f:
        rules_data = json.load(f)
    
    all_conditions = []
    for rule in rules_data['rules']:
        all_conditions.extend(rule['conditions'])
    return all_conditions

def fetch_filtered_emails():
    """Fetch only emails from the Database that match rule conditions"""
    print("Fetching filtered emails from database")
    
    # Get all rule conditions
    rule_conditions = get_rule_conditions()
    if not rule_conditions:
        print("No rules found in email_rules.json")
        return []
    
    # Start with all emails
    query = session.query(Email)
    
    # Apply filters based on rule conditions
    for condition in rule_conditions:
        field = condition['field'].lower()
        operator = condition['operator'].lower()
        value = condition['value']
        
        if field in ['sender', 'subject', 'body']:
            if operator == 'contains':
                query = query.filter(getattr(Email, field).like(f'%{value}%'))
            elif operator == 'does_not_contain':
                query = query.filter(~getattr(Email, field).like(f'%{value}%'))
            elif operator == 'equals':
                query = query.filter(getattr(Email, field) == value)
            elif operator == 'does_not_equal':
                query = query.filter(getattr(Email, field) != value)
        
        elif field == 'received_date':
            current_date = datetime.now()
            if operator == 'greater_than_days':
                date_threshold = current_date - timedelta(days=int(value))
                query = query.filter(Email.received_date < date_threshold)
            elif operator == 'less_than_days':
                date_threshold = current_date - timedelta(days=int(value))
                query = query.filter(Email.received_date > date_threshold)
            elif operator == 'greater_than_months':
                date_threshold = current_date - timedelta(days=int(value) * 30)
                query = query.filter(Email.received_date < date_threshold)
            elif operator == 'less_than_months':
                date_threshold = current_date - timedelta(days=int(value) * 30)
                query = query.filter(Email.received_date > date_threshold)
    
    # Execute query and get results
    filtered_emails = query.all()
    print(f"Found {len(filtered_emails)} emails matching rule conditions")
    return filtered_emails

def perform_filtered_rules():
    """Perform rules only on filtered emails"""
    print("Starting to perform rules on filtered emails")
    
    # Get filtered emails
    filtered_emails = fetch_filtered_emails()
    
    # Process rules on filtered emails
    for email in filtered_emails:
        print(f"Processing email: {email.message_id}")
        process_rules(email)
    
    print(f"Finished performing rules on {len(filtered_emails)} emails")

def main():
    # Fetch new emails from Gmail and store in database
    email_list = get_inbox_messages()
    print(f"Processed {len(email_list)} new emails")
    
    # Perform rules on filtered emails from the database
    perform_filtered_rules()

if __name__ == '__main__':
    main()