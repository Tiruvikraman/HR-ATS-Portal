from flask import Flask, render_template, request, jsonify, send_file
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import gridfs
from io import BytesIO
import certifi
import uuid

from email_agent import send_emails
from datetime import datetime, timedelta
import uuid
from email_service import EmailService
from other_functions import download_resume,generatecoding

email_service = EmailService(
    gmail_user="roshauninfant@gmail.com",
    gmail_app_password="kpvo hgsg jfjs qoky"
)
app = Flask(__name__)

# MongoDB connection with SSL settings
MONGODB_URI = "mongodb+srv://roshauninfant:8bYufQzyPgtLWJRE@slackbot.loflbu5.mongodb.net/?retryWrites=true&w=majority&appName=slackbot&tlsAllowInvalidCertificates=true"
client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
db = client['Resume']
fs = gridfs.GridFS(db)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/post-jobs')
def post_jobs():
    return render_template('job_posting.html')
@app.route('/get_coding_question')
def get_coding_question():
    return jsonify({"question": generatecoding()})

@app.route('/technical.html')
def technical_page():
    return render_template('technical.html')
@app.route('/dashboard')
def dashboard():
    try:
        # Get unique job IDs from ai_processed_candidates
        unique_jobs = db.ai_processed_candidates.distinct('job_id')
        jobs_data = []

        # Get candidate counts for each job
        for job_id in unique_jobs:
            total_candidates = db.ai_processed_candidates.count_documents({"job_id": job_id})
            shortlisted = db.ai_processed_candidates.count_documents({
                "job_id": job_id,
                "status": "shortlisted"
            })

            jobs_data.append({
                "job_id": job_id,
                "title": "Software Engineer",  # You can customize this
                "department": "Engineering",  # You can customize this
                "total_candidates": total_candidates,
                "shortlisted_count": shortlisted,
                "status": "active"
            })

        print("Jobs data:", jobs_data)
        return render_template('dashboard.html', job_postings=jobs_data)
    except Exception as e:
        print(f"Dashboard Error: {e}")
        return f"Error loading dashboard: {str(e)}", 500


