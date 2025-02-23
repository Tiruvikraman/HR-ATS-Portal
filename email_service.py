import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


class EmailService:
    def __init__(self, gmail_user, gmail_app_password):
        self.gmail_user = gmail_user
        self.gmail_app_password = gmail_app_password

    def send_ai_interview_email(self, candidate_email, interview_url, duration):
        subject = "Your AI Interview Link"

        body = f"""
        Dear Candidate,

        Thank you for your application. You have been selected for an AI-based interview assessment.

        Please click the link below to start your interview:
        {interview_url}

        Important Information:
        - The interview will take approximately {duration} minutes
        - Please ensure a stable internet connection
        - Have your camera and microphone ready if required
        - The link will be valid for 48 hours

        Best of luck!

        Best regards,
        HR Team
        """

        try:
            msg = MIMEMultipart()
            msg['From'] = self.gmail_user
            msg['To'] = candidate_email
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