# Gmail Rules Automation

## Description
A Python script that automates Gmail organization by fetching emails and applying custom rules. It allows you to perform actions on the basis of the rules we can sit in email_rules.json file

What does this script do?

- Fetches new emails from Gmail inbox (only 500 after 1st Jan 2025)
- Stores emails in a local SQLite database
- Applies custom rules with flexible conditions
- Supports multiple actions on matching emails
- Batch processing for better performance to fetch meta data of the emails
- Automatic label creation if it does not exist.

### Supported Rule Conditions
 - (sender, subject, body):
  - contains
  - does_not_contain
  - equals
  - does_not_equal

- (received_date):
  - greater_than_days
  - less_than_days
  - greater_than_months
  - less_than_months

### Supported Actions
- Mark email as read
- Mark email as unread
- Move message to specific folder/label

## How to run this script?

1. Clone the repository:
```bash
git clone this repo
cd gmail-rules-automation
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up Google Gmail API:
   - Go to Google Cloud Console
   - Create a new project
   - Enable Gmail API
   - Create credentials (OAuth 2.0 Client ID) with Desktop app
   - Add mock emails to test the flow
   - Download the client configuration file as `cred.json`

## Configuration

### Email Rules
Create a `email_rules.json` file with your rules:
```json
{
    "rules": [
        {
            "name": "Urgent Rule",
            "match_type": "all",
            "conditions": [
                {
                    "field": "sender",
                    "operator": "contains",
                    "value": "varunjaggiwork@gmail.com"
                },
                {
                    "field": "subject",
                    "operator": "contains",
                    "value": "urgent"
                }
            ],
            "actions": [
                {
                    "type": "move_message",
                    "folder_id": "Important"
                }
            ]
        }
    ]
}
```

## Usage

Run the script:
```bash
python myscript.py
```

The script will:
1. Authenticate with Gmail
2. Fetch new emails since the last run
3. Store them in the local database
4. Apply rules to matching emails
5. Execute specified actions


## Requirements
- Python 3.6+
- Google API Python Client
- SQLAlchemy
- Gmail API credentials

## Limitations
- Maximum 500 emails processed per run
- Gmail API quotas and rate limits apply
- SQLite database for local storage