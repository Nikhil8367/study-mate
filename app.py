import streamlit as st
import os
import fitz
import time
from pymongo import MongoClient
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from bson.objectid import ObjectId

# =========================
# LOAD ENV
# =========================
load_dotenv()

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="StudyMate", layout="wide", initial_sidebar_state="collapsed")

# =========================
# MongoDB Setup
# =========================
client = MongoClient(os.getenv("MONGO_URI"))
db = client["pdf_db"]
users_col = db["users"]
paragraphs_col = db["paragraphs"]
chats_col = db["chats"]
gemini_col = db["gemini_chats"]

# =========================
# Gemini Setup
# =========================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# =========================
# Session State
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "qa_history" not in st.session_state:
    st.session_state.qa_history = []
if "gemini_history" not in st.session_state:
    st.session_state.gemini_history = []
if "selected_response" not in st.session_state:
    st.session_state.selected_response = None

# =========================
# FUNCTIONS
# =========================

def extract_paragraphs_from_pdf(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    paragraphs = []
    for page in doc:
        text = page.get_text()
        paras = [p.strip() for p in text.split('\n\n') if p.strip()]
        paragraphs.extend(paras)
    return paragraphs


def signup_user(username, password):
    if users_col.find_one({"username": username}):
        return False, "User already exists"

    users_col.insert_one({
        "username": username,
        "password": generate_password_hash(password)
    })

    return True, None


def login_user(username, password):
    user = users_col.find_one({"username": username})
    if user and check_password_hash(user["password"], password):
        load_history(username)
        return True, None
    return False, "Invalid credentials"


def load_history(username):
    pdf_chats = list(chats_col.find({"username": username}).sort("timestamp", -1))
    gemini_chats = list(gemini_col.find({"username": username}).sort("timestamp", -1))

    st.session_state.qa_history = [
        (str(c["_id"]), c["question"], c["answer"], c.get("matched_paragraphs", []))
        for c in pdf_chats
    ]

    st.session_state.gemini_history = [
        (str(c["_id"]), c["question"], c["answer"])
        for c in gemini_chats
    ]


def upload_pdfs(files, username):
    paragraphs_col.delete_many({"username": username})

    for file in files:
        paragraphs = extract_paragraphs_from_pdf(file.read())
        for i, para in enumerate(paragraphs):
            paragraphs_col.insert_one({
                "username": username,
                "index": i,
                "text": para
            })


def ask_pdf(question, username):
    user_paras = list(paragraphs_col.find({"username": username}))
    if not user_paras:
        return None, []

    all_paragraphs = [doc["text"] for doc in user_paras]

    keywords = question.lower().split()
    scored = []

    for para in all_paragraphs:
        score = sum(word in para.lower() for word in keywords)
        if score > 0:
            scored.append((para, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_paragraphs = [p[0] for p in scored[:3]] if scored else all_paragraphs[:3]

    context = "\n\n".join(top_paragraphs)

    prompt = f"""
Answer using only context.

Context:
{context}

Question: {question}
"""

    response = model.generate_content(prompt)
    answer = response.text

    result = chats_col.insert_one({
        "username": username,
        "question": question,
        "answer": answer,
        "matched_paragraphs": top_paragraphs,
        "timestamp": time.time()
    })

    return str(result.inserted_id), answer, top_paragraphs


def ask_gemini(message, username):
    response = model.generate_content(message)
    reply = response.text

    result = gemini_col.insert_one({
        "username": username,
        "question": message,
        "answer": reply,
        "timestamp": time.time()
    })

    return str(result.inserted_id), reply


def delete_chat(chat_id):
    chats_col.delete_one({"_id": ObjectId(chat_id)})
    gemini_col.delete_one({"_id": ObjectId(chat_id)})

# =========================
# UI Styling
# =========================

st.markdown("""
<style>
.chat-bubble {
    color: black;
    padding:15px;
    border-radius:15px;
    margin-bottom:10px;
}
.user-bubble {
    background:#d1f0e1;
}
.bot-bubble {
    background:white;
}
</style>
""", unsafe_allow_html=True)

# =========================
# LOGIN
# =========================

if not st.session_state.logged_in:
    st.title("🔐 StudyMate Login")

    mode = st.radio("Choose", ["Login", "Signup"], horizontal=True)

    uname = st.text_input("Username")
    pwd = st.text_input("Password", type="password")

    if st.button("Continue"):
        if mode == "Login":
            success, err = login_user(uname, pwd)
        else:
            success, err = signup_user(uname, pwd)

        if success:
            st.session_state.logged_in = True
            st.session_state.username = uname
            st.rerun()
        else:
            st.error(err)

    st.stop()

# =========================
# SIDEBAR
# =========================

with st.sidebar:
    st.write("👤", st.session_state.username)

    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

# =========================
# PDF Upload
# =========================

st.title("🎓 StudyMate")

uploaded = st.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded:
    if st.button("Upload"):
        upload_pdfs(uploaded, st.session_state.username)
        st.success("Uploaded successfully ✅")

# =========================
# Ask PDF
# =========================

question = st.text_input("Ask from PDF")

if st.button("Ask PDF"):
    chat_id, answer, refs = ask_pdf(question, st.session_state.username)

    st.session_state.qa_history.append((chat_id, question, answer, refs))
    st.session_state.selected_response = (question, answer, refs)

# =========================
# Gemini Chat
# =========================

gemini_q = st.text_input("Ask Gemini")

if st.button("Ask Gemini"):
    gid, reply = ask_gemini(gemini_q, st.session_state.username)

    st.session_state.gemini_history.append((gid, gemini_q, reply))

# =========================
# Show PDF Response
# =========================

if st.session_state.selected_response:
    q, a, refs = st.session_state.selected_response

    st.markdown(f"<div class='chat-bubble user-bubble'>{q}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='chat-bubble bot-bubble'>{a}</div>", unsafe_allow_html=True)

    for r in refs:
        st.info(r)

# =========================
# Gemini History
# =========================

for gid, q, a in reversed(st.session_state.gemini_history):
    st.markdown(f"<div class='chat-bubble user-bubble'>{q}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='chat-bubble bot-bubble'>{a}</div>", unsafe_allow_html=True)