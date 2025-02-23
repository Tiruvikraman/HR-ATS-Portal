import requests 
import os
import gridfs
from pymongo import MongoClient

def download_resume():
    # MongoDB connection
    uri = "mongodb+srv://roshauninfant:8bYufQzyPgtLWJRE@slackbot.loflbu5.mongodb.net/?retryWrites=true&w=majority&appName=slackbot&tlsAllowInvalidCertificates=true"
    client = MongoClient(uri)
    db = client["Resume"]
    fs = gridfs.GridFS(db)

    collection = db["raw_resumes"]

    # Create a directory for saving resumes
    download_dir = "downloaded_resumes"
    os.makedirs(download_dir, exist_ok=True)

    downloaded_files = []  # Store filenames for UI

    # Fetch and download files
    for doc in collection.find():
        file_id = doc["resume"]["file_id"]
        filename = doc["resume"]["filename"]

        # Retrieve the file from GridFS
        file_data = fs.get(file_id)

        # Save the file locally
        file_path = os.path.join(download_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file_data.read())

        downloaded_files.append(filename)

    print("All resumes downloaded successfully!")
    return downloaded_files  # Return filenames for UI

def screenresume():
    print
    # IBM Granite AI Authentication
    def get_ibm_auth_token(api_key):
        auth_url = "https://iam.cloud.ibm.com/identity/token"
        auth_data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key
        }
        auth_headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(auth_url, data=auth_data, headers=auth_headers)
        return response.json().get("access_token")

    # Extract text from Word documents
    def extract_text_from_docx(file_path):
        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])

    # Construct a powerful AI prompt
    def generate_prompt(resume_text, job_id, _id):
        return f"""
        <|start_of_role|>system<|end_of_role|>You are a highly intelligent AI model specialized in resume screening for hiring purposes. You analyze candidate resumes against job descriptions, extracting key information and evaluating how well they match.

        JOB Description: Software engineer/developer

        Below is a candidate's resume. Extract structured information such as name, email, phone, experience, current company, and 5 key skills. Then, evaluate the candidate based on the job description.

        **Confidence Score Guidelines:**
        - **90 - 100 (Highly Recommended):** Strong alignment with job requirements, possesses most required skills and relevant experience, ideal for shortlisting.
        - **75 - 89 (Recommended):** Good match with the job role, some missing or secondary skills but still a strong candidate.
        - **50 - 74 (Considered):** Partial match, lacks some key skills but has relevant experience.
        - **Below 50 (Not Recommended):** Does not meet core job requirements, significant skill gaps.

        Resume:
        {resume_text}

        Example output format:
        {{
            "_id": "{_id}",
            "job_id": "{job_id}",
            "resume_id": "{_id}",
            "candidate_info": {{
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "+1234567890",
                "experience": "5 years",
                "current_company": "Tech Corp"
            }},
            "ai_evaluation": {{
                "confidence_score": 85,
                "matching_skills": ["Python", "MongoDB", "AWS"], # Return only top 8 skills
                "missing_skills": ["GraphQL"],
                "shortlist_reasons": [
                    "Strong technical match",
                    "Relevant experience"
                ] # Return only top 4 reasons
            }},
            "status": "shortlisted", # 'shortlisted' if confidence_score >= 65 else 'rejected',no other words
            "created_at": "{datetime.now().isoformat()}"
        }}
        <|end_of_role|>"""


    # Call IBM Granite AI
    def analyze_resume_with_ai(auth_token, prompt):
        url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        }
        body = {
            "input": prompt,
            "parameters": {"decoding_method": "greedy", "max_new_tokens": 900, "repetition_penalty": 1},
            "model_id": "ibm/granite-3-8b-instruct",
            "project_id": "4aa39c25-19d7-48c1-9cf6-e31b5c223a1f"
        }
        
        response = requests.post(url, headers=headers, json=body)
        return response.json().get("results", [{}])[0].get("generated_text", "{}")

    # MongoDB Connection (for later use if needed)
    client = MongoClient("mongodb+srv://roshauninfant:8bYufQzyPgtLWJRE@slackbot.loflbu5.mongodb.net/?retryWrites=true&w=majority")
    db = client["Resume"]
    collection = db["raw_resumes"]  # Assuming you have the collection with raw resumes

    # Process resumes
    resume_folder =download_resume()
    resume_folder='downloaded_resumes'
    api_key = "9FV7l0Jxqe7ceL09MeH_g9bYioIQuABXsr1j1VHbKOpr"  # Replace with your actual API key
    auth_token = get_ibm_auth_token(api_key)

    if not auth_token:
        raise Exception("Failed to retrieve IBM auth token")

    job_id = "SDE001"
    output = []
    print('hi',os.listdir(resume_folder))
    for filename in os.listdir(resume_folder):
        if filename.endswith(".docx"):
            file_path = os.path.join(resume_folder, filename)

            # Extract text from resume
            resume_text = extract_text_from_docx(file_path)

            # Find existing ObjectId based on the resume filename or other criteria
            existing_document = collection.find_one({"resume.filename": filename})
            
            if not existing_document:
                print(f"Error: No document found for {filename}")
                continue
            
            _id = str(existing_document['_id'])  # Use the existing _id from MongoDB

            # Generate AI prompt with existing _id
            prompt = generate_prompt(resume_text, job_id, _id)

            # Get AI analysis
            ai_response = analyze_resume_with_ai(auth_token, prompt)
            print(ai_response)
            try:
                ai_data = eval(ai_response)  # Convert AI output to dict (use eval safely or json.loads if needed)
                output.append(ai_data)

                # Update the existing document in MongoDB with the AI evaluation results
                # print(_id,filename)
                # print(f"Processed and saved: {filename}")
            except Exception as e:
                print(f"Error processing {filename}: {e}")

    collection = db["ai_processed_candidates"]  # New collection for storing JSON data

    # Delete existing data in the collection
    collection.delete_many({})


    # Insert JSON data into MongoDB
    if isinstance(output, list):
        collection.insert_many(output)
    else:
        collection.insert_one(output)
    collection.update_many({"status": "considered"}, {"$set": {"status": "rejected"}})


    print("output.json successfully saved to MongoDB!")



