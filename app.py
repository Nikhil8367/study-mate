import streamlit as st
import requests
import time

# === Configuration ===
BACKEND_URL = "https://study-mate-29i6.onrender.com"
st.set_page_config(page_title="StudyMate", layout="wide", initial_sidebar_state="collapsed")

# === Session State Initialization ===
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "qa_history" not in st.session_state:
    st.session_state.qa_history = []
if "selected_response" not in st.session_state:
    st.session_state.selected_response = None

# === Styling ===
st.markdown("""
<style>
html, body, .main {
    background: linear-gradient(to right, #e0eafc, #cfdef3);
    font-family: 'Segoe UI', sans-serif;
}
.header-title {
    text-align: center;
    font-size: 36px;
    font-weight: bold;
    margin-top: 20px;
    color: #2c3e50;
}
.subheading {
    text-align: center;
    font-size: 18px;
    margin-bottom: 30px;
    color: #34495e;
}
.section {
    max-width: 850px;
    margin: auto;
    background: rgba(255, 255, 255, 0.65);
    backdrop-filter: blur(14px);
    border-radius: 20px;
    padding: 30px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.05);
}
.chat-bubble {
    padding: 15px 20px;
    border-radius: 20px;
    margin-bottom: 15px;
    max-width: 85%;
    word-wrap: break-word;
    font-size: 16px;
}
.user-bubble {
    color:black;
    background-color: #d1f0e1;
    align-self: flex-end;
    margin-left: auto;
}
.bot-bubble {
    color:black;
    background-color: #ffffff;
    border: 1px solid #ddd;
    align-self: flex-start;
    margin-right: auto;
}
.reference {
    color:black;
    background-color: #fef9e7;
    padding: 10px 15px;
    border-radius: 10px;
    font-size: 15px;
    margin-top: 8px;
    border-left: 4px solid #f4c430;
}
.sidebar-question {
    cursor: pointer;
    padding: 8px 12px;
    border-radius: 10px;
    margin: 5px 0;
    background-color: #f0f8ff;
}
.sidebar-question:hover {
    background-color: #d6eaff;
}
.footer {
    text-align: center;
    margin-top: 100px;
    color: #666;
    font-size: 14px;
}
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# === Authentication Functions ===
def login_user(username, password):
    with st.spinner("🔐 Logging in..."):
        res = requests.post(f"{BACKEND_URL}/login", json={"username": username, "password": password})
        if res.status_code == 200:
            h = requests.get(f"{BACKEND_URL}/history/{username}")
            if h.status_code == 200:
                history = h.json()
                st.session_state.qa_history = [(q["question"], q["answer"], q.get("matched_paragraphs", [])) for q in history]
            return True, None
        return False, res.json().get("error")

def signup_user(username, password):
    with st.spinner("📝 Creating account..."):
        res = requests.post(f"{BACKEND_URL}/signup", json={"username": username, "password": password})
        return res.status_code == 200, res.json().get("error")

# === Login / Signup ===
if not st.session_state.logged_in:
    st.markdown("## 🔐 Login / Signup")
    auth_mode = st.radio("Choose", ["Login", "Signup"], horizontal=True)
    uname = st.text_input("Username")
    pwd = st.text_input("Password", type="password")
    btn = st.button("Continue")

    if btn:
        if not uname or not pwd:
            st.warning("Please enter username and password.")
        else:
            if auth_mode == "Login":
                success, err = login_user(uname, pwd)
            else:
                success, err = signup_user(uname, pwd)

            if success:
                st.session_state.logged_in = True
                st.session_state.username = uname
                st.success(f"Welcome, {uname}!")
                st.rerun()
            else:
                st.error(err or "Authentication failed.")
    st.stop()

# === Sidebar ===
with st.sidebar:
    st.markdown(f"<h4>👤 {st.session_state.username}</h4>", unsafe_allow_html=True)

    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.qa_history = []
        st.session_state.gemini_history = []
        st.session_state.selected_response = None
        st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("### 💬 Chat History", unsafe_allow_html=True)

    has_any_history = st.session_state.qa_history or st.session_state.get("gemini_history")

    if has_any_history:
        combined_history = []

        for idx, g in enumerate(reversed(st.session_state.get("gemini_history", []))):
            combined_history.append({"type": "gemini", "question": g["question"], "answer": g["answer"], "index": idx})

        for idx, (q, a, refs) in enumerate(reversed(st.session_state.qa_history)):
            combined_history.append({"type": "pdf", "question": q, "answer": a, "refs": refs, "index": idx})

        for i, item in enumerate(combined_history):
            label = f"🧠 {item['question']}" if item["type"] == "gemini" else f"📄 {item['question']}"
            if st.button(label, key=f"hist_btn_{i}"):
                if item["type"] == "gemini":
                    st.session_state.selected_response = (item["question"], item["answer"], None)
                else:
                    st.session_state.selected_response = (item["question"], item["answer"], item["refs"])
                st.rerun()
    else:
        st.info("No chats yet. Start by asking a question.")

# === Header ===
st.markdown("<div class='header-title'>🎓 StudyMate: Smart Study Assistant</div>", unsafe_allow_html=True)
st.markdown("<div class='subheading'>Ask questions directly from your uploaded PDF notes!</div>", unsafe_allow_html=True)

# === Upload PDFs ===
st.markdown("### 📂 Upload PDF files")
uploaded_files = st.file_uploader("Drag and drop files here", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    with st.spinner("📤 Uploading PDFs..."):
        try:
            pdf_payload = [("files", (f.name, f, "application/pdf")) for f in uploaded_files]
            data = {"username": st.session_state.username}
            upload_resp = requests.post(f"{BACKEND_URL}/upload", files=pdf_payload, data=data)
            if upload_resp.status_code == 200:
                st.success("✅ PDFs uploaded successfully!")
            else:
                st.error("❌ Upload failed.")
        except Exception as e:
            st.error(f"🔌 Upload error: {e}")

# === Ask a Question ===
st.markdown("### 💬 Ask a Question")
with st.form("chat_form", clear_on_submit=True):
    question = st.text_input("Type your question", placeholder="What is photosynthesis?")
    submit = st.form_submit_button("Ask")

    if submit and question.strip():
        with st.spinner("🤖 Thinking..."):
            try:
                r = requests.post(f"{BACKEND_URL}/ask", json={"question": question, "username": st.session_state.username})
                if r.status_code == 200:
                    result = r.json()
                    answer = result.get("answer", "No answer found.")
                    refs = result.get("matched_paragraphs", [])
                    st.session_state.qa_history.append((question, answer, refs))
                    st.session_state.selected_response = (question, answer, refs)
                    st.rerun()
                elif r.status_code == 404:
                    st.warning("📭 No answer found. Upload PDFs first.")
                else:
                    st.error("❌ Backend error.")
            except Exception as e:
                st.error(f"Request failed: {e}")

# === Display Selected Chat ===
if st.session_state.selected_response:
    q, a, refs = st.session_state.selected_response
    st.markdown(f"<div class='chat-bubble user-bubble'><b>You:</b> {q}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='chat-bubble bot-bubble'><b>StudyMate:</b> {a}</div>", unsafe_allow_html=True)

    fallback_phrases = ["no answer found", "does not provide", "unable to answer", "couldn’t find", "sorry"]
    if a and refs and all(p not in a.lower() for p in fallback_phrases):
        for ref in refs:
            st.markdown(f"<div class='reference'>• {ref}</div>", unsafe_allow_html=True)

# === Gemini Chatbot Interface ===
st.markdown("<hr>", unsafe_allow_html=True)
show_gemini_chat = st.toggle("💬 Ask Chatbot Instead", key="gemini_toggle")

if show_gemini_chat:
    st.markdown("### 🤖 Gemini Chat Assistant")
    if "gemini_history" not in st.session_state:
        st.session_state.gemini_history = []

    with st.form("gemini_chat", clear_on_submit=True):
        user_input = st.text_input("Ask anything...", placeholder="What's the capital of France?")
        submit_gemini = st.form_submit_button("Send")

    if submit_gemini and user_input.strip():
        with st.spinner("🧠 Gemini is thinking..."):
            try:
                gemini_res = requests.post(
                    f"{BACKEND_URL}/gemini_chat",
                    json={"message": user_input, "username": st.session_state.username}
                )
                if gemini_res.status_code == 200:
                    reply = gemini_res.json().get("response", "No response.")
                    st.session_state.gemini_history.append((user_input, reply))
                else:
                    st.session_state.gemini_history.append((user_input, "Error from Gemini API."))
            except Exception as e:
                st.session_state.gemini_history.append((user_input, f"Error: {e}"))

    for u, r in reversed(st.session_state.gemini_history):
        st.markdown(f"<div class='chat-bubble user-bubble'><b>You:</b> {u}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='chat-bubble bot-bubble'><b>Gemini:</b> {r}</div>", unsafe_allow_html=True)

# === Footer ===
st.markdown("<div class='footer'>✨ Developed with ❤️ for Students | Powered by Streamlit</div>", unsafe_allow_html=True)
