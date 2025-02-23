import streamlit as st
import requests
from pymongo import MongoClient
import speech_recognition as sr
from datetime import datetime
import certifi
import cv2
import threading
import time


class AIInterviewer:
    def __init__(self):
        # IBM Cloud API setup
        self.url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
        self.auth_url = "https://iam.cloud.ibm.com/identity/token"
        self.apikey = "9FV7l0Jxqe7ceL09MeH_g9bYioIQuABXsr1j1VHbKOpr"

        # MongoDB setup
        MONGODB_URI = "mongodb+srv://roshauninfant:8bYufQzyPgtLWJRE@slackbot.loflbu5.mongodb.net/?retryWrites=true&w=majority&appName=slackbot"
        self.client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
        self.db = self.client['Resume']

        # Question categories
        self.question_categories = [
            "technical_expertise",
            "problem_solving",
            "project_experience",
            "behavioral",
            "role_specific"
        ]

    def get_response(self, question_type, candidate_info, focus_areas, depth_level, special_instructions, category):
        token = self.get_auth_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        prompt = f"""<|start_of_role|>system<|end_of_role|>
        You are an experienced HR interviewer conducting a professional interview. You specialize in asking insightful questions that reveal a candidate's true capabilities and potential.

        Candidate Profile:
        - Experience Level: {candidate_info.get('experience')}
        - Key Skills: {', '.join(candidate_info.get('matching_skills', []))}
        - Focus Areas: {', '.join(focus_areas)}
        - Seniority Level: {depth_level}

        Category: {category}
        Special Instructions: {special_instructions}

        Guidelines for question generation:
        1. For Technical Expertise: Focus on practical application of skills
        2. For Problem Solving: Present real-world scenarios
        3. For Project Experience: Ask about specific achievements and challenges
        4. For Behavioral: Focus on past experiences and decision-making
        5. For Role Specific: Align with the target position requirements

        Generate a single, well-structured interview question that:
        - Is specific to the {category} category
        - Matches the candidate's experience level
        - Allows the candidate to showcase their expertise
        - Encourages detailed responses
        - Avoids yes/no answers
        - Is different from standard interview questions

        Question format: Start with a brief context (if needed) followed by the main question.
        <|end_of_text|>
        <|start_of_role|>assistant<|end_of_role|>"""

        body = {
            "input": prompt,
            "parameters": {
                "decoding_method": "sample",
                "top_k": 50,
                "temperature": 0.7,
                "max_new_tokens": 200,
                "repetition_penalty": 1.2
            },
            "model_id": "ibm/granite-3-8b-instruct",
            "project_id": "4aa39c25-19d7-48c1-9cf6-e31b5c223a1f"
        }

        response = requests.post(self.url, headers=headers, json=body)
        return response.json().get("results", [{}])[0].get("generated_text", "")

    def get_auth_token(self):
        auth_data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self.apikey
        }
        auth_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        auth_response = requests.post(self.auth_url, data=auth_data, headers=auth_headers)
        return auth_response.json().get("access_token")


def get_audio_input():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        st.write("🎤 Listening... Please speak your answer.")
        try:
            # Adjust for ambient noise
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio = r.listen(source, timeout=30, phrase_time_limit=120)
            text = r.recognize_google(audio)
            return text, None
        except sr.WaitTimeoutError:
            return None, "No speech detected. Please try again."
        except sr.UnknownValueError:
            return None, "Could not understand audio. Please try again."
        except sr.RequestError:
            return None, "Could not process speech. Please try text input instead."


def video_feed():
    cap = cv2.VideoCapture(0)
    frame_placeholder = st.empty()

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            st.error("Failed to capture video")
            break
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_placeholder.image(frame, channels="RGB")
        time.sleep(0.03)  # Reduce CPU usage

    cap.release()