@app.route('/candidate/<candidate_id>')
def get_candidate_details(candidate_id):
    try:
        # Convert string ID to ObjectId
        candidate_id = candidate_id

        # Find the candidate with proper null checks
        candidate = db.ai_processed_candidates.find_one({"_id": candidate_id})
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        # Get all interviews for the candidate
        interviews = list(db.interviews.find({"candidate_id": candidate_id}))

        # Ensure all ObjectId fields are converted to strings
        candidate['_id'] = str(candidate['_id'])
        if 'resume_id' in candidate:
            candidate['resume_id'] = str(candidate['resume_id'])

        # Ensure candidate_info exists with default values
        if 'candidate_info' not in candidate:
            candidate['candidate_info'] = {
                'name': 'Not Available',
                'email': 'Not Available',
                'phone': None,
                'experience': None,
                'current_company': None
            }

        # Ensure ai_evaluation exists with default values
        if 'ai_evaluation' not in candidate:
            candidate['ai_evaluation'] = {
                'confidence_score': None,
                'matching_skills': [],
                'missing_skills': []
            }

        # Process interviews
        processed_interviews = []
        for interview in interviews:
            interview['_id'] = str(interview['_id'])
            interview['candidate_id'] = str(interview['candidate_id'])

            # Format date if exists
            if 'scheduled_date' in interview and interview['scheduled_date']:
                interview['scheduled_date'] = interview['scheduled_date'].strftime('%Y-%m-%d %H:%M')
            else:
                interview['scheduled_date'] = 'Not scheduled'

            processed_interviews.append(interview)

        return jsonify({
            "candidate": candidate,
            "interviews": processed_interviews
        })
    except Exception as e:
        print(f"Error in get_candidate_details: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/job/<job_id>')
def view_job(job_id):
    try:
        print(f"Viewing job: {job_id}")

        # Get and segregate candidates
        shortlisted_candidates = list(db.ai_processed_candidates.find({
            "job_id": job_id,
            "status": {"$in": ["shortlisted", "interview_scheduled", "ai_interview", "tech_interview"]}
        }))

        rejected_candidates = list(db.ai_processed_candidates.find({
            "job_id": job_id,
            "status": "rejected"
        }))

        print(f"Found {len(shortlisted_candidates)} shortlisted and {len(rejected_candidates)} rejected candidates")

        # Process each candidate
        for candidate in shortlisted_candidates + rejected_candidates:
            # Convert ObjectId to string
            candidate_id = candidate['_id']
            candidate['_id'] = str(candidate['_id'])
            candidate['resume_id'] = str(candidate['resume_id'])

            # Check for interview completion if candidate is in ai_interview status
            if candidate['status'] == 'ai_interview':
                interview_result = db.interview_results.find_one({
                    "candidate_id": candidate_id
                })
                candidate['interview_completed'] = bool(interview_result)
            else:
                candidate['interview_completed'] = False

            # Get interview details if any (keeping this for reference)
            interview = db.interviews.find_one({
                "candidate_id": candidate_id
            })

            if interview:
                interview['_id'] = str(interview['_id'])
                interview['candidate_id'] = str(interview['candidate_id'])

                # Safely format scheduled_date
                scheduled_date = interview.get('scheduled_date')
                if isinstance(scheduled_date, datetime):
                    formatted_date = scheduled_date.strftime('%Y-%m-%d %H:%M')
                else:
                    formatted_date = str(scheduled_date)

                candidate['has_interview'] = True
                candidate['interview_data'] = {
                    'type': interview.get('type', 'Not specified'),
                    'scheduled_date': formatted_date,
                    'meeting_link': interview.get('meeting_link', '#'),
                    'streamlit_url': interview.get('streamlit_url', '#')
                }
            else:
                candidate['has_interview'] = False

        job = {
            "job_id": job_id,
            "title": "Software Engineer",
            "department": "Engineering",
            "status": "active",
            "total_candidates": len(shortlisted_candidates) + len(rejected_candidates),
            "shortlisted_count": len(shortlisted_candidates)
        }

        print("Rendering template...")
        return render_template('job_details.html',
                             job=job,
                             shortlisted_candidates=shortlisted_candidates,
                             rejected_candidates=rejected_candidates)

    except Exception as e:
        print(f"View Job Error: {str(e)}")
        return f"Error viewing job: {str(e)}", 500



@app.route('/send_confirmation_emails/<job_id>', methods=['POST'])
def send_shortlist_emails(job_id):
    try:
        # Your Gmail credentials
        gmail_user = "roshauninfant@gmail.com"
        gmail_app_password = "kpvo hgsg jfjs qoky"

        result = send_emails(job_id, "shortlisted", gmail_user, gmail_app_password)

        if result['success']:
            message = f"Successfully sent {result['emails_sent']} emails. "
            if result['skipped_candidates'] > 0:
                message += f"Skipped {result['skipped_candidates']} candidates who already have interviews scheduled."
            if result['failed_emails']:
                message += f"\nFailed to send to: {', '.join(result['failed_emails'])}"

            return jsonify({
                "success": True,
                "message": message,
                "details": result
            })
        else:
            return jsonify({
                "success": False,
                "message": result.get('error', 'Unknown error occurred'),
                "details": result
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@app.route('/send_rejection_emails/<job_id>', methods=['POST'])
def send_reject_emails(job_id):
    try:
        # Your Gmail credentials
        gmail_user = "roshauninfant@gmail.com"
        gmail_app_password = "kpvo hgsg jfjs qoky"

        result = send_emails(job_id, "rejected", gmail_user, gmail_app_password)

        if result['success']:
            message = f"Successfully sent {result['emails_sent']} emails. "
            if result['skipped_candidates'] > 0:
                message += f"Skipped {result['skipped_candidates']} candidates who already have interviews scheduled."
            if result['failed_emails']:
                message += f"\nFailed to send to: {', '.join(result['failed_emails'])}"

            return jsonify({
                "success": True,
                "message": message,
                "details": result
            })
        else:
            return jsonify({
                "success": False,
                "message": result.get('error', 'Unknown error occurred'),
                "details": result
            }), 400

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400


@app.route('/schedule_hr_interview', methods=['POST'])
def schedule_hr_interview():
    try:
        print("Received HR interview scheduling request")
        data = request.json
        candidate_id = data['candidate_id']

        print(f"Scheduling for candidate: {candidate_id}")

        # Get candidate details using ObjectId
        candidate = db.ai_processed_candidates.find_one({"_id": candidate_id})
        if not candidate:
            return jsonify({"success": False, "message": "Candidate not found"}), 404

        # Generate meet link
        meet_id = f"meet-{str(candidate['_id'])[-6:]}"
        meet_link = f"https://meet.google.com/{meet_id}"

        # Create interview document
        interview = {
            "candidate_id": candidate_id,  # Store as ObjectId
            "round_type": "HR Interview",
            "scheduled_date": datetime.now(),
            "meeting_link": meet_link,
            "status": "scheduled",
            "created_at": datetime.now()
        }

        print("Creating interview:", interview)

        # Insert interview
        result = db.interviews.insert_one(interview)

        # Update candidate status
        db.ai_processed_candidates.update_one(
            {"_id": candidate_id},
            {
                "$set": {
                    "status": "interview_scheduled",
                    "last_updated": datetime.now()
                }
            }
        )

        print("Interview scheduled successfully")

        return jsonify({
            "success": True,
            "message": "HR Interview scheduled successfully",
            "meeting_link": meet_link,
            "interview_id": str(result.inserted_id)
        })

    except Exception as e:
        print(f"Error scheduling HR interview: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 400


@app.route('/schedule_ai_interview', methods=['POST'])
def schedule_ai_interview():
    try:
        data = request.json
        candidate_id = data['candidate_id']

        # Get candidate details
        candidate = db.ai_processed_candidates.find_one({"_id": candidate_id})
        if not candidate:
            return jsonify({"success": False, "message": "Candidate not found"}), 404

        # Generate unique interview ID
        interview_id = str(uuid.uuid4())

        # Create interview configuration
        interview_config = {
            "candidate_id": candidate_id,
            "interview_id": interview_id,
            "type": "ai_interview",
            "interview_focus": data.get('interview_focus', 'technical'),
            "depth_level": data.get('depth_level', 'mid'),
            "focus_areas": data.get('focus_areas', []),
            "duration": int(data.get('duration', 30)),
            "special_instructions": data.get('special_instructions', ''),
            "status": "scheduled",
            "streamlit_url": f"http://localhost:8501?interview_id={interview_id}",  # For local testing
            "created_at": datetime.now(),
            "expires_at": datetime.now() + timedelta(days=2)
        }

        # Store in interviews collection
        db.interviews.insert_one(interview_config)

        # Update candidate status
        db.ai_processed_candidates.update_one(
            {"_id": candidate_id},
            {
                "$set": {
                    "status": "ai_interview",
                    "last_updated": datetime.now()
                }
            }
        )

        # Send AI interview email
        candidate_email = candidate['candidate_info']['email']
        interview_url = interview_config['streamlit_url']
        duration = interview_config['duration']

        email_sent = email_service.send_ai_interview_email(candidate_email, interview_url, duration)

        if email_sent:
            return jsonify({
                "success": True,
                "message": "AI Interview scheduled successfully, email sent",
                "interview_url": interview_url
            })
        else:
            return jsonify({"success": False, "message": "AI Interview scheduled, but email sending failed"})

    except Exception as e:
        print(f"Error scheduling AI interview: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 400


@app.route('/schedule_interview', methods=['POST'])
def schedule_interview():
    try:
        data = request.json
        candidate_id = data['candidate_id']
        scheduled_date = datetime.strptime(data['scheduled_date'], '%Y-%m-%dT%H:%M')

        # Create interview document
        interview = {
            "candidate_id": candidate_id,
            "round_type": data['round_type'],
            "scheduled_date": scheduled_date,
            "meeting_link": data['meeting_link'],
            "status": "scheduled",
            "created_at": datetime.now()
        }

        # Insert interview
        db.interviews.insert_one(interview)

        return jsonify({"message": "Interview scheduled successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/view_resume/<resume_id>')
def view_resume(resume_id):
    try:
        # First get the resume document
        resume_doc = db.raw_resumes.find_one({"_id": ObjectId(resume_id)})
        if not resume_doc:
            return "Resume not found", 404

        # Get the file from GridFS
        file_data = fs.get(resume_doc['resume']['file_id'])

        return send_file(
            BytesIO(file_data.read()),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=resume_doc['resume']['filename']
        )
    except Exception as e:
        print(f"Resume Error: {e}")
        return str(e), 400


@app.route('/favicon.ico')
def favicon():
    return '', 204
mail_db = client['Resume']


@app.route('/mail-inbox')
def email_dashboard():
    try:
        # Get all emails from MongoDB
        print(mail_db,"HI")
        job_emails = list(mail_db.email_inbox.find({"mail_type": "Job application"}))
        general_emails = list(mail_db.email_inbox.find({"mail_type": {"$ne": "Job application"}}))
        
        # Convert ObjectId to string for JSON serialization
        for email in job_emails + general_emails:
            email['_id'] = str(email['_id'])
            if 'resume_pdf' in email:
                email['resume_pdf'] = str(email['resume_pdf'])
        
        return render_template('email_dashboard.html', 
                             job_emails=job_emails,
                             general_emails=general_emails)
    except Exception as e:
        print(f"Error loading email dashboard: {str(e)}")
        return str(e), 500


@app.route('/api/get-emails')
def get_emails():
    try:
        job_emails = list(mail_db.emails.find({"mail_type": "Job application"}))
        general_emails = list(mail_db.emails.find({"mail_type": {"$ne": "Job application"}}))
        
        # Convert ObjectId to string
        for email in job_emails + general_emails:
            email['_id'] = str(email['_id'])
            if 'resume_pdf' in email:
                email['resume_pdf'] = str(email['resume_pdf'])
        
        return jsonify({
            "job_emails": job_emails,
            "general_emails": general_emails
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/test_db')
def test_db():
    try:
        candidates = list(db.ai_processed_candidates.find())
        return jsonify({
            "status": "success",
            "candidate_count": len(candidates),
            "first_candidate_id": str(candidates[0]['_id']) if candidates else None
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/download_resumes', methods=['GET'])
def trigger_resume_download():
    try:
        downloaded_files = download_resume()  # This should return a list of candidate names
        return jsonify({
            "status": "success",
            "message": "Resumes downloaded successfully",
            "candidates": downloaded_files  # Ensure frontend uses 'candidates'
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500



if __name__ == '__main__':
    app.run(debug=True, port=5000)
