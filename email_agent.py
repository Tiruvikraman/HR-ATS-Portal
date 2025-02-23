import requests
from typing import Dict, Any
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pymongo import MongoClient
import certifi

# MongoDB connection
MONGODB_URI = "mongodb+srv://roshauninfant:8bYufQzyPgtLWJRE@slackbot.loflbu5.mongodb.net/?retryWrites=true&w=majority&appName=slackbot"
client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
db = client['Resume']


class EmailAgent:
    def __init__(self, gmail_user, gmail_app_password):
        self.url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
        self.gmail_user = gmail_user
        self.gmail_app_password = gmail_app_password
        self.auth_token = self.get_ibm_auth_token()

    def get_ibm_auth_token(self):
        """Fetch a valid IBM IAM access token."""
        auth_url = "https://iam.cloud.ibm.com/identity/token"
        auth_data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": "9FV7l0Jxqe7ceL09MeH_g9bYioIQuABXsr1j1VHbKOpr"
        }
        auth_headers = {"Content-Type": "application/x-www-form-urlencoded"}

        auth_response = requests.post(auth_url, data=auth_data, headers=auth_headers)
        auth_token = auth_response.json().get("access_token")

        if not auth_token:
            raise Exception("Failed to retrieve access token: " + str(auth_response.text))

        return auth_token

    def generate_email(self, candidate_info: Dict[str, Any], task: str) -> str:
        email_prompt = f"""<|start_of_role|>system<|end_of_role|>
You are an HR Email Assistant responsible for drafting professional emails.
Your task is to generate a {task} email for the candidate.

Generate a professional, well-structured email that clearly communicates the {task} message.
Consider the specific context and requirements of a {task} email in the hiring process.
Maintain formal business email standards while keeping an appropriate tone for the {task}.

Use these candidate details:
- Name: {candidate_info['candidate_info']['name']}
- Position: Software Engineer
- Company: ABC Company Inc
- Task: {task}

Requirements for the email:
1. Clear and direct communication about the {task}
2. Professional and appropriate tone for the specific {task}
3. Any necessary next steps or actions required from the candidate
4. Professional closing with name Roshaun - HR - ABC Company Inc

Return only the email content without any explanations or meta text.
<|end_of_text|>
<|start_of_role|>assistant<|end_of_role|>"""

        body = {
            "input": email_prompt,
            "parameters": {
                "decoding_method": "greedy",
                "max_new_tokens": 900,
                "min_new_tokens": 0,
                "repetition_penalty": 1
            },
            "model_id": "ibm/granite-3-8b-instruct",
            "project_id": "4aa39c25-19d7-48c1-9cf6-e31b5c223a1f"
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.auth_token}"
        }

        try:
            response = requests.post(self.url, headers=headers, json=body)

            if response.status_code != 200:
                raise Exception(f"API Error: {response.text}")

            email_content = response.json()['results'][0]['generated_text']
            return email_content

        except Exception as e:
            print(f"Error generating email: {str(e)}")
            return None

    def send_email(self, to_email: str, subject: str, body: str) -> bool:
        try:
            msg = MIMEMultipart()
            msg['From'] = self.gmail_user
            msg['To'] = to_email
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(self.gmail_user, self.gmail_app_password)
            server.send_message(msg)
            server.quit()

            return True
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return False


def send_emails(job_id: str, task: str, gmail_user: str, gmail_app_password: str, candidate_list: list = None) -> Dict:
    try:
        # Get candidates based on parameter or status
        if candidate_list:
            # If candidate list is provided, get those specific candidates
            candidates = list(db.ai_processed_candidates.find({
                "job_id": job_id,
                "_id": {"$in": candidate_list}
            }))
        else:
            # If no candidate list, get all candidates with matching status
            candidates = list(db.ai_processed_candidates.find({
                "job_id": job_id,
                "status": task
            }))

        print(f"Found {len(candidates)} candidates for {task}")

        if not candidates:
            return {
                "success": False,
                "error": f"No candidates found for {task} emails"
            }

        email_agent = EmailAgent(gmail_user, gmail_app_password)
        emails_sent = 0
        failed_emails = []
        skipped_candidates = 0

        for candidate in candidates:
            # Skip if candidate already received this type of email
            if db.email_communications.find_one({
                "candidate_id": candidate['_id'],
                "email_type": task,
                "status": "sent"
            }):
                skipped_candidates += 1
                continue

            print(f"Processing candidate: {candidate['candidate_info']['email']}")

            email_content = email_agent.generate_email(candidate, task)
            if not email_content:
                print(f"Email content generation failed for {candidate['candidate_info']['email']}")
                continue

            success = email_agent.send_email(
                to_email=candidate['candidate_info']['email'],
                subject=f"ABC Company Inc | {task.replace('_', ' ').title()} Update",
                body=email_content
            )

            print(f"Email sent: {'Success' if success else 'Failed'} for {candidate['candidate_info']['email']}")

            # Store email record in MongoDB
            email_record = {
                "candidate_id": candidate['_id'],
                "job_id": job_id,
                "email_type": task,
                "email_content": email_content,
                "sent_date": datetime.now(),
                "status": "sent" if success else "failed"
            }
            db.email_communications.insert_one(email_record)

            if success:
                emails_sent += 1
            else:
                failed_emails.append(candidate['candidate_info']['email'])

        return {
            "success": True,
            "emails_sent": emails_sent,
            "failed_emails": failed_emails,
            "skipped_candidates": skipped_candidates,
            "total_candidates": len(candidates)
        }

    except Exception as e:
        print(f"Error sending emails: {str(e)}")
        return {"success": False, "error": str(e)}