import requests
def generatecoding():
    # IBM Granite AI Authentication
    def get_ibm_auth_token(api_key):
        auth_url = "https://iam.cloud.ibm.com/identity/token"
        auth_data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key
        }
        auth_headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(auth_url, data=auth_data, headers=auth_headers)
        return response.json().get("access_token")



    # Construct a powerful AI prompt
    def generate_prompt(job_title ):
        return f"""
        <|start_of_role|>system<|end_of_role|>You are an advanced AI specializing in technical hiring and coding assessments. Your task is to generate two high-quality coding question for evaluating candidates applying for the role of {job_title}. 

        The problem should be designed to assess proficiency in {job_title} and should include:

        1. **Problem Description**: A clear and concise problem statement that describes the coding task.
        2. **Input Format**: A detailed explanation of the expected input.
        3. **Output Format**: A description of the expected output.
        4. **Constraints**: Reasonable constraints on input values to ensure efficiency.
        5. **Test Cases**: At most 3 sample test cases with explanations.

        Ensure that the problem is relevant to real-world scenarios particularly Leetcode Medium DSA problem for a {job_title} and effectively measures problem-solving skills.

        <|end_of_role|>
        """



    # Call IBM Granite AI
    def analyze_resume_with_ai(auth_token, prompt):
        url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}"
        }
        body = {
            "input": prompt,
            "parameters": {"decoding_method": "greedy", "max_new_tokens": 900, "repetition_penalty": 1},
            "model_id": "ibm/granite-3-8b-instruct",
            "project_id": "4aa39c25-19d7-48c1-9cf6-e31b5c223a1f"
        }
        
        response = requests.post(url, headers=headers, json=body)
        return response.json().get("results", [{}])[0].get("generated_text", "{}")

    
    api_key = "9FV7l0Jxqe7ceL09MeH_g9bYioIQuABXsr1j1VHbKOpr"  # Replace with your actual API key
    auth_token = get_ibm_auth_token(api_key)

    
    prompt = generate_prompt("Software developer")

    # Get AI analysis
    ai_response = analyze_resume_with_ai(auth_token, prompt)
    print(ai_response)
    return ai_response