def main():
    st.set_page_config(page_title="Professional AI Interview", page_icon="👔")

    # Styling
    st.markdown("""
        <style>
        .main {
            padding: 2rem;
        }
        .stButton button {
            width: 100%;
            border-radius: 5px;
            height: 3em;
        }
        </style>
    """, unsafe_allow_html=True)

    # Initialize interviewer
    interviewer = AIInterviewer()

    # Get interview ID and details
    query_params = st.query_params
    interview_id = query_params.get("interview_id", None)

    if not interview_id:
        st.error("⚠️ Invalid interview link")
        return

    # Get interview and candidate details
    interview = interviewer.db.interviews.find_one({"interview_id": interview_id})
    if not interview:
        st.error("⚠️ Interview not found")
        return

    candidate = interviewer.db.ai_processed_candidates.find_one({"_id": interview["candidate_id"]})
    if not candidate:
        st.error("⚠️ Candidate information not found")
        return

    # Professional welcome message
    st.title("🤝 Professional AI Interview")
    st.write(
        f"Welcome, {candidate['candidate_info']['name']}! We're excited to learn more about your experience and expertise.")

    # Video feed in sidebar
    st.sidebar.title("📹 Video Feed")
    st.sidebar.info("Please ensure your camera is on and you're well-positioned in the frame.")
    if 'video_thread' not in st.session_state:
        st.session_state.video_thread = threading.Thread(target=video_feed, daemon=True)
        st.session_state.video_thread.start()

    # Initialize interview state
    if 'current_question' not in st.session_state:
        st.session_state.current_question = 0
        st.session_state.questions_total = 5
        st.session_state.answers = []
        st.session_state.verbal_questions = [1, 3]  # 2nd and 4th questions
        st.session_state.current_category = None
        st.session_state.verbal_response = None

    # Display progress
    progress = st.progress(st.session_state.current_question / st.session_state.questions_total)
    st.write(f"📝 Question {st.session_state.current_question + 1} of {st.session_state.questions_total}")

    # Generate question based on category
    if st.session_state.current_category is None and st.session_state.current_question < st.session_state.questions_total:
        st.session_state.current_category = interviewer.question_categories[st.session_state.current_question]

    current_q = interviewer.get_response(
        interview.get('interview_focus', 'technical'),
        {
            'experience': candidate['candidate_info'].get('experience'),
            'matching_skills': candidate['ai_evaluation'].get('matching_skills', []),
            'interview_focus': interview.get('interview_focus')
        },
        focus_areas=interview.get('focus_areas', []),
        depth_level=interview.get('depth_level', 'entry'),
        special_instructions=interview.get('special_instructions', ''),
        category=st.session_state.current_category
    )

    # Display question with styling
    st.markdown(f"### Question {st.session_state.current_question + 1}:")
    st.write(current_q)

    # Handle answer input
    if st.session_state.current_question in st.session_state.verbal_questions:
        col1, col2 = st.columns(2)

        with col1:
            if st.session_state.verbal_response is None:
                if st.button("🎤 Answer Verbally"):
                    answer, error = get_audio_input()
                    if error:
                        st.error(error)
                    else:
                        st.session_state.verbal_response = answer
                        st.rerun()

            if st.session_state.verbal_response is not None:
                st.write("Your answer (transcribed):", st.session_state.verbal_response)
                if st.button("✅ Submit Answer"):
                    st.session_state.answers.append({
                        "question": current_q,
                        "answer": st.session_state.verbal_response,
                        "category": st.session_state.current_category
                    })
                    st.session_state.current_question += 1
                    st.session_state.current_category = None
                    st.session_state.verbal_response = None
                    st.rerun()
                if st.button("🔄 Record Again"):
                    st.session_state.verbal_response = None
                    st.rerun()

        with col2:
            if st.button("⌨️ Switch to Text Input"):
                st.session_state.verbal_questions.remove(st.session_state.current_question)
                st.session_state.verbal_response = None
                st.rerun()
    else:
        answer = st.text_area("Your answer:", height=150)
        if st.button("Submit Answer"):
            if answer.strip():
                st.session_state.answers.append({
                    "question": current_q,
                    "answer": answer,
                    "category": st.session_state.current_category
                })
                st.session_state.current_question += 1
                st.session_state.current_category = None
                st.rerun()
            else:
                st.warning("Please provide an answer before continuing.")

    # Interview completion
    if st.session_state.current_question >= st.session_state.questions_total:
        st.success("Interview completed! Thank you for your time.")

        # Save interview results to MongoDB
        interview_results = {
            "interview_id": interview_id,
            "candidate_id": candidate["_id"],
            "completion_time": datetime.now(),
            "answers": st.session_state.answers
        }
        interviewer.db.interview_results.insert_one(interview_results)

        st.balloons()

        # Display completion message
        st.markdown("""
        ### Next Steps
        - Our team will carefully review your responses
        - You will receive feedback within 2-3 business days
        - If you have any questions, please contact your hiring manager

        Thank you for participating in our AI-assisted interview process!
        """)

        return


if __name__ == "__main__":
    main()
